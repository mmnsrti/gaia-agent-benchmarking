"""Post-hoc V9 candidate recovery within-run metrics.

These helpers operate exclusively on post-hoc scored records where both
candidate recovery telemetry and evaluation correctness flags are available.
They are never imported by runtime agent code and have zero access to or
influence on runtime execution.
"""

from typing import Any, Dict, Iterable, List, Optional


def _safe_rate(numerator: int, denominator: int) -> Optional[float]:
    """Returns a deterministic rounded rate, or None when mathematically undefined."""
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def calculate_candidate_recovery_metrics(
    records: Iterable[Dict[str, Any]],
    total_benchmark_tasks: Optional[int] = None,
) -> Dict[str, Any]:
    """Computes comprehensive within-run candidate recovery metrics for V9.

    Tracks:
    - Pre/post candidate reachability
    - Trigger, attempt, and success counts
    - Recovered candidate accuracy
    - Non-triggered recovery-boundary preservation rate
    - Downstream safeguard effect on recovered candidates:
      * RECOVERY_CORRECT_FINAL_CORRECT
      * RECOVERY_CORRECT_FINAL_WRONG
      * RECOVERY_WRONG_FINAL_CORRECT
      * RECOVERY_WRONG_FINAL_WRONG
    - Failure class breakdown
    """
    items: List[Dict[str, Any]] = list(records)
    total_tasks = total_benchmark_tasks if total_benchmark_tasks is not None else len(items)

    pre_reachability_count = 0
    post_reachability_count = 0

    recovery_eligible_count = 0
    recovery_triggered_count = 0
    recovery_attempted_count = 0
    recovery_success_count = 0
    recovery_parse_success_count = 0

    recovered_candidate_correct_count = 0

    # Non-triggered boundary preservation
    non_triggered_count = 0
    non_triggered_preserved_count = 0

    # Downstream safeguard effect on recovered candidates
    recovery_correct_final_correct = 0
    recovery_correct_final_wrong = 0
    recovery_wrong_final_correct = 0
    recovery_wrong_final_wrong = 0

    # Overall correctness transitions
    improvements = 0
    regressions = 0
    stable_correct = 0
    stable_failure = 0

    # Failure-class breakdown
    failure_class_stats: Dict[str, Dict[str, int]] = {}

    for item in items:
        pre_cand = str(item.get("pre_recovery_candidate") or "").strip()
        post_cand = str(item.get("post_recovery_candidate") or "").strip()
        final_ans = str(item.get("final_answer") or "").strip()

        if pre_cand:
            pre_reachability_count += 1
        if post_cand:
            post_reachability_count += 1

        is_eligible = bool(item.get("candidate_recovery_eligible", False))
        is_triggered = bool(item.get("candidate_recovery_triggered", False))
        is_attempted = bool(item.get("candidate_recovery_attempted", False))
        is_success = bool(item.get("candidate_recovery_success", False))
        is_parse_success = bool(item.get("candidate_recovery_parse_success", False))
        fail_class = item.get("candidate_recovery_failure_class")

        if is_eligible:
            recovery_eligible_count += 1
        if is_triggered:
            recovery_triggered_count += 1
        if is_attempted:
            recovery_attempted_count += 1
        if is_success:
            recovery_success_count += 1
        if is_parse_success:
            recovery_parse_success_count += 1

        # Non-triggered recovery-boundary preservation check
        if not is_triggered:
            non_triggered_count += 1
            if item.get("pre_recovery_candidate") == item.get("post_recovery_candidate"):
                non_triggered_preserved_count += 1

        # Track failure classes
        if fail_class:
            if fail_class not in failure_class_stats:
                failure_class_stats[fail_class] = {
                    "eligible": 0,
                    "attempted": 0,
                    "recovered": 0,
                    "correct": 0,
                }
            if is_eligible:
                failure_class_stats[fail_class]["eligible"] += 1
            if is_attempted:
                failure_class_stats[fail_class]["attempted"] += 1
            if is_success:
                failure_class_stats[fail_class]["recovered"] += 1

        # Post-hoc correctness evaluation if available
        # recovered_candidate_correct evaluates correctness of post_recovery_candidate
        # final_correct evaluates correctness of final_answer
        rec_cand = str(item.get("post_recovery_candidate") or "").strip()
        gt_val = str(item.get("ground_truth") or "").strip()
        rec_corr = bool(item.get("recovered_candidate_correct", False))
        if not rec_corr and rec_cand and gt_val and rec_cand == gt_val:
            rec_corr = True

        fin_corr = bool(item.get("final_correct", item.get("is_correct", False)))
        if not fin_corr and final_ans and gt_val and final_ans == gt_val:
            fin_corr = True

        base_corr = bool(item.get("baseline_candidate_correct", False))

        if is_success and rec_corr:
            recovered_candidate_correct_count += 1
            if fail_class and fail_class in failure_class_stats:
                failure_class_stats[fail_class]["correct"] += 1

        # Downstream effect tracking for triggered tasks
        if is_triggered and is_success:
            if rec_corr and fin_corr:
                recovery_correct_final_correct += 1
            elif rec_corr and not fin_corr:
                recovery_correct_final_wrong += 1
            elif not rec_corr and fin_corr:
                recovery_wrong_final_correct += 1
            else:
                recovery_wrong_final_wrong += 1

        # End-to-end transitions
        if is_triggered:
            if not base_corr and fin_corr:
                improvements += 1
            elif base_corr and not fin_corr:
                regressions += 1
            elif base_corr and fin_corr:
                stable_correct += 1
            else:
                stable_failure += 1

    reachability_pre = _safe_rate(pre_reachability_count, total_tasks)
    reachability_post = _safe_rate(post_reachability_count, total_tasks)
    reach_delta = round((reachability_post - reachability_pre) * 100, 2) if (reachability_pre is not None and reachability_post is not None) else None

    preservation_rate = _safe_rate(non_triggered_preserved_count, non_triggered_count)

    downstream_breakdown = {
        "RECOVERY_CORRECT_FINAL_CORRECT": recovery_correct_final_correct,
        "RECOVERY_CORRECT_FINAL_WRONG": recovery_correct_final_wrong,
        "RECOVERY_WRONG_FINAL_CORRECT": recovery_wrong_final_correct,
        "RECOVERY_WRONG_FINAL_WRONG": recovery_wrong_final_wrong,
    }

    return {
        "total_tasks": total_tasks,
        "pre_reachability_count": pre_reachability_count,
        "post_reachability_count": post_reachability_count,
        "reachability_pre_recovery_count": pre_reachability_count,
        "reachability_post_recovery_count": post_reachability_count,
        "reachability_pre": reachability_pre,
        "reachability_post": reachability_post,
        "reachability_rate_pre_recovery": reachability_pre,
        "reachability_rate_post_recovery": reachability_post,
        "reachability_net_gain": post_reachability_count - pre_reachability_count,
        "reachability_delta_pp": reach_delta,
        "recovery_eligible_count": recovery_eligible_count,
        "recovery_triggered_count": recovery_triggered_count,
        "recovery_attempted_count": recovery_attempted_count,
        "recovery_success_count": recovery_success_count,
        "recovery_parse_success_count": recovery_parse_success_count,
        "recovery_success_rate": _safe_rate(recovery_success_count, recovery_triggered_count),
        "recovered_candidate_correct_count": recovered_candidate_correct_count,
        "recovered_candidate_accuracy": _safe_rate(recovered_candidate_correct_count, recovery_success_count),
        "candidate_recovery_eligible_count": recovery_eligible_count,
        "candidate_recovery_triggered_count": recovery_triggered_count,
        "candidate_recovery_trigger_rate": _safe_rate(recovery_triggered_count, total_tasks),
        "candidate_recovery_attempted_count": recovery_attempted_count,
        "candidate_recovery_success_count": recovery_success_count,
        "candidate_recovery_recovered_count": recovery_success_count,
        "candidate_recovery_attempt_success_rate": _safe_rate(recovery_success_count, recovery_attempted_count),
        "candidate_recovery_parse_success_count": recovery_parse_success_count,
        "non_triggered_count": non_triggered_count,
        "non_triggered_preserved_count": non_triggered_preserved_count,
        "non_triggered_recovery_boundary_preservation_rate": preservation_rate,
        "candidate_recovery_non_triggered_preservation_rate": preservation_rate,
        "candidate_recovery_downstream_safeguard_breakdown": downstream_breakdown,
        "downstream_effects": {
            "recovery_correct_final_correct": recovery_correct_final_correct,
            "recovery_correct_final_wrong": recovery_correct_final_wrong,
            "recovery_wrong_final_correct": recovery_wrong_final_correct,
            "recovery_wrong_final_wrong": recovery_wrong_final_wrong,
        },
        "within_run_transitions": {
            "improvements": improvements,
            "regressions": regressions,
            "stable_correct": stable_correct,
            "stable_failure": stable_failure,
            "net_delta": improvements - regressions,
        },
        "failure_class_breakdown": failure_class_stats,
    }
