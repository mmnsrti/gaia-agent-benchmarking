"""Post-hoc V6 self-evaluation diagnostic metrics.

These helpers intentionally operate only after official scorer correctness has
already been produced by the evaluation layer. They are not imported by runtime
agent code and therefore cannot influence an answer or evaluator prompt.
"""

import math
from typing import Any, Dict, Iterable, List, Optional


_SUSPECT_RISK_TYPES = {
    "EVIDENCE",
    "REASONING",
    "CALCULATION",
    "FORMAT",
    "EXECUTION",
    "UNKNOWN",
}


def _safe_rate(numerator: int, denominator: int) -> Optional[float]:
    """Returns a deterministic rounded rate, or None when mathematically undefined."""
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _valid_record(record: Dict[str, Any]) -> bool:
    assessment = record.get("assessment")
    risk_type = record.get("risk_type")
    confidence = record.get("confidence")
    if not record.get("eligible") or not record.get("success"):
        return False
    if assessment == "PASS":
        schema_valid = risk_type == "NONE"
    elif assessment == "SUSPECT":
        schema_valid = risk_type in _SUSPECT_RISK_TYPES
    else:
        return False
    if not schema_valid or isinstance(confidence, bool):
        return False
    try:
        numeric_confidence = float(confidence)
    except (TypeError, ValueError):
        return False
    return math.isfinite(numeric_confidence) and 0.0 <= numeric_confidence <= 1.0


def calculate_self_evaluation_metrics(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes V6 diagnostic metrics with ERROR/INCORRECT as the positive class.

    Empty-answer bypasses are excluded because they are not eligible. Invalid and
    failed evaluator events count against coverage but never enter the confusion
    matrix. Undefined rates use ``None``; zero eligible tasks have coverage ``0.0``.
    """
    items: List[Dict[str, Any]] = list(records)
    eligible = [item for item in items if bool(item.get("eligible"))]
    valid = [item for item in eligible if _valid_record(item)]

    tp = fp = tn = fn = 0
    pass_count = suspect_count = 0
    correct_among_pass = incorrect_among_pass = 0
    correct_among_suspect = incorrect_among_suspect = 0
    suspect_probabilities: List[float] = []
    brier_terms: List[float] = []
    risk_stats: Dict[str, Dict[str, int]] = {}

    for item in valid:
        assessment = item["assessment"]
        risk_type = item["risk_type"]
        is_correct = bool(item.get("correct"))
        confidence = float(item["confidence"])
        is_incorrect = not is_correct

        if assessment == "SUSPECT":
            suspect_count += 1
            suspect_probability = confidence
            if is_incorrect:
                tp += 1
                incorrect_among_suspect += 1
            else:
                fp += 1
                correct_among_suspect += 1
        else:
            pass_count += 1
            suspect_probability = 1.0 - confidence
            if is_incorrect:
                fn += 1
                incorrect_among_pass += 1
            else:
                tn += 1
                correct_among_pass += 1

        suspect_probabilities.append(suspect_probability)
        brier_terms.append((suspect_probability - (1.0 if is_incorrect else 0.0)) ** 2)
        risk_entry = risk_stats.setdefault(risk_type, {"count": 0, "correct": 0, "incorrect": 0})
        risk_entry["count"] += 1
        risk_entry["incorrect" if is_incorrect else "correct"] += 1

    precision = _safe_rate(tp, tp + fp)
    recall = _safe_rate(tp, tp + fn)
    if precision is None or recall is None or precision + recall == 0:
        f1 = None
    else:
        f1 = round(2 * precision * recall / (precision + recall), 4)

    risk_type_distribution = {risk: values["count"] for risk, values in sorted(risk_stats.items())}
    risk_type_conditional_error_rates = {
        risk: {
            "count": values["count"],
            "correct": values["correct"],
            "incorrect": values["incorrect"],
            "error_rate": _safe_rate(values["incorrect"], values["count"]),
        }
        for risk, values in sorted(risk_stats.items())
    }

    eligible_count = len(eligible)
    valid_count = len(valid)
    return {
        "eligible_count": eligible_count,
        "attempted_count": sum(1 for item in eligible if bool(item.get("attempted"))),
        "valid_assessment_count": valid_count,
        "failure_or_invalid_count": eligible_count - valid_count,
        "pass_count": pass_count,
        "suspect_count": suspect_count,
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_alarm_rate": _safe_rate(fp, fp + tn),
        "missed_error_rate": _safe_rate(fn, tp + fn),
        "specificity": _safe_rate(tn, tn + fp),
        "diagnostic_coverage": round(valid_count / eligible_count, 4) if eligible_count else 0.0,
        "correct_among_pass": correct_among_pass,
        "incorrect_among_pass": incorrect_among_pass,
        "correct_among_suspect": correct_among_suspect,
        "incorrect_among_suspect": incorrect_among_suspect,
        "pass_group_correctness_rate": _safe_rate(correct_among_pass, pass_count),
        "suspect_group_error_rate": _safe_rate(incorrect_among_suspect, suspect_count),
        "risk_type_distribution": risk_type_distribution,
        "risk_type_conditional_error_rates": risk_type_conditional_error_rates,
        "brier_diagnostic_score": round(sum(brier_terms) / len(brier_terms), 4) if brier_terms else None,
    }
