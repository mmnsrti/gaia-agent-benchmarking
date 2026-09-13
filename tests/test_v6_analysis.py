"""Tests for V6 post-benchmark analysis and verification utility."""

import json
import tempfile
import unittest
from pathlib import Path

from evaluation.analyze_v6 import (
    analyze_v6_experiment,
    compute_file_hash,
    format_summary_report,
    to_se_record,
)


class TestV6AnalysisUtility(unittest.TestCase):
    def test_compute_file_hash(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as tmp:
            tmp.write("hello world")
            tmp_path = Path(tmp.name)
        try:
            h = compute_file_hash(tmp_path)
            # sha256("hello world")
            self.assertEqual(h, "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9")
        finally:
            tmp_path.unlink()

    def test_to_se_record(self):
        record = {
            "self_eval_eligible": True,
            "self_eval_attempted": True,
            "self_eval_success": True,
            "self_eval_assessment": "PASS",
            "self_eval_risk_type": "NONE",
            "self_eval_confidence": 0.95,
            "correct": True,
        }
        se_rec = to_se_record(record)
        self.assertTrue(se_rec["eligible"])
        self.assertTrue(se_rec["attempted"])
        self.assertTrue(se_rec["success"])
        self.assertEqual(se_rec["assessment"], "PASS")
        self.assertEqual(se_rec["risk_type"], "NONE")
        self.assertEqual(se_rec["confidence"], 0.95)
        self.assertTrue(se_rec["correct"])

    def test_synthetic_audit_run(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            v6_dir = base / "v6"
            v5_dir = base / "v5"
            v6_dir.mkdir()
            v5_dir.mkdir()

            # Level 1 mock data
            v6_detailed_1 = [
                # TP: SUSPECT, incorrect
                {
                    "task_id": "t1",
                    "level": 1,
                    "correct": False,
                    "completion_success": True,
                    "self_eval_eligible": True,
                    "self_eval_attempted": True,
                    "self_eval_success": True,
                    "self_eval_assessment": "SUSPECT",
                    "self_eval_risk_type": "EVIDENCE",
                    "self_eval_confidence": 0.9,
                    "self_eval_answer_unchanged": True,
                    "llm_generation_attempts": 3,
                    "self_eval_generation_attempts": 1,
                    "attachment_required": False,
                    "router_decision": "DIRECT",
                },
                # TN: PASS, correct
                {
                    "task_id": "t2",
                    "level": 1,
                    "correct": True,
                    "completion_success": True,
                    "self_eval_eligible": True,
                    "self_eval_attempted": True,
                    "self_eval_success": True,
                    "self_eval_assessment": "PASS",
                    "self_eval_risk_type": "NONE",
                    "self_eval_confidence": 0.95,
                    "self_eval_answer_unchanged": True,
                    "llm_generation_attempts": 3,
                    "self_eval_generation_attempts": 1,
                    "attachment_required": False,
                    "router_decision": "DIRECT",
                },
                # Ineligible: missing candidate, incorrect
                {
                    "task_id": "t3",
                    "level": 1,
                    "correct": False,
                    "completion_success": False,
                    "self_eval_eligible": False,
                    "self_eval_attempted": False,
                    "self_eval_success": False,
                    "self_eval_assessment": None,
                    "self_eval_risk_type": None,
                    "self_eval_confidence": None,
                    "self_eval_answer_unchanged": True,
                    "llm_generation_attempts": 2,
                    "self_eval_generation_attempts": 0,
                    "attachment_required": False,
                    "router_decision": "DIRECT",
                },
            ]

            v5_detailed_1 = [
                {"task_id": "t1", "level": 1, "correct": False, "completion_success": True},
                {"task_id": "t2", "level": 1, "correct": False, "completion_success": True},  # v5 wrong, v6 correct
                {"task_id": "t3", "level": 1, "correct": False, "completion_success": False},
            ]

            for lvl in [1, 2, 3]:
                recs_v6 = v6_detailed_1 if lvl == 1 else []
                recs_v5 = v5_detailed_1 if lvl == 1 else []
                with open(v6_dir / f"detailed_eval_level_{lvl}.jsonl", "w", encoding="utf-8") as f:
                    for r in recs_v6:
                        f.write(json.dumps(r) + "\n")
                with open(v6_dir / f"predictions_level_{lvl}.jsonl", "w", encoding="utf-8") as f:
                    for r in recs_v6:
                        f.write(json.dumps(r) + "\n")
                with open(v6_dir / f"summary_level_{lvl}.json", "w", encoding="utf-8") as f:
                    json.dump({"accuracy": 1 / 3 if lvl == 1 else 0.0}, f)

                with open(v5_dir / f"detailed_eval_level_{lvl}.jsonl", "w", encoding="utf-8") as f:
                    for r in recs_v5:
                        f.write(json.dumps(r) + "\n")
                with open(v5_dir / f"predictions_level_{lvl}.jsonl", "w", encoding="utf-8") as f:
                    for r in recs_v5:
                        f.write(json.dumps(r) + "\n")
                with open(v5_dir / f"summary_level_{lvl}.json", "w", encoding="utf-8") as f:
                    json.dump({"accuracy": 0.0}, f)

            results = analyze_v6_experiment(v6_dir, v5_dir)
            self.assertEqual(results["performance_overall"]["v6_correct"], 1)
            self.assertEqual(results["performance_overall"]["v5_correct"], 0)
            self.assertEqual(results["diagnostics_overall"]["true_positive"], 1)
            self.assertEqual(results["diagnostics_overall"]["true_negative"], 1)
            self.assertEqual(results["diagnostics_overall"]["false_positive"], 0)
            self.assertEqual(results["diagnostics_overall"]["false_negative"], 0)
            self.assertEqual(results["invariants"]["answer_mutation_violations"], 0)
            self.assertEqual(results["invariants"]["generation_cap_violations"], 0)

            report = format_summary_report(results)
            self.assertIn("Canonical benchmark:", report)
            self.assertIn("Diagnostic Results", report)

    def test_canonical_v6_audit_exact_metrics(self):
        repo_root = Path(__file__).resolve().parent.parent
        v6_dir = repo_root / "experiments" / "v6"
        v5_dir = repo_root / "experiments" / "v6_matched_v5"
        inv_dir = repo_root / "experiments" / "v6_matched_v5_invalid_l3_provider_collapse"

        if not (v6_dir / "detailed_eval_level_1.jsonl").exists():
            self.skipTest("Canonical experiment artifacts not present")

        results = analyze_v6_experiment(v6_dir, v5_dir, inv_dir)

        # Performance
        po = results["performance_overall"]
        self.assertEqual(po["total_tasks"], 165)
        self.assertEqual(po["v6_correct"], 42)
        self.assertEqual(po["v5_correct"], 47)
        self.assertEqual(po["accuracy_delta_tasks"], -5)
        self.assertAlmostEqual(po["accuracy_delta_pp"], -3.03, places=2)

        # Transitions
        tr = results["transitions_from_matched_v5"]
        self.assertEqual(tr["both_correct"], 29)
        self.assertEqual(tr["both_wrong"], 105)
        self.assertEqual(tr["v5_wrong_to_v6_correct"], 13)
        self.assertEqual(tr["v5_correct_to_v6_wrong"], 18)

        # Diagnostics
        do = results["diagnostics_overall"]
        self.assertEqual(do["eligible_count"], 73)
        self.assertEqual(do["valid_assessment_count"], 73)
        self.assertEqual(do["failure_or_invalid_count"], 0)
        self.assertEqual(do["true_positive"], 14)
        self.assertEqual(do["false_positive"], 2)
        self.assertEqual(do["true_negative"], 40)
        self.assertEqual(do["false_negative"], 17)
        self.assertAlmostEqual(do["precision"], 0.8750, places=4)
        self.assertAlmostEqual(do["recall"], 0.4516, places=4)
        self.assertAlmostEqual(do["f1"], 0.5957, places=4)
        self.assertAlmostEqual(do["specificity"], 0.9524, places=4)
        self.assertAlmostEqual(do["false_alarm_rate"], 0.0476, places=4)
        self.assertAlmostEqual(do["missed_error_rate"], 0.5484, places=4)
        self.assertAlmostEqual(do["pass_group_correctness_rate"], 0.7018, places=4)
        self.assertAlmostEqual(do["suspect_group_error_rate"], 0.8750, places=4)
        self.assertAlmostEqual(do["brier_diagnostic_score"], 0.2490, places=4)

        # Invariants
        inv = results["invariants"]
        self.assertEqual(inv["answer_mutation_violations"], 0)
        self.assertEqual(inv["generation_cap_violations"], 0)
        self.assertEqual(inv["evaluator_tool_calls"], 0)
        self.assertEqual(inv["runtime_ground_truth_leakage"], 0)

        # Candidate Starvation
        cs = results["candidate_starvation"]
        self.assertEqual(cs["eligible_tasks"], 73)
        self.assertEqual(cs["ineligible_tasks"], 92)
        self.assertEqual(cs["total_system_errors"], 123)
        self.assertEqual(cs["ineligible_errors"], 92)
        self.assertAlmostEqual(cs["starvation_share_of_total_errors"], 0.7480, places=4)
        self.assertAlmostEqual(cs["end_to_end_error_detection_rate"], 0.1138, places=4)

        # Operational health
        oh = results["operational_health"]
        self.assertEqual(oh["v6"]["tavily_search_success_rate"], 1.0)
        self.assertEqual(oh["matched_v5"]["tavily_search_success_rate"], 1.0)

        # Invalid matched V5 L3
        inv_v5 = results["invalid_matched_v5_l3"]
        self.assertIsNotNone(inv_v5)
        self.assertEqual(inv_v5["tasks"], 26)
        self.assertEqual(inv_v5["completed"], 0)
        self.assertEqual(inv_v5["correct"], 0)
        self.assertEqual(inv_v5["router_fallbacks"], 25)

    def test_completed_tasks_reconciliation(self):
        repo_root = Path(__file__).resolve().parent.parent
        v6_dir = repo_root / "experiments" / "v6"
        v5_dir = repo_root / "experiments" / "v6_matched_v5"

        if not (v6_dir / "detailed_eval_level_1.jsonl").exists():
            self.skipTest("Canonical experiment artifacts not present")

        results = analyze_v6_experiment(v6_dir, v5_dir)
        pbl = results["performance_by_level"]
        po = results["performance_overall"]

        # 1. Per-level V6 completed sum must equal overall completed
        v6_sum_completed = sum(pbl[f"level_{lvl}"]["v6_completed"] for lvl in [1, 2, 3])
        self.assertEqual(pbl["level_1"]["v6_completed"], 35)
        self.assertEqual(pbl["level_2"]["v6_completed"], 35)
        self.assertEqual(pbl["level_3"]["v6_completed"], 4)
        self.assertEqual(v6_sum_completed, 74)
        self.assertEqual(po["v6_completed"], 74)

        # 2. Per-level Matched V5 completed sum must equal overall completed (71, NOT 84)
        v5_sum_completed = sum(pbl[f"level_{lvl}"]["v5_completed"] for lvl in [1, 2, 3])
        self.assertEqual(pbl["level_1"]["v5_completed"], 32)
        self.assertEqual(pbl["level_2"]["v5_completed"], 33)
        self.assertEqual(pbl["level_3"]["v5_completed"], 6)
        self.assertEqual(v5_sum_completed, 71)
        self.assertEqual(po["v5_completed"], 71)

        # 3. Must match canonical summary JSON files exactly
        for lvl in [1, 2, 3]:
            with open(v6_dir / f"summary_level_{lvl}.json", encoding="utf-8") as f:
                s6 = json.load(f)
            with open(v5_dir / f"summary_level_{lvl}.json", encoding="utf-8") as f:
                s5 = json.load(f)
            self.assertEqual(s6["completed_tasks"], pbl[f"level_{lvl}"]["v6_completed"])
            self.assertEqual(s5["completed_tasks"], pbl[f"level_{lvl}"]["v5_completed"])

    def test_brier_score_semantics_explicit(self):
        from evaluation.self_evaluation_metrics import calculate_self_evaluation_metrics
        # Synthetic records testing exact mapping:
        # Case 1: SUSPECT with conf 0.8, incorrect -> prob=0.8, label=1.0 -> sq=(0.8-1)^2 = 0.04
        # Case 2: SUSPECT with conf 0.8, correct   -> prob=0.8, label=0.0 -> sq=(0.8-0)^2 = 0.64
        # Case 3: PASS with conf 0.9, correct     -> prob=0.1, label=0.0 -> sq=(0.1-0)^2 = 0.01
        # Case 4: PASS with conf 0.9, incorrect   -> prob=0.1, label=1.0 -> sq=(0.1-1)^2 = 0.81
        # Mean = (0.04 + 0.64 + 0.01 + 0.81) / 4 = 1.50 / 4 = 0.3750
        records = [
            {"eligible": True, "attempted": True, "success": True, "assessment": "SUSPECT", "risk_type": "EVIDENCE", "confidence": 0.8, "correct": False},
            {"eligible": True, "attempted": True, "success": True, "assessment": "SUSPECT", "risk_type": "EVIDENCE", "confidence": 0.8, "correct": True},
            {"eligible": True, "attempted": True, "success": True, "assessment": "PASS", "risk_type": "NONE", "confidence": 0.9, "correct": True},
            {"eligible": True, "attempted": True, "success": True, "assessment": "PASS", "risk_type": "NONE", "confidence": 0.9, "correct": False},
        ]
        m = calculate_self_evaluation_metrics(records)
        self.assertAlmostEqual(m["brier_diagnostic_score"], 0.3750, places=4)

    def test_artifact_integrity_and_freeze_verdict(self):
        repo_root = Path(__file__).resolve().parent.parent
        v6_dir = repo_root / "experiments" / "v6"
        v5_dir = repo_root / "experiments" / "v6_matched_v5"

        if not (v6_dir / "detailed_eval_level_1.jsonl").exists():
            self.skipTest("Canonical experiment artifacts not present")

        results = analyze_v6_experiment(v6_dir, v5_dir)
        ai = results["artifact_integrity"]

        # V6 L1 and L2 are complete, L3 is incomplete (11 != 26)
        self.assertTrue(ai["v6"]["level_1"]["is_complete"])
        self.assertTrue(ai["v6"]["level_2"]["is_complete"])
        self.assertFalse(ai["v6"]["level_3"]["is_complete"])
        self.assertEqual(ai["v6"]["level_3"]["predictions_count"], 11)
        self.assertEqual(ai["v6"]["level_3"]["detailed_eval_count"], 26)

        # Matched V5 all levels are complete
        self.assertTrue(ai["matched_v5"]["level_1"]["is_complete"])
        self.assertTrue(ai["matched_v5"]["level_2"]["is_complete"])
        self.assertTrue(ai["matched_v5"]["level_3"]["is_complete"])

        # Blocking issue must be present and verdict must be NOT_READY_TO_FREEZE
        self.assertIn("V6 Level 3 artifact mismatch: predictions=11, detailed_eval=26, expected=26", results["blocking_issues"])
        self.assertEqual(results["freeze_verdict"], "NOT_READY_TO_FREEZE")


if __name__ == "__main__":
    unittest.main()
