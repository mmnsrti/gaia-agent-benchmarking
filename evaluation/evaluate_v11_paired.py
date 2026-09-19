"""V11 Follow-Up-Eligible Shared-Plan Paired Retrieval Ablation Evaluator.

Scores raw paired execution records against official local GAIA ground truth,
filters to the preregistered Follow-Up-Eligible cohort, populates the primary
transition matrix:
  - RETRIEVAL_IMPROVEMENT
  - RETRIEVAL_REGRESSION
  - RETRIEVAL_STABLE_CORRECT
  - RETRIEVAL_STABLE_FAILURE
and computes the primary paired intervention metric:
  Delta_followup = N(RETRIEVAL_IMPROVEMENT) - N(RETRIEVAL_REGRESSION)
"""

import argparse
import json
import os
import statistics
import sys
from collections import Counter
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
from evaluation.metrics import gaia_question_scorer


def calculate_paired_metrics(
    records: List[Dict[str, Any]],
    tasks_by_id: Dict[str, Any],
) -> Dict[str, Any]:
    """Calculates paired retrieval metrics, transitions, and detailed records."""
    detailed_records: List[Dict[str, Any]] = []

    followup_eligible_count = 0
    branch_A_correct_count = 0
    branch_B_correct_count = 0
    retrieval_improvements = 0
    retrieval_regressions = 0
    retrieval_stable_correct = 0
    retrieval_stable_failure = 0

    candidate_without_followup_empty_count = 0
    candidate_with_followup_empty_count = 0

    python_without_followup_count = 0
    python_with_followup_count = 0

    retrieval_categories: Counter = Counter()

    # Search operational counters
    second_search_triggered_count = 0
    second_search_attempted_count = 0
    second_search_success_count = 0
    second_search_empty_results_count = 0
    second_search_duplicate_skipped_count = 0
    second_search_provider_failure_count = 0

    # Novelty tracking
    new_urls_counts: List[int] = []
    has_new_urls_count = 0
    successful_searches_count = 0

    # Planner v2 tracking
    planner_parse_success_count = 0
    planner_fallback_count = 0

    for rec in records:
        tid = rec.get("task_id")
        task = tasks_by_id.get(tid)
        if task is None:
            raise ValueError(f"Ground truth not found for task_id: {tid}")

        gt = task.final_answer
        if not gt or not gt.strip():
            raise ValueError(f"Ground truth answer is missing or empty for task_id: {tid}")

        if not rec.get("followup_eligible"):
            raise ValueError(
                f"Contamination error: record for task {tid} has followup_eligible={rec.get('followup_eligible')}. "
                "Raw paired execution records must contain ONLY follow-up eligible tasks."
            )

        if rec.get("second_search_success") and rec.get("second_search_empty_results"):
            raise ValueError(
                f"Mutual exclusion violation for task {tid}: "
                "second_search_success and second_search_empty_results cannot both be True."
            )

        category = rec.get("v11_retrieval_category", "UNKNOWN")
        retrieval_categories[category] += 1

        if rec.get("planner_parse_success"):
            planner_parse_success_count += 1
        if rec.get("planner_fallback_used"):
            planner_fallback_count += 1

        if rec.get("second_search_triggered"):
            second_search_triggered_count += 1
        if rec.get("second_search_attempted"):
            second_search_attempted_count += 1
        if rec.get("second_search_success"):
            second_search_success_count += 1
            successful_searches_count += 1
            if rec.get("second_search_has_new_urls"):
                has_new_urls_count += 1
            new_cnt = rec.get("second_search_new_urls_count")
            if new_cnt is not None and isinstance(new_cnt, int):
                new_urls_counts.append(new_cnt)
        if rec.get("second_search_empty_results"):
            second_search_empty_results_count += 1
        if rec.get("second_search_skipped_duplicate_query"):
            second_search_duplicate_skipped_count += 1
        if category == "FOLLOWUP_ELIGIBLE_SEARCH2_PROVIDER_FAILURE":
            second_search_provider_failure_count += 1

        is_eligible = bool(rec.get("followup_eligible"))
        cand_A = rec.get("candidate_without_followup")
        cand_B = rec.get("candidate_with_followup")

        correct_A: Optional[bool] = None
        correct_B: Optional[bool] = None
        transition: Optional[str] = None

        if is_eligible:
            followup_eligible_count += 1

            if cand_A is None or str(cand_A).strip() == "":
                candidate_without_followup_empty_count += 1
            if cand_B is None or str(cand_B).strip() == "":
                candidate_with_followup_empty_count += 1

            if rec.get("python_without_followup"):
                python_without_followup_count += 1
            if rec.get("python_with_followup"):
                python_with_followup_count += 1

            # Post-hoc official GAIA scoring
            str_A = str(cand_A or "").strip()
            str_B = str(cand_B or "").strip()
            correct_A = bool(gaia_question_scorer(str_A, gt)) if str_A else False
            correct_B = bool(gaia_question_scorer(str_B, gt)) if str_B else False

            if correct_A:
                branch_A_correct_count += 1
            if correct_B:
                branch_B_correct_count += 1

            if not correct_A and correct_B:
                transition = "RETRIEVAL_IMPROVEMENT"
                retrieval_improvements += 1
            elif correct_A and not correct_B:
                transition = "RETRIEVAL_REGRESSION"
                retrieval_regressions += 1
            elif correct_A and correct_B:
                transition = "RETRIEVAL_STABLE_CORRECT"
                retrieval_stable_correct += 1
            else:
                transition = "RETRIEVAL_STABLE_FAILURE"
                retrieval_stable_failure += 1

        detailed_entry = dict(rec)
        detailed_entry["ground_truth"] = gt
        detailed_entry["candidate_without_followup_correct"] = correct_A
        detailed_entry["candidate_with_followup_correct"] = correct_B
        detailed_entry["retrieval_transition"] = transition
        detailed_records.append(detailed_entry)

    total_tasks = len(records)
    if followup_eligible_count > 0:
        delta_followup = retrieval_improvements - retrieval_regressions
        branch_A_acc = round(branch_A_correct_count / followup_eligible_count, 4)
        branch_B_acc = round(branch_B_correct_count / followup_eligible_count, 4)
        net_acc_delta = round(branch_B_acc - branch_A_acc, 4)
        if delta_followup > 0:
            scientific_verdict = "POSITIVE (Supports H1)"
        elif delta_followup == 0:
            scientific_verdict = "NEUTRAL (Inconclusive)"
        else:
            scientific_verdict = "NEGATIVE (Refutes H1)"
    else:
        delta_followup = 0
        branch_A_acc = 0.0
        branch_B_acc = 0.0
        net_acc_delta = 0.0
        scientific_verdict = "NOT_TESTABLE"

    novelty_prop = (
        round(has_new_urls_count / successful_searches_count, 4)
        if successful_searches_count > 0
        round(has_new_urls_count / second_search_attempted_count, 4)
        if second_search_attempted_count > 0
        else 0.0
    )
    mean_new_urls = (
        round(sum(new_urls_counts) / len(new_urls_counts), 2)
        if new_urls_counts
        else 0.0
    )
    median_new_urls = (
        round(float(statistics.median(new_urls_counts)), 2)
        if new_urls_counts
        else 0.0
    )

    summary: Dict[str, Any] = {
        "schema_version": 9,
        "evaluation_type": "followup_eligible_shared_plan_paired_retrieval_ablation",
        "total_tasks_recorded": total_tasks,
        "followup_eligible_cohort_size": followup_eligible_count,
        "primary_metric": "Delta_followup",
        "delta_followup": delta_followup,
        "scientific_verdict": scientific_verdict,
        "decision_criterion": "Delta_followup > 0",
        "transition_matrix": {
            "RETRIEVAL_IMPROVEMENT": retrieval_improvements,
            "RETRIEVAL_REGRESSION": retrieval_regressions,
            "RETRIEVAL_STABLE_CORRECT": retrieval_stable_correct,
            "RETRIEVAL_STABLE_FAILURE": retrieval_stable_failure,
        },
        "retrieval_improvements": retrieval_improvements,
        "retrieval_regressions": retrieval_regressions,
        "retrieval_stable_correct": retrieval_stable_correct,
        "retrieval_stable_failure": retrieval_stable_failure,
        "branch_A_without_followup": {
            "correct_candidates": branch_A_correct_count,
            "cohort_accuracy": branch_A_acc,
            "empty_candidates": candidate_without_followup_empty_count,
            "python_executed_count": python_without_followup_count,
        },
        "branch_B_with_followup": {
            "correct_candidates": branch_B_correct_count,
            "cohort_accuracy": branch_B_acc,
            "empty_candidates": candidate_with_followup_empty_count,
            "python_executed_count": python_with_followup_count,
        },
        "net_accuracy_delta": net_acc_delta,
        "retrieval_categories": dict(retrieval_categories),
        "search_operational_telemetry": {
            "second_search_triggered_count": second_search_triggered_count,
            "second_search_attempted_count": second_search_attempted_count,
            "second_search_success_count": second_search_success_count,
            "second_search_empty_results_count": second_search_empty_results_count,
            "second_search_skipped_duplicate_query_count": second_search_duplicate_skipped_count,
            "second_search_provider_failure_count": second_search_provider_failure_count,
        },
        "search_novelty_diagnostics": {
            "successful_searches_count": successful_searches_count,
            "attempted_searches_count": second_search_attempted_count,
            "successful_searches_count": second_search_success_count,
            "has_new_urls_count": has_new_urls_count,
            "has_new_urls_proportion": novelty_prop,
            "mean_new_urls": mean_new_urls,
            "median_new_urls": median_new_urls,
        },
        "planner_v2_operational": {
            "planner_parse_success_count": planner_parse_success_count,
            "planner_parse_success_rate": round(planner_parse_success_count / total_tasks, 4) if total_tasks > 0 else 0.0,
            "planner_fallback_count": planner_fallback_count,
            "planner_fallback_rate": round(planner_fallback_count / total_tasks, 4) if total_tasks > 0 else 0.0,
        },
    }

    return {
        "summary": summary,
        "detailed": detailed_records,
    }


def evaluate_paired_retrieval(
    input_file: str,
    data_path: Optional[str] = None,
    summary_output: Optional[str] = None,
    detailed_output: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluates raw paired retrieval execution JSONL records and produces structured summaries."""
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Paired execution file not found at: {input_file}")

    records: List[Dict[str, Any]] = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))

    if not records:
        raise ValueError(f"No paired records found in {input_file}")

    # Zero-eligible cohort support: empty raw file is valid if it exists on disk
    # Load ground truth tasks across levels
    tasks_by_id: Dict[str, Any] = {}
    for lvl in (1, 2, 3):
        for task in load_gaia_tasks(data_path=data_path, level=lvl):
            tasks_by_id[task.task_id] = task

    res = calculate_paired_metrics(records, tasks_by_id)
    summary = res["summary"]
    detailed_records = res["detailed"]

    total_tasks = summary["total_tasks_recorded"]
    cohort_size = summary["followup_eligible_cohort_size"]
    delta_followup = summary["delta_followup"]
    verdict = summary["scientific_verdict"]

    print("\n" + "=" * 65)
    print("V11 FOLLOW-UP-ELIGIBLE SHARED-PLAN PAIRED RETRIEVAL ABLATION")
    print("=" * 65)
    print(f"Total Tasks Recorded:            {total_tasks}")
    print(f"Follow-Up-Eligible Cohort (H1): {cohort_size}")
    if cohort_size > 0:
        bA = summary["branch_A_without_followup"]
        bB = summary["branch_B_with_followup"]
        print(f"  Branch A (Without Search 2):  {bA['correct_candidates']}/{cohort_size} ({bA['cohort_accuracy'] * 100:.2f}%)")
        print(f"  Branch B (With Search 2):     {bB['correct_candidates']}/{cohort_size} ({bB['cohort_accuracy'] * 100:.2f}%)")
        print("-" * 65)
        print(f"  RETRIEVAL_IMPROVEMENT:        {summary['retrieval_improvements']}")
        print(f"  RETRIEVAL_REGRESSION:         {summary['retrieval_regressions']}")
        print(f"  RETRIEVAL_STABLE_CORRECT:     {summary['retrieval_stable_correct']}")
        print(f"  RETRIEVAL_STABLE_FAILURE:     {summary['retrieval_stable_failure']}")
        print("-" * 65)
        print(f"PRIMARY METRIC: Delta_followup = {delta_followup}")
        print(f"SCIENTIFIC VERDICT: {verdict}")
    else:
        print("  NO FOLLOW-UP ELIGIBLE TASKS RECORDED.")
        print("PRIMARY METRIC: Delta_followup = 0")
        print("SCIENTIFIC VERDICT: NOT_TESTABLE")
    print("=" * 65)

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
    parser = argparse.ArgumentParser(
        description="Evaluate V11 Follow-Up-Eligible Shared-Plan Paired Retrieval Ablation."
    )
    parser.add_argument("--input_file", type=str, required=True, help="Path to raw paired JSONL file.")
    parser.add_argument("--data_path", type=str, default=None, help="Path to GAIA dataset.")
    parser.add_argument("--summary_output", type=str, default=None, help="Path to write summary JSON.")
    parser.add_argument("--detailed_output", type=str, default=None, help="Path to write detailed JSONL.")
    args = parser.parse_args()

    evaluate_paired_retrieval(
        input_file=args.input_file,
        data_path=args.data_path,
        summary_output=args.summary_output,
        detailed_output=args.detailed_output,
    )


if __name__ == "__main__":
    main()

