"""V10 Shared-Context Paired Upstream Ablation Evaluator.

Scores raw paired execution records against official local GAIA ground truth,
populates the primary upstream transition matrix:
  - UPSTREAM_IMPROVEMENT
  - UPSTREAM_REGRESSION
  - UPSTREAM_STABLE_CORRECT
  - UPSTREAM_STABLE_FAILURE
and computes the primary paired intervention metric:
  Delta_upstream = N(UPSTREAM_IMPROVEMENT) - N(UPSTREAM_REGRESSION)
"""

import argparse
import json
import os
import sys
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

from evaluation.dataset import load_gaia_tasks
from evaluation.metrics import gaia_question_scorer, check_exact_match


def evaluate_paired_ablation(
    input_file: str,
    data_path: Optional[str] = None,
    summary_output: Optional[str] = None,
    detailed_output: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluates raw paired execution JSONL records and produces structured summaries."""
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Paired execution file not found at: {input_file}")

    # 1. Read raw paired records
    records: List[Dict[str, Any]] = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))

    if not records:
        raise ValueError(f"No paired records found in {input_file}")

    # 2. Load ground truth tasks across levels
    tasks_by_id: Dict[str, Any] = {}
    for lvl in (1, 2, 3):
        for task in load_gaia_tasks(data_path=data_path, level=lvl):
            tasks_by_id[task.task_id] = task

    # 3. Post-hoc scoring and transition assignment
    detailed_records: List[Dict[str, Any]] = []
    v9_correct_count = 0
    v10_correct_count = 0
    upstream_improvements = 0
    upstream_regressions = 0
    upstream_stable_correct = 0
    upstream_stable_failure = 0

    v9_direct_count = 0
    v9_python_count = 0
    v10_direct_count = 0
    v10_python_count = 0
    v9_python_exec_count = 0
    v10_python_exec_count = 0
    v10_planner_attempted_count = 0
    v10_planner_parse_success_count = 0
    v10_planner_fallback_count = 0

    for rec in records:
        tid = rec.get("task_id")
        task = tasks_by_id.get(tid)
        if task is None:
            raise ValueError(f"Ground truth not found for task_id: {tid}")

        gt = task.final_answer
        if not gt or not gt.strip():
            raise ValueError(f"Ground truth answer is missing or empty for task_id: {tid}")

        v9_cand = rec.get("v9_upstream_candidate") or ""
        v10_cand = rec.get("v10_upstream_candidate") or ""

        # Post-hoc score with official scorer
        v9_correct = bool(gaia_question_scorer(v9_cand, gt)) if str(v9_cand).strip() else False
        v10_correct = bool(gaia_question_scorer(v10_cand, gt)) if str(v10_cand).strip() else False

        if v9_correct:
            v9_correct_count += 1
        if v10_correct:
            v10_correct_count += 1

        # Categorize transition
        if not v9_correct and v10_correct:
            transition = "UPSTREAM_IMPROVEMENT"
            upstream_improvements += 1
        elif v9_correct and not v10_correct:
            transition = "UPSTREAM_REGRESSION"
            upstream_regressions += 1
        elif v9_correct and v10_correct:
            transition = "UPSTREAM_STABLE_CORRECT"
            upstream_stable_correct += 1
        else:
            transition = "UPSTREAM_STABLE_FAILURE"
            upstream_stable_failure += 1

        if rec.get("v9_router_mode") == "DIRECT":
            v9_direct_count += 1
        elif rec.get("v9_router_mode") == "PYTHON":
            v9_python_count += 1

        if rec.get("v10_planner_mode") == "DIRECT":
            v10_direct_count += 1
        elif rec.get("v10_planner_mode") == "PYTHON":
            v10_python_count += 1

        if rec.get("v9_python_executed"):
            v9_python_exec_count += 1
        if rec.get("v10_python_executed"):
            v10_python_exec_count += 1

        if rec.get("v10_planner_attempted"):
            v10_planner_attempted_count += 1
        if rec.get("v10_planner_parse_success"):
            v10_planner_parse_success_count += 1
        if rec.get("v10_planner_fallback_used"):
            v10_planner_fallback_count += 1

        detailed_entry = dict(rec)
        detailed_entry["ground_truth"] = gt
        detailed_entry["v9_upstream_candidate_correct"] = v9_correct
        detailed_entry["v10_upstream_candidate_correct"] = v10_correct
        detailed_entry["upstream_transition"] = transition
        detailed_records.append(detailed_entry)

    total_tasks = len(records)
    delta_upstream = upstream_improvements - upstream_regressions
    v9_acc = round(v9_correct_count / total_tasks, 4) if total_tasks > 0 else 0.0
    v10_acc = round(v10_correct_count / total_tasks, 4) if total_tasks > 0 else 0.0

    summary: Dict[str, Any] = {
        "schema_version": 8,
        "evaluation_type": "shared_context_paired_upstream_ablation",
        "total_paired_tasks": total_tasks,
        "primary_metric": "delta_upstream",
        "delta_upstream": delta_upstream,
        "upstream_improvements": upstream_improvements,
        "upstream_regressions": upstream_regressions,
        "upstream_stable_correct": upstream_stable_correct,
        "upstream_stable_failure": upstream_stable_failure,
        "transition_matrix": {
            "UPSTREAM_IMPROVEMENT": upstream_improvements,
            "UPSTREAM_REGRESSION": upstream_regressions,
            "UPSTREAM_STABLE_CORRECT": upstream_stable_correct,
            "UPSTREAM_STABLE_FAILURE": upstream_stable_failure,
        },
        "v9_upstream_candidates_correct": v9_correct_count,
        "v9_upstream_accuracy": v9_acc,
        "v10_upstream_candidates_correct": v10_correct_count,
        "v10_upstream_accuracy": v10_acc,
        "net_accuracy_delta": round(v10_acc - v9_acc, 4),
        "v9_routing": {
            "direct_count": v9_direct_count,
            "python_count": v9_python_count,
            "python_executed_count": v9_python_exec_count,
        },
        "v10_planning": {
            "direct_count": v10_direct_count,
            "python_count": v10_python_count,
            "python_executed_count": v10_python_exec_count,
            "planner_attempted_count": v10_planner_attempted_count,
            "planner_parse_success_count": v10_planner_parse_success_count,
            "planner_parse_success_rate": round(v10_planner_parse_success_count / v10_planner_attempted_count, 4) if v10_planner_attempted_count > 0 else 0.0,
            "planner_fallback_count": v10_planner_fallback_count,
            "planner_fallback_rate": round(v10_planner_fallback_count / total_tasks, 4) if total_tasks > 0 else 0.0,
        },
    }

    print("\n" + "=" * 60)
    print("V10 SHARED-CONTEXT PAIRED UPSTREAM ABLATION RESULTS")
    print("=" * 60)
    print(f"Total Paired Tasks Evaluated: {total_tasks}")
    print(f"Branch A (Frozen V9 Upstream): {v9_correct_count}/{total_tasks} ({v9_acc * 100:.2f}%)")
    print(f"Branch B (V10 Upstream):       {v10_correct_count}/{total_tasks} ({v10_acc * 100:.2f}%)")
    print("-" * 60)
    print(f"  UPSTREAM_IMPROVEMENT:       {upstream_improvements}")
    print(f"  UPSTREAM_REGRESSION:        {upstream_regressions}")
    print(f"  UPSTREAM_STABLE_CORRECT:    {upstream_stable_correct}")
    print(f"  UPSTREAM_STABLE_FAILURE:    {upstream_stable_failure}")
    print("-" * 60)
    print(f"PRIMARY METRIC: Delta_upstream = {delta_upstream}")
    if delta_upstream > 0:
        print("RESULT: POSITIVE (Supports H1)")
    elif delta_upstream == 0:
        print("RESULT: NEUTRAL (Inconclusive)")
    else:
        print("RESULT: NEGATIVE (Refutes H1)")
    print("=" * 60)

    # Save outputs if requested
    if summary_output:
        os.makedirs(os.path.dirname(os.path.abspath(summary_output)), exist_ok=True)
        with open(summary_output, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"Saved summary to: {summary_output}")

    if detailed_output:
        os.makedirs(os.path.dirname(os.path.abspath(detailed_output)), exist_ok=True)
        with open(detailed_output, "w", encoding="utf-8") as f:
            for d in detailed_records:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        print(f"Saved detailed records to: {detailed_output}")

    return {
        "summary": summary,
        "detailed": detailed_records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate V10 Shared-Context Paired Upstream Ablation.")
    parser.add_argument("--input_file", type=str, required=True, help="Path to raw paired JSONL file.")
    parser.add_argument("--data_path", type=str, default=None, help="Path to GAIA dataset.")
    parser.add_argument("--summary_output", type=str, default=None, help="Path to write summary JSON.")
    parser.add_argument("--detailed_output", type=str, default=None, help="Path to write detailed JSONL.")
    args = parser.parse_args()

    evaluate_paired_ablation(
        input_file=args.input_file,
        data_path=args.data_path,
        summary_output=args.summary_output,
        detailed_output=args.detailed_output,
    )


if __name__ == "__main__":
    main()
