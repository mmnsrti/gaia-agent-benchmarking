"""V10 Shared-Context Paired Upstream Ablation Runner.

Executes counterfactual paired evaluation between:
  - Branch A: Frozen V9 Upstream (Capability Router -> Worker)
  - Branch B: V10 Upstream (Structured Planner -> Plan-Guided Executor)

Key Invariants:
  1. Shared Immutable Context: Single search call, single file parse per task.
  2. Strict Tool Budgets: <= 1 search, <= 1 file parse, <= 1 Python per branch.
  3. Ground-Truth Isolation (Firewall): No access to ground truth answers or scorer
     during execution. Correctness and transitions are strictly computed post-hoc.
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
    GAIAUpstreamCandidateRecoveryAgent,
    GAIAPlannerExecutorAgent,
    LLMClient,
    UpstreamContext,
)
from tools.python_tool import PythonTool
from evaluation.dataset import load_gaia_tasks
from evaluation.runner import resolve_attachment_path


def run_paired_ablation(
    level: Optional[int] = None,
    data_path: Optional[str] = None,
    limit: Optional[int] = None,
    task_id: Optional[str] = None,
    output_file: Optional[str] = None,
    resume: bool = True,
    delay: float = 5.0,
    v9_agent: Optional[Any] = None,
    v10_agent: Optional[Any] = None,
) -> str:
    """Executes shared-context paired upstream ablation across GAIA tasks.

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
    print(f"=== Starting V10 Shared-Context Paired Upstream Ablation ===")
    print(f"Total tasks: {total_tasks}")

    if output_file is None:
        output_file = os.path.join(repo_root, "experiments", "v10", "paired_upstream_raw.jsonl")
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

    # Initialize agents if not provided
    if v10_agent is None:
        llm_client = LLMClient()
        v10_agent = GAIAPlannerExecutorAgent(
            llm_client=llm_client,
            python_tool=PythonTool(),
        )
    if v9_agent is None:
        llm_client = getattr(v10_agent, "llm_client", LLMClient())
        v9_agent = GAIAUpstreamCandidateRecoveryAgent(
            llm_client=llm_client,
            search_tool=v10_agent.search_tool,
            file_tool=v10_agent.file_tool,
            python_tool=PythonTool(),
        )

    processed_count = 0
    with open(output_file, "a", encoding="utf-8") as f:
        for idx, task in enumerate(tasks, start=1):
            if task.task_id in completed_ids:
                continue

            print(f"\n[{idx}/{total_tasks}] Running paired task: {task.task_id} (Level {task.level})")

            # Resolve attachment path safely
            resolved_file_path = resolve_attachment_path(
                file_path=getattr(task, "file_path", None),
                file_name=getattr(task, "file_name", None),
                repo_root=repo_root,
            )

            # 1. SHARED CONTEXT ACQUISITION (Single search, single file)
            shared_context: UpstreamContext = v10_agent._prepare_upstream_context(
                question=task.question,
                file_path=resolved_file_path,
            )

            # Compute SHA-256 hashes of shared contexts
            search_hash = hashlib.sha256(
                (shared_context.web_evidence or "").encode("utf-8")
            ).hexdigest()
            file_hash = hashlib.sha256(
                (shared_context.file_evidence or "").encode("utf-8")
            ).hexdigest()

            # 2. BRANCH A: Frozen V9 Upstream (Capability Router -> Worker)
            v9_start = time.time()
            v9_res = v9_agent._execute_upstream_pair_from_context(shared_context)
            v9_lat = round(time.time() - v9_start, 2)
            v9_candidate = v9_res.final_answer or ""
            v9_mode = v9_res.router_decision or v9_res.worker_mode

            # 3. BRANCH B: V10 Upstream (Structured Planner -> Plan-Guided Executor)
            v10_start = time.time()
            v10_res = v10_agent._execute_upstream_pair_from_context(shared_context)
            v10_lat = round(time.time() - v10_start, 2)
            v10_candidate = v10_res.final_answer or ""
            v10_mode = v10_res.planner_mode

            # Telemetry record (Strictly no ground truth or scorer access)
            paired_record: Dict[str, Any] = {
                "schema_version": 8,
                "task_id": task.task_id,
                "level": task.level,
                "question": task.question,
                "file_name": task.file_name,
                "shared_context_search_hash": search_hash,
                "shared_context_file_hash": file_hash,
                "v9_upstream_candidate": v9_candidate,
                "v10_upstream_candidate": v10_candidate,
                "v9_router_mode": v9_mode,
                "v10_planner_mode": v10_mode,
                "v9_python_executed": bool(v9_res.python_executed),
                "v10_python_executed": bool(v10_res.python_executed),
                "v9_upstream_latency_seconds": v9_lat,
                "v10_upstream_latency_seconds": v10_lat,
                "v9_upstream_input_tokens": (getattr(v9_res, "router_input_tokens", None) or 0) + (getattr(v9_res, "worker_input_tokens", None) or 0),
                "v9_upstream_output_tokens": (getattr(v9_res, "router_output_tokens", None) or 0) + (getattr(v9_res, "worker_output_tokens", None) or 0),
                "v10_upstream_input_tokens": (getattr(v10_res, "planner_input_tokens", None) or 0) + (getattr(v10_res, "executor_input_tokens", None) or 0),
                "v10_upstream_output_tokens": (getattr(v10_res, "planner_output_tokens", None) or 0) + (getattr(v10_res, "executor_output_tokens", None) or 0),
                "v10_planner_attempted": getattr(v10_res, "planner_attempted", False),
                "v10_planner_success": getattr(v10_res, "planner_success", False),
                "v10_planner_parse_success": getattr(v10_res, "planner_parse_success", False),
                "v10_planner_fallback_used": getattr(v10_res, "planner_fallback_used", False),
                "v10_plan_step_count": getattr(v10_res, "plan_step_count", None),
                "v10_plan_steps": getattr(v10_res, "plan_steps", None),
                "v10_plan_answer_type": getattr(v10_res, "plan_answer_type", None),
                "v10_executor_mode": getattr(v10_res, "executor_mode", None),
                "v10_executor_plan_used": getattr(v10_res, "executor_plan_used", False),
                "v10_executor_success": getattr(v10_res, "executor_success", False),
            }

            f.write(json.dumps(paired_record, ensure_ascii=False) + "\n")
            f.flush()
            completed_ids.add(task.task_id)
            processed_count += 1

            if delay > 0 and idx < total_tasks:
                time.sleep(delay)

    print(f"\nPaired ablation run complete. Total processed: {processed_count}. Written to: {output_file}")
    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V10 Shared-Context Paired Upstream Ablation.")
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
