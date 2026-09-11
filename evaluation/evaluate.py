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
from evaluation.metrics import (
    normalize_answer,
    check_exact_match,
    gaia_question_scorer,
    SCORER_NAME,
    SCORER_COMMIT,
)
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

    # Determine resolved project version
    resolved_pv = project_version
    if predictions and predictions[0].get("project_version"):
        resolved_pv = predictions[0].get("project_version")

    has_python = (resolved_pv in ("v3", "v4", "v5")) or any(
        pred.get("python_requested") or pred.get("python_executed") or pred.get("python_prompt_version")
        for pred in predictions
    )
    python_requested_count = 0
    python_execution_count = 0
    python_success_count = 0
    python_failure_count = 0
    python_timeout_count = 0
    python_fallback_count = 0
    python_latencies: List[float] = []
    python_executed_correct = 0
    python_not_executed_count = 0
    python_not_executed_correct = 0

    has_router = (resolved_pv in ("v4", "v5")) or any(
        pred.get("router_requested") or pred.get("router_decision")
        for pred in predictions
    )
    router_direct_count = 0
    router_python_count = 0
    router_fallback_count = 0
    router_failure_count = 0
    router_direct_correct = 0
    router_python_correct = 0
    router_fallback_correct = 0
    router_latencies: List[float] = []
    worker_latencies: List[float] = []
    total_llm_generations_list: List[int] = []

    has_verifier = (resolved_pv == "v5") or any(
        pred.get("verifier_attempted") or pred.get("verifier_eligible") or pred.get("verifier_verdict")
        for pred in predictions
    )
    pre_verification_correct_tasks = 0
    verifier_eligible_count = 0
    verifier_attempted_count = 0
    verifier_keep_count = 0
    verifier_keep_correct = 0
    verifier_revise_count = 0
    verifier_revise_correct = 0
    verifier_fallback_count = 0
    verifier_fallback_correct = 0
    verifier_improvements = 0
    verifier_regressions = 0
    verifier_stable_correct = 0
    verifier_stable_failure = 0
    verifier_error_breakdown: Dict[str, int] = {}
    verifier_latencies: List[float] = []
    verifier_input_tokens_list: List[int] = []
    verifier_output_tokens_list: List[int] = []
    verifier_thinking_tokens_list: List[int] = []
    verifier_total_tokens_list: List[int] = []

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

        # Track Python metrics for V3
        if pred.get("python_requested"):
            python_requested_count += 1
        py_exec = bool(pred.get("python_executed"))
        if py_exec:
            python_execution_count += 1
            if pred.get("python_success"):
                python_success_count += 1
            else:
                python_failure_count += 1
            if pred.get("python_timeout"):
                python_timeout_count += 1
            py_lat = pred.get("python_latency_seconds")
            if py_lat is not None:
                try:
                    python_latencies.append(float(py_lat))
                except (ValueError, TypeError):
                    pass
            if is_correct:
                python_executed_correct += 1
        else:
            python_not_executed_count += 1
            if is_correct:
                python_not_executed_correct += 1

        if pred.get("python_fallback"):
            python_fallback_count += 1

        # Track Router & Worker metrics for V4
        if has_router or pred.get("router_requested") or pred.get("router_decision"):
            r_dec = pred.get("router_decision")
            if r_dec == "DIRECT":
                router_direct_count += 1
                if is_correct:
                    router_direct_correct += 1
            elif r_dec == "PYTHON":
                router_python_count += 1
                if is_correct:
                    router_python_correct += 1
            if pred.get("router_fallback"):
                router_fallback_count += 1
                if is_correct:
                    router_fallback_correct += 1
            if pred.get("router_success") is False:
                router_failure_count += 1
            r_lat = pred.get("router_latency_seconds")
            if r_lat is not None:
                try:
                    router_latencies.append(float(r_lat))
                except (ValueError, TypeError):
                    pass
            w_lat = pred.get("worker_latency_seconds")
            if w_lat is not None:
                try:
                    worker_latencies.append(float(w_lat))
                except (ValueError, TypeError):
                    pass
            tot_gens = pred.get("llm_generation_attempts")
            if tot_gens is not None:
                try:
                    total_llm_generations_list.append(int(tot_gens))
                except (ValueError, TypeError):
                    pass

        # Track Verifier metrics for V5
        pre_ans = pred.get("pre_verification_answer")
        post_ans = pred.get("post_verification_answer") or final_ans
        pre_is_correct = False
        post_is_correct = is_correct
        transition = "not_applicable"

        if has_verifier or pred.get("verifier_attempted") or pred.get("verifier_eligible"):
            if comp_success and pre_ans is not None and str(pre_ans).strip():
                pre_is_correct = gaia_question_scorer(str(pre_ans), gt)
            else:
                pre_is_correct = False

            if pre_is_correct:
                pre_verification_correct_tasks += 1

            if not pre_is_correct and post_is_correct:
                verifier_improvements += 1
                transition = "improvement"
            elif pre_is_correct and not post_is_correct:
                verifier_regressions += 1
                transition = "regression"
            elif pre_is_correct and post_is_correct:
                verifier_stable_correct += 1
                transition = "stable_correct"
            else:
                verifier_stable_failure += 1
                transition = "stable_failure"

            if pred.get("verifier_eligible"):
                verifier_eligible_count += 1
            if pred.get("verifier_attempted"):
                verifier_attempted_count += 1
                v_verdict = pred.get("verifier_verdict")
                if v_verdict == "KEEP":
                    verifier_keep_count += 1
                    if is_correct:
                        verifier_keep_correct += 1
                elif v_verdict == "REVISE":
                    verifier_revise_count += 1
                    if is_correct:
                        verifier_revise_correct += 1
                if pred.get("verifier_fallback"):
                    verifier_fallback_count += 1
                    if is_correct:
                        verifier_fallback_correct += 1
                v_err = pred.get("verifier_error_type")
                if v_err:
                    verifier_error_breakdown[v_err] = verifier_error_breakdown.get(v_err, 0) + 1
                v_lat = pred.get("verifier_latency_seconds")
                if v_lat is not None:
                    try:
                        verifier_latencies.append(float(v_lat))
                    except (ValueError, TypeError):
                        pass
                for v_k, v_t_list in [
                    ("verifier_input_tokens", verifier_input_tokens_list),
                    ("verifier_output_tokens", verifier_output_tokens_list),
                    ("verifier_thinking_tokens", verifier_thinking_tokens_list),
                    ("verifier_total_tokens", verifier_total_tokens_list),
                ]:
                    v_val = pred.get(v_k)
                    if v_val is not None:
                        try:
                            v_t_list.append(int(v_val))
                        except (ValueError, TypeError):
                            pass

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
        if has_python or pred.get("python_requested") or pred.get("python_executed") or pred.get("python_prompt_version"):
            detailed_entry.update({
                "python_prompt_version": pred.get("python_prompt_version"),
                "llm_generation_count": pred.get("llm_generation_count"),
                "python_requested": pred.get("python_requested", False),
                "python_executed": pred.get("python_executed", False),
                "python_execution_count": pred.get("python_execution_count", 1 if py_exec else 0),
                "python_success": pred.get("python_success", False),
                "python_timeout": pred.get("python_timeout", False),
                "python_exit_code": pred.get("python_exit_code"),
                "python_error_type": pred.get("python_error_type"),
                "python_latency_seconds": pred.get("python_latency_seconds"),
                "python_stdout_length": pred.get("python_stdout_length", 0),
                "python_stderr_length": pred.get("python_stderr_length", 0),
                "python_output_truncated": pred.get("python_output_truncated", False),
                "python_fallback": pred.get("python_fallback", False),
            })
        if has_router or pred.get("router_requested") or pred.get("router_decision"):
            detailed_entry.update({
                "router_requested": pred.get("router_requested", False),
                "router_decision": pred.get("router_decision"),
                "router_success": pred.get("router_success", False),
                "router_fallback": pred.get("router_fallback", False),
                "router_error_type": pred.get("router_error_type"),
                "router_prompt_version": pred.get("router_prompt_version"),
                "router_latency_seconds": pred.get("router_latency_seconds"),
                "router_input_tokens": pred.get("router_input_tokens"),
                "router_output_tokens": pred.get("router_output_tokens"),
                "router_thinking_tokens": pred.get("router_thinking_tokens"),
                "router_generation_attempts": pred.get("router_generation_attempts", 1),
                "router_generation_success": pred.get("router_generation_success", False),
                "worker_mode": pred.get("worker_mode"),
                "worker_success": pred.get("worker_success", False),
                "worker_error_type": pred.get("worker_error_type"),
                "worker_prompt_version": pred.get("worker_prompt_version"),
                "worker_latency_seconds": pred.get("worker_latency_seconds"),
                "worker_input_tokens": pred.get("worker_input_tokens"),
                "worker_output_tokens": pred.get("worker_output_tokens"),
                "worker_thinking_tokens": pred.get("worker_thinking_tokens"),
                "worker_generation_attempts": pred.get("worker_generation_attempts", 1),
                "worker_generation_success": pred.get("worker_generation_success", False),
                "llm_generation_attempts": pred.get("llm_generation_attempts", 2),
                "llm_generation_success_count": pred.get("llm_generation_success_count", 0),
            })
        if has_verifier or pred.get("verifier_attempted") or pred.get("verifier_eligible"):
            detailed_entry.update({
                "pre_verification_answer": pre_ans,
                "pre_verification_correct": pre_is_correct,
                "post_verification_answer": post_ans,
                "post_verification_correct": post_is_correct,
                "verification_transition": transition,
                "verifier_eligible": pred.get("verifier_eligible", False),
                "verifier_attempted": pred.get("verifier_attempted", False),
                "verifier_generation_attempts": pred.get("verifier_generation_attempts", 0),
                "verifier_generation_success": pred.get("verifier_generation_success", False),
                "verifier_finish_reason": pred.get("verifier_finish_reason"),
                "verifier_error_type": pred.get("verifier_error_type"),
                "verifier_verdict": pred.get("verifier_verdict"),
                "verifier_revised": pred.get("verifier_revised", False),
                "verifier_fallback": pred.get("verifier_fallback", False),
                "verifier_latency_seconds": pred.get("verifier_latency_seconds"),
                "verifier_input_tokens": pred.get("verifier_input_tokens"),
                "verifier_output_tokens": pred.get("verifier_output_tokens"),
                "verifier_thinking_tokens": pred.get("verifier_thinking_tokens"),
                "verifier_total_tokens": pred.get("verifier_total_tokens"),
                "verifier_prompt_version": pred.get("verifier_prompt_version"),
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
    if resolved_pv == "v5" or (has_verifier and resolved_pv not in ("v0", "v1", "v2", "v3", "v4")):
        primary_pv = "capability-router-v1"
        fallback_pv = "router-direct-worker-v1" if any(p.get("router_fallback") for p in predictions) else None
        prompt_pv = "answer-verifier-v1"
        if distinct_primary:
            if len(distinct_primary) == 1:
                primary_pv = distinct_primary[0]
                fallback_pv = distinct_fallback[0] if distinct_fallback else fallback_pv
                prompt_pv = primary_pv
    elif resolved_pv == "v4" or (has_router and resolved_pv not in ("v0", "v1", "v2", "v3")):
        primary_pv = "capability-router-v1"
        fallback_pv = "router-direct-worker-v1" if any(p.get("router_fallback") for p in predictions) else None
        prompt_pv = "capability-router-v1"
        if distinct_primary:
            if len(distinct_primary) == 1:
                primary_pv = distinct_primary[0]
                fallback_pv = distinct_fallback[0] if distinct_fallback else fallback_pv
                prompt_pv = primary_pv
    elif resolved_pv == "v3" or (has_python and resolved_pv not in ("v0", "v1", "v2")):
        primary_pv = "python-execution-v1"
        fallback_pv = None
        prompt_pv = "python-execution-v1"
        if distinct_primary:
            if len(distinct_primary) == 1:
                primary_pv = distinct_primary[0]
                fallback_pv = distinct_fallback[0] if distinct_fallback else None
                prompt_pv = primary_pv
            else:
                preferred_order = ["python-execution-v1"]
                sorted_primary = sorted(distinct_primary, key=lambda x: preferred_order.index(x) if x in preferred_order else 99)
                primary_pv = " / ".join(sorted_primary)
                fallback_pv = " / ".join(distinct_fallback) if distinct_fallback else None
                prompt_pv = primary_pv
    elif resolved_pv == "v2" or has_file:
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

    if has_python:
        summary["python_enabled"] = True
        summary["python_requested_count"] = python_requested_count
        summary["python_execution_count"] = python_execution_count
        summary["python_execution_rate"] = round(python_execution_count / total_tasks, 4) if total_tasks > 0 else 0.0
        summary["python_success_count"] = python_success_count
        summary["python_success_rate"] = round(python_success_count / python_execution_count, 4) if python_execution_count > 0 else 0.0
        summary["python_failure_count"] = python_failure_count
        summary["python_timeout_count"] = python_timeout_count
        summary["python_fallback_count"] = python_fallback_count
        summary["average_python_latency_seconds"] = round(statistics.mean(python_latencies), 2) if python_latencies else None
        summary["python_executed_correct"] = python_executed_correct
        summary["python_executed_accuracy"] = round(python_executed_correct / python_execution_count, 4) if python_execution_count > 0 else None
        summary["python_not_executed_count"] = python_not_executed_count
        summary["python_not_executed_correct"] = python_not_executed_correct
        summary["python_not_executed_accuracy"] = round(python_not_executed_correct / python_not_executed_count, 4) if python_not_executed_count > 0 else None

    if has_router:
        summary["router_enabled"] = True
        summary["router_prompt_version"] = next((p.get("router_prompt_version") for p in predictions if p.get("router_prompt_version")), "capability-router-v1")
        summary["router_direct_count"] = router_direct_count
        summary["router_python_count"] = router_python_count
        summary["router_python_routing_rate"] = round(router_python_count / total_tasks, 4) if total_tasks > 0 else 0.0
        summary["router_fallback_count"] = router_fallback_count
        summary["router_fallback_rate"] = round(router_fallback_count / total_tasks, 4) if total_tasks > 0 else 0.0
        summary["router_failure_count"] = router_failure_count
        summary["average_router_latency_seconds"] = round(statistics.mean(router_latencies), 2) if router_latencies else None
        summary["router_direct_accuracy"] = round(router_direct_correct / router_direct_count, 4) if router_direct_count > 0 else None
        summary["router_python_accuracy"] = round(router_python_correct / router_python_count, 4) if router_python_count > 0 else None
        summary["router_fallback_accuracy"] = round(router_fallback_correct / router_fallback_count, 4) if router_fallback_count > 0 else None
        summary["average_worker_latency_seconds"] = round(statistics.mean(worker_latencies), 2) if worker_latencies else None
        summary["average_total_llm_generations"] = round(statistics.mean(total_llm_generations_list), 2) if total_llm_generations_list else None

    if has_verifier:
        summary["verifier_enabled"] = True
        summary["verifier_prompt_version"] = next(
            (p.get("verifier_prompt_version") for p in predictions if p.get("verifier_prompt_version")),
            "answer-verifier-v1",
        )
        summary["pre_verification_correct_tasks"] = pre_verification_correct_tasks
        summary["pre_verification_accuracy"] = round(pre_verification_correct_tasks / total_tasks, 4) if total_tasks > 0 else 0.0
        summary["post_verification_correct_tasks"] = correct_tasks
        summary["post_verification_accuracy"] = accuracy
        summary["net_correct_delta"] = correct_tasks - pre_verification_correct_tasks
        summary["net_accuracy_delta"] = round(accuracy - (pre_verification_correct_tasks / total_tasks), 4) if total_tasks > 0 else 0.0
        summary["verifier_eligible_count"] = verifier_eligible_count
        summary["verifier_eligible_rate"] = round(verifier_eligible_count / total_tasks, 4) if total_tasks > 0 else 0.0
        summary["verifier_attempted_count"] = verifier_attempted_count
        summary["verifier_attempt_rate"] = round(verifier_attempted_count / total_tasks, 4) if total_tasks > 0 else 0.0
        summary["verifier_keep_count"] = verifier_keep_count
        summary["verifier_keep_accuracy"] = round(verifier_keep_correct / verifier_keep_count, 4) if verifier_keep_count > 0 else None
        summary["verifier_revise_count"] = verifier_revise_count
        summary["verifier_revise_accuracy"] = round(verifier_revise_correct / verifier_revise_count, 4) if verifier_revise_count > 0 else None
        summary["verifier_fallback_count"] = verifier_fallback_count
        summary["verifier_fallback_accuracy"] = round(verifier_fallback_correct / verifier_fallback_count, 4) if verifier_fallback_count > 0 else None
        summary["verifier_improvements"] = verifier_improvements
        summary["verifier_regressions"] = verifier_regressions
        summary["verifier_stable_correct"] = verifier_stable_correct
        summary["verifier_stable_failure"] = verifier_stable_failure
        summary["verifier_error_breakdown"] = verifier_error_breakdown
        summary["average_verifier_latency_seconds"] = round(statistics.mean(verifier_latencies), 2) if verifier_latencies else None
        summary["average_verifier_total_tokens"] = round(statistics.mean(verifier_total_tokens_list), 1) if verifier_total_tokens_list else None

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
    if summary.get("python_enabled"):
        print(f"Python Execution:    {summary.get('python_execution_count')}/{summary.get('total_tasks')} ({summary.get('python_execution_rate', 0.0) * 100:.1f}%)")
        print(f"Python Success Rate: {summary.get('python_success_rate', 0.0) * 100:.1f}% ({summary.get('python_success_count')}/{summary.get('python_execution_count')})")
        print(f"Python Failures:     {summary.get('python_failure_count')} (timeouts: {summary.get('python_timeout_count')})")
        print(f"Python Fallbacks:    {summary.get('python_fallback_count')}")
        if summary.get("average_python_latency_seconds") is not None:
            print(f"Avg Python Latency:  {summary.get('average_python_latency_seconds')}s")
        if summary.get("python_executed_accuracy") is not None:
            print(f"Py Executed Acc:     {summary.get('python_executed_accuracy') * 100:.2f}% ({summary.get('python_executed_correct')}/{summary.get('python_execution_count')})")
        if summary.get("python_not_executed_accuracy") is not None:
            print(f"Py Non-Exec Acc:     {summary.get('python_not_executed_accuracy') * 100:.2f}% ({summary.get('python_not_executed_correct')}/{summary.get('python_not_executed_count')})")
    if summary.get("router_enabled"):
        print(f"Router Prompt Ver:   {summary.get('router_prompt_version')}")
        print(f"Router DIRECT:       {summary.get('router_direct_count')}/{summary.get('total_tasks')}")
        print(f"Router PYTHON:       {summary.get('router_python_count')}/{summary.get('total_tasks')} ({summary.get('router_python_routing_rate', 0.0) * 100:.1f}%)")
        print(f"Router Fallbacks:    {summary.get('router_fallback_count')} ({summary.get('router_fallback_rate', 0.0) * 100:.1f}%)")
        if summary.get("average_router_latency_seconds") is not None:
            print(f"Avg Router Latency:  {summary.get('average_router_latency_seconds')}s")
        if summary.get("router_direct_accuracy") is not None:
            print(f"Router DIRECT Acc:   {summary.get('router_direct_accuracy') * 100:.2f}%")
        if summary.get("router_python_accuracy") is not None:
            print(f"Router PYTHON Acc:   {summary.get('router_python_accuracy') * 100:.2f}%")
    if summary.get("verifier_enabled"):
        print(f"Verifier Prompt Ver: {summary.get('verifier_prompt_version')}")
        print(f"Verifier Eligible:   {summary.get('verifier_eligible_count')}/{summary.get('total_tasks')} ({summary.get('verifier_eligible_rate', 0.0) * 100:.1f}%)")
        print(f"Verifier Attempted:  {summary.get('verifier_attempted_count')}/{summary.get('total_tasks')} ({summary.get('verifier_attempt_rate', 0.0) * 100:.1f}%)")
        print(f"Verifier KEEP:       {summary.get('verifier_keep_count')} (Acc: {summary.get('verifier_keep_accuracy') * 100 if summary.get('verifier_keep_accuracy') is not None else 0.0:.1f}%)")
        print(f"Verifier REVISE:     {summary.get('verifier_revise_count')} (Acc: {summary.get('verifier_revise_accuracy') * 100 if summary.get('verifier_revise_accuracy') is not None else 0.0:.1f}%)")
        print(f"Verifier Fallbacks:  {summary.get('verifier_fallback_count')} (Acc: {summary.get('verifier_fallback_accuracy') * 100 if summary.get('verifier_fallback_accuracy') is not None else 0.0:.1f}%)")
        print(f"Transitions:         +{summary.get('verifier_improvements')} improvements, -{summary.get('verifier_regressions')} regressions (stable correct: {summary.get('verifier_stable_correct')}, stable failure: {summary.get('verifier_stable_failure')})")
        print(f"Pre-Ver Accuracy:    {summary.get('pre_verification_accuracy', 0.0) * 100:.2f}% ({summary.get('pre_verification_correct_tasks')}/{summary.get('total_tasks')})")
        print(f"Post-Ver Accuracy:   {summary.get('post_verification_accuracy', 0.0) * 100:.2f}% ({summary.get('post_verification_correct_tasks')}/{summary.get('total_tasks')})")
        print(f"Net Delta:           {summary.get('net_correct_delta'):+d} tasks ({summary.get('net_accuracy_delta', 0.0) * 100:+.2f} pp)")
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
    # Legacy CLI choices compatibility: choices=["v0", "v1", "v2", "v3"]
    # Legacy CLI choices compatibility: choices=["v0", "v1", "v2", "v3", "v4"]
    parser.add_argument("--version", type=str, default="v1", choices=["v0", "v1", "v2", "v3", "v4", "v5"], help="Agent version (v0: baseline, v1: web search, v2: file attachments, v3: controlled single-shot Python execution, v4: explicit capability routing, v5: one-shot post-answer verification; default: v1)")
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

