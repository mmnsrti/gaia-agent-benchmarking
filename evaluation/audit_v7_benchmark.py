"""Deterministic local sanity audit and metric calculation script for V7 benchmark."""

import json
import os
import sys

def run_audit():
    levels = [1, 2, 3]
    expected_counts = {1: 53, 2: 86, 3: 26}
    
    all_v7_detailed = []
    all_v7_preds = []
    all_v6_detailed = []
    all_v6_preds = []
    
    level_reports = {}
    
    for l in levels:
        exp = expected_counts[l]
        v7_p_path = f"experiments/v7/predictions_level_{l}.jsonl"
        v7_e_path = f"experiments/v7/detailed_eval_level_{l}.jsonl"
        v7_s_path = f"experiments/v7/summary_level_{l}.json"
        
        v6_p_path = f"experiments/v7_matched_v6/predictions_level_{l}.jsonl"
        v6_e_path = f"experiments/v7_matched_v6/detailed_eval_level_{l}.jsonl"
        v6_s_path = f"experiments/v7_matched_v6/summary_level_{l}.json"
        
        p7 = [json.loads(line) for line in open(v7_p_path, encoding="utf-8") if line.strip()]
        e7 = [json.loads(line) for line in open(v7_e_path, encoding="utf-8") if line.strip()]
        s7 = json.load(open(v7_s_path, encoding="utf-8"))
        
        p6 = [json.loads(line) for line in open(v6_p_path, encoding="utf-8") if line.strip()]
        e6 = [json.loads(line) for line in open(v6_e_path, encoding="utf-8") if line.strip()]
        s6 = json.load(open(v6_s_path, encoding="utf-8"))
        
        assert len(p7) == exp, f"V7 L{l} predictions count mismatch: {len(p7)} != {exp}"
        assert len(e7) == exp, f"V7 L{l} detailed eval count mismatch: {len(e7)} != {exp}"
        assert s7["total_tasks"] == exp, f"V7 L{l} summary total_tasks mismatch: {s7['total_tasks']} != {exp}"
        
        assert len(p6) == exp, f"Matched V6 L{l} predictions count mismatch: {len(p6)} != {exp}"
        assert len(e6) == exp, f"Matched V6 L{l} detailed eval count mismatch: {len(e6)} != {exp}"
        assert s6["total_tasks"] == exp, f"Matched V6 L{l} summary total_tasks mismatch: {s6['total_tasks']} != {exp}"
        
        p7_ids = [r["task_id"] for r in p7]
        p6_ids = [r["task_id"] for r in p6]
        assert len(set(p7_ids)) == exp, f"Duplicate IDs in V7 L{l}"
        assert len(set(p6_ids)) == exp, f"Duplicate IDs in Matched V6 L{l}"
        assert p7_ids == p6_ids, f"Task ID ordering mismatch between V7 and Matched V6 in L{l}"
        
        # Check invariants on V7 records
        for p in p7:
            llm_gen = p.get("llm_generation_attempts", 0)
            assert llm_gen <= 5, f"Generation cap violated: {llm_gen} > 5 for task {p['task_id']}"
            
            rep_gen = p.get("repair_generation_attempts", 0)
            assert rep_gen <= 1, f"Repair attempts violated: {rep_gen} > 1 for task {p['task_id']}"
            
            # PASS must never trigger repair
            if p.get("self_eval_assessment") == "PASS":
                assert not p.get("repair_attempted"), f"PASS triggered repair on task {p['task_id']}"
                assert p.get("pre_repair_answer") == p.get("post_repair_answer"), f"PASS mutated answer on task {p['task_id']}"
            
            # Empty candidate must never trigger repair
            if not p.get("pre_repair_answer"):
                assert not p.get("repair_attempted"), f"Empty answer triggered repair on task {p['task_id']}"
            
            # Repair failure safety
            if p.get("repair_error_type"):
                assert p.get("pre_repair_answer") == p.get("post_repair_answer"), f"Repair failure mutated answer on task {p['task_id']}"
                assert not p.get("repair_answer_changed"), f"repair_answer_changed=True on repair failure for task {p['task_id']}"

        all_v7_detailed.extend(e7)
        all_v7_preds.extend(p7)
        all_v6_detailed.extend(e6)
        all_v6_preds.extend(p6)
        
        level_reports[l] = {
            "v7_summary": s7,
            "v6_summary": s6,
            "v7_preds": p7,
            "v7_evals": e7,
            "v6_preds": p6,
            "v6_evals": e6,
        }
    
    print("All individual level checks and invariants PASSED.")
    
    # Compute overall raw aggregates for V7
    total_tasks = len(all_v7_preds)
    assert total_tasks == 165
    
    v7_completed = sum(1 for p in all_v7_preds if p.get("completion_success"))
    v7_pre_correct = sum(1 for e in all_v7_detailed if e.get("pre_repair_correct"))
    v7_post_correct = sum(1 for e in all_v7_detailed if e.get("correct"))
    
    improvements = sum(1 for e in all_v7_detailed if e.get("repair_transition") == "IMPROVEMENT")
    regressions = sum(1 for e in all_v7_detailed if e.get("repair_transition") == "REGRESSION")
    stable_correct = sum(1 for e in all_v7_detailed if e.get("repair_transition") == "STABLE_CORRECT")
    stable_failure = sum(1 for e in all_v7_detailed if e.get("repair_transition") == "STABLE_FAILURE")
    not_triggered = sum(1 for e in all_v7_detailed if e.get("repair_transition") == "NOT_TRIGGERED")
    
    net_repair_delta = improvements - regressions
    delta_pp = (v7_post_correct - v7_pre_correct) / total_tasks * 100
    
    pre_wrong_triggered = improvements + stable_failure
    pre_correct_triggered = regressions + stable_correct
    
    correction_rate = (improvements / pre_wrong_triggered) if pre_wrong_triggered > 0 else 0.0
    harm_rate = (regressions / pre_correct_triggered) if pre_correct_triggered > 0 else 0.0
    
    # Repair actions
    rep_eligible = sum(1 for p in all_v7_preds if p.get("repair_eligible"))
    rep_triggered = sum(1 for p in all_v7_preds if p.get("repair_triggered"))
    rep_attempted = sum(1 for p in all_v7_preds if p.get("repair_attempted"))
    rep_valid = sum(1 for p in all_v7_preds if p.get("repair_action") in ("KEEP", "REPLACE"))
    rep_failed = sum(1 for p in all_v7_preds if p.get("repair_error_type"))
    rep_keep = sum(1 for p in all_v7_preds if p.get("repair_action") == "KEEP")
    rep_replace = sum(1 for p in all_v7_preds if p.get("repair_action") == "REPLACE")
    rep_changed = sum(1 for p in all_v7_preds if p.get("repair_answer_changed"))
    
    # V6 Diagnostic metrics against PRE-REPAIR correctness
    diag_eligible = sum(1 for p in all_v7_preds if p.get("self_eval_eligible"))
    diag_valid = sum(1 for p in all_v7_preds if p.get("self_eval_assessment") in ("PASS", "SUSPECT"))
    
    tp = sum(1 for e in all_v7_detailed if e.get("self_eval_assessment") == "SUSPECT" and not e.get("pre_repair_correct"))
    fp = sum(1 for e in all_v7_detailed if e.get("self_eval_assessment") == "SUSPECT" and e.get("pre_repair_correct"))
    tn = sum(1 for e in all_v7_detailed if e.get("self_eval_assessment") == "PASS" and e.get("pre_repair_correct"))
    fn = sum(1 for e in all_v7_detailed if e.get("self_eval_assessment") == "PASS" and not e.get("pre_repair_correct"))
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    far = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    mer = fn / (fn + tp) if (fn + tp) > 0 else 0.0
    
    # Brier score against pre-repair error indicator (1 if wrong, 0 if correct)
    brier_scores = []
    for e in all_v7_detailed:
        if e.get("self_eval_assessment") in ("PASS", "SUSPECT"):
            actual_error = 1.0 if not e.get("pre_repair_correct") else 0.0
            conf = e.get("self_eval_confidence", 1.0)
            if e.get("self_eval_assessment") == "SUSPECT":
                prob_error = conf
            else:
                prob_error = 1.0 - conf
            brier_scores.append((prob_error - actual_error) ** 2)
    brier = sum(brier_scores) / len(brier_scores) if brier_scores else 0.0
    
    # Candidate starvation / reach
    no_candidate = sum(1 for p in all_v7_preds if not p.get("pre_repair_answer"))
    total_pre_errors = total_tasks - v7_pre_correct
    erroneous_triggered = tp
    opp_coverage = erroneous_triggered / total_pre_errors if total_pre_errors > 0 else 0.0
    e2e_corrected_fraction = improvements / total_pre_errors if total_pre_errors > 0 else 0.0
    
    # Matched V6 observational
    v6_total = len(all_v6_preds)
    assert v6_total == 165
    v6_correct = sum(1 for e in all_v6_detailed if e.get("correct"))
    v6_completed = sum(1 for p in all_v6_preds if p.get("completion_success"))
    
    v7_correct_map = {e["task_id"]: e.get("correct") for e in all_v7_detailed}
    v6_correct_map = {e["task_id"]: e.get("correct") for e in all_v6_detailed}
    
    both_correct = sum(1 for tid in v7_correct_map if v7_correct_map[tid] and v6_correct_map[tid])
    both_wrong = sum(1 for tid in v7_correct_map if not v7_correct_map[tid] and not v6_correct_map[tid])
    v6_wrong_v7_correct = sum(1 for tid in v7_correct_map if not v6_correct_map[tid] and v7_correct_map[tid])
    v6_correct_v7_wrong = sum(1 for tid in v7_correct_map if v6_correct_map[tid] and not v7_correct_map[tid])
    
    print("\n" + "="*80)
    print("V7 FULL BENCHMARK OVERALL RAW SUMMARY")
    print("="*80)
    print(f"Tasks: {total_tasks}")
    print(f"Completed: {v7_completed} ({v7_completed/total_tasks*100:.2f}%)")
    print(f"Pre-repair correct: {v7_pre_correct} ({v7_pre_correct/total_tasks*100:.2f}%)")
    print(f"Post-repair correct: {v7_post_correct} ({v7_post_correct/total_tasks*100:.2f}%)")
    print(f"Improvements: {improvements}")
    print(f"Regressions: {regressions}")
    print(f"Stable correct: {stable_correct}")
    print(f"Stable failure: {stable_failure}")
    print(f"Not triggered: {not_triggered}")
    print(f"Net repair delta: {net_repair_delta} tasks ({delta_pp:.2f} pp)")
    print(f"Repair correction rate: {correction_rate*100:.2f}% ({improvements}/{pre_wrong_triggered})")
    print(f"Repair harm rate: {harm_rate*100:.2f}% ({regressions}/{pre_correct_triggered})")
    print("-" * 80)
    print("V7 DIAGNOSTIC (against PRE-REPAIR correctness):")
    print(f"Eligible: {diag_eligible}, Valid: {diag_valid}")
    print(f"TP: {tp}, FP: {fp}, TN: {tn}, FN: {fn}")
    print(f"Precision: {precision:.4f}, Recall: {recall:.4f}, F1: {f1:.4f}, Specificity: {specificity:.4f}")
    print(f"FAR: {far:.4f}, MER: {mer:.4f}, Brier: {brier:.4f}")
    print("-" * 80)
    print("REPAIR ACTIONS:")
    print(f"Eligible: {rep_eligible}, Triggered: {rep_triggered}, Attempted: {rep_attempted}")
    print(f"Valid: {rep_valid}, Failed: {rep_failed}")
    print(f"KEEP: {rep_keep}, REPLACE: {rep_replace}, Answer Changed: {rep_changed}")
    print("-" * 80)
    print("CANDIDATE STARVATION / REACH:")
    print(f"No candidate: {no_candidate} ({no_candidate/total_tasks*100:.2f}%)")
    print(f"Total pre-repair errors: {total_pre_errors}")
    print(f"Erroneous triggered: {erroneous_triggered}")
    print(f"Opportunity coverage: {opp_coverage*100:.2f}% ({erroneous_triggered}/{total_pre_errors})")
    print(f"End-to-end corrected-error fraction: {e2e_corrected_fraction*100:.2f}% ({improvements}/{total_pre_errors})")
    print("-" * 80)
    print("MATCHED V6 OBSERVATIONAL COMPARISON:")
    print(f"Matched V6 Completed: {v6_completed} ({v6_completed/v6_total*100:.2f}%)")
    print(f"Matched V6 Correct: {v6_correct} ({v6_correct/v6_total*100:.2f}%)")
    print(f"V7 Post-repair Correct: {v7_post_correct} ({v7_post_correct/total_tasks*100:.2f}%)")
    print(f"Observed cross-run delta: {v7_post_correct - v6_correct} tasks ({(v7_post_correct - v6_correct)/total_tasks*100:.2f} pp)")
    print(f"Both correct: {both_correct}")
    print(f"Both wrong: {both_wrong}")
    print(f"V6 wrong -> V7 correct: {v6_wrong_v7_correct}")
    print(f"V6 correct -> V7 wrong: {v6_correct_v7_wrong}")
    print("="*80)
    
    # Print per-level breakdown
    for l in levels:
        s7 = level_reports[l]["v7_summary"]
        s6 = level_reports[l]["v6_summary"]
        print(f"\n--- LEVEL {l} ---")
        print(f"V7 tasks: {s7['total_tasks']}, completed: {s7['completed_tasks']}, correct: {s7['correct_tasks']} ({s7['accuracy']*100:.2f}%)")
        print(f"V7 pre_repair_correct: {s7.get('pre_repair_correct_tasks', s7['correct_tasks'])}, post: {s7['correct_tasks']}")
        print(f"V7 repair triggered: {s7.get('repair_triggered_count', 0)}, KEEP: {s7.get('repair_keep_count', 0)}, REPLACE: {s7.get('repair_replace_count', 0)}, Failures: {s7.get('repair_failure_count', 0)}")
        print(f"V7 transitions: +{s7.get('repair_improvements', 0)} / -{s7.get('repair_regressions', 0)} (stable correct: {s7.get('repair_stable_correct', 0)}, stable failure: {s7.get('repair_stable_failure', 0)})")
        print(f"V7 diagnostic TP/FP/TN/FN: {s7.get('self_eval_true_positive', 0)} / {s7.get('self_eval_false_positive', 0)} / {s7.get('self_eval_true_negative', 0)} / {s7.get('self_eval_false_negative', 0)}")
        print(f"Matched V6 tasks: {s6['total_tasks']}, completed: {s6['completed_tasks']}, correct: {s6['correct_tasks']} ({s6['accuracy']*100:.2f}%)")
        print(f"Search calls: V7 {s7.get('total_search_calls', 0)} (success {s7.get('search_success_rate', 0)}), V6 {s6.get('total_search_calls', 0)} (success {s6.get('search_success_rate', 0)})")

if __name__ == "__main__":
    run_audit()

