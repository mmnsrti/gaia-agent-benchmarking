"""V11 Follow-Up-Eligible Shared-Plan Paired Retrieval Ablation Runner.

Executes within-task paired retrieval ablation under identical question, Search 1 evidence,
file context, and planner output:
  - Branch A: Without Follow-Up Search Evidence (Search 1 evidence only)
  - Branch B: With Follow-Up Search Evidence (Search 1 + Search 2 evidence or clean fallback)

Key Invariants:
  1. Shared Context & Plan: Identical Search 1, file context, planner output, and plan.
  2. Single Search 2 Execution: Search 2 executed at most once per eligible task.
  3. Pre-Recovery Candidate Boundary: Both branches stop before recovery, verifier, self-eval, repair.
  4. Ground-Truth Scorer Firewall: Zero access to reference answers or scoring functions during execution.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

# Add repository root to python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure Unicode output compatibility on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

from agent import (
    GAIAAdaptiveEvidenceAgent,
    LLMClient,
    LLMResponse,
    UpstreamContext,
    build_adaptive_planner_prompt,
    parse_adaptive_planner_result,
    build_adaptive_fallback_plan,
    normalize_followup_query,
    canonical_execution_plan_payload,
    hash_canonical_execution_plan,
    _execute_v11_executor_from_plan,
    _plan_v11_from_context,
    _evaluate_v11_followup_control,
    _execute_v11_followup_search,
    _build_v11_executor_evidence,
)
from agent.agent import (
    extract_direct_answer,
    extract_python_code,
    extract_python_final_answer,
)
from prompts.executor import (
    build_direct_executor_prompt,
    build_python_executor_prompt,
)
from tools.python_tool import PythonTool
from evaluation.dataset import load_gaia_tasks
from evaluation.runner import resolve_attachment_path


def hash_shared_search_context(context: UpstreamContext) -> str:
    """Computes a deterministic SHA-256 hash of shared search context."""
    return hashlib.sha256((context.web_evidence or "").encode("utf-8")).hexdigest()


def hash_shared_file_context(context: UpstreamContext) -> str:
    """Computes a deterministic SHA-256 hash of shared file context without re-reading from disk."""
    hasher = hashlib.sha256()
    hasher.update((context.file_evidence or "").encode("utf-8"))
    hasher.update((context.attachment_filename or "").encode("utf-8"))
    if context.file_res is not None:
        if context.file_res.mime_type:
            hasher.update(context.file_res.mime_type.encode("utf-8"))
        if context.file_res.content_mode:
            hasher.update(context.file_res.content_mode.encode("utf-8"))
        if context.file_res.native_bytes:
            hasher.update(context.file_res.native_bytes)
    return hasher.hexdigest()


def hash_shared_plan(plan_spec: Any) -> str:
    """Computes a deterministic SHA-256 hash of the shared operational plan execution payload."""
    if isinstance(plan_spec, str):
        return hashlib.sha256(plan_spec.encode("utf-8")).hexdigest()
    return hash_canonical_execution_plan(plan_spec)



def execute_plan_branch(
    agent: Any,
    question: str,
    plan_spec: Any,
    web_evidence: str,
    file_evidence: str,
    attachment_filename: str,
    attachment_parts: Any,
    file_path: Optional[str] = None,
) -> tuple[str, bool, Optional[str]]:
    """Executes a single Plan-Guided Executor branch (pre-recovery candidate boundary).

    Delegates directly to the shared _execute_v11_executor_from_plan helper.
    Returns (candidate_answer, python_executed, raw_response).
    """
    res = _execute_v11_executor_from_plan(
        agent=agent,
        question=question,
        plan_spec=plan_spec,
        combined_web_evidence=web_evidence,
        file_evidence=file_evidence,
        attachment_filename=attachment_filename,
        attachment_parts=attachment_parts,
        file_path=file_path,
    )
    return res.candidate_answer, res.python_executed, res.raw_response


def validate_paired_resume_artifacts(raw_file: str, enrollment_file: str) -> set[str]:
    """Validates raw and enrollment sidecar artifacts for paired run resumption.

    Enforces:
    1. If neither file exists, returns empty set.
    2. If one file exists but the other does not, raises RuntimeError (fail-closed).
    3. If files exist:
       - No duplicate task_id in raw file (raises RuntimeError).
       - No duplicate task_id in enrollment ledger (raises RuntimeError).
       - In raw file, every record must have followup_eligible is True (raises RuntimeError).
       - Every task in raw file must be present in enrollment ledger with followup_eligible=True
         and paired_record_written=True (raises RuntimeError).
       - Every eligible task in enrollment ledger must have paired_record_written=True
         and be present in raw file (raises RuntimeError).
       - Every non-eligible task in enrollment ledger must have paired_record_written=False
         and MUST NOT be present in raw file (raises RuntimeError).
    Returns:
       Set of completed task IDs from the enrollment ledger.
    """
    raw_exists = os.path.exists(raw_file)
    ledger_exists = os.path.exists(enrollment_file)

    if not raw_exists and not ledger_exists:
        return set()

    if raw_exists and not ledger_exists:
        raise RuntimeError(
            f"Output file exists ({raw_file}) but sidecar enrollment ledger is missing ({enrollment_file}). "
            "To restart from scratch, run with --no_resume."
        )

    if not raw_exists and ledger_exists:
        raise RuntimeError(
            f"Sidecar enrollment ledger exists ({enrollment_file}) but raw output file is missing ({raw_file}). "
            "To restart from scratch, run with --no_resume."
        )

    raw_task_ids: List[str] = []
    with open(raw_file, "r", encoding="utf-8") as rf:
        for line_num, line in enumerate(rf, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as err:
                raise RuntimeError(
                    f"Corrupt JSON line in raw paired file {raw_file} (line {line_num}): {err}"
                ) from err
            tid = rec.get("task_id")
            if not tid:
                raise RuntimeError(f"Missing task_id in raw paired file {raw_file} (line {line_num}).")
            if tid in raw_task_ids:
                raise RuntimeError(f"Duplicate task_id '{tid}' in raw paired file {raw_file}.")
            if not rec.get("followup_eligible", False):
                raise RuntimeError(
                    f"Contaminated raw paired file {raw_file}: task_id '{tid}' has followup_eligible={rec.get('followup_eligible')} (must be True)."
                )
            raw_task_ids.append(tid)

    raw_id_set = set(raw_task_ids)

    ledger_task_ids: List[str] = []
    ledger_by_id: Dict[str, Dict[str, Any]] = {}
    with open(enrollment_file, "r", encoding="utf-8") as lf:
        for line_num, line in enumerate(lf, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as err:
                raise RuntimeError(
                    f"Corrupt JSON line in enrollment ledger {enrollment_file} (line {line_num}): {err}"
                ) from err
            tid = rec.get("task_id")
            if not tid:
                raise RuntimeError(f"Missing task_id in enrollment ledger {enrollment_file} (line {line_num}).")
            if tid in ledger_task_ids:
                raise RuntimeError(f"Duplicate task_id '{tid}' in enrollment ledger {enrollment_file}.")
            ledger_task_ids.append(tid)
            ledger_by_id[tid] = rec

    ledger_id_set = set(ledger_task_ids)

    # Cross-validate bijection and consistency
    # 1. Every raw record must be in ledger and marked eligible with paired_record_written=True
    for tid in raw_task_ids:
        if tid not in ledger_by_id:
            raise RuntimeError(
                f"Task '{tid}' found in raw paired file {raw_file} but missing from enrollment ledger {enrollment_file}."
            )
        l_rec = ledger_by_id[tid]
        if not l_rec.get("followup_eligible", False):
            raise RuntimeError(
                f"Contamination discrepancy: Task '{tid}' in raw file is marked followup_eligible={l_rec.get('followup_eligible')} in enrollment ledger."
            )
        if not l_rec.get("paired_record_written", False):
            raise RuntimeError(
                f"Crash-window discrepancy: Task '{tid}' in raw file has paired_record_written={l_rec.get('paired_record_written')} in enrollment ledger."
            )

    # 2. Every ledger record
    for tid, l_rec in ledger_by_id.items():
        is_eligible = bool(l_rec.get("followup_eligible", False))
        paired_written = bool(l_rec.get("paired_record_written", False))

        if is_eligible:
            if not paired_written:
                raise RuntimeError(
                    f"Crash-window discrepancy: Task '{tid}' in enrollment ledger is follow-up eligible but paired_record_written is False."
                )
            if tid not in raw_id_set:
                raise RuntimeError(
                    f"Crash-window discrepancy: Task '{tid}' in enrollment ledger is follow-up eligible with paired_record_written=True, but missing from raw file {raw_file}."
                )
        else:
            if paired_written:
                raise RuntimeError(
                    f"Contamination discrepancy: Non-eligible task '{tid}' in enrollment ledger has paired_record_written=True."
                )
            if tid in raw_id_set:
                raise RuntimeError(
                    f"Contamination discrepancy: Non-eligible task '{tid}' in enrollment ledger is present in raw file {raw_file}."
                )

    return ledger_id_set


def run_paired_ablation(
    level: Optional[int] = None,
    data_path: Optional[str] = None,
    limit: Optional[int] = None,
    task_id: Optional[str] = None,
    output_file: Optional[str] = None,
    resume: bool = True,
    delay: float = 5.0,
    agent: Optional[Any] = None,
) -> str:
    """Executes follow-up-eligible shared-plan paired retrieval ablation across GAIA tasks.

    Writes ONLY followup_eligible records to output_file.
    Writes every scanned task to sidecar enrollment ledger (<output_file>.enrollment.jsonl).
    Does NOT access ground truth answers or scoring functions.
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # Load tasks
    tasks = []
    if level is not None:
        tasks = load_gaia_tasks(data_path=data_path, level=level)
    else:
        for lvl in (1, 2, 3):
            tasks.extend(load_gaia_tasks(data_path=data_path, level=lvl))

    if task_id:
        tasks = [t for t in tasks if t.task_id == task_id]
        if not tasks:
            print(f"Error: task_id '{task_id}' not found.")
            return ""

    if limit is not None and limit > 0:
        tasks = tasks[:limit]

    total_tasks = len(tasks)
    print("=== Starting V11 Follow-Up-Eligible Shared-Plan Paired Retrieval Ablation ===")
    print(f"Total tasks in scope: {total_tasks}")

    if output_file is None:
        output_file = os.path.join(repo_root, "experiments", "v11", "paired_retrieval_raw.jsonl")
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

    enrollment_file = (
        f"{output_file[:-6]}.enrollment.jsonl"
        if output_file.endswith(".jsonl")
        else f"{output_file}.enrollment.jsonl"
    )

    completed_ids: set[str] = set()
    if resume:
        completed_ids = validate_paired_resume_artifacts(output_file, enrollment_file)
        if completed_ids:
            print(f"Resuming paired run from validated artifacts: {len(completed_ids)}/{total_tasks} already completed.")

    if agent is None:
        llm_client = LLMClient()
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm_client,
            python_tool=PythonTool(),
        )

    processed_count = 0
    eligible_count = 0

    file_mode = "a" if resume else "w"
    with open(output_file, file_mode, encoding="utf-8") as f_out, open(enrollment_file, file_mode, encoding="utf-8") as f_ledger:
        for idx, task in enumerate(tasks, start=1):
            if task.task_id in completed_ids:
                continue

            print(f"\n[{idx}/{total_tasks}] Processing task: {task.task_id} (Level {task.level})")

            # Resolve attachment path safely
            resolved_file_path = resolve_attachment_path(
                file_path=getattr(task, "file_path", None),
                file_name=getattr(task, "file_name", None),
                repo_root=repo_root,
            )

            # 1. SHARED CONTEXT ACQUISITION (Search 1 + File)
            shared_context: UpstreamContext = agent._prepare_upstream_context(
                question=task.question,
                file_path=resolved_file_path,
            )

            search1_hash = hash_shared_search_context(shared_context)
            file_hash = hash_shared_file_context(shared_context)

            web_evidence_primary = (
                shared_context.web_evidence
                if (shared_context.search_res and shared_context.search_res.success)
                else "[Web search unavailable]"
            )

            primary_urls: list[str] = []
            if shared_context.search_res and getattr(shared_context.search_res, "results", None):
                for item in shared_context.search_res.results:
                    url = getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else None)
                    if url:
                        primary_urls.append(url)

            # 2. SHARED PLANNER v2 GENERATION
            parse_res, p_telem = _plan_v11_from_context(
                agent=agent,
                question=task.question,
                web_evidence_primary=web_evidence_primary,
                file_evidence=shared_context.file_evidence,
                attachment_filename=shared_context.attachment_filename,
                attachment_parts=shared_context.attachment_parts,
            )

            plan_spec = parse_res.plan_spec
            plan_hash = hash_shared_plan(plan_spec)

            planner_parse_success = parse_res.success
            planner_fallback_used = plan_spec.is_fallback
            planner_evidence_status = plan_spec.evidence_status
            raw_followup_query = plan_spec.followup_query

            # Evaluate Cohort Eligibility (Pre-Search 2)
            search1_q = (
                shared_context.search_res.query
                if (shared_context.search_res and shared_context.search_res.query)
                else task.question
            )
            ctrl = _evaluate_v11_followup_control(
                plan_spec=plan_spec,
                parse_success=planner_parse_success,
                search1_query_candidate=search1_q,
            )

            planner_requested_followup = ctrl["planner_requested_followup"]
            norm_followup_query = ctrl["norm_followup_query"]
            followup_truncated = ctrl["followup_truncated"]
            followup_query_valid = ctrl["followup_query_valid"]
            followup_query_duplicate = ctrl["followup_query_duplicate"]
            followup_eligible = ctrl["followup_eligible"]

            # Search 2 Telemetry Defaults
            second_search_triggered = False
            second_search_attempted = False
            second_search_success = False
            second_search_empty_results = False
            second_search_skipped_duplicate_query = False
            second_search_query = None
            second_search_provider_query = None
            second_search_query_truncated = False
            second_search_latency_seconds = None
            second_search_result_count = None
            second_search_error_type = None
            second_search_error_message = None
            second_search_new_urls_count = None
            second_search_urls = None
            second_search_has_new_urls = None
            followup_search_hash = None
            followup_evidence_text = None

            candidate_A = None
            candidate_B = None
            python_A = False
            python_B = False

            if planner_requested_followup and followup_query_duplicate:
                second_search_triggered = True
                second_search_skipped_duplicate_query = True
                second_search_attempted = False
                second_search_query = raw_followup_query
                second_search_provider_query = norm_followup_query
                v11_retrieval_category = "INSUFFICIENT_DUPLICATE_QUERY"
                print(f"--> Task {task.task_id}: Duplicate query skipped.")
            elif followup_eligible:
                eligible_count += 1
                second_search_triggered = True
                second_search_attempted = True
                second_search_query = raw_followup_query
                second_search_provider_query = norm_followup_query
                second_search_query_truncated = followup_truncated

                print(f"--> Task {task.task_id}: Follow-up eligible. Executing Search 2 once.")
                s2_info = _execute_v11_followup_search(
                    search_tool=agent.search_tool,
                    norm_followup_query=norm_followup_query,
                    primary_urls=primary_urls,
                )
                second_search_success = s2_info["second_search_success"]
                second_search_empty_results = s2_info["second_search_empty_results"]
                second_search_latency_seconds = s2_info["second_search_latency_seconds"]
                second_search_result_count = s2_info["second_search_result_count"]
                second_search_error_type = s2_info["second_search_error_type"]
                second_search_error_message = s2_info["second_search_error_message"]
                second_search_urls = s2_info["second_search_urls"]
                second_search_new_urls_count = s2_info["second_search_new_urls_count"]
                second_search_has_new_urls = s2_info["second_search_has_new_urls"]
                followup_evidence_text = s2_info["followup_evidence_text"]
                followup_search_hash = s2_info["followup_search_hash"]
                v11_retrieval_category = s2_info["v11_retrieval_category"]

                # 3. FORK TO PARALLEL UPSTREAM EXECUTOR BRANCHES
                # Branch A: Without Follow-Up Search Evidence
                print(f"--> Task {task.task_id}: Running Branch A (without Search 2 evidence)...")
                web_evidence_A, _ = _build_v11_executor_evidence(
                    web_evidence_primary=web_evidence_primary,
                    second_search_success=False,
                    followup_evidence_text=None,
                )
                candidate_A, python_A, _ = execute_plan_branch(
                    agent=agent,
                    question=task.question,
                    plan_spec=plan_spec,
                    web_evidence=web_evidence_A,
                    file_evidence=shared_context.file_evidence,
                    attachment_filename=shared_context.attachment_filename,
                    attachment_parts=shared_context.attachment_parts,
                    file_path=resolved_file_path,
                )

                # Branch B: With Follow-Up Search Evidence (or clean fallback)
                print(f"--> Task {task.task_id}: Running Branch B (with Search 2 evidence)...")
                web_evidence_B, _ = _build_v11_executor_evidence(
                    web_evidence_primary=web_evidence_primary,
                    second_search_success=second_search_success,
                    followup_evidence_text=followup_evidence_text,
                )
                candidate_B, python_B, _ = execute_plan_branch(
                    agent=agent,
                    question=task.question,
                    plan_spec=plan_spec,
                    web_evidence=web_evidence_B,
                    file_evidence=shared_context.file_evidence,
                    attachment_filename=shared_context.attachment_filename,
                    attachment_parts=shared_context.attachment_parts,
                    file_path=resolved_file_path,
                )
            else:
                if planner_fallback_used:
                    v11_retrieval_category = "PLANNER_FALLBACK"
                else:
                    v11_retrieval_category = "SUFFICIENT_NON_TRIGGERED"
                print(f"--> Task {task.task_id}: Not follow-up eligible ({v11_retrieval_category}). Bypassing paired fork.")

            # Record in sidecar enrollment ledger for ALL scanned tasks
            # Write to raw paired file ONLY if followup_eligible == True (BEFORE ledger entry)
            if followup_eligible:
                paired_record: Dict[str, Any] = {
                    "schema_version": 9,
                    "task_id": task.task_id,
                    "level": task.level,
                    "question": task.question,
                    "file_name": task.file_name,
                    "shared_primary_search_hash": search1_hash,
                    "shared_file_hash": file_hash,
                    "shared_plan_hash": plan_hash,
                    "planner_evidence_status": planner_evidence_status,
                    "planner_followup_query": raw_followup_query,
                    "planner_requested_followup": planner_requested_followup,
                    "followup_query_valid": followup_query_valid,
                    "followup_query_duplicate": followup_query_duplicate,
                    "followup_eligible": followup_eligible,
                    "second_search_triggered": second_search_triggered,
                    "second_search_attempted": second_search_attempted,
                    "second_search_success": second_search_success,
                    "second_search_empty_results": second_search_empty_results,
                    "second_search_skipped_duplicate_query": second_search_skipped_duplicate_query,
                    "second_search_query": second_search_query,
                    "second_search_provider_query": second_search_provider_query,
                    "second_search_query_truncated": second_search_query_truncated,
                    "second_search_latency_seconds": second_search_latency_seconds,
                    "second_search_result_count": second_search_result_count,
                    "second_search_error_type": second_search_error_type,
                    "second_search_error_message": second_search_error_message,
                    "second_search_new_urls_count": second_search_new_urls_count,
                    "second_search_urls": second_search_urls,
                    "primary_search_urls": primary_urls,
                    "second_search_has_new_urls": second_search_has_new_urls,
                    "followup_search_hash": followup_search_hash,
                    "candidate_without_followup": candidate_A,
                    "candidate_with_followup": candidate_B,
                    "python_without_followup": python_A,
                    "python_with_followup": python_B,
                    "planner_mode": plan_spec.mode,
                    "plan_step_count": len(plan_spec.plan_steps),
                    "planner_parse_success": planner_parse_success,
                    "planner_fallback_used": planner_fallback_used,
                    "v11_retrieval_category": v11_retrieval_category,
                }
                f_out.write(json.dumps(paired_record, ensure_ascii=False) + "\n")
                f_out.flush()

            # Record in sidecar enrollment ledger for ALL scanned tasks (AFTER raw record written)
            ledger_entry: Dict[str, Any] = {
                "schema_version": 9,
                "task_id": task.task_id,
                "level": task.level,
                "question": task.question,
                "file_name": task.file_name,
                "shared_primary_search_hash": search1_hash,
                "shared_file_hash": file_hash,
                "shared_plan_hash": plan_hash,
                "planner_evidence_status": planner_evidence_status,
                "planner_followup_query": raw_followup_query,
                "planner_requested_followup": planner_requested_followup,
                "followup_query_valid": followup_query_valid,
                "followup_query_duplicate": followup_query_duplicate,
                "followup_eligible": followup_eligible,
                "second_search_triggered": second_search_triggered,
                "second_search_attempted": second_search_attempted,
                "second_search_success": second_search_success,
                "second_search_empty_results": second_search_empty_results,
                "second_search_skipped_duplicate_query": second_search_skipped_duplicate_query,
                "second_search_query": second_search_query,
                "second_search_provider_query": second_search_provider_query,
                "second_search_query_truncated": second_search_query_truncated,
                "second_search_latency_seconds": second_search_latency_seconds,
                "second_search_result_count": second_search_result_count,
                "second_search_error_type": second_search_error_type,
                "second_search_error_message": second_search_error_message,
                "second_search_new_urls_count": second_search_new_urls_count,
                "second_search_urls": second_search_urls,
                "primary_search_urls": primary_urls,
                "second_search_has_new_urls": second_search_has_new_urls,
                "followup_search_hash": followup_search_hash,
                "candidate_without_followup": candidate_A,
                "candidate_with_followup": candidate_B,
                "python_without_followup": python_A,
                "python_with_followup": python_B,
                "planner_mode": plan_spec.mode,
                "plan_step_count": len(plan_spec.plan_steps),
                "planner_parse_success": planner_parse_success,
                "planner_fallback_used": planner_fallback_used,
                "v11_retrieval_category": v11_retrieval_category,
                "paired_record_written": followup_eligible,
            }
            f_ledger.write(json.dumps(ledger_entry, ensure_ascii=False) + "\n")
            f_ledger.flush()

            # Write to raw paired file ONLY if followup_eligible == True
            completed_ids.add(task.task_id)
            processed_count += 1

            if delay > 0 and idx < total_tasks:
                time.sleep(delay)

    print(
        f"\nPaired ablation run complete. Total processed: {processed_count}, Follow-up eligible: {eligible_count}."
    )
    print(f"Written to: {output_file}")
    print(f"Enrollment ledger: {enrollment_file}")
    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run V11 Follow-Up-Eligible Shared-Plan Paired Retrieval Ablation."
    )
    parser.add_argument("--level", type=int, choices=[1, 2, 3], default=None, help="GAIA Level (1, 2, 3, or all).")
    parser.add_argument("--data_path", type=str, default=None, help="Path to GAIA dataset.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of tasks.")
    parser.add_argument("--task_id", type=str, default=None, help="Run specific task ID.")
    parser.add_argument("--output_file", type=str, default=None, help="Output JSONL path.")
    parser.add_argument("--no_resume", action="store_true", help="Do not resume existing run.")
    parser.add_argument("--delay", type=float, default=5.0, help="Delay between tasks in seconds.")
    args = parser.parse_args()

    run_paired_ablation(
        level=args.level,
        data_path=args.data_path,
        limit=args.limit,
        task_id=args.task_id,
        output_file=args.output_file,
        resume=not args.no_resume,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()

