"""V7 Post-Benchmark Analysis and Verification Utility.

Computes comprehensive within-run targeted repair metrics, diagnostic calibration,
candidate starvation / repair reach, invariant verification, matched-control observational
comparisons, and operational-health audits from canonical GAIA evaluation artifacts
without calling external models, search tools, Python execution sandbox, or scorers.
"""

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.self_evaluation_metrics import calculate_self_evaluation_metrics
from evaluation.targeted_repair_metrics import calculate_targeted_repair_metrics


EXPECTED_COUNTS = {1: 53, 2: 86, 3: 26}
TOTAL_TASKS = 165


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


def write_manifest(directory: Path, filenames: List[str]) -> Path:
    """Writes deterministic SHA-256 manifest for specified files in directory."""
    manifest_path = directory / "ARTIFACT_MANIFEST.sha256"
    lines = []
    for fn in sorted(filenames):
        fp = directory / fn
        if fp.exists():
            h = compute_file_hash(fp)
            lines.append(f"{h}  {fn}\n")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return manifest_path


def to_repair_record(r: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts targeted repair fields into standard record format."""
    return {
        "task_id": r.get("task_id"),
        "level": r.get("level"),
        "repair_eligible": bool(r.get("repair_eligible")),
        "repair_triggered": bool(r.get("repair_triggered")),
        "repair_attempted": bool(r.get("repair_attempted")),
        "repair_success": r.get("repair_success"),
        "repair_action": r.get("repair_action"),
        "repair_answer_changed": bool(r.get("repair_answer_changed")),
        "repair_error_type": r.get("repair_error_type"),
        "pre_repair_answer": r.get("pre_repair_answer"),
        "post_repair_answer": r.get("post_repair_answer"),
        "pre_repair_correct": bool(r.get("pre_repair_correct")),
        "post_repair_correct": bool(r.get("correct")),
        "self_eval_assessment": r.get("self_eval_assessment"),
        "self_eval_risk_type": r.get("self_eval_risk_type"),
        "self_eval_confidence": r.get("self_eval_confidence"),
        "llm_generation_attempts": r.get("llm_generation_attempts", 0),
        "repair_generation_attempts": r.get("repair_generation_attempts", 0),
    }


def analyze_v7_experiment(
    v7_dir: Path,
    matched_v6_dir: Path,
    invalid_l1_dir: Optional[Path] = None,
    invalid_l2_dir: Optional[Path] = None,
    generate_manifests: bool = True,
) -> Dict[str, Any]:
    """Runs complete deterministic audit and analysis on V7 and matched V6 artifacts."""
    # 1. Load canonical V7 records
    v7_preds_by_lvl = {}
    v7_evals_by_lvl = {}
    v7_summary_by_lvl = {}
    
    v6_preds_by_lvl = {}
    v6_evals_by_lvl = {}
    v6_summary_by_lvl = {}
    
    all_v7_preds = []
    all_v7_evals = []
    all_v6_preds = []
    all_v6_evals = []
    
    integrity_errors = []
    invariant_violations = []

    for lvl in [1, 2, 3]:
        exp = EXPECTED_COUNTS[lvl]
        p_path = v7_dir / f"predictions_level_{lvl}.jsonl"
        e_path = v7_dir / f"detailed_eval_level_{lvl}.jsonl"
        s_path = v7_dir / f"summary_level_{lvl}.json"
        
        preds = load_jsonl(p_path)
        evals = load_jsonl(e_path)
        summary = load_json(s_path)
        
        if len(preds) != exp:
            integrity_errors.append(f"V7 L{lvl} predictions count {len(preds)} != {exp}")
        if len(evals) != exp:
            integrity_errors.append(f"V7 L{lvl} detailed eval count {len(evals)} != {exp}")
        if summary.get("total_tasks") != exp:
            integrity_errors.append(f"V7 L{lvl} summary count {summary.get('total_tasks')} != {exp}")
            
        v7_preds_by_lvl[lvl] = preds
        v7_evals_by_lvl[lvl] = evals
        v7_summary_by_lvl[lvl] = summary
        all_v7_preds.extend(preds)
        all_v7_evals.extend(evals)
        
        # Matched V6
        p6_path = matched_v6_dir / f"predictions_level_{lvl}.jsonl"
        e6_path = matched_v6_dir / f"detailed_eval_level_{lvl}.jsonl"
        s6_path = matched_v6_dir / f"summary_level_{lvl}.json"
        
        p6 = load_jsonl(p6_path)
        e6 = load_jsonl(e6_path)
        s6 = load_json(s6_path)
        
        if len(p6) != exp:
            integrity_errors.append(f"Matched V6 L{lvl} predictions count {len(p6)} != {exp}")
        if len(e6) != exp:
            integrity_errors.append(f"Matched V6 L{lvl} detailed eval count {len(e6)} != {exp}")
        if s6.get("total_tasks") != exp:
            integrity_errors.append(f"Matched V6 L{lvl} summary count {s6.get('total_tasks')} != {exp}")
            
        v6_preds_by_lvl[lvl] = p6
        v6_evals_by_lvl[lvl] = e6
        v6_summary_by_lvl[lvl] = s6
        all_v6_preds.extend(p6)
        all_v6_evals.extend(e6)
        
        # Task ID equality
        p7_ids = [r["task_id"] for r in preds]
        p6_ids = [r["task_id"] for r in p6]
        if len(set(p7_ids)) != exp:
            integrity_errors.append(f"V7 L{lvl} has duplicate task IDs")
        if len(set(p6_ids)) != exp:
            integrity_errors.append(f"Matched V6 L{lvl} has duplicate task IDs")
        if p7_ids != p6_ids:
            integrity_errors.append(f"Task ID ordering mismatch between V7 and Matched V6 in L{lvl}")

    # Invariants audit across all 165 V7 tasks
    pass_repair_violations = 0
    empty_repair_violations = 0
    invalid_eval_repair_violations = 0
    suspect_bypass_violations = 0
    multi_repair_violations = 0
    generation_cap_violations = 0
    tool_search_violations = 0
    tool_python_violations = 0
    tool_file_violations = 0
    failed_repair_mutations = 0

    for p in all_v7_preds:
        tid = p.get("task_id")
        llm_gen = p.get("llm_generation_attempts", 0)
        if llm_gen > 5:
            generation_cap_violations += 1
            invariant_violations.append(f"Task {tid}: llm_generation_attempts={llm_gen} > 5")
            
        rep_gen = p.get("repair_generation_attempts", 0)
        if rep_gen > 1:
            multi_repair_violations += 1
            invariant_violations.append(f"Task {tid}: repair_generation_attempts={rep_gen} > 1")
            
        se_assess = p.get("self_eval_assessment")
        rep_att = p.get("repair_attempted")
        pre_ans = p.get("pre_repair_answer")
        post_ans = p.get("post_repair_answer")
        
        if se_assess == "PASS":
            if rep_att:
                pass_repair_violations += 1
                invariant_violations.append(f"Task {tid}: PASS triggered repair attempt")
            if pre_ans != post_ans:
                pass_repair_violations += 1
                invariant_violations.append(f"Task {tid}: PASS mutated answer")
                
        if not pre_ans and rep_att:
            empty_repair_violations += 1
            invariant_violations.append(f"Task {tid}: empty candidate triggered repair attempt")
            
        if se_assess not in ("PASS", "SUSPECT", None) and rep_att:
            invalid_eval_repair_violations += 1
            invariant_violations.append(f"Task {tid}: invalid eval assessment {se_assess} triggered repair")
            
        if pre_ans and se_assess == "SUSPECT" and not p.get("repair_triggered"):
            suspect_bypass_violations += 1
            invariant_violations.append(f"Task {tid}: valid SUSPECT bypassed repair trigger")
            
        if p.get("repair_error_type"):
            if pre_ans != post_ans or p.get("repair_answer_changed"):
                failed_repair_mutations += 1
                invariant_violations.append(f"Task {tid}: repair failure mutated answer")

    # 2. Manifests
    manifest_files = [
        "predictions_level_1.jsonl", "predictions_level_2.jsonl", "predictions_level_3.jsonl",
        "detailed_eval_level_1.jsonl", "detailed_eval_level_2.jsonl", "detailed_eval_level_3.jsonl",
        "summary_level_1.json", "summary_level_2.json", "summary_level_3.json",
    ]
    if generate_manifests and v7_dir.exists():
        write_manifest(v7_dir, manifest_files)
    if generate_manifests and matched_v6_dir.exists():
        write_manifest(matched_v6_dir, manifest_files)

    # 3. Compute Within-Run Targeted Repair Metrics (Overall & Per-Level)
    total_tasks = len(all_v7_preds)
    v7_completed = sum(1 for p in all_v7_preds if p.get("completion_success"))
    v7_pre_correct = sum(1 for e in all_v7_evals if e.get("pre_repair_correct"))
    v7_post_correct = sum(1 for e in all_v7_evals if e.get("correct"))
    
    improvements = sum(1 for e in all_v7_evals if e.get("repair_transition") == "IMPROVEMENT")
    regressions = sum(1 for e in all_v7_evals if e.get("repair_transition") == "REGRESSION")
    stable_correct = sum(1 for e in all_v7_evals if e.get("repair_transition") == "STABLE_CORRECT")
    stable_failure = sum(1 for e in all_v7_evals if e.get("repair_transition") == "STABLE_FAILURE")
    not_triggered = sum(1 for e in all_v7_evals if e.get("repair_transition") == "NOT_TRIGGERED")
    
    net_repair_delta = improvements - regressions
    delta_pp = ((v7_post_correct - v7_pre_correct) / total_tasks * 100) if total_tasks else 0.0
    
    pre_wrong_triggered = improvements + stable_failure
    pre_correct_triggered = regressions + stable_correct
    
    correction_rate = (improvements / pre_wrong_triggered) if pre_wrong_triggered > 0 else 0.0
    harm_rate = (regressions / pre_correct_triggered) if pre_correct_triggered > 0 else 0.0
    
    # Repair actions breakdown
    rep_eligible = sum(1 for p in all_v7_preds if p.get("repair_eligible"))
    rep_triggered = sum(1 for p in all_v7_preds if p.get("repair_triggered"))
    rep_attempted = sum(1 for p in all_v7_preds if p.get("repair_attempted"))
    rep_valid = sum(1 for p in all_v7_preds if p.get("repair_action") in ("KEEP", "REPLACE"))
    rep_failed = sum(1 for p in all_v7_preds if p.get("repair_error_type"))
    rep_keep = sum(1 for p in all_v7_preds if p.get("repair_action") == "KEEP")
    rep_replace = sum(1 for p in all_v7_preds if p.get("repair_action") == "REPLACE")
    rep_changed = sum(1 for p in all_v7_preds if p.get("repair_answer_changed"))
    
    # 4. Diagnostic Metrics Strictly Anchored to PRE-REPAIR Correctness
    diag_eligible = sum(1 for p in all_v7_preds if p.get("self_eval_eligible"))
    diag_valid = sum(1 for p in all_v7_preds if p.get("self_eval_assessment") in ("PASS", "SUSPECT"))
    
    tp = sum(1 for e in all_v7_evals if e.get("self_eval_assessment") == "SUSPECT" and not e.get("pre_repair_correct"))
    fp = sum(1 for e in all_v7_evals if e.get("self_eval_assessment") == "SUSPECT" and e.get("pre_repair_correct"))
    tn = sum(1 for e in all_v7_evals if e.get("self_eval_assessment") == "PASS" and e.get("pre_repair_correct"))
    fn = sum(1 for e in all_v7_evals if e.get("self_eval_assessment") == "PASS" and not e.get("pre_repair_correct"))
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    far = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    mer = fn / (fn + tp) if (fn + tp) > 0 else 0.0
    
    brier_scores = []
    for e in all_v7_evals:
        if e.get("self_eval_assessment") in ("PASS", "SUSPECT"):
            actual_error = 1.0 if not e.get("pre_repair_correct") else 0.0
            conf = e.get("self_eval_confidence", 1.0)
            prob_error = conf if e.get("self_eval_assessment") == "SUSPECT" else (1.0 - conf)
            brier_scores.append((prob_error - actual_error) ** 2)
    brier = (sum(brier_scores) / len(brier_scores)) if brier_scores else 0.0

    # 5. Risk-Type Breakdown & Outcomes
    suspects = [e for e in all_v7_evals if e.get("self_eval_assessment") == "SUSPECT"]
    risk_counts = defaultdict(int)
    risk_outcomes = {}
    for s in suspects:
        rt = s.get("self_eval_risk_type") or "UNKNOWN"
        risk_counts[rt] += 1
        
    for rt in sorted(risk_counts.keys()):
        subset = [s for s in suspects if (s.get("self_eval_risk_type") or "UNKNOWN") == rt]
        risk_outcomes[rt] = {
            "count": len(subset),
            "keep": sum(1 for s in subset if s.get("repair_action") == "KEEP"),
            "replace": sum(1 for s in subset if s.get("repair_action") == "REPLACE"),
            "failure": sum(1 for s in subset if s.get("repair_error_type")),
            "improvements": sum(1 for s in subset if s.get("repair_transition") == "IMPROVEMENT"),
            "regressions": sum(1 for s in subset if s.get("repair_transition") == "REGRESSION"),
            "stable_correct": sum(1 for s in subset if s.get("repair_transition") == "STABLE_CORRECT"),
            "stable_failure": sum(1 for s in subset if s.get("repair_transition") == "STABLE_FAILURE"),
            "net_delta": 0,
        }

    # 6. Candidate Starvation & Reach
    no_candidate = sum(1 for p in all_v7_preds if not p.get("pre_repair_answer"))
    total_pre_errors = total_tasks - v7_pre_correct
    erroneous_triggered = tp
    starved_errors = no_candidate
    starved_error_share = (starved_errors / total_pre_errors) if total_pre_errors > 0 else 0.0
    opp_coverage = (erroneous_triggered / total_pre_errors) if total_pre_errors > 0 else 0.0
    candidate_bearing_coverage = (erroneous_triggered / (tp + fn)) if (tp + fn) > 0 else 0.0
    e2e_corrected_fraction = (improvements / total_pre_errors) if total_pre_errors > 0 else 0.0

    # 7. Matched V6 Observational Comparison
    v6_total = len(all_v6_preds)
    v6_completed = sum(1 for p in all_v6_preds if p.get("completion_success"))
    v6_correct = sum(1 for e in all_v6_evals if e.get("correct"))
    
    v7_correct_map = {e["task_id"]: bool(e.get("correct")) for e in all_v7_evals}
    v6_correct_map = {e["task_id"]: bool(e.get("correct")) for e in all_v6_evals}
    
    both_correct = sum(1 for tid in v7_correct_map if v7_correct_map[tid] and v6_correct_map[tid])
    both_wrong = sum(1 for tid in v7_correct_map if not v7_correct_map[tid] and not v6_correct_map[tid])
    v6_wrong_v7_correct = sum(1 for tid in v7_correct_map if not v6_correct_map[tid] and v7_correct_map[tid])
    v6_correct_v7_wrong = sum(1 for tid in v7_correct_map if v6_correct_map[tid] and not v7_correct_map[tid])

    # 8. Quarantined Runs Inspection
    quarantine_info = {}
    for q_label, q_dir in [("invalid_l1", invalid_l1_dir), ("invalid_l2", invalid_l2_dir)]:
        if q_dir and q_dir.exists():
            qp = load_jsonl(q_dir / "predictions_level_1.jsonl" if "l1" in q_label else q_dir / "predictions_level_2.jsonl")
            qs = load_json(q_dir / "summary_level_1.json" if "l1" in q_label else q_dir / "summary_level_2.json")
            rf = sum(1 for r in qp if r.get("router_fallback"))
            pe = sum(1 for r in qp if r.get("worker_error_type") == "provider_api_error")
            quarantine_info[q_label] = {
                "path": str(q_dir),
                "tasks": len(qp),
                "router_fallbacks": rf,
                "provider_errors": pe,
                "summary": qs,
            }

    # 9. Repair Cost Telemetry (Latency & Tokens)
    attempted_reps = [p for p in all_v7_preds if p.get("repair_attempted")]
    rep_latencies = [p["repair_latency_seconds"] for p in attempted_reps if p.get("repair_latency_seconds") is not None]
    rep_in_tokens = [p["repair_input_tokens"] for p in attempted_reps if p.get("repair_input_tokens") is not None]
    rep_out_tokens = [p["repair_output_tokens"] for p in attempted_reps if p.get("repair_output_tokens") is not None]
    rep_th_tokens = [p["repair_thinking_tokens"] for p in attempted_reps if p.get("repair_thinking_tokens") is not None]
    rep_tot_tokens = [p["repair_total_tokens"] for p in attempted_reps if p.get("repair_total_tokens") is not None]

    cost_stats = {
        "attempt_count": len(attempted_reps),
        "mean_latency": statistics.mean(rep_latencies) if rep_latencies else 0.0,
        "median_latency": statistics.median(rep_latencies) if rep_latencies else 0.0,
        "min_latency": min(rep_latencies) if rep_latencies else 0.0,
        "max_latency": max(rep_latencies) if rep_latencies else 0.0,
        "mean_input_tokens": statistics.mean(rep_in_tokens) if rep_in_tokens else 0.0,
        "mean_output_tokens": statistics.mean(rep_out_tokens) if rep_out_tokens else 0.0,
        "mean_thinking_tokens": statistics.mean(rep_th_tokens) if rep_th_tokens else 0.0,
        "mean_total_tokens": statistics.mean(rep_tot_tokens) if rep_tot_tokens else 0.0,
        "total_repair_tokens": sum(rep_tot_tokens),
    }

    # 10. Per-Level Results Summary
    per_level = {}
    for lvl in [1, 2, 3]:
        s7 = v7_summary_by_lvl[lvl]
        s6 = v6_summary_by_lvl[lvl]
        e7 = v7_evals_by_lvl[lvl]
        per_level[lvl] = {
            "v7": {
                "tasks": len(e7),
                "completed": s7.get("completed_tasks", 0),
                "pre_correct": s7.get("pre_repair_correct_tasks", s7.get("correct_tasks", 0)),
                "post_correct": s7.get("correct_tasks", 0),
                "pre_accuracy": s7.get("pre_repair_accuracy", s7.get("accuracy", 0.0)),
                "post_accuracy": s7.get("accuracy", 0.0),
                "repair_eligible": s7.get("repair_eligible_count", 0),
                "repair_triggered": s7.get("repair_triggered_count", 0),
                "repair_attempted": s7.get("repair_attempted_count", 0),
                "repair_valid": s7.get("repair_valid_count", 0),
                "repair_failed": s7.get("repair_failure_count", 0),
                "keep": s7.get("repair_keep_count", 0),
                "replace": s7.get("repair_replace_count", 0),
                "improvements": s7.get("repair_improvements", 0),
                "regressions": s7.get("repair_regressions", 0),
                "stable_correct": s7.get("repair_stable_correct", 0),
                "stable_failure": s7.get("repair_stable_failure", 0),
                "net_delta": s7.get("net_repair_correct_delta", 0),
                "tp": s7.get("self_eval_true_positive", 0),
                "fp": s7.get("self_eval_false_positive", 0),
                "tn": s7.get("self_eval_true_negative", 0),
                "fn": s7.get("self_eval_false_negative", 0),
            },
            "matched_v6": {
                "tasks": len(v6_evals_by_lvl[lvl]),
                "completed": s6.get("completed_tasks", 0),
                "correct": s6.get("correct_tasks", 0),
                "accuracy": s6.get("accuracy", 0.0),
            }
        }

    # 11. Freeze-readiness verdict determination
    is_ready = (
        len(integrity_errors) == 0
        and len(invariant_violations) == 0
        and total_tasks == TOTAL_TASKS
        and v6_total == TOTAL_TASKS
    )
    verdict = "READY_TO_FREEZE_WITH_DOCUMENTED_LIMITATIONS" if is_ready else "NOT_READY_TO_FREEZE"

    return {
        "verdict": verdict,
        "integrity_errors": integrity_errors,
        "invariant_violations": invariant_violations,
        "total_tasks": total_tasks,
        "v7_completed": v7_completed,
        "v7_pre_correct": v7_pre_correct,
        "v7_post_correct": v7_post_correct,
        "v7_pre_accuracy": (v7_pre_correct / total_tasks) if total_tasks else 0.0,
        "v7_post_accuracy": (v7_post_correct / total_tasks) if total_tasks else 0.0,
        "improvements": improvements,
        "regressions": regressions,
        "stable_correct": stable_correct,
        "stable_failure": stable_failure,
        "not_triggered": not_triggered,
        "net_repair_delta": net_repair_delta,
        "delta_pp": delta_pp,
        "pre_wrong_triggered": pre_wrong_triggered,
        "pre_correct_triggered": pre_correct_triggered,
        "correction_rate": correction_rate,
        "harm_rate": harm_rate,
        "rep_eligible": rep_eligible,
        "rep_triggered": rep_triggered,
        "rep_attempted": rep_attempted,
        "rep_valid": rep_valid,
        "rep_failed": rep_failed,
        "rep_keep": rep_keep,
        "rep_replace": rep_replace,
        "rep_changed": rep_changed,
        "diag_eligible": diag_eligible,
        "diag_valid": diag_valid,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "specificity": specificity,
        "far": far,
        "mer": mer,
        "brier": brier,
        "risk_counts": dict(risk_counts),
        "risk_outcomes": risk_outcomes,
        "no_candidate": no_candidate,
        "total_pre_errors": total_pre_errors,
        "erroneous_triggered": erroneous_triggered,
        "starved_errors": starved_errors,
        "starved_error_share": starved_error_share,
        "opp_coverage": opp_coverage,
        "candidate_bearing_coverage": candidate_bearing_coverage,
        "e2e_corrected_fraction": e2e_corrected_fraction,
        "v6_total": v6_total,
        "v6_completed": v6_completed,
        "v6_correct": v6_correct,
        "v6_accuracy": (v6_correct / v6_total) if v6_total else 0.0,
        "cross_run_delta": v7_post_correct - v6_correct,
        "cross_run_delta_pp": ((v7_post_correct - v6_correct) / total_tasks * 100) if total_tasks else 0.0,
        "both_correct": both_correct,
        "both_wrong": both_wrong,
        "v6_wrong_v7_correct": v6_wrong_v7_correct,
        "v6_correct_v7_wrong": v6_correct_v7_wrong,
        "quarantine_info": quarantine_info,
        "cost_stats": cost_stats,
        "per_level": per_level,
    }


def format_summary_report(results: Dict[str, Any]) -> str:
    """Formats the audit analysis results into the standard report markdown."""
    c = results["cost_stats"]
    q = results.get("quarantine_info", {})
    lines = [
        "=" * 80,
        "V7 POST-BENCHMARK AUDIT REPORT",
        "=" * 80,
        f"Experimental version: V7 — SUSPECT-Triggered Targeted Repair",
        f"Freeze Readiness Verdict: {results['verdict']}",
        f"Total Tasks: {results['total_tasks']}",
        f"Integrity Errors: {len(results['integrity_errors'])}",
        f"Invariant Violations: {len(results['invariant_violations'])}",
        "-" * 80,
        "CANONICAL V7 WITHIN-RUN REPAIR EFFECT:",
        f"  Pre-repair correct:  {results['v7_pre_correct']} / {results['total_tasks']} ({results['v7_pre_accuracy']*100:.2f}%)",
        f"  Post-repair correct: {results['v7_post_correct']} / {results['total_tasks']} ({results['v7_post_accuracy']*100:.2f}%)",
        f"  IMPROVEMENTS:        {results['improvements']}",
        f"  REGRESSIONS:         {results['regressions']}",
        f"  STABLE_CORRECT:      {results['stable_correct']}",
        f"  STABLE_FAILURE:      {results['stable_failure']}",
        f"  NOT_TRIGGERED:       {results['not_triggered']}",
        f"  Net repair delta:    {results['net_repair_delta']} tasks ({results['delta_pp']:.2f} pp)",
        f"  Correction rate:     {results['correction_rate']*100:.2f}% ({results['improvements']}/{results['pre_wrong_triggered']})",
        f"  Harm rate:           {results['harm_rate']*100:.2f}% ({results['regressions']}/{results['pre_correct_triggered']})",
        "-" * 80,
        "REPAIR ACTIONS BREAKDOWN:",
        f"  Eligible: {results['rep_eligible']} | Triggered: {results['rep_triggered']} | Attempted: {results['rep_attempted']}",
        f"  Valid: {results['rep_valid']} | Failed: {results['rep_failed']}",
        f"  KEEP: {results['rep_keep']} | REPLACE: {results['rep_replace']} | Answers Changed: {results['rep_changed']}",
        "-" * 80,
        "V6 DIAGNOSTIC (Strictly anchored to PRE-REPAIR correctness):",
        f"  Eligible: {results['diag_eligible']} | Valid: {results['diag_valid']}",
        f"  TP: {results['tp']} | FP: {results['fp']} | TN: {results['tn']} | FN: {results['fn']}",
        f"  Precision:   {results['precision']:.4f} ({results['precision']*100:.2f}%)",
        f"  Recall:      {results['recall']:.4f} ({results['recall']*100:.2f}%)",
        f"  F1 Score:    {results['f1']:.4f}",
        f"  Specificity: {results['specificity']:.4f} ({results['specificity']*100:.2f}%)",
        f"  FAR:         {results['far']:.4f}",
        f"  MER:         {results['mer']:.4f}",
        f"  Brier Score: {results['brier']:.4f}",
        "-" * 80,
        "CANDIDATE STARVATION / REPAIR REACH:",
        f"  No-candidate tasks:                 {results['no_candidate']} ({results['no_candidate']/results['total_tasks']*100:.2f}%)",
        f"  Total pre-repair errors:            {results['total_pre_errors']}",
        f"  Starved errors (unreachable):       {results['starved_errors']} ({results['starved_error_share']*100:.2f}%)",
        f"  Erroneous answers triggered:        {results['erroneous_triggered']}",
        f"  Opportunity coverage (all errors):  {results['opp_coverage']*100:.2f}% ({results['erroneous_triggered']}/{results['total_pre_errors']})",
        f"  Opportunity coverage (reach errors):{results['candidate_bearing_coverage']*100:.2f}% ({results['erroneous_triggered']}/{results['tp']+results['fn']})",
        f"  End-to-end corrected fraction:      {results['e2e_corrected_fraction']*100:.2f}%",
        "-" * 80,
        "MATCHED V6 OBSERVATIONAL COMPARISON:",
        f"  Matched V6 Completed:   {results['v6_completed']} ({results['v6_completed']/results['v6_total']*100:.2f}%)",
        f"  Matched V6 Correct:     {results['v6_correct']} ({results['v6_accuracy']*100:.2f}%)",
        f"  V7 Post-repair Correct: {results['v7_post_correct']} ({results['v7_post_accuracy']*100:.2f}%)",
        f"  Cross-run delta:        {results['cross_run_delta']} tasks ({results['cross_run_delta_pp']:.2f} pp)",
        f"  Both correct:           {results['both_correct']}",
        f"  Both wrong:             {results['both_wrong']}",
        f"  V6 wrong -> V7 correct: {results['v6_wrong_v7_correct']}",
        f"  V6 correct -> V7 wrong: {results['v6_correct_v7_wrong']}",
        "-" * 80,
        "REPAIR LATENCY & TOKEN TELEMETRY:",
        f"  Attempted Repairs: {c['attempt_count']}",
        f"  Mean Latency:      {c['mean_latency']:.2f}s (Median: {c['median_latency']:.2f}s, Min: {c['min_latency']:.2f}s, Max: {c['max_latency']:.2f}s)",
        f"  Mean Tokens:       Total: {c['mean_total_tokens']:.1f} | Input: {c['mean_input_tokens']:.1f} | Output: {c['mean_output_tokens']:.1f} | Thinking: {c['mean_thinking_tokens']:.1f}",
        f"  Sum Total Tokens:  {c['total_repair_tokens']}",
        "=" * 80,
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V7 post-benchmark audit utility")
    parser.add_argument("--v7-dir", type=str, default="experiments/v7", help="Path to V7 artifacts directory")
    parser.add_argument("--matched-v6-dir", type=str, default="experiments/v7_matched_v6", help="Path to matched V6 directory")
    parser.add_argument("--invalid-l1-dir", type=str, default="experiments/v7_matched_v6_invalid_l1_provider_collapse", help="Path to invalid L1 directory")
    parser.add_argument("--invalid-l2-dir", type=str, default="experiments/v7_matched_v6_invalid_l2_provider_collapse", help="Path to invalid L2 directory")
    parser.add_argument("--no-manifest", action="store_true", help="Skip SHA-256 manifest generation")
    args = parser.parse_args()
    
    res = analyze_v7_experiment(
        v7_dir=Path(args.v7_dir),
        matched_v6_dir=Path(args.matched_v6_dir),
        invalid_l1_dir=Path(args.invalid_l1_dir),
        invalid_l2_dir=Path(args.invalid_l2_dir),
        generate_manifests=not args.no_manifest,
    )
    
    print(format_summary_report(res))

