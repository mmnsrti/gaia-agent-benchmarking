"""Tests for V7 post-benchmark analysis and verification utility."""

import json
import tempfile
import unittest
from pathlib import Path

from evaluation.analyze_v7 import (
    analyze_v7_experiment,
    compute_file_hash,
    format_summary_report,
    to_repair_record,
)


class TestV7AnalysisUtility(unittest.TestCase):
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

    def test_to_repair_record(self):
        record = {
            "task_id": "t1",
            "level": 1,
            "repair_eligible": True,
            "repair_triggered": True,
            "repair_attempted": True,
            "repair_success": True,
            "repair_action": "KEEP",
            "repair_answer_changed": False,
            "repair_error_type": None,
            "pre_repair_answer": "42",
            "post_repair_answer": "42",
            "pre_repair_correct": False,
            "correct": False,
            "self_eval_assessment": "SUSPECT",
            "self_eval_risk_type": "EVIDENCE",
            "self_eval_confidence": 0.9,
            "llm_generation_attempts": 3,
            "repair_generation_attempts": 1,
        }
        rep_rec = to_repair_record(record)
        self.assertEqual(rep_rec["task_id"], "t1")
        self.assertTrue(rep_rec["repair_eligible"])
        self.assertTrue(rep_rec["repair_triggered"])
        self.assertTrue(rep_rec["repair_attempted"])
        self.assertTrue(rep_rec["repair_success"])
        self.assertEqual(rep_rec["repair_action"], "KEEP")
        self.assertFalse(rep_rec["repair_answer_changed"])
        self.assertIsNone(rep_rec["repair_error_type"])
        self.assertEqual(rep_rec["pre_repair_answer"], "42")
        self.assertEqual(rep_rec["post_repair_answer"], "42")
        self.assertFalse(rep_rec["pre_repair_correct"])
        self.assertFalse(rep_rec["post_repair_correct"])
        self.assertEqual(rep_rec["self_eval_assessment"], "SUSPECT")
        self.assertEqual(rep_rec["self_eval_risk_type"], "EVIDENCE")
        self.assertEqual(rep_rec["self_eval_confidence"], 0.9)
        self.assertEqual(rep_rec["llm_generation_attempts"], 3)
        self.assertEqual(rep_rec["repair_generation_attempts"], 1)

    def test_synthetic_audit_run(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            v7_dir = base / "v7"
            v6_dir = base / "v6"
            v7_dir.mkdir()
            v6_dir.mkdir()

            # Level 1 mock data (3 tasks)
            # t1: TP (SUSPECT, pre-repair wrong) -> KEEP -> STABLE_FAILURE
            # t2: TN (PASS, pre-repair correct) -> NOT_TRIGGERED -> STABLE_CORRECT
            # t3: Starved / Ineligible (no candidate answer) -> NOT_TRIGGERED
            v7_preds_1 = [
                {
                    "task_id": "t1",
                    "level": 1,
                    "completion_success": True,
                    "self_eval_eligible": True,
                    "self_eval_assessment": "SUSPECT",
                    "self_eval_risk_type": "EVIDENCE",
                    "self_eval_confidence": 0.9,
                    "pre_repair_answer": "wrong_ans",
                    "post_repair_answer": "wrong_ans",
                    "repair_eligible": True,
                    "repair_triggered": True,
                    "repair_attempted": True,
                    "repair_action": "KEEP",
                    "repair_answer_changed": False,
                    "repair_error_type": None,
                    "llm_generation_attempts": 3,
                    "repair_generation_attempts": 1,
                    "repair_latency_seconds": 2.5,
                    "repair_input_tokens": 1000,
                    "repair_output_tokens": 10,
                    "repair_thinking_tokens": 200,
                    "repair_total_tokens": 1210,
                },
                {
                    "task_id": "t2",
                    "level": 1,
                    "completion_success": True,
                    "self_eval_eligible": True,
                    "self_eval_assessment": "PASS",
                    "self_eval_risk_type": "NONE",
                    "self_eval_confidence": 0.95,
                    "pre_repair_answer": "correct_ans",
                    "post_repair_answer": "correct_ans",
                    "repair_eligible": False,
                    "repair_triggered": False,
                    "repair_attempted": False,
                    "repair_action": None,
                    "repair_answer_changed": False,
                    "repair_error_type": None,
                    "llm_generation_attempts": 2,
                    "repair_generation_attempts": 0,
                },
                {
                    "task_id": "t3",
                    "level": 1,
                    "completion_success": False,
                    "self_eval_eligible": False,
                    "self_eval_assessment": None,
                    "self_eval_risk_type": None,
                    "self_eval_confidence": None,
                    "pre_repair_answer": "",
                    "post_repair_answer": "",
                    "repair_eligible": False,
                    "repair_triggered": False,
                    "repair_attempted": False,
                    "repair_action": None,
                    "repair_answer_changed": False,
                    "repair_error_type": None,
                    "llm_generation_attempts": 2,
                    "repair_generation_attempts": 0,
                },
            ]

            v7_evals_1 = [
                {
                    "task_id": "t1",
                    "level": 1,
                    "pre_repair_correct": False,
                    "correct": False,
                    "repair_transition": "STABLE_FAILURE",
                    "self_eval_assessment": "SUSPECT",
                    "self_eval_risk_type": "EVIDENCE",
                    "self_eval_confidence": 0.9,
                    "repair_action": "KEEP",
                    "repair_error_type": None,
                },
                {
                    "task_id": "t2",
                    "level": 1,
                    "pre_repair_correct": True,
                    "correct": True,
                    "repair_transition": "NOT_TRIGGERED",
                    "self_eval_assessment": "PASS",
                    "self_eval_risk_type": "NONE",
                    "self_eval_confidence": 0.95,
                    "repair_action": None,
                    "repair_error_type": None,
                },
                {
                    "task_id": "t3",
                    "level": 1,
                    "pre_repair_correct": False,
                    "correct": False,
                    "repair_transition": "NOT_TRIGGERED",
                    "self_eval_assessment": None,
                    "self_eval_risk_type": None,
                    "self_eval_confidence": None,
                    "repair_action": None,
                    "repair_error_type": None,
                },
            ]

            v6_preds_1 = [
                {"task_id": "t1", "level": 1, "completion_success": True},
                {"task_id": "t2", "level": 1, "completion_success": True},
                {"task_id": "t3", "level": 1, "completion_success": False},
            ]

            v6_evals_1 = [
                {"task_id": "t1", "level": 1, "correct": False},
                {"task_id": "t2", "level": 1, "correct": True},
                {"task_id": "t3", "level": 1, "correct": False},
            ]

            for lvl in [1, 2, 3]:
                p7 = v7_preds_1 if lvl == 1 else []
                e7 = v7_evals_1 if lvl == 1 else []
                p6 = v6_preds_1 if lvl == 1 else []
                e6 = v6_evals_1 if lvl == 1 else []

                with open(v7_dir / f"predictions_level_{lvl}.jsonl", "w", encoding="utf-8") as f:
                    for r in p7:
                        f.write(json.dumps(r) + "\n")
                with open(v7_dir / f"detailed_eval_level_{lvl}.jsonl", "w", encoding="utf-8") as f:
                    for r in e7:
                        f.write(json.dumps(r) + "\n")
                with open(v7_dir / f"summary_level_{lvl}.json", "w", encoding="utf-8") as f:
                    json.dump({"total_tasks": len(p7), "correct_tasks": 1 if lvl == 1 else 0}, f)

                with open(v6_dir / f"predictions_level_{lvl}.jsonl", "w", encoding="utf-8") as f:
                    for r in p6:
                        f.write(json.dumps(r) + "\n")
                with open(v6_dir / f"detailed_eval_level_{lvl}.jsonl", "w", encoding="utf-8") as f:
                    for r in e6:
                        f.write(json.dumps(r) + "\n")
                with open(v6_dir / f"summary_level_{lvl}.json", "w", encoding="utf-8") as f:
                    json.dump({"total_tasks": len(p6), "correct_tasks": 1 if lvl == 1 else 0}, f)

            results = analyze_v7_experiment(v7_dir, v6_dir, generate_manifests=True)
            self.assertEqual(results["total_tasks"], 3)
            self.assertEqual(results["v7_pre_correct"], 1)
            self.assertEqual(results["v7_post_correct"], 1)
            self.assertEqual(results["improvements"], 0)
            self.assertEqual(results["regressions"], 0)
            self.assertEqual(results["stable_correct"], 0)
            self.assertEqual(results["stable_failure"], 1)
            self.assertEqual(results["not_triggered"], 2)
            self.assertEqual(results["net_repair_delta"], 0)
            self.assertEqual(results["rep_eligible"], 1)
            self.assertEqual(results["rep_triggered"], 1)
            self.assertEqual(results["rep_attempted"], 1)
            self.assertEqual(results["rep_valid"], 1)
            self.assertEqual(results["rep_failed"], 0)
            self.assertEqual(results["rep_keep"], 1)
            self.assertEqual(results["rep_replace"], 0)
            self.assertEqual(results["tp"], 1)
            self.assertEqual(results["fp"], 0)
            self.assertEqual(results["tn"], 1)
            self.assertEqual(results["fn"], 0)
            self.assertEqual(results["precision"], 1.0)
            self.assertEqual(results["recall"], 1.0)
            self.assertEqual(results["f1"], 1.0)
            self.assertEqual(results["no_candidate"], 1)
            self.assertEqual(results["starved_errors"], 1)
            self.assertEqual(len(results["invariant_violations"]), 0)

            report = format_summary_report(results)
            self.assertIn("V7 POST-BENCHMARK AUDIT REPORT", report)
            self.assertIn("STABLE_FAILURE:      1", report)

    def test_canonical_v7_audit_exact_metrics(self):
        repo_root = Path(__file__).resolve().parent.parent
        v7_dir = repo_root / "experiments" / "v7"
        v6_dir = repo_root / "experiments" / "v7_matched_v6"
        inv_l1_dir = repo_root / "experiments" / "v7_matched_v6_invalid_l1_provider_collapse"
        inv_l2_dir = repo_root / "experiments" / "v7_matched_v6_invalid_l2_provider_collapse"

        if not (v7_dir / "detailed_eval_level_1.jsonl").exists():
            self.skipTest("Canonical experiment artifacts not present")

        results = analyze_v7_experiment(v7_dir, v6_dir, inv_l1_dir, inv_l2_dir, generate_manifests=False)

        # Baseline & Verification Status
        self.assertEqual(results["verdict"], "READY_TO_FREEZE_WITH_DOCUMENTED_LIMITATIONS")
        self.assertEqual(len(results["integrity_errors"]), 0)
        self.assertEqual(len(results["invariant_violations"]), 0)
        self.assertEqual(results["total_tasks"], 165)

        # Performance & Transitions
        self.assertEqual(results["v7_completed"], 80)
        self.assertEqual(results["v7_pre_correct"], 46)
        self.assertEqual(results["v7_post_correct"], 46)
        self.assertAlmostEqual(results["v7_pre_accuracy"], 46 / 165, places=4)
        self.assertAlmostEqual(results["v7_post_accuracy"], 46 / 165, places=4)
        self.assertEqual(results["improvements"], 0)
        self.assertEqual(results["regressions"], 0)
        self.assertEqual(results["stable_correct"], 4)
        self.assertEqual(results["stable_failure"], 15)
        self.assertEqual(results["not_triggered"], 146)
        self.assertEqual(results["net_repair_delta"], 0)
        self.assertAlmostEqual(results["delta_pp"], 0.0, places=4)
        self.assertAlmostEqual(results["correction_rate"], 0.0, places=4)
        self.assertAlmostEqual(results["harm_rate"], 0.0, places=4)

        # Repair Actions Breakdown
        self.assertEqual(results["rep_eligible"], 19)
        self.assertEqual(results["rep_triggered"], 19)
        self.assertEqual(results["rep_attempted"], 19)
        self.assertEqual(results["rep_valid"], 18)
        self.assertEqual(results["rep_failed"], 1)
        self.assertEqual(results["rep_keep"], 16)
        self.assertEqual(results["rep_replace"], 2)
        self.assertEqual(results["rep_changed"], 2)

        # Diagnostics (Strictly anchored to pre-repair correctness)
        self.assertEqual(results["diag_eligible"], 78)
        self.assertEqual(results["diag_valid"], 78)
        self.assertEqual(results["tp"], 15)
        self.assertEqual(results["fp"], 4)
        self.assertEqual(results["tn"], 42)
        self.assertEqual(results["fn"], 17)
        self.assertAlmostEqual(results["precision"], 15 / 19, places=4)
        self.assertAlmostEqual(results["recall"], 15 / 32, places=4)
        self.assertAlmostEqual(results["f1"], 0.5882, places=4)
        self.assertAlmostEqual(results["specificity"], 42 / 46, places=4)
        self.assertAlmostEqual(results["far"], 4 / 46, places=4)
        self.assertAlmostEqual(results["mer"], 17 / 32, places=4)
        self.assertAlmostEqual(results["brier"], 0.2581, places=4)

        # Candidate Starvation & Reach
        self.assertEqual(results["no_candidate"], 87)
        self.assertEqual(results["total_pre_errors"], 119)
        self.assertEqual(results["erroneous_triggered"], 15)
        self.assertEqual(results["starved_errors"], 87)
        self.assertAlmostEqual(results["starved_error_share"], 87 / 119, places=4)
        self.assertAlmostEqual(results["opp_coverage"], 15 / 119, places=4)
        self.assertAlmostEqual(results["candidate_bearing_coverage"], 15 / 32, places=4)
        self.assertAlmostEqual(results["e2e_corrected_fraction"], 0.0, places=4)

        # Matched V6 Comparison
        self.assertEqual(results["v6_total"], 165)
        self.assertEqual(results["v6_completed"], 85)
        self.assertEqual(results["v6_correct"], 52)
        self.assertAlmostEqual(results["v6_accuracy"], 52 / 165, places=4)
        self.assertEqual(results["cross_run_delta"], -6)
        self.assertAlmostEqual(results["cross_run_delta_pp"], -3.64, places=2)
        self.assertEqual(results["both_correct"], 36)
        self.assertEqual(results["both_wrong"], 103)
        self.assertEqual(results["v6_wrong_v7_correct"], 10)
        self.assertEqual(results["v6_correct_v7_wrong"], 16)

        # Cost Telemetry
        c = results["cost_stats"]
        self.assertEqual(c["attempt_count"], 19)
        self.assertAlmostEqual(c["mean_latency"], 4.86, places=2)
        self.assertAlmostEqual(c["median_latency"], 2.28, places=2)
        self.assertEqual(c["total_repair_tokens"], 57896)

        # Quarantined Runs Inspection
        q = results["quarantine_info"]
        self.assertIn("invalid_l1", q)
        self.assertIn("invalid_l2", q)
        self.assertEqual(q["invalid_l1"]["tasks"], 53)
        self.assertEqual(q["invalid_l2"]["tasks"], 86)

    def test_completed_tasks_reconciliation(self):
        repo_root = Path(__file__).resolve().parent.parent
        v7_dir = repo_root / "experiments" / "v7"
        v6_dir = repo_root / "experiments" / "v7_matched_v6"

        if not (v7_dir / "detailed_eval_level_1.jsonl").exists():
            self.skipTest("Canonical experiment artifacts not present")

        results = analyze_v7_experiment(v7_dir, v6_dir, generate_manifests=False)
        pl = results["per_level"]

        # V7 completed
        self.assertEqual(pl[1]["v7"]["completed"], 34)
        self.assertEqual(pl[2]["v7"]["completed"], 38)
        self.assertEqual(pl[3]["v7"]["completed"], 8)
        self.assertEqual(
            pl[1]["v7"]["completed"] + pl[2]["v7"]["completed"] + pl[3]["v7"]["completed"],
            results["v7_completed"]
        )

        # Matched V6 completed
        self.assertEqual(pl[1]["matched_v6"]["completed"], 34)
        self.assertEqual(pl[2]["matched_v6"]["completed"], 45)
        self.assertEqual(pl[3]["matched_v6"]["completed"], 6)
        self.assertEqual(
            pl[1]["matched_v6"]["completed"] + pl[2]["matched_v6"]["completed"] + pl[3]["matched_v6"]["completed"],
            results["v6_completed"]
        )

    def test_manifest_verification(self):
        repo_root = Path(__file__).resolve().parent.parent
        for d in [repo_root / "experiments" / "v7", repo_root / "experiments" / "v7_matched_v6"]:
            manifest_file = d / "ARTIFACT_MANIFEST.sha256"
            self.assertTrue(manifest_file.exists(), f"Manifest missing in {d}")
            with open(manifest_file, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            self.assertGreaterEqual(len(lines), 9)
            for line in lines:
                parts = line.split(maxsplit=1)
                self.assertEqual(len(parts), 2)
                expected_hash, fn = parts
                actual_hash = compute_file_hash(d / fn)
                self.assertEqual(actual_hash, expected_hash, f"Hash mismatch for {fn} in {d}")


if __name__ == "__main__":
    unittest.main()
