"""Post-hoc V7 targeted repair within-run metrics.

These helpers operate exclusively on post-hoc scored records where both
pre_repair_correct and post_repair_correct are known. They are never imported
by runtime agent code and have zero access to or influence on runtime execution.
"""

import statistics
from typing import Any, Dict, Iterable, List, Optional


def _safe_rate(numerator: int, denominator: int) -> Optional[float]:
    """Returns a deterministic rounded rate, or None when mathematically undefined."""
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def calculate_targeted_repair_metrics(
    records: Iterable[Dict[str, Any]],
    total_benchmark_tasks: Optional[int] = None,
) -> Dict[str, Any]:
    """Computes comprehensive within-run targeted repair metrics for V7.

    Transitions are defined strictly over repair-triggered tasks:
    - IMPROVEMENT: pre_repair_correct is False, post_repair_correct is True
    - REGRESSION: pre_repair_correct is True, post_repair_correct is False
    - STABLE_CORRECT: pre_repair_correct is True, post_repair_correct is True
    - STABLE_FAILURE: pre_repair_correct is False, post_repair_correct is False
    """
    items: List[Dict[str, Any]] = list(records)
    total_tasks = total_benchmark_tasks if total_benchmark_tasks is not None else len(items)

    repair_eligible_count = 0
    repair_triggered_count = 0
    repair_attempted_count = 0
    repair_valid_count = 0
    repair_failure_count = 0
    repair_keep_count = 0
    repair_replace_count = 0
    repair_changed_count = 0

    improvements = 0
    regressions = 0
    stable_correct = 0
    stable_failure = 0

    pre_repair_correct_tasks = 0
    post_repair_correct_tasks = 0

    # Sub-breakdowns
    keep_stats = {"count": 0, "pre_correct": 0, "pre_wrong": 0, "post_correct": 0, "post_wrong": 0}
    replace_stats = {"count": 0, "improvements": 0, "regressions": 0, "stable_correct": 0, "stable_failure": 0}
    failure_stats = {"count": 0, "stable_correct": 0, "stable_failure": 0, "error_breakdown": {}}

    risk_stats: Dict[str, Dict[str, Any]] = {}
    repair_latencies: List[float] = []
    repair_total_tokens_list: List[int] = []
    repair_input_tokens_list: List[int] = []
    repair_output_tokens_list: List[int] = []
    repair_thinking_tokens_list: List[int] = []

    # Starvation tracking
    starved_errors = 0
    reachable_errors = 0

    for item in items:
        pre_corr = bool(item.get("pre_repair_correct", False))
        post_corr = bool(item.get("post_repair_correct", False))

        if pre_corr:
            pre_repair_correct_tasks += 1
        if post_corr:
            post_repair_correct_tasks += 1

        is_eligible = bool(item.get("repair_eligible", False))
        is_triggered = bool(item.get("repair_triggered", False))
        is_attempted = bool(item.get("repair_attempted", False))
        is_success = bool(item.get("repair_success", False))
        action = item.get("repair_action")
        changed = bool(item.get("repair_answer_changed", False))
        error_type = item.get("repair_error_type")
        risk_type = str(item.get("self_eval_risk_type") or "UNKNOWN").upper()

        # Candidate starvation classification
        candidate_ans = item.get("pre_repair_answer")
        has_candidate = bool(candidate_ans and str(candidate_ans).strip())
        if not pre_corr:
            if not has_candidate:
                starved_errors += 1
            else:
                reachable_errors += 1

        if is_eligible:
            repair_eligible_count += 1
        if is_triggered:
            repair_triggered_count += 1
        if is_attempted:
            repair_attempted_count += 1
            lat = item.get("repair_latency_seconds")
            if lat is not None:
                try:
                    repair_latencies.append(float(lat))
                except (ValueError, TypeError):
                    pass
            for key, target_list in [
                ("repair_total_tokens", repair_total_tokens_list),
                ("repair_input_tokens", repair_input_tokens_list),
                ("repair_output_tokens", repair_output_tokens_list),
                ("repair_thinking_tokens", repair_thinking_tokens_list),
            ]:
                val = item.get(key)
                if val is not None:
                    try:
                        target_list.append(int(val))
                    except (ValueError, TypeError):
                        pass

        if is_triggered:
            if is_success:
                repair_valid_count += 1
            else:
                repair_failure_count += 1

            if changed:
                repair_changed_count += 1

            # Transition classification
            transition = "STABLE_FAILURE"
            if not pre_corr and post_corr:
                improvements += 1
                transition = "IMPROVEMENT"
            elif pre_corr and not post_corr:
                regressions += 1
                transition = "REGRESSION"
            elif pre_corr and post_corr:
                stable_correct += 1
                transition = "STABLE_CORRECT"
            else:
                stable_failure += 1
                transition = "STABLE_FAILURE"

            # Action-specific breakdown
            if action == "KEEP":
                repair_keep_count += 1
                keep_stats["count"] += 1
                keep_stats["pre_correct" if pre_corr else "pre_wrong"] += 1
                keep_stats["post_correct" if post_corr else "post_wrong"] += 1
            elif action == "REPLACE":
                repair_replace_count += 1
                replace_stats["count"] += 1
                if transition == "IMPROVEMENT":
                    replace_stats["improvements"] += 1
                elif transition == "REGRESSION":
                    replace_stats["regressions"] += 1
                elif transition == "STABLE_CORRECT":
                    replace_stats["stable_correct"] += 1
                else:
                    replace_stats["stable_failure"] += 1
            else:
                # Failure / invalid repair output
                failure_stats["count"] += 1
                if pre_corr:
                    failure_stats["stable_correct"] += 1
                else:
                    failure_stats["stable_failure"] += 1
                if error_type:
                    failure_stats["error_breakdown"][error_type] = (
                        failure_stats["error_breakdown"].get(error_type, 0) + 1
                    )

            # Risk-type breakdown
            risk_entry = risk_stats.setdefault(
                risk_type,
                {
                    "count": 0,
                    "keep_count": 0,
                    "replace_count": 0,
                    "failure_count": 0,
                    "improvements": 0,
                    "regressions": 0,
                    "stable_correct": 0,
                    "stable_failure": 0,
                },
            )
            risk_entry["count"] += 1
            if action == "KEEP":
                risk_entry["keep_count"] += 1
            elif action == "REPLACE":
                risk_entry["replace_count"] += 1
            else:
                risk_entry["failure_count"] += 1

            if transition == "IMPROVEMENT":
                risk_entry["improvements"] += 1
            elif transition == "REGRESSION":
                risk_entry["regressions"] += 1
            elif transition == "STABLE_CORRECT":
                risk_entry["stable_correct"] += 1
            else:
                risk_entry["stable_failure"] += 1

    pre_wrong_triggered = improvements + stable_failure
    pre_correct_triggered = regressions + stable_correct
    repair_correction_rate = _safe_rate(improvements, pre_wrong_triggered)
    repair_harm_rate = _safe_rate(regressions, pre_correct_triggered)
    net_repair_delta = improvements - regressions

    pre_acc = round(pre_repair_correct_tasks / total_tasks, 4) if total_tasks > 0 else 0.0
    post_acc = round(post_repair_correct_tasks / total_tasks, 4) if total_tasks > 0 else 0.0
    delta_pp = round((post_acc - pre_acc) * 100, 2)

    for rk, rv in risk_stats.items():
        rv["net_delta"] = rv["improvements"] - rv["regressions"]

    total_system_errors = total_tasks - pre_repair_correct_tasks
    end_to_end_detection_rate = _safe_rate(repair_triggered_count, total_system_errors)
    end_to_end_repair_rate = _safe_rate(improvements, total_system_errors)

    return {
        "repair_eligible_count": repair_eligible_count,
        "repair_eligible_rate": _safe_rate(repair_eligible_count, total_tasks),
        "repair_triggered_count": repair_triggered_count,
        "repair_trigger_rate": _safe_rate(repair_triggered_count, total_tasks) if total_tasks > 0 else 0.0,
        "repair_attempted_count": repair_attempted_count,
        "repair_attempt_rate": _safe_rate(repair_attempted_count, total_tasks),
        "repair_valid_count": repair_valid_count,
        "repair_failure_count": repair_failure_count,
        "repair_valid_output_rate": _safe_rate(repair_valid_count, repair_attempted_count),
        "repair_keep_count": repair_keep_count,
        "repair_replace_count": repair_replace_count,
        "repair_changed_count": repair_changed_count,
        "repair_improvement_count": improvements,
        "repair_regression_count": regressions,
        "repair_stable_correct_count": stable_correct,
        "repair_stable_failure_count": stable_failure,
        "repair_improvements": improvements,
        "repair_regressions": regressions,
        "repair_stable_correct": stable_correct,
        "repair_stable_failure": stable_failure,
        "repair_not_triggered": sum(1 for item in items if not item.get("repair_triggered")),
        "repair_net_correct_delta": net_repair_delta,
        "net_repair_correct_delta": net_repair_delta,
        "net_repair_accuracy_delta": round((post_acc - pre_acc), 4),
        "pre_repair_correct_tasks": pre_repair_correct_tasks,
        "post_repair_correct_tasks": post_repair_correct_tasks,
        "pre_repair_accuracy": pre_acc,
        "post_repair_accuracy": post_acc,
        "repair_accuracy_delta_tasks": post_repair_correct_tasks - pre_repair_correct_tasks,
        "repair_accuracy_delta_pp": delta_pp,
        "repair_correction_rate": repair_correction_rate,
        "repair_harm_count": regressions,
        "repair_harm_rate": repair_harm_rate,
        "repair_keep_outcomes": keep_stats,
        "repair_replace_outcomes": replace_stats,
        "repair_failure_outcomes": failure_stats,
        "risk_type_repair_outcomes": dict(sorted(risk_stats.items())),
        "average_repair_latency_seconds": round(statistics.mean(repair_latencies), 2) if repair_latencies else None,
        "median_repair_latency_seconds": round(statistics.median(repair_latencies), 2) if repair_latencies else None,
        "total_repair_tokens": sum(repair_total_tokens_list) if repair_total_tokens_list else 0,
        "average_repair_total_tokens": round(statistics.mean(repair_total_tokens_list), 1) if repair_total_tokens_list else None,
        "average_repair_input_tokens": round(statistics.mean(repair_input_tokens_list), 1) if repair_input_tokens_list else None,
        "average_repair_output_tokens": round(statistics.mean(repair_output_tokens_list), 1) if repair_output_tokens_list else None,
        "average_repair_thinking_tokens": round(statistics.mean(repair_thinking_tokens_list), 1) if repair_thinking_tokens_list else None,
        "candidate_starvation": {
            "total_system_errors": total_system_errors,
            "starved_errors": starved_errors,
            "starved_error_rate": _safe_rate(starved_errors, total_system_errors),
            "reachable_errors": reachable_errors,
            "reachable_error_rate": _safe_rate(reachable_errors, total_system_errors),
            "end_to_end_error_detection_rate": end_to_end_detection_rate,
            "end_to_end_repair_rate": end_to_end_repair_rate,
        },
    }
