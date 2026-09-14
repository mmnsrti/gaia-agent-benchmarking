"""Post-hoc V8 active evidence verification within-run metrics.

These helpers operate exclusively on post-hoc scored records where both
pre_active_verification_correct and post_active_verification_correct are known.
They are never imported by runtime agent code and have zero access to or
influence on runtime execution.
"""

import statistics
from typing import Any, Dict, Iterable, List, Optional


def _safe_rate(numerator: int, denominator: int) -> Optional[float]:
    """Returns a deterministic rounded rate, or None when mathematically undefined."""
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def calculate_active_verification_metrics(
    records: Iterable[Dict[str, Any]],
    total_benchmark_tasks: Optional[int] = None,
) -> Dict[str, Any]:
    """Computes comprehensive within-run active evidence verification metrics for V8.

    Transitions are defined strictly over verification-triggered tasks:
    - IMPROVEMENT: pre_active_verification_correct is False, post_active_verification_correct is True
    - REGRESSION: pre_active_verification_correct is True, post_active_verification_correct is False
    - STABLE_CORRECT: pre_active_verification_correct is True, post_active_verification_correct is True
    - STABLE_FAILURE: pre_active_verification_correct is False, post_active_verification_correct is False
    """
    items: List[Dict[str, Any]] = list(records)
    total_tasks = total_benchmark_tasks if total_benchmark_tasks is not None else len(items)

    non_empty_v7_answers = 0
    valid_suspect_candidates = 0
    suspect_evidence_candidates = 0

    eligible_count = 0
    triggered_count = 0

    search_attempted_count = 0
    search_success_count = 0
    search_usable_count = 0
    search_failure_count = 0

    adjudication_attempted_count = 0
    valid_adjudication_count = 0
    failed_adjudication_count = 0
    keep_count = 0
    replace_count = 0
    changed_count = 0

    improvements = 0
    regressions = 0
    stable_correct = 0
    stable_failure = 0

    pre_correct_tasks = 0
    post_correct_tasks = 0

    initially_wrong_eligible = 0
    initially_correct_eligible = 0

    search_latencies: List[float] = []
    adjudication_latencies: List[float] = []
    total_stage_latencies: List[float] = []

    adjudication_input_tokens_list: List[int] = []
    adjudication_output_tokens_list: List[int] = []
    adjudication_thinking_tokens_list: List[int] = []
    adjudication_total_tokens_list: List[int] = []

    # Starvation / reachability tracking
    starved_errors = 0
    reachable_errors = 0

    for item in items:
        # Resolve pre/post correctness
        # pre_active_verification_correct falls back to pre_repair_correct or pre_correct if not explicitly present
        pre_corr = bool(item.get("pre_active_verification_correct", item.get("post_repair_correct", item.get("pre_repair_correct", False))))
        # post_active_verification_correct corresponds to the final task correctness
        post_corr = bool(item.get("correct", item.get("post_active_verification_correct", False)))

        if pre_corr:
            pre_correct_tasks += 1
        if post_corr:
            post_correct_tasks += 1

        pre_ans = item.get("pre_active_verification_answer", item.get("post_repair_answer", item.get("final_answer")))
        has_v7_ans = bool(pre_ans and str(pre_ans).strip())
        if has_v7_ans:
            non_empty_v7_answers += 1

        se_success = bool(item.get("self_eval_success", False))
        se_assess = str(item.get("self_eval_assessment") or "").strip().upper()
        se_risk = str(item.get("self_eval_risk_type") or "").strip().upper()

        if se_success and se_assess == "SUSPECT":
            valid_suspect_candidates += 1
            if se_risk == "EVIDENCE":
                suspect_evidence_candidates += 1

        is_eligible = bool(item.get("active_verification_eligible", False))
        is_triggered = bool(item.get("active_verification_triggered", False))

        if is_eligible:
            eligible_count += 1
            if pre_corr:
                initially_correct_eligible += 1
            else:
                initially_wrong_eligible += 1

        if is_triggered:
            triggered_count += 1

        if not pre_corr:
            if not has_v7_ans:
                starved_errors += 1
            else:
                reachable_errors += 1

        is_search_att = bool(item.get("active_verification_search_attempted", False))
        is_search_succ = bool(item.get("active_verification_search_success", False))
        is_search_usable = bool(item.get("active_verification_search_usable", False))

        if is_search_att:
            search_attempted_count += 1
            s_lat = item.get("active_verification_search_latency_seconds")
            if s_lat is not None:
                try:
                    search_latencies.append(float(s_lat))
                except (ValueError, TypeError):
                    pass

        if is_search_succ:
            search_success_count += 1
        elif is_search_att:
            search_failure_count += 1

        if is_search_usable:
            search_usable_count += 1

        is_adj_att = bool(item.get("active_verification_adjudication_attempted", False))
        is_adj_succ = bool(item.get("active_verification_adjudication_success", False))
        adj_action = item.get("active_verification_action")
        changed = bool(item.get("active_verification_answer_changed", False))

        if is_adj_att:
            adjudication_attempted_count += 1
            a_lat = item.get("active_verification_latency_seconds")
            if a_lat is not None:
                try:
                    adjudication_latencies.append(float(a_lat))
                except (ValueError, TypeError):
                    pass

            for key, target_list in [
                ("active_verification_total_tokens", adjudication_total_tokens_list),
                ("active_verification_input_tokens", adjudication_input_tokens_list),
                ("active_verification_output_tokens", adjudication_output_tokens_list),
                ("active_verification_thinking_tokens", adjudication_thinking_tokens_list),
            ]:
                val = item.get(key)
                if val is not None:
                    try:
                        target_list.append(int(val))
                    except (ValueError, TypeError):
                        pass

        if is_adj_att:
            if is_adj_succ and adj_action in {"KEEP", "REPLACE"}:
                valid_adjudication_count += 1
                if adj_action == "KEEP":
                    keep_count += 1
                elif adj_action == "REPLACE":
                    replace_count += 1
            else:
                failed_adjudication_count += 1

        if changed:
            changed_count += 1

        # Within-run intervention transition classification over triggered tasks
        if is_triggered:
            if not pre_corr and post_corr:
                improvements += 1
            elif pre_corr and not post_corr:
                regressions += 1
            elif pre_corr and post_corr:
                stable_correct += 1
            else:
                stable_failure += 1

    net_delta = improvements - regressions
    pre_accuracy = _safe_rate(pre_correct_tasks, total_tasks)
    post_accuracy = _safe_rate(post_correct_tasks, total_tasks)
    accuracy_delta = round(post_accuracy - pre_accuracy, 4) if (pre_accuracy is not None and post_accuracy is not None) else None

    # Correction rate: improvements / initially wrong eligible tasks
    correction_rate = _safe_rate(improvements, initially_wrong_eligible)
    # Harm rate: regressions / initially correct eligible tasks
    harm_rate = _safe_rate(regressions, initially_correct_eligible)

    # Rates
    usable_evidence_rate = _safe_rate(search_usable_count, search_attempted_count)
    adjudication_coverage = _safe_rate(valid_adjudication_count, search_usable_count)
    change_rate = _safe_rate(changed_count, valid_adjudication_count)

    # Passive upstream V6 diagnostic metrics (anchored strictly to pre-V7 candidate correctness)
    # To maintain semantic comparability across V6/V7/V8.
    tp = sum(1 for it in items if str(it.get("self_eval_assessment") or "").upper() == "SUSPECT" and not bool(it.get("pre_repair_correct", it.get("pre_self_evaluation_correct", False))))
    fp = sum(1 for it in items if str(it.get("self_eval_assessment") or "").upper() == "SUSPECT" and bool(it.get("pre_repair_correct", it.get("pre_self_evaluation_correct", False))))
    tn = sum(1 for it in items if str(it.get("self_eval_assessment") or "").upper() == "PASS" and bool(it.get("pre_repair_correct", it.get("pre_self_evaluation_correct", False))))
    fn = sum(1 for it in items if str(it.get("self_eval_assessment") or "").upper() == "PASS" and not bool(it.get("pre_repair_correct", it.get("pre_self_evaluation_correct", False))))

    eval_precision = _safe_rate(tp, tp + fp)
    eval_recall = _safe_rate(tp, tp + fn)
    eval_f1 = None
    if eval_precision is not None and eval_recall is not None and (eval_precision + eval_recall) > 0:
        eval_f1 = round(2 * (eval_precision * eval_recall) / (eval_precision + eval_recall), 4)

    return {
        "benchmark_tasks_count": total_tasks,
        "processed_tasks_count": len(items),
        "pre_active_verification_correct_count": pre_correct_tasks,
        "post_active_verification_correct_count": post_correct_tasks,
        "pre_active_verification_accuracy": pre_accuracy,
        "post_active_verification_accuracy": post_accuracy,
        "accuracy_delta": accuracy_delta,
        # Transitions
        "improvements": improvements,
        "regressions": regressions,
        "stable_correct": stable_correct,
        "stable_failure": stable_failure,
        "net_active_verification_delta": net_delta,
        "correction_rate": correction_rate,
        "harm_rate": harm_rate,
        # Funnel
        "non_empty_v7_answers": non_empty_v7_answers,
        "valid_suspect_candidates": valid_suspect_candidates,
        "suspect_evidence_candidates": suspect_evidence_candidates,
        "active_verification_eligible_count": eligible_count,
        "active_verification_triggered_count": triggered_count,
        "active_verification_search_attempted_count": search_attempted_count,
        "active_verification_search_success_count": search_success_count,
        "active_verification_search_usable_count": search_usable_count,
        "active_verification_search_failure_count": search_failure_count,
        "active_verification_adjudication_attempted_count": adjudication_attempted_count,
        "active_verification_valid_adjudication_count": valid_adjudication_count,
        "active_verification_failed_adjudication_count": failed_adjudication_count,
        "active_verification_keep_count": keep_count,
        "active_verification_replace_count": replace_count,
        "active_verification_answers_changed_count": changed_count,
        # Rates
        "usable_evidence_rate": usable_evidence_rate,
        "adjudication_coverage": adjudication_coverage,
        "change_rate": change_rate,
        # Eligible subsets
        "initially_wrong_eligible_count": initially_wrong_eligible,
        "initially_correct_eligible_count": initially_correct_eligible,
        "starved_errors_count": starved_errors,
        "reachable_errors_count": reachable_errors,
        # Resource & Latency
        "avg_search_latency_seconds": round(statistics.mean(search_latencies), 2) if search_latencies else None,
        "avg_adjudication_latency_seconds": round(statistics.mean(adjudication_latencies), 2) if adjudication_latencies else None,
        "avg_adjudication_total_tokens": round(statistics.mean(adjudication_total_tokens_list), 1) if adjudication_total_tokens_list else None,
        "avg_adjudication_input_tokens": round(statistics.mean(adjudication_input_tokens_list), 1) if adjudication_input_tokens_list else None,
        "avg_adjudication_output_tokens": round(statistics.mean(adjudication_output_tokens_list), 1) if adjudication_output_tokens_list else None,
        "avg_adjudication_thinking_tokens": round(statistics.mean(adjudication_thinking_tokens_list), 1) if adjudication_thinking_tokens_list else None,
        # Upstream Passive Evaluator Diagnostic Performance
        "upstream_evaluator_diagnostic": {
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "precision": eval_precision,
            "recall": eval_recall,
            "f1": eval_f1,
        },
    }

