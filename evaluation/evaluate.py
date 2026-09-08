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

    has_search = any(pred.get("search_enabled") for pred in predictions)
    search_provider = None
    search_call_counts: List[int] = []
    search_success_count = 0
    search_latencies: List[float] = []
    search_result_counts: List[int] = []
    search_fallback_count = 0

    has_file = any(pred.get("file_enabled") for pred in predictions)
    file_attempts = 0
    file_successes = 0
    file_fallbacks = 0
    file_truncations = 0
    file_latencies: List[float] = []
    extension_stats: Dict[str, Dict[str, int]] = {}

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

        # Track search metrics for V1
        if pred.get("search_enabled"):
            search_provider = pred.get("search_provider") or search_provider
            search_call_counts.append(pred.get("search_call_count", 1))
            if pred.get("search_success"):
                search_success_count += 1
            lat = pred.get("search_latency_seconds")
            if lat is not None:
                try:
                    search_latencies.append(float(lat))
                except (ValueError, TypeError):
                    pass
            search_result_counts.append(pred.get("search_result_count", 0))
            if pred.get("search_fallback"):
                search_fallback_count += 1

        # Track file metrics for V2
        if pred.get("file_enabled"):
            if pred.get("file_processing_attempted"):
                file_attempts += 1
                if pred.get("file_processing_success"):
                    file_successes += 1
                flat = pred.get("file_processing_latency_seconds")
                if flat is not None:
                    try:
                        file_latencies.append(float(flat))
                    except (ValueError, TypeError):
                        pass
            if pred.get("file_fallback"):
                file_fallbacks += 1
            if pred.get("file_content_truncated"):
                file_truncations += 1

            ext = pred.get("file_extension")
            if ext:
                if ext not in extension_stats:
                    extension_stats[ext] = {"total": 0, "correct": 0, "processing_success": 0}
                extension_stats[ext]["total"] += 1
                if is_correct:
                    extension_stats[ext]["correct"] += 1
                if pred.get("file_processing_success"):
                    extension_stats[ext]["processing_success"] += 1

        detailed_entry = {
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
        }
        if pred.get("search_enabled"):
            detailed_entry.update({
                "search_enabled": True,
                "search_provider": pred.get("search_provider"),
                "search_query": pred.get("search_query"),
                "search_query_truncated": pred.get("search_query_truncated", False),
                "original_query_length": pred.get("original_query_length"),
                "provider_query_length": pred.get("provider_query_length"),
                "search_call_count": pred.get("search_call_count"),
                "search_success": pred.get("search_success"),
                "search_latency_seconds": pred.get("search_latency_seconds"),
                "search_result_count": pred.get("search_result_count"),
                "search_error_type": pred.get("search_error_type"),
                "search_error_message": pred.get("search_error_message"),
                "search_fallback": pred.get("search_fallback"),
                "search_results": pred.get("search_results"),
            })
        if pred.get("file_enabled"):
            detailed_entry.update({
                "file_enabled": True,
                "file_present": pred.get("file_present"),
                "file_extension": pred.get("file_extension"),
                "file_processing_attempted": pred.get("file_processing_attempted"),
                "file_processing_success": pred.get("file_processing_success"),
                "file_processing_latency_seconds": pred.get("file_processing_latency_seconds"),
                "file_processor": pred.get("file_processor"),
                "file_content_mode": pred.get("file_content_mode"),
                "file_content_truncated": pred.get("file_content_truncated", False),
                "original_file_content_length": pred.get("original_file_content_length"),
                "provided_file_content_length": pred.get("provided_file_content_length"),
                "file_error_type": pred.get("file_error_type"),
                "file_error_message": pred.get("file_error_message"),
                "file_fallback": pred.get("file_fallback"),
            })
        detailed_eval.append(detailed_entry)

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

    # Determine resolved project version
    resolved_pv = project_version
    if predictions and predictions[0].get("project_version"):
        resolved_pv = predictions[0].get("project_version")

    # Collect prompt version counts from actual predictions
    prompt_version_counts: Dict[str, int] = {}
    for pred in predictions:
        pv = pred.get("prompt_version")
        if pv:
            prompt_version_counts[pv] = prompt_version_counts.get(pv, 0) + 1

    distinct_primary = [p for p in dict.fromkeys(pred.get("primary_prompt_version") for pred in predictions if pred.get("primary_prompt_version"))]
    distinct_fallback = [p for p in dict.fromkeys(pred.get("fallback_prompt_version") for pred in predictions if pred.get("fallback_prompt_version"))]

    # Determine prompt version provenance
    # Avoid recording entire run as 'baseline-v1' if task 0 experienced search fallback
    if resolved_pv == "v2" or has_file:
        primary_pv = "file-search-v1"
        fallback_pv = "web-search-v1"
        if distinct_primary:
            if len(distinct_primary) == 1:
                primary_pv = distinct_primary[0]
                fallback_pv = distinct_fallback[0] if distinct_fallback else ("web-search-v1" if primary_pv == "file-search-v1" else "baseline-v1")
                prompt_pv = primary_pv
            else:
                # Mixed V2 run (both file-search-v1 and web-search-v1 paths present)
                preferred_order = ["file-search-v1", "web-search-v1"]
                sorted_primary = sorted(distinct_primary, key=lambda x: preferred_order.index(x) if x in preferred_order else 99)
                primary_pv = " / ".join(sorted_primary)

                preferred_fb_order = ["web-search-v1", "baseline-v1"]
                sorted_fb = sorted(distinct_fallback, key=lambda x: preferred_fb_order.index(x) if x in preferred_fb_order else 99)
                fallback_pv = " / ".join(sorted_fb) if sorted_fb else "web-search-v1 / baseline-v1"
                prompt_pv = primary_pv
        else:
            # Fallback if prediction records lack explicit primary_prompt_version
            if attachment_count > 0 and non_attachment_count == 0:
                primary_pv = "file-search-v1"
                fallback_pv = "web-search-v1"
                prompt_pv = "file-search-v1"
            elif non_attachment_count > 0 and attachment_count == 0:
                primary_pv = "web-search-v1"
                fallback_pv = "baseline-v1"
                prompt_pv = "web-search-v1"
            else:
                primary_pv = "file-search-v1 / web-search-v1"
                fallback_pv = "web-search-v1 / baseline-v1"
                prompt_pv = "file-search-v1 / web-search-v1"
    elif resolved_pv == "v1" or has_search:
        primary_pv = "web-search-v1"
        fallback_pv = "baseline-v1"
        prompt_pv = "web-search-v1"
    else:
        primary_pv = prompt_version or (
            distinct_primary[0] if distinct_primary else
            next((p.get("prompt_version") for p in predictions if p.get("prompt_version")), "baseline-v1")
        )
        fallback_pv = distinct_fallback[0] if distinct_fallback else None
        prompt_pv = primary_pv

    if prompt_version is not None:
        prompt_pv = prompt_version
        primary_pv = prompt_version

    # Safe summary strictly omits questions, ground truths, or raw responses
    summary = {
        "project_version": resolved_pv,
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
        "prompt_version": prompt_pv,
        "primary_prompt_version": primary_pv,
        "fallback_prompt_version": fallback_pv,
        "prompt_version_counts": prompt_version_counts,

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

    if has_search:
        total_searches = sum(search_call_counts)
        summary["search_enabled"] = True
        summary["search_provider"] = search_provider or "tavily"
        summary["total_search_calls"] = total_searches
        summary["successful_search_calls"] = search_success_count
        summary["search_success_rate"] = round(search_success_count / total_tasks, 4) if total_tasks > 0 else 0.0
        summary["average_search_latency_seconds"] = round(statistics.mean(search_latencies), 2) if search_latencies else None
        summary["average_results_per_search"] = round(statistics.mean(search_result_counts), 2) if search_result_counts else 0.0
        summary["search_fallback_count"] = search_fallback_count
        summary["search_query_truncated_count"] = sum(1 for p in predictions if p.get("search_query_truncated"))

    if has_file:
        summary["file_enabled"] = True
        summary["file_processing_attempts"] = file_attempts
        summary["successful_file_processing_count"] = file_successes
        summary["file_processing_success_rate"] = round(file_successes / file_attempts, 4) if file_attempts > 0 else 0.0
        summary["average_file_processing_latency_seconds"] = round(statistics.mean(file_latencies), 2) if file_latencies else None
        summary["file_fallback_count"] = file_fallbacks
        summary["file_content_truncated_count"] = file_truncations
        if extension_stats:
            summary["extension_breakdown"] = {
                ext: {
                    "total": data["total"],
                    "correct": data["correct"],
                    "accuracy": round(data["correct"] / data["total"], 4) if data["total"] > 0 else 0.0,
                    "processing_success_rate": round(data["processing_success"] / data["total"], 4) if data["total"] > 0 else 0.0,
                }
                for ext, data in sorted(extension_stats.items())
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
    project_version: Optional[str] = None,
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
        project_version=project_version or (predictions[0].get("project_version") if predictions else "v0"),
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
    prompt_counts = summary.get("prompt_version_counts", {})
    if len(prompt_counts) > 1:
        preferred_order = ["file-search-v1", "web-search-v1", "baseline-v1"]
        sorted_counts = sorted(
            prompt_counts.items(),
            key=lambda item: preferred_order.index(item[0]) if item[0] in preferred_order else 99,
        )
        counts_str = ", ".join(f"{k} ({v})" for k, v in sorted_counts)
        print(f"Prompt Versions:     {counts_str}")
    else:
        print(f"Prompt Version:      {summary.get('primary_prompt_version') or summary.get('prompt_version')}")
    if summary.get("fallback_prompt_version"):
        print(f"Fallback Prompt:     {summary.get('fallback_prompt_version')}")
    if summary['attachment_task_count'] > 0:
        print(f"Attachment Acc:      {summary['attachment_accuracy'] * 100 if summary['attachment_accuracy'] is not None else 0.0:.2f}% ({summary['attachment_task_count']} tasks)")
        print(f"Non-Attachment Acc:  {summary['non_attachment_accuracy'] * 100 if summary['non_attachment_accuracy'] is not None else 0.0:.2f}% ({summary['non_attachment_task_count']} tasks)")
    if summary.get("search_enabled"):
        print(f"Search Provider:     {summary.get('search_provider')}")
        print(f"Total Search Calls:  {summary.get('total_search_calls')}")
        print(f"Search Success Rate: {summary.get('search_success_rate') * 100:.1f}% ({summary.get('successful_search_calls')}/{summary.get('total_search_calls')})")
        print(f"Avg Search Latency:  {summary.get('average_search_latency_seconds')}s")
        print(f"Avg Results/Search:  {summary.get('average_results_per_search')}")
        print(f"Search Fallbacks:    {summary.get('search_fallback_count')}")
        if summary.get("search_query_truncated_count"):
            print(f"Truncated Queries:   {summary.get('search_query_truncated_count')}")
    if summary.get("file_enabled"):
        print(f"File Processing:     {summary.get('successful_file_processing_count')}/{summary.get('file_processing_attempts')} ({summary.get('file_processing_success_rate', 0.0) * 100:.1f}%)")
        print(f"File Fallbacks:      {summary.get('file_fallback_count')}")
        print(f"Truncated Files:     {summary.get('file_content_truncated_count')}")
        if summary.get("average_file_processing_latency_seconds") is not None:
            print(f"Avg File Latency:    {summary.get('average_file_processing_latency_seconds')}s")
        if summary.get("extension_breakdown"):
            print("Extension Breakdown:")
            for ext, s in summary["extension_breakdown"].items():
                print(f"  {ext:8s}: {s['correct']}/{s['total']} ({s['accuracy']*100:.1f}%) | proc: {s['processing_success_rate']*100:.1f}%")
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
    parser.add_argument("--version", type=str, default="v1", choices=["v0", "v1"], help="Agent version (default: v1)")
    parser.add_argument("--version", type=str, default="v1", choices=["v0", "v1", "v2"], help="Agent version (default: v1)")
    parser.add_argument("--predictions", type=str, default=None, help="Path to predictions JSONL file")
    parser.add_argument("--data", type=str, default=None, help="Path to local ground-truth dataset")
    parser.add_argument("--summary-output", type=str, default=None, help="Output path for safe public summary JSON")
    parser.add_argument("--detailed-output", type=str, default=None, help="Output path for private per-task evaluation JSONL")
    parser.add_argument("--enforce-task-count", action="store_true", help="Fail if total tasks does not match official expected validation task count")
    args = parser.parse_args()

    pred_path = args.predictions
    if not pred_path:
        pred_path = os.path.join("experiments", args.version, f"predictions_level_{args.level}.jsonl")
        if not os.path.exists(pred_path):
            pred_path = os.path.join("experiments", args.version, "runs.jsonl")

    sum_out = args.summary_output or os.path.join("experiments", args.version, f"summary_level_{args.level}.json")

    evaluate_predictions(
        predictions_path=pred_path,
        data_path=args.data,
        level=args.level,
        summary_output=sum_out,
        detailed_output=args.detailed_output,
        enforce_task_count=args.enforce_task_count,
        project_version=args.version,
    )

