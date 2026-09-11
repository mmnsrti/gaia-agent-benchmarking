"""Benchmark level runner for GAIA baselines (v0, v1, v2, v3).

Runs tasks sequentially for a specific GAIA level, supports resuming,
and triggers automatic evaluation with official scoring.
"""

import argparse
import os
import sys
import json
import time
from typing import Optional, Any

# Add repository root to python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure Unicode output compatibility on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass


def _safe_str(val: Optional[str], max_len: int = 80) -> str:
    """Safely formats a string preview without UnicodeEncodeError on Windows."""
    if not val:
        return ""
    snippet = str(val)[:max_len].replace("\n", " ")
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        snippet.encode(enc)
        return snippet
    except UnicodeEncodeError:
        return snippet.encode("ascii", errors="backslashreplace").decode("ascii")


from agent import GAIAAgent, GAIAWebAgent, GAIAFileAgent, GAIAPythonAgent, GAIARouterAgent, GAIAVerificationAgent, LLMClient
from evaluation.dataset import load_gaia_tasks, EXPECTED_VALIDATION_COUNTS
from evaluation.runner import execute_task
from evaluation.experiment_logger import ExperimentLogger
from evaluation.evaluate import evaluate_predictions


def run_level(
    level: int,
    data_path: Optional[str] = None,
    limit: Optional[int] = None,
    task_id: Optional[str] = None,
    output_file: Optional[str] = None,
    resume: bool = True,
    auto_eval: bool = True,
    enforce_task_count: bool = False,
    delay: float = 0.0,
    version: str = "v1",
    agent: Optional[Any] = None,
) -> str:
    """Runs the specified baseline (v0, v1, v2, or v3) on all tasks for a specified GAIA level.

    Stores complete experiment records and never submits to Hugging Face.
    """
    tasks = load_gaia_tasks(data_path=data_path, level=level)

    if task_id:
        tasks = [t for t in tasks if t.task_id == task_id]
        if not tasks:
            print(f"Error: task_id '{task_id}' not found for level {level}.")
            return ""

    if limit is not None and limit > 0:
        tasks = tasks[:limit]

    total_tasks = len(tasks)
    expected_tasks = EXPECTED_VALIDATION_COUNTS.get(level)
    is_partial = bool(limit or (expected_tasks and total_tasks < expected_tasks))
    run_tag = f"PARTIAL RUN (--limit {limit})" if limit else ("PARTIAL RUN" if is_partial else "COMPLETE BENCHMARK RUN")
    if version == "v5":
        version_desc = "v5 (One-shot post-answer verification + V4 routing + Python + V2 capabilities)"
    elif version == "v4":
        version_desc = "v4 (Explicit two-stage capability routing + Python + V2 capabilities)"
    elif version == "v3":
        version_desc = "v3 (Controlled single-shot Python execution + V2 capabilities)"
    elif version == "v2":
        version_desc = "v2 (File/attachment + web baseline)"
    elif version == "v1":
        version_desc = "v1 (Web retrieval baseline)"
    else:
        version_desc = "v0 (LLM-only baseline)"

    print("=" * 80)
    print(f"GAIA BENCHMARK RUN — Level {level} [{run_tag}]")
    print(f"Total tasks selected: {total_tasks} (expected for complete split: {expected_tasks})")
    print(f"Agent version:        {version_desc}")
    print(f"Resume existing:      {resume}")
    if delay > 0:
        print(f"Inter-task delay:     {delay}s")
    print("=" * 80)

    # Determine output predictions file
    if output_file is None:
        experiments_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "experiments", version))
        output_file = os.path.join(experiments_dir, f"predictions_level_{level}.jsonl")

    if not resume and os.path.exists(output_file):
        os.remove(output_file)

    # If resuming, check already completed task_ids
    completed_task_ids = set()
    valid_records = []
    if resume and os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        t_id = record.get("task_id")
                        req_success = record.get("request_success")
                        # Only count as completed if it did not fail due to a request error
                        if t_id and req_success is not False:
                            completed_task_ids.add(t_id)
                            valid_records.append(record)
                    except Exception:
                        pass

        # If there were failed request records, prune them so retrying doesn't cause duplicates
        with open(output_file, "r", encoding="utf-8-sig") as f:
            total_file_lines = sum(1 for line in f if line.strip())
        if len(valid_records) < total_file_lines:
            print(f"Pruned {total_file_lines - len(valid_records)} failed request record(s) from {output_file} to allow clean retry.")
            with open(output_file, "w", encoding="utf-8") as f:
                for r in valid_records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

        if completed_task_ids:
            print(f"Resuming run: found {len(completed_task_ids)} completed task(s) in {output_file}.")

    # Initialize client & agent once
    llm = LLMClient()
    if agent is None:
        if version == "v5":
            agent = GAIAVerificationAgent(llm_client=llm)
        elif version == "v4":
            agent = GAIARouterAgent(llm_client=llm)
        elif version == "v3":
            agent = GAIAPythonAgent(llm_client=llm)
        elif version == "v2":
            agent = GAIAFileAgent(llm_client=llm)
        elif version == "v1":
            agent = GAIAWebAgent(llm_client=llm)
        else:
            agent = GAIAAgent(llm_client=llm)

    output_dir = os.path.dirname(os.path.abspath(output_file))
    filename = os.path.basename(output_file)
    logger = ExperimentLogger(base_dir=output_dir, version="", filename=filename)

    for idx, task in enumerate(tasks, start=1):
        if resume and task.task_id in completed_task_ids:
            print(f"[{idx}/{total_tasks}] Task {task.task_id} already executed. Skipping.")
            continue

        print(f"\n[{idx}/{total_tasks}] Running Task ID: {task.task_id}")
        print(f"Question (preview): {_safe_str(task.question, 80)}...")
        print(f"Attachment: {'yes (' + task.file_name + ')' if task.has_attachment else 'no'}")

        record = execute_task(
            task_id=task.task_id,
            question=task.question,
            level=task.level,
            file_name=task.file_name,
            file_path=task.file_path,
            agent=agent,
            llm=llm,
            project_version=version,
        )

        status_str = "SUCCESS" if record["completion_success"] else ("FAIL (request)" if not record["request_success"] else "INCOMPLETE")
        print(f"--> Status: {status_str} | Latency: {record['latency_seconds']}s | Answer: {_safe_str(record['final_answer'], 60) if record['final_answer'] else '<None>'}")

        # Check for rate limit / quota exhaustion (HTTP 429)
        if not record["request_success"]:
            err_msg = str(record.get("error_message") or "")
            is_429 = "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "Quota exceeded" in err_msg
            if is_429:
                print("\n" + "!" * 80)
                print(f"[RATE LIMIT / QUOTA EXHAUSTED] Task {task.task_id} failed with HTTP 429:")
                print(f"  {err_msg}")
                print("\nHalting run to preserve quota and avoid false failure logging.")
                print("You can resume later with:")
                print(f"  python -m evaluation.run_level --level {level}")
                print(f"  python -m evaluation.run_level --version {version} --level {level}")
                print("!" * 80 + "\n")
                break

        logger.append(record)

        if delay > 0 and idx < total_tasks:
            time.sleep(delay)

    print("\n" + "=" * 80)
    print(f"Completed run for Level {level}. Predictions saved to:\n  {output_file}")
    print("=" * 80)

    # Automatic local evaluation if ground truth is available
    if auto_eval:
        summary_file = os.path.join(os.path.dirname(output_file), f"summary_level_{level}.json")
        detailed_file = os.path.join(os.path.dirname(output_file), f"detailed_eval_level_{level}.jsonl")
        try:
            evaluate_predictions(
                predictions_path=output_file,
                data_path=data_path,
                level=level,
                summary_output=summary_file,
                detailed_output=detailed_file,
                enforce_task_count=enforce_task_count,
                project_version=version,
            )
        except Exception as e:
            print(f"Auto-evaluation warning: {e}")

    return output_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run GAIA benchmark tasks for a specific level.")
    parser.add_argument("--level", type=int, required=True, choices=[1, 2, 3], help="GAIA level to run (1, 2, or 3)")
    # Legacy CLI choices compatibility: choices=["v0", "v1", "v2", "v3"]
    # Legacy CLI choices compatibility: choices=["v0", "v1", "v2", "v3", "v4"]
    parser.add_argument("--version", type=str, required=True, choices=["v0", "v1", "v2", "v3", "v4", "v5"], help="Agent version to evaluate (v0: baseline, v1: web search, v2: file attachments, v3: controlled single-shot Python execution, v4: explicit capability routing, v5: one-shot post-answer verification; required)")
    parser.add_argument("--data", type=str, default=None, help="Path to local GAIA dataset file")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of tasks to execute")
    parser.add_argument("--task-id", type=str, default=None, help="Run single specific task ID")
    parser.add_argument("--output", type=str, default=None, help="Custom output JSONL file for predictions")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay in seconds between tasks to prevent rate limiting (default: 1.0s)")
    parser.add_argument("--no-resume", action="store_true", help="Do not resume; re-run already executed tasks")
    parser.add_argument("--no-eval", action="store_true", help="Skip automatic local evaluation after level run")
    parser.add_argument("--enforce-task-count", action="store_true", help="Enforce exact expected task count during evaluation")
    args = parser.parse_args()

    run_level(
        level=args.level,
        data_path=args.data,
        limit=args.limit,
        task_id=args.task_id,
        output_file=args.output,
        resume=not args.no_resume,
        auto_eval=not args.no_eval,
        enforce_task_count=args.enforce_task_count,
        delay=args.delay,
        version=args.version,
    )

