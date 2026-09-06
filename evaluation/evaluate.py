"""Evaluation script to score agent predictions against official GAIA ground truth.

Computes exact benchmark metrics using the official GAIA scorer from gaia-benchmark/leaderboard.
Enforces strict integrity:
- Fails clearly if dataset or ground truth is missing (never emits false 0% accuracy)
- Rejects duplicate task predictions
- Tracks official expected validation task counts (Level 1: 53, Level 2: 86, Level 3: 26, Total: 165)
- Differentiates partial / smoke runs (--limit) from complete benchmark runs
- Produces safe public summaries without benchmark questions or ground truths
"""

import argparse
import json
import os
import sys
import statistics
from typing import List, Dict, Any, Optional

# Add repository root to python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from evaluation.dataset import load_gaia_tasks, GAIATask
from evaluation.metrics import normalize_answer, check_exact_match
from evaluation.dataset import load_gaia_tasks, GAIATask, EXPECTED_VALIDATION_COUNTS
from evaluation.metrics import gaia_question_scorer, SCORER_NAME, SCORER_COMMIT
from evaluation.experiment_logger import get_git_metadata


def calculate_metrics(
    predictions: List[Dict[str, Any]],
    tasks_by_id: Dict[str, GAIATask],
    level: Optional[int] = None,
    project_version: str = "v0",
    model_name: Optional[str] = None,
    prompt_version: Optional[str] = None,
    dataset_name: str = "GAIA",
    dataset_version: str = "2023",
    dataset_split: str = "validation",
    expected_task_count: Optional[int] = None,
    scorer_name: str = SCORER_NAME,
    scorer_version: str = SCORER_COMMIT,
) -> Dict[str, Any]:
    """Computes aggregate benchmark metrics across matched tasks."""
    """Computes aggregate benchmark metrics across matched tasks with official GAIA scoring.

    Raises:
    - ValueError: If duplicate predictions are found, or if any task cannot be matched to ground truth.
    """
    total_tasks = len(predictions)
    if total_tasks == 0:
        raise ValueError("Cannot calculate metrics on empty predictions list.")

    # 1. Duplicate prediction check
    seen_task_ids = set()
    for idx, pred in enumerate(predictions, start=1):
        task_id = pred.get("task_id")
        if not task_id:
            raise ValueError(f"Prediction record #{idx} is missing 'task_id'.")
        if task_id in seen_task_ids:
            raise ValueError(
                f"Duplicate prediction detected for task_id '{task_id}'. "
                "Benchmark evaluations require unique task predictions."
            )
        seen_task_ids.add(task_id)

    # 2. Task completeness determination
    if expected_task_count is None:
        expected_task_count = EXPECTED_VALIDATION_COUNTS.get(level)

    is_complete_benchmark = bool(
        expected_task_count is not None and total_tasks == expected_task_count
    )

    completed_tasks = 0
    correct_tasks = 0
    request_failures = 0
    completion_failures = 0

    latencies: List[float] = []
    input_tokens_list: List[int] = []
    output_tokens_list: List[int] = []
    thinking_tokens_list: List[int] = []
    total_tokens_list: List[int] = []

    attachment_count = 0
    attachment_correct = 0
    non_attachment_count = 0
    non_attachment_correct = 0

    detailed_eval: List[Dict[str, Any]] = []

    for pred in predictions:
        task_id = pred.get("task_id")
        task = tasks_by_id.get(task_id)
        if task is None:
            raise ValueError(
                f"Prediction for task_id '{task_id}' cannot be matched to ground truth dataset. "
                "Local evaluation requires valid ground truth for all evaluated predictions."
            )

        gt = task.final_answer
        if gt is None or not gt.strip():
            raise ValueError(
                f"Ground truth answer is missing or empty for task_id '{task_id}'."
            )

        req_success = bool(pred.get("request_success"))
        comp_success = bool(pred.get("completion_success"))

        if not req_success:
            request_failures += 1
        if not comp_success:
            completion_failures += 1
        else:
            completed_tasks += 1

        final_ans = pred.get("final_answer")
        gt = task.final_answer if task else pred.get("ground_truth", "")

        is_correct = False
        if comp_success and gt:
            is_correct = check_exact_match(final_ans, gt)
        if comp_success:
            is_correct = gaia_question_scorer(final_ans, gt)

        if is_correct:
            correct_tasks += 1

        has_att = bool(pred.get("attachment_required"))
        if has_att:
            attachment_count += 1
            if is_correct:
                attachment_correct += 1
        else:
            non_attachment_count += 1
            if is_correct:
                non_attachment_correct += 1

        latency = pred.get("latency_seconds")
        if latency is not None:
            try:
                latencies.append(float(latency))
            except (ValueError, TypeError):
                pass

        for key, target_list in [
            ("input_tokens", input_tokens_list),
            ("output_tokens", output_tokens_list),
            ("thinking_tokens", thinking_tokens_list),
            ("total_tokens", total_tokens_list),
        ]:
            val = pred.get(key)
            if val is not None:
                try:
                    target_list.append(int(val))
                except (ValueError, TypeError):
                    pass

        detailed_eval.append({
            "task_id": task_id,
            "level": pred.get("level", level),
            "prediction": final_ans,
            "ground_truth": gt,
            "correct": is_correct,
            "request_success": req_success,
            "completion_success": comp_success,
            "latency_seconds": latency,
            "input_tokens": pred.get("input_tokens"),
            "output_tokens": pred.get("output_tokens"),
            "thinking_tokens": pred.get("thinking_tokens"),
            "total_tokens": pred.get("total_tokens"),
            "attachment_required": has_att,
            "error_type": pred.get("error_type"),
            "error_message": pred.get("error_message"),
        })

    accuracy = round(correct_tasks / total_tasks, 4) if total_tasks > 0 else 0.0
    completion_rate = round(completed_tasks / total_tasks, 4) if total_tasks > 0 else 0.0

    att_acc = round(attachment_correct / attachment_count, 4) if attachment_count > 0 else None
    non_att_acc = round(non_attachment_correct / non_attachment_count, 4) if non_attachment_count > 0 else None

    avg_lat = round(statistics.mean(latencies), 2) if latencies else None
    med_lat = round(statistics.median(latencies), 2) if latencies else None

    tot_in = sum(input_tokens_list) if input_tokens_list else 0
    tot_out = sum(output_tokens_list) if output_tokens_list else 0
    tot_think = sum(thinking_tokens_list) if thinking_tokens_list else 0
    tot_tok = sum(total_tokens_list) if total_tokens_list else 0

    avg_in = round(statistics.mean(input_tokens_list), 1) if input_tokens_list else None
    avg_out = round(statistics.mean(output_tokens_list), 1) if output_tokens_list else None
    avg_think = round(statistics.mean(thinking_tokens_list), 1) if thinking_tokens_list else None
    avg_tok = round(statistics.mean(total_tokens_list), 1) if total_tokens_list else None

    git_meta = get_git_metadata()

    # Safe summary strictly omits questions, ground truths, or raw responses
    summary = {
        "project_version": project_version,
        "git_commit": git_meta.get("git_commit") or (predictions[0].get("git_commit") if predictions else None),
        "git_branch": git_meta.get("git_branch") or (predictions[0].get("git_branch") if predictions else None),
        "git_dirty": git_meta.get("git_dirty") if git_meta.get("git_dirty") is not None else (predictions[0].get("git_dirty") if predictions else None),

        "dataset_name": dataset_name,
        "dataset_version": dataset_version,
        "dataset_split": dataset_split,
        "level": level,

        "scorer_name": scorer_name,
        "scorer_version": scorer_version,

        "model": model_name or (predictions[0].get("model") if predictions else None),
        "model_version": (predictions[0].get("model_version") if predictions else None),
        "prompt_version": prompt_version or (predictions[0].get("prompt_version") if predictions else None),

        "total_tasks": total_tasks,
        "selected_task_count": total_tasks,
        "expected_task_count": expected_task_count,
        "is_complete_benchmark": is_complete_benchmark,

        "completed_tasks": completed_tasks,
        "completion_rate": completion_rate,
        "correct_tasks": correct_tasks,
        "accuracy": accuracy,
        "request_failures": request_failures,
        "completion_failures": completion_failures,
        "average_latency_seconds": avg_lat,
        "median_latency_seconds": med_lat,
        "total_input_tokens": tot_in,
        "total_output_tokens": tot_out,
        "total_thinking_tokens": tot_think,
        "total_tokens": tot_tok,
        "average_input_tokens": avg_in,
        "average_output_tokens": avg_out,
        "average_thinking_tokens": avg_think,
        "average_total_tokens": avg_tok,
        "attachment_task_count": attachment_count,
        "attachment_accuracy": att_acc,
        "non_attachment_task_count": non_attachment_count,
        "non_attachment_accuracy": non_att_acc,
    }

    return {
        "summary": summary,
        "detailed": detailed_eval,
    }


def evaluate_predictions(
    predictions_path: str,
    data_path: Optional[str] = None,
    level: Optional[int] = None,
    summary_output: Optional[str] = None,
    detailed_output: Optional[str] = None,
    enforce_task_count: bool = False,
    dataset_name: str = "GAIA",
    dataset_version: str = "2023",
    dataset_split: str = "validation",
) -> Dict[str, Any]:
    """Loads prediction records, matches with local ground truth, evaluates, and writes outputs.

    Raises:
    - FileNotFoundError: If predictions file or ground truth dataset cannot be found.
    - ValueError: If ground truth is missing, duplicate predictions exist, or task count check fails.
    """
    if not os.path.exists(predictions_path):
        raise FileNotFoundError(f"Predictions file not found at '{predictions_path}'.")

    predictions: List[Dict[str, Any]] = []
    with open(predictions_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                predictions.append(json.loads(line))

    if level is not None:
        predictions = [p for p in predictions if int(p.get("level", 0)) == level]

    if not predictions:
        print(f"No predictions found for level {level} in {predictions_path}.")
        return {}

    # Load local ground truth dataset strictly requiring ground truth
    tasks = load_gaia_tasks(data_path=data_path, level=level, require_ground_truth=True)
    tasks_by_id = {t.task_id: t for t in tasks}

    eval_result = calculate_metrics(
        predictions=predictions,
        tasks_by_id=tasks_by_id,
        level=level,
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        dataset_split=dataset_split,
    )
    summary = eval_result["summary"]
    detailed = eval_result["detailed"]

    if enforce_task_count and not summary["is_complete_benchmark"]:
        raise ValueError(
            f"Benchmark task count integrity check failed: expected {summary['expected_task_count']} tasks "
            f"for Level {level}, but evaluated {summary['total_tasks']} tasks."
        )

    status_tag = "COMPLETE BENCHMARK" if summary["is_complete_benchmark"] else f"PARTIAL / DEV RUN ({summary['total_tasks']}/{summary['expected_task_count']} tasks)"

    print("\n" + "=" * 65)
    print(f"EVALUATION SUMMARY — Level {level if level is not None else 'All'} [{status_tag}]")
    print("=" * 65)
    print(f"Dataset Split:       {summary['dataset_name']} {summary['dataset_version']} ({summary['dataset_split']})")
    print(f"Scorer:              {summary['scorer_name']} ({summary['scorer_version'][:8]})")
    print(f"Total Tasks:         {summary['total_tasks']} (expected: {summary['expected_task_count']})")
    print(f"Complete Benchmark:  {summary['is_complete_benchmark']}")
    print(f"Completed Tasks:     {summary['completed_tasks']} ({summary['completion_rate'] * 100:.1f}%)")
    print(f"Correct Tasks:       {summary['correct_tasks']}")
    print(f"Accuracy:            {summary['accuracy'] * 100:.2f}%")
    print(f"Average Latency:     {summary['average_latency_seconds']}s")
    print(f"Average Tokens:      {summary['average_total_tokens']}")
    if summary['attachment_task_count'] > 0:
        print(f"Attachment Acc:      {summary['attachment_accuracy'] * 100 if summary['attachment_accuracy'] is not None else 0.0:.2f}% ({summary['attachment_task_count']} tasks)")
        print(f"Non-Attachment Acc:  {summary['non_attachment_accuracy'] * 100 if summary['non_attachment_accuracy'] is not None else 0.0:.2f}% ({summary['non_attachment_task_count']} tasks)")
    print("=" * 65 + "\n")

    # Write safe summary if requested
    if summary_output:
        os.makedirs(os.path.dirname(os.path.abspath(summary_output)), exist_ok=True)
        with open(summary_output, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"Public summary written to: {summary_output}")

    # Write detailed evaluation (ignored by git) if requested
    if detailed_output:
        os.makedirs(os.path.dirname(os.path.abspath(detailed_output)), exist_ok=True)
        with open(detailed_output, "w", encoding="utf-8") as f:
            for item in detailed:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"Detailed per-task evaluation written to: {detailed_output}")

    return eval_result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate agent predictions against local GAIA ground truth.")
    parser.add_argument("--level", type=int, default=1, help="Benchmark level (1, 2, or 3)")
    parser.add_argument("--predictions", type=str, default=None, help="Path to predictions JSONL file")
    parser.add_argument("--data", type=str, default=None, help="Path to local ground-truth dataset")
    parser.add_argument("--summary-output", type=str, default=None, help="Output path for safe public summary JSON")
    parser.add_argument("--detailed-output", type=str, default=None, help="Output path for private per-task evaluation JSONL")
    parser.add_argument("--enforce-task-count", action="store_true", help="Fail if total tasks does not match official expected validation task count")
    args = parser.parse_args()

    pred_path = args.predictions
    if not pred_path:
        pred_path = os.path.join("experiments", "v0", f"predictions_level_{args.level}.jsonl")
        if not os.path.exists(pred_path):
            pred_path = os.path.join("experiments", "v0", "runs.jsonl")

    sum_out = args.summary_output or os.path.join("experiments", "v0", f"summary_level_{args.level}.json")

    evaluate_predictions(
        predictions_path=pred_path,
        data_path=args.data,
        level=args.level,
        summary_output=sum_out,
        detailed_output=args.detailed_output,
        enforce_task_count=args.enforce_task_count,
    )
