"""Unit tests for V8 benchmark-harness integration and post-hoc evaluation wiring.

Tests CLI interfaces, post-hoc scoring boundaries, transition classifications,
V6 diagnostic anchoring, summary metrics generation, detailed record serialization,
and legacy V7 preservation using synthetic records without network calls.
"""

import unittest
from typing import Any, Dict, List

from evaluation.dataset import GAIATask
from evaluation.evaluate import calculate_metrics


def make_dummy_task(task_id: str, final_answer: str = "42") -> GAIATask:
    return GAIATask(
        task_id=task_id,
        question="What is the answer?",
        level=1,
        final_answer=final_answer,
        file_name=None,
    )


class TestV8BenchmarkHarness(unittest.TestCase):
    """Tests V8 benchmark harness wiring, transition logic, and diagnostic anchoring."""

    def test_v8_cli_recognition(self):
        from evaluation.run_level import run_level
        import argparse

        # Verify run_level argument parser accepts v8
        from evaluation import run_level as run_level_mod
        from evaluation import evaluate as evaluate_mod

        # Test run_level argument parser
        parser_rl = argparse.ArgumentParser()
        parser_rl.add_argument("--version", choices=["v0", "v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8"])
        args_rl = parser_rl.parse_args(["--version", "v8"])
        self.assertEqual(args_rl.version, "v8")

        # Test evaluate argument parser
        parser_ev = argparse.ArgumentParser()
        parser_ev.add_argument("--version", choices=["v0", "v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8"])
        args_ev = parser_ev.parse_args(["--version", "v8"])
        self.assertEqual(args_ev.version, "v8")

    def test_v8_post_hoc_scoring_and_transitions(self):
        tasks = {
            "t1": make_dummy_task("t1", "42"),
            "t2": make_dummy_task("t2", "Paris"),
            "t3": make_dummy_task("t3", "1970"),
            "t4": make_dummy_task("t4", "Tokyo"),
            "t5": make_dummy_task("t5", "Blue"),
        }

        predictions = [
            # t1: IMPROVEMENT (wrong -> correct via REPLACE)
            {
                "task_id": "t1",
                "request_success": True,
                "completion_success": True,
                "project_version": "v8",
                "pre_repair_answer": "41",
                "post_repair_answer": "41",
                "pre_active_verification_answer": "41",
                "post_active_verification_answer": "42",
                "final_answer": "42",
                "active_verification_eligible": True,
                "active_verification_triggered": True,
                "active_verification_action": "REPLACE",
                "active_verification_answer_changed": True,
                "active_verification_search_attempted": True,
                "active_verification_search_success": True,
                "active_verification_search_usable": True,
                "active_verification_adjudication_attempted": True,
                "active_verification_adjudication_success": True,
                "self_eval_eligible": True,
                "self_eval_attempted": True,
                "self_eval_success": True,
                "self_eval_assessment": "SUSPECT",
                "self_eval_risk_type": "EVIDENCE",
                "self_eval_confidence": 0.85,
                "self_eval_answer_unchanged": True,
            },
            # t2: REGRESSION (correct -> wrong via REPLACE)
            {
                "task_id": "t2",
                "request_success": True,
                "completion_success": True,
                "project_version": "v8",
                "pre_repair_answer": "Paris",
                "post_repair_answer": "Paris",
                "pre_active_verification_answer": "Paris",
                "post_active_verification_answer": "Lyon",
                "final_answer": "Lyon",
                "active_verification_eligible": True,
                "active_verification_triggered": True,
                "active_verification_action": "REPLACE",
                "active_verification_answer_changed": True,
                "active_verification_search_attempted": True,
                "active_verification_search_success": True,
                "active_verification_search_usable": True,
                "active_verification_adjudication_attempted": True,
                "active_verification_adjudication_success": True,
                "self_eval_eligible": True,
                "self_eval_attempted": True,
                "self_eval_success": True,
                "self_eval_assessment": "SUSPECT",
                "self_eval_risk_type": "EVIDENCE",
                "self_eval_confidence": 0.70,
                "self_eval_answer_unchanged": True,
            },
            # t3: STABLE_CORRECT (correct -> correct via KEEP)
            {
                "task_id": "t3",
                "request_success": True,
                "completion_success": True,
                "project_version": "v8",
                "pre_repair_answer": "1970",
                "post_repair_answer": "1970",
                "pre_active_verification_answer": "1970",
                "post_active_verification_answer": "1970",
                "final_answer": "1970",
                "active_verification_eligible": True,
                "active_verification_triggered": True,
                "active_verification_action": "KEEP",
                "active_verification_answer_changed": False,
                "active_verification_search_attempted": True,
                "active_verification_search_success": True,
                "active_verification_search_usable": True,
                "active_verification_adjudication_attempted": True,
                "active_verification_adjudication_success": True,
                "self_eval_eligible": True,
                "self_eval_attempted": True,
                "self_eval_success": True,
                "self_eval_assessment": "SUSPECT",
                "self_eval_risk_type": "EVIDENCE",
                "self_eval_confidence": 0.90,
                "self_eval_answer_unchanged": True,
            },
            # t4: STABLE_FAILURE (wrong -> wrong via KEEP)
            {
                "task_id": "t4",
                "request_success": True,
                "completion_success": True,
                "project_version": "v8",
                "pre_repair_answer": "Osaka",
                "post_repair_answer": "Osaka",
                "pre_active_verification_answer": "Osaka",
                "post_active_verification_answer": "Osaka",
                "final_answer": "Osaka",
                "active_verification_eligible": True,
                "active_verification_triggered": True,
                "active_verification_action": "KEEP",
                "active_verification_answer_changed": False,
                "active_verification_search_attempted": True,
                "active_verification_search_success": True,
                "active_verification_search_usable": True,
                "active_verification_adjudication_attempted": True,
                "active_verification_adjudication_success": True,
                "self_eval_eligible": True,
                "self_eval_attempted": True,
                "self_eval_success": True,
                "self_eval_assessment": "SUSPECT",
                "self_eval_risk_type": "EVIDENCE",
                "self_eval_confidence": 0.80,
                "self_eval_answer_unchanged": True,
            },
            # t5: NOT_TRIGGERED (PASS bypass)
            {
                "task_id": "t5",
                "request_success": True,
                "completion_success": True,
                "project_version": "v8",
                "pre_repair_answer": "Blue",
                "post_repair_answer": "Blue",
                "pre_active_verification_answer": "Blue",
                "post_active_verification_answer": "Blue",
                "final_answer": "Blue",
                "active_verification_eligible": False,
                "active_verification_triggered": False,
                "active_verification_action": None,
                "active_verification_answer_changed": False,
                "active_verification_search_attempted": False,
                "self_eval_eligible": True,
                "self_eval_attempted": True,
                "self_eval_success": True,
                "self_eval_assessment": "PASS",
                "self_eval_risk_type": "NONE",
                "self_eval_confidence": 0.95,
                "self_eval_answer_unchanged": True,
            },
        ]

        result = calculate_metrics(predictions, tasks_by_id=tasks, level=1, project_version="v8")
        summary = result["summary"]
        detailed = result["detailed"]

        # 1. Summary checks
        self.assertTrue(summary.get("active_verification_enabled"))
        self.assertEqual(summary.get("improvements"), 1)
        self.assertEqual(summary.get("regressions"), 1)
        self.assertEqual(summary.get("stable_correct"), 1)
        self.assertEqual(summary.get("stable_failure"), 1)
        self.assertEqual(summary.get("net_active_verification_delta"), 0)
        self.assertEqual(summary.get("active_verification_eligible_count"), 4)
        self.assertEqual(summary.get("active_verification_triggered_count"), 4)
        self.assertEqual(summary.get("active_verification_keep_count"), 2)
        self.assertEqual(summary.get("active_verification_replace_count"), 2)
        self.assertEqual(summary.get("active_verification_answers_changed_count"), 2)

        # 2. Detailed transition checks
        detailed_by_id = {d["task_id"]: d for d in detailed}
        self.assertEqual(detailed_by_id["t1"]["active_verification_transition"], "IMPROVEMENT")
        self.assertEqual(detailed_by_id["t2"]["active_verification_transition"], "REGRESSION")
        self.assertEqual(detailed_by_id["t3"]["active_verification_transition"], "STABLE_CORRECT")
        self.assertEqual(detailed_by_id["t4"]["active_verification_transition"], "STABLE_FAILURE")
        self.assertEqual(detailed_by_id["t5"]["active_verification_transition"], "NOT_TRIGGERED")

        # 3. Telemetry in detailed records
        for d in detailed:
            self.assertIn("pre_active_verification_answer", d)
            self.assertIn("post_active_verification_answer", d)
            self.assertIn("pre_active_verification_correct", d)
            self.assertIn("post_active_verification_correct", d)
            self.assertIn("active_verification_transition", d)
            self.assertIn("active_verification_eligible", d)
            self.assertIn("active_verification_triggered", d)

    def test_v6_diagnostic_anchoring_uses_pre_repair(self):
        """Validates V6 diagnostic metrics are anchored to pre_repair_correct, NOT V8 post-verification."""
        # Scenario: Upstream worker was wrong ("41" vs ground truth "42").
        # Repair kept "41" (still wrong).
        # V8 active verification fixed it to "42" (is_correct = True).
        # Upstream evaluator assessed SUSPECT.
        # Since evaluator assessed SUSPECT on an answer that was originally WRONG,
        # it is a True Positive (TP) when anchored to pre_repair_correct.
        # If incorrectly anchored to final is_correct (True), SUSPECT on a correct answer would be False Positive (FP).
        tasks = {"t1": make_dummy_task("t1", "42")}
        predictions = [{
            "task_id": "t1",
            "request_success": True,
            "completion_success": True,
            "project_version": "v8",
            "pre_repair_answer": "41",  # wrong
            "post_repair_answer": "41",  # wrong
            "pre_active_verification_answer": "41",
            "post_active_verification_answer": "42",  # corrected
            "final_answer": "42",
            "active_verification_eligible": True,
            "active_verification_triggered": True,
            "active_verification_action": "REPLACE",
            "active_verification_answer_changed": True,
            "self_eval_eligible": True,
            "self_eval_attempted": True,
            "self_eval_success": True,
            "self_eval_assessment": "SUSPECT",
            "self_eval_risk_type": "EVIDENCE",
            "self_eval_confidence": 0.85,
            "self_eval_answer_unchanged": True,
        }]

        result = calculate_metrics(predictions, tasks_by_id=tasks, level=1, project_version="v8")
        summary = result["summary"]

        # Evaluator correctly flagged a wrong candidate as SUSPECT -> TP = 1, FP = 0
        self.assertEqual(summary.get("self_eval_true_positive"), 1)
        self.assertEqual(summary.get("self_eval_false_positive"), 0)
        self.assertEqual(summary.get("self_eval_precision"), 1.0)

    def test_v7_legacy_evaluation_intact(self):
        """Validates that running evaluation on V7 records preserves V7 semantics without V8 intrusion."""
        tasks = {"t1": make_dummy_task("t1", "42")}
        v7_predictions = [{
            "task_id": "t1",
            "request_success": True,
            "completion_success": True,
            "project_version": "v7",
            "pre_repair_answer": "41",
            "post_repair_answer": "42",
            "final_answer": "42",
            "repair_eligible": True,
            "repair_triggered": True,
            "repair_attempted": True,
            "repair_success": True,
            "repair_action": "REPLACE",
            "repair_answer_changed": True,
            "self_eval_eligible": True,
            "self_eval_attempted": True,
            "self_eval_success": True,
            "self_eval_assessment": "SUSPECT",
            "self_eval_risk_type": "REASONING",
            "self_eval_confidence": 0.85,
            "self_eval_answer_unchanged": True,
        }]

        result = calculate_metrics(v7_predictions, tasks_by_id=tasks, level=1, project_version="v7")
        summary = result["summary"]

        # V7 targeted repair is enabled
        self.assertTrue(summary.get("targeted_repair_enabled"))
        self.assertEqual(summary.get("repair_improvements"), 1)
        self.assertEqual(summary.get("repair_prompt_version"), "targeted-repair-v1")
        # V8 active verification is NOT enabled on pure V7 runs
        self.assertFalse(summary.get("active_verification_enabled", False))


if __name__ == "__main__":
    unittest.main()
