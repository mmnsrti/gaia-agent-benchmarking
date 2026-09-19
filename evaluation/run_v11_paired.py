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


def hash_shared_plan(plan_text: str) -> str:
    """Computes a deterministic SHA-256 hash of the shared operational plan."""
    return hashlib.sha256((plan_text or "").encode("utf-8")).hexdigest()


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

    Returns (candidate_answer, python_executed, raw_response).
    """
    executor_mode = plan_spec.mode
    if executor_mode == "DIRECT":
        prompt = build_direct_executor_prompt(
            question=question,
            plan_spec=plan_spec,
            web_evidence=web_evidence,
            file_evidence=file_evidence,
            attachment_filename=attachment_filename,
        )
    else:
        prompt = build_python_executor_prompt(
            question=question,
            plan_spec=plan_spec,
            web_evidence=web_evidence,
            file_evidence=file_evidence,
            attachment_filename=attachment_filename,
        )

    llm_resp = agent.llm.generate(prompt, attachment_parts=attachment_parts)
    raw_response = (
        llm_resp.raw_text
        if isinstance(llm_resp, LLMResponse) and llm_resp.raw_text
        else getattr(llm_resp, "text", str(llm_resp))
    )

    candidate = ""
    python_executed = False
    if executor_mode == "DIRECT":
        candidate = agent.clean_answer(extract_direct_answer(raw_response or ""))
    else:
        code = extract_python_code(raw_response or "")
        if code:
            python_executed = True
            py_res = agent.python_tool.execute(code, attachment_path=file_path)
            if py_res.success:
                extracted = extract_python_final_answer(py_res.stdout)
                if extracted is not None:
                    candidate = agent.clean_answer(extracted)
                else:
                    candidate = (
                        agent.clean_answer(extract_direct_answer(raw_response or ""))
                        if "FINAL:" in (raw_response or "")
                        else ""
                    )
            else:
                candidate = (
                    agent.clean_answer(extract_direct_answer(raw_response or ""))
                    if "FINAL:" in (raw_response or "")
                    else ""
                )
        else:
            candidate = (
                agent.clean_answer(extract_direct_answer(raw_response or ""))
                if "FINAL:" in (raw_response or "")
                else ""
            )

    return candidate, python_executed, raw_response


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

    completed_ids = set()
    if resume and os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    tid = rec.get("task_id")
                    if tid:
                        completed_ids.add(tid)
                except json.JSONDecodeError:
                    pass
        print(f"Resuming paired run: {len(completed_ids)}/{total_tasks} already completed.")

    if agent is None:
        llm_client = LLMClient()
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm_client,
            python_tool=PythonTool(),
        )

    processed_count = 0
    eligible_count = 0

    with open(output_file, "a", encoding="utf-8") as f:
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
            planner_prompt = build_adaptive_planner_prompt(
                question=task.question,
                web_evidence=web_evidence_primary,
                file_evidence=shared_context.file_evidence,
                attachment_filename=shared_context.attachment_filename,
            )

            planner_raw_response = None
            planner_error_type = None
            try:
                p_resp = agent.llm.generate(planner_prompt, attachment_parts=shared_context.attachment_parts)
                if isinstance(p_resp, LLMResponse):
                    planner_raw_response = p_resp.raw_text if p_resp.raw_text else p_resp.text
                    if p_resp.finish_reason not in (None, "", "STOP"):
                        planner_error_type = "unexpected_finish_reason"
                else:
                    planner_raw_response = str(p_resp)
            except Exception as e:
                planner_error_type = type(e).__name__
                planner_raw_response = None

            if planner_error_type is not None or not planner_raw_response or not planner_raw_response.strip():
                parse_res = parse_adaptive_planner_result("")
            else:
                parse_res = parse_adaptive_planner_result(planner_raw_response)

            plan_spec = parse_res.plan_spec
            plan_hash = hash_shared_plan(plan_spec.raw_plan)

            planner_parse_success = parse_res.success
            planner_fallback_used = plan_spec.is_fallback
            planner_evidence_status = plan_spec.evidence_status
            raw_followup_query = plan_spec.followup_query

            # Evaluate Cohort Eligibility (Pre-Search 2)
            planner_requested_followup = bool(planner_parse_success and planner_evidence_status == "INSUFFICIENT")
            norm_followup_query, followup_truncated = normalize_followup_query(raw_followup_query)
            followup_query_valid = bool(
                planner_requested_followup and norm_followup_query and norm_followup_query.upper() != "NONE"
            )

            search1_q = (
                shared_context.search_res.query
                if (shared_context.search_res and shared_context.search_res.query)
                else task.question
            )
            norm_search1_q, _ = normalize_followup_query(search1_q)
            followup_query_duplicate = bool(
                planner_requested_followup
                and followup_query_valid
                and (norm_followup_query.lower() == norm_search1_q.lower())
            )

            followup_eligible = bool(
                planner_requested_followup and followup_query_valid and not followup_query_duplicate
            )

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
                s2_start = time.time()
                try:
                    second_search_res = agent.search_tool.search(norm_followup_query)
                    second_search_latency_seconds = round(
                        getattr(second_search_res, "latency_seconds", None) or (time.time() - s2_start), 2
                    )
                    second_search_success = bool(second_search_res and second_search_res.success)
                    second_search_result_count = (
                        len(second_search_res.results) if (second_search_res and second_search_res.results) else 0
                    )
                    second_search_empty_results = bool(second_search_success and second_search_result_count == 0)
                    second_search_error_type = second_search_res.error_type if second_search_res else None
                    second_search_error_message = second_search_res.error_message if second_search_res else None

                    if second_search_res and second_search_res.results:
                        second_urls = []
                        for item in second_search_res.results:
                            u = getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else None)
                            if u:
                                second_urls.append(u)
                        second_search_urls = second_urls
                        primary_url_set = set(primary_urls)
                        new_urls = [u for u in second_urls if u not in primary_url_set]
                        second_search_new_urls_count = len(new_urls)
                        second_search_has_new_urls = len(new_urls) > 0
                    else:
                        second_search_urls = []
                        second_search_new_urls_count = 0
                        second_search_has_new_urls = False

                    if second_search_success and second_search_result_count > 0:
                        followup_evidence_text = second_search_res.format_evidence_block()
                        followup_search_hash = hashlib.sha256(followup_evidence_text.encode("utf-8")).hexdigest()
                        v11_retrieval_category = "FOLLOWUP_ELIGIBLE_SEARCH2_SUCCESS"
                    elif second_search_success and second_search_result_count == 0:
                        v11_retrieval_category = "FOLLOWUP_ELIGIBLE_SEARCH2_EMPTY_RESULTS"
                    else:
                        v11_retrieval_category = "FOLLOWUP_ELIGIBLE_SEARCH2_PROVIDER_FAILURE"
                except Exception as e:
                    second_search_latency_seconds = round(time.time() - s2_start, 2)
                    second_search_success = False
                    second_search_error_type = type(e).__name__
                    second_search_error_message = str(e)
                    second_search_result_count = 0
                    second_search_empty_results = False
                    second_search_urls = []
                    second_search_new_urls_count = 0
                    second_search_has_new_urls = False
                    v11_retrieval_category = "FOLLOWUP_ELIGIBLE_SEARCH2_PROVIDER_FAILURE"

                # 3. FORK TO PARALLEL UPSTREAM EXECUTOR BRANCHES
                # Branch A: Without Follow-Up Search Evidence
                print(f"--> Task {task.task_id}: Running Branch A (without Search 2 evidence)...")
                web_evidence_A = f"=== PRIMARY WEB SEARCH EVIDENCE ===\n{web_evidence_primary}"
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
                if second_search_success and followup_evidence_text and followup_evidence_text.strip():
                    web_evidence_B = (
                        f"=== PRIMARY WEB SEARCH EVIDENCE ===\n{web_evidence_primary}\n\n"
                        f"=== FOLLOW-UP WEB SEARCH EVIDENCE ===\n{followup_evidence_text.strip()}"
                    )
                else:
                    web_evidence_B = f"=== PRIMARY WEB SEARCH EVIDENCE ===\n{web_evidence_primary}"

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

            # Paired Telemetry Record (Strictly Public-Safe, Zero Ground Truth)
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

            f.write(json.dumps(paired_record, ensure_ascii=False) + "\n")
            f.flush()
            completed_ids.add(task.task_id)
            processed_count += 1

            if delay > 0 and idx < total_tasks:
                time.sleep(delay)

    print(
        f"\nPaired ablation run complete. Total processed: {processed_count}, Follow-up eligible: {eligible_count}."
    )
    print(f"Written to: {output_file}")
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

