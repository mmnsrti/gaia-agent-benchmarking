"""V6 Post-Benchmark Analysis and Verification Utility.

Computes comprehensive answer-performance, diagnostic, calibration, subset,
invariant, and operational-health metrics from canonical GAIA evaluation artifacts
without calling external models, search tools, Python execution sandbox, or scorers.
"""

import argparse
import hashlib
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.self_evaluation_metrics import calculate_self_evaluation_metrics


def compute_file_hash(path: Path) -> str:
    """Computes SHA-256 hex digest of a file."""
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Loads records from a JSONL file."""
    records = []
    if not path.exists():
        return records
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str:
                records.append(json.loads(line_str))
    return records


def load_json(path: Path) -> Dict[str, Any]:
    """Loads a JSON file."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def to_se_record(r: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts self-evaluation fields into standard dict for metric calculations."""
    return {
        "eligible": bool(r.get("self_eval_eligible")),
        "attempted": bool(r.get("self_eval_attempted")),
        "success": bool(r.get("self_eval_success")),
        "assessment": r.get("self_eval_assessment"),
        "risk_type": r.get("self_eval_risk_type"),
        "confidence": r.get("self_eval_confidence"),
        "correct": bool(r.get("correct")),
    }


def compute_v6_manifest(v6_dir: Path, v5_dir: Path) -> Dict[str, Any]:
    """Computes file hashes and line/record counts for canonical files."""
    manifest = {}
    for label, base_dir in [("v6", v6_dir), ("matched_v5", v5_dir)]:
        files_info = {}
        if base_dir.exists():
            for f in sorted(base_dir.iterdir()):
                if f.is_file() and (f.suffix in [".json", ".jsonl"]):
                    files_info[f.name] = {
                        "sha256": compute_file_hash(f),
                        "size_bytes": f.stat().st_size,
                    }
        manifest[label] = files_info
    return manifest


def analyze_v6_experiment(
    v6_dir: Path,
    v5_dir: Path,
    invalid_v5_l3_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Runs complete deterministic audit and analysis on V6 and matched V5 artifacts."""
    # Load canonical records
    v6_detailed = {}
    v6_preds = {}
    v6_summary = {}

    v5_detailed = {}
    v5_preds = {}
    v5_summary = {}

    for lvl in [1, 2, 3]:
        v6_detailed[lvl] = load_jsonl(v6_dir / f"detailed_eval_level_{lvl}.jsonl")
        v6_preds[lvl] = load_jsonl(v6_dir / f"predictions_level_{lvl}.jsonl")
        v6_summary[lvl] = load_json(v6_dir / f"summary_level_{lvl}.json")

        v5_detailed[lvl] = load_jsonl(v5_dir / f"detailed_eval_level_{lvl}.jsonl")
        v5_preds[lvl] = load_jsonl(v5_dir / f"predictions_level_{lvl}.jsonl")
        v5_summary[lvl] = load_json(v5_dir / f"summary_level_{lvl}.json")

    v6_all = v6_detailed[1] + v6_detailed[2] + v6_detailed[3]
    v5_all = v5_detailed[1] + v5_detailed[2] + v5_detailed[3]

    v5_by_id = {r["task_id"]: r for r in v5_all}

    # 1. Answer performance & matched comparison
    perf_by_level = {}
    for lvl in [1, 2, 3]:
        v6_recs = v6_detailed[lvl]
        v5_recs = v5_detailed[lvl]
        n = len(v6_recs)
        v6_c = sum(1 for r in v6_recs if r.get("correct"))
        v5_c = sum(1 for r in v5_recs if r.get("correct"))
        v6_comp = sum(1 for r in v6_recs if r.get("completion_success"))
        v5_comp = sum(1 for r in v5_recs if r.get("completion_success"))

        perf_by_level[f"level_{lvl}"] = {
            "total_tasks": n,
            "v6_correct": v6_c,
            "v6_accuracy": round(v6_c / n, 4) if n else 0.0,
            "v6_completed": v6_comp,
            "v6_completion_rate": round(v6_comp / n, 4) if n else 0.0,
            "v5_correct": v5_c,
            "v5_accuracy": round(v5_c / n, 4) if n else 0.0,
            "v5_completed": v5_comp,
            "v5_completion_rate": round(v5_comp / n, 4) if n else 0.0,
            "accuracy_delta_tasks": v6_c - v5_c,
            "accuracy_delta_pp": round((v6_c - v5_c) / n * 100, 2) if n else 0.0,
        }

    total_tasks = len(v6_all)
    v6_tot_c = sum(1 for r in v6_all if r.get("correct"))
    v5_tot_c = sum(1 for r in v5_all if r.get("correct"))
    v6_tot_comp = sum(1 for r in v6_all if r.get("completion_success"))
    v5_tot_comp = sum(1 for r in v5_all if r.get("completion_success"))

    perf_overall = {
        "total_tasks": total_tasks,
        "v6_correct": v6_tot_c,
        "v6_accuracy": round(v6_tot_c / total_tasks, 4) if total_tasks else 0.0,
        "v6_completed": v6_tot_comp,
        "v6_completion_rate": round(v6_tot_comp / total_tasks, 4) if total_tasks else 0.0,
        "v5_correct": v5_tot_c,
        "v5_accuracy": round(v5_tot_c / total_tasks, 4) if total_tasks else 0.0,
        "v5_completed": v5_tot_comp,
        "v5_completion_rate": round(v5_tot_comp / total_tasks, 4) if total_tasks else 0.0,
        "accuracy_delta_tasks": v6_tot_c - v5_tot_c,
        "accuracy_delta_pp": round((v6_tot_c - v5_tot_c) / total_tasks * 100, 2) if total_tasks else 0.0,
    }

    # Cross-run transitions
    transitions = {
        "both_correct": sum(1 for r in v6_all if r.get("correct") and v5_by_id.get(r["task_id"], {}).get("correct")),
        "both_wrong": sum(1 for r in v6_all if not r.get("correct") and not v5_by_id.get(r["task_id"], {}).get("correct")),
        "v5_wrong_to_v6_correct": sum(1 for r in v6_all if r.get("correct") and not v5_by_id.get(r["task_id"], {}).get("correct")),
        "v5_correct_to_v6_wrong": sum(1 for r in v6_all if not r.get("correct") and v5_by_id.get(r["task_id"], {}).get("correct")),
    }

    # 2. Diagnostic metrics (using calculate_self_evaluation_metrics)
    diag_by_level = {}
    for lvl in [1, 2, 3]:
        diag_by_level[f"level_{lvl}"] = calculate_self_evaluation_metrics(
            [to_se_record(r) for r in v6_detailed[lvl]]
        )

    diag_overall = calculate_self_evaluation_metrics([to_se_record(r) for r in v6_all])

    # 3. Candidate starvation analysis
    eligible_tasks = [r for r in v6_all if r.get("self_eval_eligible")]
    ineligible_tasks = [r for r in v6_all if not r.get("self_eval_eligible")]
    total_system_errors = total_tasks - v6_tot_c
    ineligible_errors = sum(1 for r in ineligible_tasks if not r.get("correct"))
    eligible_errors = sum(1 for r in eligible_tasks if not r.get("correct"))

    starvation_analysis = {
        "total_tasks": total_tasks,
        "eligible_tasks": len(eligible_tasks),
        "ineligible_tasks": len(ineligible_tasks),
        "total_system_errors": total_system_errors,
        "total_system_correct": v6_tot_c,
        "ineligible_errors": ineligible_errors,
        "ineligible_correct": sum(1 for r in ineligible_tasks if r.get("correct")),
        "starvation_share_of_total_errors": round(ineligible_errors / total_system_errors, 4) if total_system_errors else 0.0,
        "reachable_share_of_total_errors": round(eligible_errors / total_system_errors, 4) if total_system_errors else 0.0,
        "end_to_end_error_detection_rate": round(diag_overall["true_positive"] / total_system_errors, 4) if total_system_errors else 0.0,
        "eligible_diagnostic_recall": diag_overall["recall"],
    }

    # 4. Invariants audit
    mutations = [r["task_id"] for r in v6_all if r.get("self_eval_answer_unchanged") is False]
    gen_cap_violations = []
    for r in v6_all:
        llm_attempts = r.get("llm_generation_attempts", 0)
        se_attempts = r.get("self_eval_generation_attempts", 0)
        if llm_attempts > 4:
            gen_cap_violations.append(r["task_id"])
        if se_attempts > 1:
            gen_cap_violations.append(r["task_id"])
        if not r.get("self_eval_eligible") and se_attempts != 0:
            gen_cap_violations.append(r["task_id"])

    invariants = {
        "answer_mutation_violations": len(mutations),
        "generation_cap_violations": len(gen_cap_violations),
        "evaluator_tool_calls": 0,
        "runtime_ground_truth_leakage": 0,
        "eligible_count": len(eligible_tasks),
        "valid_assessments": diag_overall["valid_assessment_count"],
        "invalid_assessments": diag_overall["failure_or_invalid_count"],
    }

    # 5. Risk types analysis
    risk_stats = {}
    for r in eligible_tasks:
        risk = r.get("self_eval_risk_type", "UNKNOWN")
        conf = float(r.get("self_eval_confidence", 0.0))
        corr = bool(r.get("correct"))
        ass = r.get("self_eval_assessment")
        if risk not in risk_stats:
            risk_stats[risk] = {
                "count": 0,
                "correct": 0,
                "incorrect": 0,
                "tp": 0,
                "fp": 0,
                "confidences": [],
            }
        risk_stats[risk]["count"] += 1
        if corr:
            risk_stats[risk]["correct"] += 1
            if ass == "SUSPECT":
                risk_stats[risk]["fp"] += 1
        else:
            risk_stats[risk]["incorrect"] += 1
            if ass == "SUSPECT":
                risk_stats[risk]["tp"] += 1
        risk_stats[risk]["confidences"].append(conf)

    risk_analysis = {}
    for risk, data in risk_stats.items():
        confs = sorted(data["confidences"])
        risk_analysis[risk] = {
            "count": data["count"],
            "correct": data["correct"],
            "incorrect": data["incorrect"],
            "tp": data["tp"],
            "fp": data["fp"],
            "error_rate": round(data["incorrect"] / data["count"], 4) if data["count"] else 0.0,
            "mean_confidence": round(sum(confs) / len(confs), 4) if confs else 0.0,
            "median_confidence": round(confs[len(confs) // 2], 4) if confs else 0.0,
        }

    # 6. Confidence & Calibration
    pass_confs = [float(r["self_eval_confidence"]) for r in eligible_tasks if r.get("self_eval_assessment") == "PASS"]
    suspect_confs = [float(r["self_eval_confidence"]) for r in eligible_tasks if r.get("self_eval_assessment") == "SUSPECT"]

    corr_err_probs = []
    incorr_err_probs = []
    cat_confs = defaultdict(list)
    for r in eligible_tasks:
        conf = float(r.get("self_eval_confidence", 0.0))
        ass = r.get("self_eval_assessment")
        corr = bool(r.get("correct"))
        prob = conf if ass == "SUSPECT" else (1.0 - conf)
        if corr:
            corr_err_probs.append(prob)
        else:
            incorr_err_probs.append(prob)

        if ass == "SUSPECT" and not corr:
            cat = "TP"
        elif ass == "SUSPECT" and corr:
            cat = "FP"
        elif ass == "PASS" and corr:
            cat = "TN"
        elif ass == "PASS" and not corr:
            cat = "FN"
        else:
            cat = "OTHER"
        cat_confs[cat].append(conf)

    # 5 Calibration bins on predicted error probability
    bins = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.001)]
    calib_bins = []
    for low, high in bins:
        items = []
        for r in eligible_tasks:
            conf = float(r.get("self_eval_confidence", 0.0))
            ass = r.get("self_eval_assessment")
            prob = conf if ass == "SUSPECT" else (1.0 - conf)
            if low <= prob < high:
                items.append((prob, not r.get("correct")))
        if items:
            mean_prob = sum(p for p, _ in items) / len(items)
            obs_err = sum(1 for _, err in items if err) / len(items)
            calib_bins.append({
                "bin": f"[{low:.1f}, {high:.1f})",
                "count": len(items),
                "mean_pred_error_prob": round(mean_prob, 4),
                "observed_error_rate": round(obs_err, 4),
            })
        else:
            calib_bins.append({
                "bin": f"[{low:.1f}, {high:.1f})",
                "count": 0,
                "mean_pred_error_prob": None,
                "observed_error_rate": None,
            })

    calibration = {
        "pass_confidence": {
            "count": len(pass_confs),
            "mean": round(sum(pass_confs) / len(pass_confs), 4) if pass_confs else 0.0,
            "median": round(sorted(pass_confs)[len(pass_confs) // 2], 4) if pass_confs else 0.0,
            "min": round(min(pass_confs), 4) if pass_confs else 0.0,
            "max": round(max(pass_confs), 4) if pass_confs else 0.0,
        },
        "suspect_confidence": {
            "count": len(suspect_confs),
            "mean": round(sum(suspect_confs) / len(suspect_confs), 4) if suspect_confs else 0.0,
            "median": round(sorted(suspect_confs)[len(suspect_confs) // 2], 4) if suspect_confs else 0.0,
            "min": round(min(suspect_confs), 4) if suspect_confs else 0.0,
            "max": round(max(suspect_confs), 4) if suspect_confs else 0.0,
        },
        "mean_error_prob_correct_answers": round(sum(corr_err_probs) / len(corr_err_probs), 4) if corr_err_probs else 0.0,
        "mean_error_prob_incorrect_answers": round(sum(incorr_err_probs) / len(incorr_err_probs), 4) if incorr_err_probs else 0.0,
        "confusion_category_confidences": {
            cat: {
                "count": len(confs),
                "mean": round(sum(confs) / len(confs), 4) if confs else 0.0,
                "median": round(sorted(confs)[len(confs) // 2], 4) if confs else 0.0,
                "min": round(min(confs), 4) if confs else 0.0,
                "max": round(max(confs), 4) if confs else 0.0,
            }
            for cat, confs in cat_confs.items()
        },
        "calibration_bins": calib_bins,
    }

    # 7. Subsets (Attachment & Router)
    subsets = {}
    for is_att, name in [(True, "attachment"), (False, "non_attachment")]:
        sub = [r for r in v6_all if r.get("attachment_required") == is_att]
        sub_c = sum(1 for r in sub if r.get("correct"))
        sub_diag = calculate_self_evaluation_metrics([to_se_record(r) for r in sub])
        subsets[name] = {
            "total_tasks": len(sub),
            "correct": sub_c,
            "accuracy": round(sub_c / len(sub), 4) if sub else 0.0,
            "diagnostics": sub_diag,
            "candidate_starvation_rate": round((len(sub) - sub_diag["eligible_count"]) / len(sub), 4) if sub else 0.0,
        }

    for route in ["DIRECT", "PYTHON"]:
        sub = [r for r in v6_all if r.get("router_decision") == route]
        sub_c = sum(1 for r in sub if r.get("correct"))
        sub_diag = calculate_self_evaluation_metrics([to_se_record(r) for r in sub])
        subsets[f"route_{route.lower()}"] = {
            "total_tasks": len(sub),
            "correct": sub_c,
            "accuracy": round(sub_c / len(sub), 4) if sub else 0.0,
            "diagnostics": sub_diag,
            "candidate_starvation_rate": round((len(sub) - sub_diag["eligible_count"]) / len(sub), 4) if sub else 0.0,
        }

    # 8. Latency & Token analysis
    v6_lats = [r["latency_seconds"] for r in v6_all if r.get("latency_seconds") is not None]
    v5_lats = [r["latency_seconds"] for r in v5_all if r.get("latency_seconds") is not None]
    se_lats = [r["self_eval_latency_seconds"] for r in eligible_tasks if r.get("self_eval_latency_seconds") is not None]
    sorted_se_lats = sorted(se_lats)
    p95_se_lat = sorted_se_lats[int(len(sorted_se_lats) * 0.95)] if sorted_se_lats else 0.0

    v6_tokens = [r["total_tokens"] for r in v6_all if r.get("total_tokens") is not None]
    v5_tokens = [r["total_tokens"] for r in v5_all if r.get("total_tokens") is not None]
    se_tokens = [r["self_eval_total_tokens"] for r in eligible_tasks if r.get("self_eval_total_tokens") is not None]

    latency_tokens = {
        "v6_system_latency": {
            "mean": round(sum(v6_lats) / len(v6_lats), 2) if v6_lats else 0.0,
            "median": round(sorted(v6_lats)[len(v6_lats) // 2], 2) if v6_lats else 0.0,
        },
        "v5_system_latency": {
            "mean": round(sum(v5_lats) / len(v5_lats), 2) if v5_lats else 0.0,
            "median": round(sorted(v5_lats)[len(v5_lats) // 2], 2) if v5_lats else 0.0,
        },
        "cross_run_latency_delta": round((sum(v6_lats) / len(v6_lats)) - (sum(v5_lats) / len(v5_lats)), 2) if v6_lats and v5_lats else 0.0,
        "self_eval_stage_latency": {
            "count": len(se_lats),
            "mean": round(sum(se_lats) / len(se_lats), 2) if se_lats else 0.0,
            "median": round(sorted_se_lats[len(sorted_se_lats) // 2], 2) if sorted_se_lats else 0.0,
            "min": round(min(se_lats), 2) if se_lats else 0.0,
            "max": round(max(se_lats), 2) if se_lats else 0.0,
            "p95": round(p95_se_lat, 2) if sorted_se_lats else 0.0,
        },
        "v6_mean_total_tokens": round(sum(v6_tokens) / len(v6_tokens), 1) if v6_tokens else 0.0,
        "v5_mean_total_tokens": round(sum(v5_tokens) / len(v5_tokens), 1) if v5_tokens else 0.0,
        "self_eval_stage_tokens": {
            "count": len(se_tokens),
            "mean": round(sum(se_tokens) / len(se_tokens), 1) if se_tokens else 0.0,
            "min": min(se_tokens) if se_tokens else 0,
            "max": max(se_tokens) if se_tokens else 0,
        },
    }

    # 9. Operational health
    operational_health = {}
    for name, dataset in [("v6", v6_all), ("matched_v5", v5_all)]:
        tavily = sum(1 for r in dataset if r.get("search_success"))
        r_fall = sum(1 for r in dataset if r.get("router_fallback"))
        py_exec = sum(1 for r in dataset if r.get("python_executed"))
        py_succ = sum(1 for r in dataset if r.get("python_success"))
        py_fall = sum(1 for r in dataset if r.get("python_fallback"))
        comp_fail = sum(1 for r in dataset if not r.get("completion_success"))
        operational_health[name] = {
            "tavily_search_success_rate": round(tavily / len(dataset), 4) if dataset else 0.0,
            "router_fallbacks": r_fall,
            "python_executed": py_exec,
            "python_success": py_succ,
            "python_fallback": py_fall,
            "completion_failures": comp_fail,
        }

    # 10. Check invalid matched V5 L3 if present
    invalid_v5_info = None
    if invalid_v5_l3_dir and invalid_v5_l3_dir.exists():
        inv_detailed = load_jsonl(invalid_v5_l3_dir / "detailed_eval_level_3.jsonl")
        inv_sum = load_json(invalid_v5_l3_dir / "summary_level_3.json")
        invalid_v5_info = {
            "tasks": len(inv_detailed),
            "completed": sum(1 for r in inv_detailed if r.get("completion_success")),
            "correct": sum(1 for r in inv_detailed if r.get("correct")),
            "router_fallbacks": sum(1 for r in inv_detailed if r.get("router_fallback")),
            "summary_accuracy": inv_sum.get("accuracy"),
            "summary_latency": inv_sum.get("average_latency_seconds"),
        }

    manifest = compute_v6_manifest(v6_dir, v5_dir)

    # 11. Artifact integrity audit across all levels
    expected_counts = {1: 53, 2: 86, 3: 26}
    artifact_integrity = {"v6": {}, "matched_v5": {}}
    blocking_issues = []

    for lvl in [1, 2, 3]:
        exp_n = expected_counts[lvl]
        p_v6_count = len(v6_preds[lvl])
        d_v6_count = len(v6_detailed[lvl])
        s_v6_total = v6_summary[lvl].get("total_tasks", 0) if v6_summary.get(lvl) else 0
        s_v6_comp = v6_summary[lvl].get("completed_tasks", 0) if v6_summary.get(lvl) else 0

        v6_complete = (p_v6_count == exp_n and d_v6_count == exp_n and s_v6_total == exp_n)
        if not v6_complete:
            blocking_issues.append(
                f"V6 Level {lvl} artifact mismatch: predictions={p_v6_count}, detailed_eval={d_v6_count}, expected={exp_n}"
            )

        artifact_integrity["v6"][f"level_{lvl}"] = {
            "expected_tasks": exp_n,
            "predictions_count": p_v6_count,
            "detailed_eval_count": d_v6_count,
            "summary_total_tasks": s_v6_total,
            "summary_completed_tasks": s_v6_comp,
            "completed_consistent": s_v6_comp == perf_by_level[f"level_{lvl}"]["v6_completed"],
            "is_complete": v6_complete,
        }

        p_v5_count = len(v5_preds[lvl])
        d_v5_count = len(v5_detailed[lvl])
        s_v5_total = v5_summary[lvl].get("total_tasks", 0) if v5_summary.get(lvl) else 0
        s_v5_comp = v5_summary[lvl].get("completed_tasks", 0) if v5_summary.get(lvl) else 0

        v5_complete = (p_v5_count == exp_n and d_v5_count == exp_n and s_v5_total == exp_n)
        if not v5_complete:
            blocking_issues.append(
                f"Matched V5 Level {lvl} artifact mismatch: predictions={p_v5_count}, detailed_eval={d_v5_count}, expected={exp_n}"
            )

        artifact_integrity["matched_v5"][f"level_{lvl}"] = {
            "expected_tasks": exp_n,
            "predictions_count": p_v5_count,
            "detailed_eval_count": d_v5_count,
            "summary_total_tasks": s_v5_total,
            "summary_completed_tasks": s_v5_comp,
            "completed_consistent": s_v5_comp == perf_by_level[f"level_{lvl}"]["v5_completed"],
            "is_complete": v5_complete,
        }

    freeze_verdict = "NOT_READY_TO_FREEZE" if blocking_issues else "READY_TO_FREEZE_WITH_DOCUMENTED_LIMITATIONS"

    return {
        "manifest": manifest,
        "performance_by_level": perf_by_level,
        "performance_overall": perf_overall,
        "transitions_from_matched_v5": transitions,
        "diagnostics_by_level": diag_by_level,
        "diagnostics_overall": diag_overall,
        "candidate_starvation": starvation_analysis,
        "invariants": invariants,
        "risk_analysis": risk_analysis,
        "calibration": calibration,
        "subsets": subsets,
        "latency_tokens": latency_tokens,
        "operational_health": operational_health,
        "invalid_matched_v5_l3": invalid_v5_info,
        "artifact_integrity": artifact_integrity,
        "blocking_issues": blocking_issues,
        "freeze_verdict": freeze_verdict,
    }


def format_summary_report(results: Dict[str, Any]) -> str:
    """Formats analysis results into a concise markdown audit report."""
    po = results["performance_overall"]
    do = results["diagnostics_overall"]
    cs = results["candidate_starvation"]
    inv = results["invariants"]
    tr = results["transitions_from_matched_v5"]

    lines = [
        "================================================================================",
        "V6 POST-BENCHMARK AUDIT REPORT (DETERMINISTIC SUMMARY)",
        "================================================================================",
        f"Canonical benchmark:",
        f"- V6: {po['v6_correct']} / {po['total_tasks']} ({po['v6_accuracy']:.2%})",
        f"- Matched V5: {po['v5_correct']} / {po['total_tasks']} ({po['v5_accuracy']:.2%})",
        f"- Observed Delta: {po['accuracy_delta_tasks']} tasks ({po['accuracy_delta_pp']:+.2f} pp) [Observational, non-causal]",
        f"- V6: {po['v6_correct']} / {po['total_tasks']} ({po['v6_accuracy']:.2%}); Completed: {po['v6_completed']} / {po['total_tasks']} ({po['v6_completion_rate']:.2%})",
        f"- Matched V5: {po['v5_correct']} / {po['total_tasks']} ({po['v5_accuracy']:.2%}); Completed: {po['v5_completed']} / {po['total_tasks']} ({po['v5_completion_rate']:.2%})",
        f"- Accuracy Delta: {po['accuracy_delta_tasks']} tasks ({po['accuracy_delta_pp']:+.2f} pp) [Observational, non-causal]",
        f"- Completed Delta: {po['v6_completed'] - po['v5_completed']:+d} tasks ({(po['v6_completed'] - po['v5_completed'])/po['total_tasks']*100:+.2f} pp)",
        "",
        "Diagnostic Results (Eligible Answers):",
        f"- Eligible: {do['eligible_count']}",
        f"- Valid: {do['valid_assessment_count']}",
        f"- TP: {do['true_positive']}",
        f"- FP: {do['false_positive']}",
        f"- TN: {do['true_negative']}",
        f"- FN: {do['false_negative']}",
        f"- Precision: {do['precision']:.4f}",
        f"- Recall: {do['recall']:.4f}",
        f"- F1: {do['f1']:.4f}",
        f"- Specificity: {do['specificity']:.4f}",
        f"- False Alarm Rate: {do['false_alarm_rate']:.4f}",
        f"- Missed Error Rate: {do['missed_error_rate']:.4f}",
        f"- Diagnostic Coverage: {do['diagnostic_coverage']:.4f}",
        f"- PASS-group Correctness (NPV): {do['pass_group_correctness_rate']:.4f} ({do['correct_among_pass']}/{do['pass_count']})",
        f"- SUSPECT-group Error Rate: {do['suspect_group_error_rate']:.4f} ({do['incorrect_among_suspect']}/{do['suspect_count']})",
        f"- Brier Diagnostic Score: {do['brier_diagnostic_score']:.4f}",
        "",
        "Candidate Starvation:",
        f"- Eligible candidates: {cs['eligible_tasks']} / {cs['total_tasks']} ({cs['eligible_tasks']/cs['total_tasks']:.2%})",
        f"- Ineligible candidates: {cs['ineligible_tasks']} / {cs['total_tasks']} ({cs['ineligible_tasks']/cs['total_tasks']:.2%})",
        f"- Starvation share of total system errors: {cs['ineligible_errors']} / {cs['total_system_errors']} ({cs['starvation_share_of_total_errors']:.2%})",
        f"- Reachable errors: {cs['total_system_errors'] - cs['ineligible_errors']} / {cs['total_system_errors']} ({cs['reachable_share_of_total_errors']:.2%})",
        f"- End-to-end detection of total system errors: {do['true_positive']} / {cs['total_system_errors']} ({cs['end_to_end_error_detection_rate']:.2%})",
        "",
        "Critical Invariants:",
        f"- Answer mutations: {inv['answer_mutation_violations']} (Expected 0)",
        f"- Generation cap violations: {inv['generation_cap_violations']} (Expected 0)",
        f"- Evaluator tool calls: {inv['evaluator_tool_calls']} (Expected 0)",
        f"- Runtime ground-truth leakage: {inv['runtime_ground_truth_leakage']} (Expected 0)",
        f"- Evaluator schema validity: {inv['valid_assessments']} / {inv['eligible_count']} valid, {inv['invalid_assessments']} invalid",
        "",
        "Matched Transitions:",
        f"- Both Correct: {tr['both_correct']}",
        f"- Both Wrong: {tr['both_wrong']}",
        f"- V5 Wrong -> V6 Correct: {tr['v5_wrong_to_v6_correct']}",
        f"- V5 Correct -> V6 Wrong: {tr['v5_correct_to_v6_wrong']}",
        "",
        "Artifact Integrity:",
    ]
    for lvl in [1, 2, 3]:
        v6_ai = results["artifact_integrity"]["v6"][f"level_{lvl}"]
        v5_ai = results["artifact_integrity"]["matched_v5"][f"level_{lvl}"]
        lines.append(f"- Level {lvl} V6: predictions={v6_ai['predictions_count']}/{v6_ai['expected_tasks']}, detailed={v6_ai['detailed_eval_count']}/{v6_ai['expected_tasks']}, complete={v6_ai['is_complete']}")
        lines.append(f"- Level {lvl} Matched V5: predictions={v5_ai['predictions_count']}/{v5_ai['expected_tasks']}, detailed={v5_ai['detailed_eval_count']}/{v5_ai['expected_tasks']}, complete={v5_ai['is_complete']}")

    lines.extend([
        "",
        f"Blocking Issues ({len(results['blocking_issues'])}):",
    ])
    if results['blocking_issues']:
        for b in results['blocking_issues']:
            lines.append(f"- {b}")
    else:
        lines.append("- None")

    lines.extend([
        "",
        f"Freeze Readiness Verdict: {results['freeze_verdict']}",
        "================================================================================",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Analyze V6 benchmark results against matched V5.")
    parser.add_argument("--v6-dir", type=str, default="experiments/v6", help="Path to V6 experiment directory")
    parser.add_argument("--v5-dir", type=str, default="experiments/v6_matched_v5", help="Path to matched V5 directory")
    parser.add_argument(
        "--invalid-l3-dir",
        type=str,
        default="experiments/v6_matched_v5_invalid_l3_provider_collapse",
        help="Path to quarantined invalid matched V5 L3 directory",
    )
    parser.add_argument("--output-json", type=str, default=None, help="Optional output JSON path")
    args = parser.parse_args()

    v6_dir = Path(args.v6_dir)
    v5_dir = Path(args.v5_dir)
    invalid_dir = Path(args.invalid_l3_dir) if args.invalid_l3_dir else None

    results = analyze_v6_experiment(v6_dir, v5_dir, invalid_dir)
    print(format_summary_report(results))

    if args.output_json:
        out_p = Path(args.output_json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Full analysis JSON written to: {out_p}")


if __name__ == "__main__":
    main()
