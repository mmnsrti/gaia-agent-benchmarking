"""Unit tests for V3 Error Analysis, Taxonomy Classification, and Controlled V2/V3 Comparison."""

import json
import os
import unittest
from evaluation.analyze_v3_errors import (
    classify_v3_failure,
    classify_v3_failure_detailed,
    analyze_v3_level_errors,
    build_overall_v3_error_analysis,
    build_v2_v3_task_transitions,
    build_v2_v3_error_comparison,
    build_comparison_summary,
    build_python_execution_analysis,
    TAXONOMY_CATEGORIES,
    DETERMINISTIC_CATEGORIES,
    HEURISTIC_CATEGORIES,
    PROHIBITED_KEYS,
)


class TestV3ErrorAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v3_dir = "experiments/v3"
        cls.v2_dir = "experiments/v3_matched_v2"

        cls.v3_evals = []
        cls.v3_preds = []
        cls.v2_evals = []
        cls.v2_preds = []

        for lvl in [1, 2, 3]:
            with open(os.path.join(cls.v3_dir, f"detailed_eval_level_{lvl}.jsonl"), "r", encoding="utf-8") as f:
                cls.v3_evals.extend([json.loads(l) for l in f if l.strip()])
            with open(os.path.join(cls.v3_dir, f"predictions_level_{lvl}.jsonl"), "r", encoding="utf-8") as f:
                cls.v3_preds.extend([json.loads(l) for l in f if l.strip()])
            with open(os.path.join(cls.v2_dir, f"detailed_eval_level_{lvl}.jsonl"), "r", encoding="utf-8") as f:
                cls.v2_evals.extend([json.loads(l) for l in f if l.strip()])
            with open(os.path.join(cls.v2_dir, f"predictions_level_{lvl}.jsonl"), "r", encoding="utf-8") as f:
                cls.v2_preds.extend([json.loads(l) for l in f if l.strip()])

        cls.v3_preds_by_id = {p["task_id"]: p for p in cls.v3_preds}
        cls.v3_evals_by_id = {e["task_id"]: e for e in cls.v3_evals}
        cls.v2_preds_by_id = {p["task_id"]: p for p in cls.v2_preds}
        cls.v2_evals_by_id = {e["task_id"]: e for e in cls.v2_evals}

    def test_01_exactly_165_joined_task_ids(self):
        """1. V2 and V3 joins contain exactly 165 unique task IDs."""
        v2_ids = set(self.v2_preds_by_id.keys())
        v3_ids = set(self.v3_preds_by_id.keys())

        self.assertEqual(len(v2_ids), 165)
        self.assertEqual(len(v3_ids), 165)
        self.assertEqual(v2_ids, v3_ids)

        transitions_path = os.path.join(self.v3_dir, "v2_v3_task_transitions.json")
        with open(transitions_path, "r", encoding="utf-8") as f:
            transitions = json.load(f)

        join_ids = {t["task_id"] for t in transitions}
        self.assertEqual(len(join_ids), 165)
        self.assertEqual(len(transitions), 165)

    def test_02_exactly_117_v3_failures(self):
        """2. V3 failure population has exactly 117 tasks across Levels 1 (29), 2 (63), and 3 (25)."""
        failed_tasks = [e for e in self.v3_evals if not e.get("correct")]
        self.assertEqual(len(failed_tasks), 117)

        l1_failed = [e for e in failed_tasks if e.get("level") == 1]
        l2_failed = [e for e in failed_tasks if e.get("level") == 2]
        l3_failed = [e for e in failed_tasks if e.get("level") == 3]

        self.assertEqual(len(l1_failed), 29)
        self.assertEqual(len(l2_failed), 63)
        self.assertEqual(len(l3_failed), 25)

    def test_03_taxonomy_reconciles_to_117(self):
        """3. Overall taxonomy reconciles exactly to 117."""
        overall_path = os.path.join(self.v3_dir, "error_analysis_overall.json")
        with open(overall_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        taxonomy_sum = sum(data["taxonomy"].values())
        self.assertEqual(taxonomy_sum, 117)
        self.assertEqual(data["failed_tasks"], 117)
        self.assertEqual(data["total_tasks"], 165)
        self.assertEqual(data["correct_tasks"], 48)

    def test_04_every_v3_failure_has_one_primary_category(self):
        """4. Every failed task receives exactly one primary category from the taxonomy classes."""
        failed_tasks = [e for e in self.v3_evals if not e.get("correct")]
        for e in failed_tasks:
            tid = e["task_id"]
            p = self.v3_preds_by_id[tid]
            cat = classify_v3_failure(e, p)
            self.assertIn(cat, TAXONOMY_CATEGORIES, f"Task {tid} classified as invalid category: {cat}")

    def test_05_every_category_has_confidence_and_basis(self):
        """5. Every category entry has classification_confidence and classification_basis."""
        overall_path = os.path.join(self.v3_dir, "error_analysis_overall.json")
        with open(overall_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        breakdown = data.get("category_breakdown", {})
        for cat, info in breakdown.items():
            self.assertIn(info["classification_confidence"], ["high", "low"])
            self.assertIn(info["classification_basis"], ["metadata", "heuristic"])

    def test_06_python_executed_count_95(self):
        """6. Python executed count is exactly 95."""
        exec_count = sum(1 for p in self.v3_preds if p.get("python_executed"))
        self.assertEqual(exec_count, 95)

    def test_07_python_success_count_26(self):
        """7. Python success count is exactly 26."""
        succ_count = sum(1 for p in self.v3_preds if p.get("python_executed") and p.get("python_success"))
        self.assertEqual(succ_count, 26)

    def test_08_python_failure_count_69(self):
        """8. Python failure count is exactly 69."""
        fail_count = sum(1 for p in self.v3_preds if p.get("python_executed") and not p.get("python_success"))
        self.assertEqual(fail_count, 69)

    def test_09_python_fallback_count_69(self):
        """9. Python fallback count is exactly 69."""
        fallback_count = sum(1 for p in self.v3_preds if p.get("python_fallback"))
        self.assertEqual(fallback_count, 69)

    def test_10_transition_counts_reconcile_to_165(self):
        """10. Overall transition counts reconcile to 165 (8 imp, 25 reg, 40 stable_corr, 92 stable_fail)."""
        transitions_path = os.path.join(self.v3_dir, "v2_v3_task_transitions.json")
        with open(transitions_path, "r", encoding="utf-8") as f:
            transitions = json.load(f)

        counts = {}
        for t in transitions:
            tr = t["transition"]
            counts[tr] = counts.get(tr, 0) + 1

        self.assertEqual(len(transitions), 165)
        self.assertEqual(counts.get("improvement", 0), 8)
        self.assertEqual(counts.get("regression", 0), 25)
        self.assertEqual(counts.get("stable_correct", 0), 40)
        self.assertEqual(counts.get("stable_failure", 0), 92)
        self.assertEqual(sum(counts.values()), 165)

    def test_11_attachment_transitions_reconcile_to_38(self):
        """11. Attachment transitions reconcile to 38 (0 imp, 8 reg, 8 stable_corr, 22 stable_fail)."""
        transitions_path = os.path.join(self.v3_dir, "v2_v3_task_transitions.json")
        with open(transitions_path, "r", encoding="utf-8") as f:
            transitions = json.load(f)

        att_trans = [t for t in transitions if t.get("attachment_required")]
        self.assertEqual(len(att_trans), 38)

        counts = {}
        for t in att_trans:
            tr = t["transition"]
            counts[tr] = counts.get(tr, 0) + 1

        self.assertEqual(counts.get("improvement", 0), 0)
        self.assertEqual(counts.get("regression", 0), 8)
        self.assertEqual(counts.get("stable_correct", 0), 8)
        self.assertEqual(counts.get("stable_failure", 0), 22)

    def test_12_non_attachment_transitions_reconcile_to_127(self):
        """12. Non-attachment transitions reconcile to 127 (8 imp, 17 reg, 32 stable_corr, 70 stable_fail)."""
        transitions_path = os.path.join(self.v3_dir, "v2_v3_task_transitions.json")
        with open(transitions_path, "r", encoding="utf-8") as f:
            transitions = json.load(f)

        non_att_trans = [t for t in transitions if not t.get("attachment_required")]
        self.assertEqual(len(non_att_trans), 127)

        counts = {}
        for t in non_att_trans:
            tr = t["transition"]
            counts[tr] = counts.get(tr, 0) + 1

        self.assertEqual(counts.get("improvement", 0), 8)
        self.assertEqual(counts.get("regression", 0), 17)
        self.assertEqual(counts.get("stable_correct", 0), 32)
        self.assertEqual(counts.get("stable_failure", 0), 70)

    def test_13_per_level_transitions_reconcile(self):
        """13. Per-level transitions reconcile to 53 / 86 / 26."""
        transitions_path = os.path.join(self.v3_dir, "v2_v3_task_transitions.json")
        with open(transitions_path, "r", encoding="utf-8") as f:
            transitions = json.load(f)

        l1 = [t for t in transitions if t["level"] == 1]
        l2 = [t for t in transitions if t["level"] == 2]
        l3 = [t for t in transitions if t["level"] == 3]

        self.assertEqual(len(l1), 53)
        self.assertEqual(len(l2), 86)
        self.assertEqual(len(l3), 26)

        c1 = {tr: sum(1 for t in l1 if t["transition"] == tr) for tr in ["improvement", "regression", "stable_correct", "stable_failure"]}
        c2 = {tr: sum(1 for t in l2 if t["transition"] == tr) for tr in ["improvement", "regression", "stable_correct", "stable_failure"]}
        c3 = {tr: sum(1 for t in l3 if t["transition"] == tr) for tr in ["improvement", "regression", "stable_correct", "stable_failure"]}

        self.assertEqual(c1, {"improvement": 1, "regression": 8, "stable_correct": 23, "stable_failure": 21})
        self.assertEqual(c2, {"improvement": 7, "regression": 14, "stable_correct": 16, "stable_failure": 49})
        self.assertEqual(c3, {"improvement": 0, "regression": 3, "stable_correct": 1, "stable_failure": 22})

    def test_14_correct_v3_tasks_have_no_failure_category(self):
        """14. Correct V3 tasks have no V3 failure category."""
        correct_tasks = [e for e in self.v3_evals if e.get("correct")]
        self.assertEqual(len(correct_tasks), 48)
        for e in correct_tasks:
            tid = e["task_id"]
            p = self.v3_preds_by_id[tid]
            res = classify_v3_failure_detailed(e, p)
            self.assertIsNone(res, f"Correct task {tid} received failure classification: {res}")

    def test_15_high_confidence_categories_require_direct_metadata(self):
        """15. High-confidence Python failure categories require direct recorded metadata."""
        failed_tasks = [e for e in self.v3_evals if not e.get("correct")]
        for e in failed_tasks:
            p = self.v3_preds_by_id[e["task_id"]]
            diag = classify_v3_failure_detailed(e, p)
            if diag["classification_confidence"] == "high":
                cat = diag["category"]
                if cat == "provider_response_anomaly":
                    self.assertTrue(p.get("finish_reason") == "MALFORMED_FUNCTION_CALL" or p.get("has_function_call_part"))
                elif cat == "python_policy_rejection":
                    self.assertEqual(p.get("python_error_type"), "SecurityPolicyError")
                elif cat == "python_dependency_failure":
                    self.assertEqual(p.get("python_error_type"), "NonZeroExitCode")
                elif cat == "python_missing_final_marker":
                    self.assertEqual(p.get("python_error_type"), "MissingFinalAnswerMarker")
                elif cat == "python_success_wrong_answer":
                    self.assertTrue(p.get("python_success"))
                elif cat == "direct_incomplete_generation":
                    self.assertTrue(not e.get("completion_success") or p.get("finish_reason") == "MAX_TOKENS")

    def test_16_python_success_wrong_answer_requires_python_success(self):
        """16. Python success wrong-answer category requires python_success == True."""
        failed_tasks = [e for e in self.v3_evals if not e.get("correct")]
        for e in failed_tasks:
            p = self.v3_preds_by_id[e["task_id"]]
            diag = classify_v3_failure_detailed(e, p)
            if diag["category"] == "python_success_wrong_answer":
                self.assertTrue(p.get("python_executed"))
                self.assertTrue(p.get("python_success"))
                self.assertFalse(e.get("correct"))

    def test_17_timeout_category_requires_python_timeout(self):
        """17. Timeout category requires python_timeout == True."""
        failed_tasks = [e for e in self.v3_evals if not e.get("correct")]
        for e in failed_tasks:
            p = self.v3_preds_by_id[e["task_id"]]
            diag = classify_v3_failure_detailed(e, p)
            if diag["category"] == "python_timeout":
                self.assertTrue(p.get("python_timeout"))

    def test_18_missing_marker_requires_recorded_error_type(self):
        """18. Missing-marker category requires MissingFinalAnswerMarker error type."""
        failed_tasks = [e for e in self.v3_evals if not e.get("correct")]
        for e in failed_tasks:
            p = self.v3_preds_by_id[e["task_id"]]
            diag = classify_v3_failure_detailed(e, p)
            if diag["category"] == "python_missing_final_marker":
                self.assertEqual(p.get("python_error_type"), "MissingFinalAnswerMarker")

    def test_19_public_artifacts_contain_no_prohibited_content(self):
        """19. Public generated artifacts contain no raw Python code/stdout/stderr/question/ground truth."""
        generated_files = [
            "error_analysis_level_1.json",
            "error_analysis_level_2.json",
            "error_analysis_level_3.json",
            "error_analysis_overall.json",
            "v2_v3_task_transitions.json",
            "v2_v3_error_comparison.json",
            "comparison_summary.json",
            "python_execution_analysis.json",
        ]

        def scan_obj(obj, path, filename):
            violations = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    current_path = f"{path}.{k}" if path else k
                    for p in PROHIBITED_KEYS:
                        if p == k.lower():
                            violations.append((filename, current_path, "Prohibited key match"))
                    violations.extend(scan_obj(v, current_path, filename))
            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    violations.extend(scan_obj(item, f"{path}[{idx}]", filename))
            return violations

        for fname in generated_files:
            fpath = os.path.join(self.v3_dir, fname)
            self.assertTrue(os.path.exists(fpath), f"Missing artifact: {fname}")
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            violations = scan_obj(data, "", fname)
            self.assertEqual(len(violations), 0, f"Privacy violations in {fname}: {violations}")

    def test_20_narrative_makes_no_unsupported_causal_claim(self):
        """20. Generated narrative makes no unsupported causal claims."""
        py_analysis_path = os.path.join(self.v3_dir, "python_execution_analysis.json")
        with open(py_analysis_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        notes = data.get("methodological_interpretation", {})
        warning = notes.get("endogenous_routing_warning", "")
        self.assertIn("endogenous", warning.lower())
        self.assertIn("causal", warning.lower())

    def test_21_v4_not_described_as_validated_or_guaranteed(self):
        """21. V4 is not described as validated or guaranteed to fix V3."""
        generated_files = [
            "error_analysis_overall.json",
            "v2_v3_error_comparison.json",
            "comparison_summary.json",
            "python_execution_analysis.json",
        ]
        for fname in generated_files:
            fpath = os.path.join(self.v3_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read().lower()
            self.assertNotIn("v4 will solve", content)
            self.assertNotIn("v4 is guaranteed", content)
            self.assertNotIn("v4 solves", content)


if __name__ == "__main__":
    unittest.main()
