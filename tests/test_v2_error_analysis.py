"""Unit tests for V2 Error Analysis, Taxonomy Classification, and Controlled V1/V2 Comparison."""

import json
import os
import unittest
from evaluation.analyze_v2_errors import (
    classify_v2_failure,
    analyze_v2_level_errors,
    build_overall_v2_error_analysis,
    build_v1_v2_task_transitions,
    build_v1_v2_error_comparison,
    build_comparison_summary,
    TAXONOMY_CATEGORIES,
)


class TestV2ErrorAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v2_dir = "experiments/v2"
        cls.v1_dir = "experiments/v2_matched_v1"

        cls.v2_evals = []
        cls.v2_preds = []
        cls.v1_evals = []
        cls.v1_preds = []

        for lvl in [1, 2, 3]:
            with open(os.path.join(cls.v2_dir, f"detailed_eval_level_{lvl}.jsonl"), "r", encoding="utf-8") as f:
                cls.v2_evals.extend([json.loads(l) for l in f if l.strip()])
            with open(os.path.join(cls.v2_dir, f"predictions_level_{lvl}.jsonl"), "r", encoding="utf-8") as f:
                cls.v2_preds.extend([json.loads(l) for l in f if l.strip()])
            with open(os.path.join(cls.v1_dir, f"detailed_eval_level_{lvl}.jsonl"), "r", encoding="utf-8") as f:
                cls.v1_evals.extend([json.loads(l) for l in f if l.strip()])
            with open(os.path.join(cls.v1_dir, f"predictions_level_{lvl}.jsonl"), "r", encoding="utf-8") as f:
                cls.v1_preds.extend([json.loads(l) for l in f if l.strip()])

        cls.v2_preds_by_id = {p["task_id"]: p for p in cls.v2_preds}
        cls.v2_evals_by_id = {e["task_id"]: e for e in cls.v2_evals}
        cls.v1_preds_by_id = {p["task_id"]: p for p in cls.v1_preds}
        cls.v1_evals_by_id = {e["task_id"]: e for e in cls.v1_evals}

    def test_1_failed_tasks_receive_exactly_one_category(self):
        """1. Every failed V2 task receives exactly one category from the 8 taxonomy classes."""
        failed_tasks = [e for e in self.v2_evals if not e.get("correct")]
        self.assertEqual(len(failed_tasks), 104)

        for e in failed_tasks:
            tid = e["task_id"]
            p = self.v2_preds_by_id[tid]
            cat = classify_v2_failure(e, p)
            self.assertIn(cat, TAXONOMY_CATEGORIES, f"Task {tid} classified as invalid category: {cat}")

    def test_2_overall_taxonomy_sums_to_104(self):
        """2. Overall taxonomy sums to exactly 104."""
        overall_path = os.path.join(self.v2_dir, "error_analysis_overall.json")
        self.assertTrue(os.path.exists(overall_path))
        with open(overall_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        taxonomy_sum = sum(data["taxonomy"].values())
        self.assertEqual(taxonomy_sum, 104)
        self.assertEqual(data["failed_tasks"], 104)
        self.assertEqual(data["total_tasks"], 165)
        self.assertEqual(data["correct_tasks"], 61)

    def test_3_level_1_taxonomy_sums_to_26(self):
        """3. Level 1 taxonomy sums to exactly 26 (53 - 27)."""
        l1_path = os.path.join(self.v2_dir, "error_analysis_level_1.json")
        self.assertTrue(os.path.exists(l1_path))
        with open(l1_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        taxonomy_sum = sum(data["taxonomy"].values())
        self.assertEqual(taxonomy_sum, 26)
        self.assertEqual(data["failed_tasks"], 26)
        self.assertEqual(data["total_tasks"], 53)
        self.assertEqual(data["correct_tasks"], 27)

    def test_4_level_2_taxonomy_sums_to_56(self):
        """4. Level 2 taxonomy sums to exactly 56 (86 - 30)."""
        l2_path = os.path.join(self.v2_dir, "error_analysis_level_2.json")
        self.assertTrue(os.path.exists(l2_path))
        with open(l2_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        taxonomy_sum = sum(data["taxonomy"].values())
        self.assertEqual(taxonomy_sum, 56)
        self.assertEqual(data["failed_tasks"], 56)
        self.assertEqual(data["total_tasks"], 86)
        self.assertEqual(data["correct_tasks"], 30)

    def test_5_level_3_taxonomy_sums_to_22(self):
        """5. Level 3 taxonomy sums to exactly 22 (26 - 4)."""
        l3_path = os.path.join(self.v2_dir, "error_analysis_level_3.json")
        self.assertTrue(os.path.exists(l3_path))
        with open(l3_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        taxonomy_sum = sum(data["taxonomy"].values())
        self.assertEqual(taxonomy_sum, 22)
        self.assertEqual(data["failed_tasks"], 22)
        self.assertEqual(data["total_tasks"], 26)
        self.assertEqual(data["correct_tasks"], 4)

    def test_6_no_correct_task_in_failure_taxonomy(self):
        """6. No correct task is included in failure taxonomy."""
        correct_tasks = [e for e in self.v2_evals if e.get("correct")]
        self.assertEqual(len(correct_tasks), 61)

        transitions_path = os.path.join(self.v2_dir, "v1_v2_task_transitions.json")
        with open(transitions_path, "r", encoding="utf-8") as f:
            transitions = json.load(f)

        for t in transitions:
            if t["v2_correct"]:
                self.assertIsNone(
                    t["v2_error_category"],
                    f"Correct task {t['task_id']} has an error category: {t['v2_error_category']}"
                )

    def test_7_provider_response_anomaly_requires_has_function_call_part(self):
        """7. provider_response_anomaly requires has_function_call_part=True."""
        transitions_path = os.path.join(self.v2_dir, "v1_v2_task_transitions.json")
        with open(transitions_path, "r", encoding="utf-8") as f:
            transitions = json.load(f)

        anomaly_count = 0
        for t in transitions:
            if t["v2_error_category"] == "provider_response_anomaly":
                anomaly_count += 1
                tid = t["task_id"]
                p = self.v2_preds_by_id[tid]
                self.assertTrue(
                    p.get("has_function_call_part"),
                    f"Task {tid} categorized as provider_response_anomaly but has_function_call_part is not True"
                )
        self.assertEqual(anomaly_count, 7)

    def test_8_retrieval_failure_requires_search_failure_evidence(self):
        """8. retrieval_failure requires actual search failure evidence."""
        transitions_path = os.path.join(self.v2_dir, "v1_v2_task_transitions.json")
        with open(transitions_path, "r", encoding="utf-8") as f:
            transitions = json.load(f)

        for t in transitions:
            if t["v2_error_category"] == "retrieval_failure":
                tid = t["task_id"]
                p = self.v2_preds_by_id[tid]
                e = self.v2_evals_by_id[tid]
                has_search_err = not p.get("search_success", True) or p.get("search_fallback", False)
                self.assertTrue(has_search_err, f"Task {tid} classified as retrieval_failure without search error")

    def test_9_attachment_reasoning_failure_requires_successful_processing(self):
        """9. Attachment reasoning failure requires successful attachment processing."""
        transitions_path = os.path.join(self.v2_dir, "v1_v2_task_transitions.json")
        with open(transitions_path, "r", encoding="utf-8") as f:
            transitions = json.load(f)

        arf_count = 0
        for t in transitions:
            if t["v2_error_category"] == "attachment_reasoning_failure":
                arf_count += 1
                tid = t["task_id"]
                p = self.v2_preds_by_id[tid]
                self.assertTrue(
                    p.get("file_processing_success"),
                    f"Task {tid} classified as attachment_reasoning_failure but file_processing_success is False"
                )
                self.assertFalse(
                    p.get("file_fallback"),
                    f"Task {tid} classified as attachment_reasoning_failure but file_fallback is True"
                )
                self.assertTrue(t["attachment_required"])
        self.assertEqual(arf_count, 8)

    def test_10_unsupported_attachment_requires_unsupported_or_failed_processing(self):
        """10. Unsupported attachment requires attachment-processing failure or unsupported type evidence."""
        transitions_path = os.path.join(self.v2_dir, "v1_v2_task_transitions.json")
        with open(transitions_path, "r", encoding="utf-8") as f:
            transitions = json.load(f)

        unsupported_count = 0
        unsupported_exts = {".zip", ".pdb", ".jsonld"}
        for t in transitions:
            if t["v2_error_category"] == "unsupported_attachment":
                unsupported_count += 1
                tid = t["task_id"]
                p = self.v2_preds_by_id[tid]
                self.assertTrue(t["attachment_required"])
                has_failed_proc = not p.get("file_processing_success") or p.get("file_fallback") or p.get("file_extension") in unsupported_exts
                self.assertTrue(
                    has_failed_proc,
                    f"Task {tid} classified as unsupported_attachment but was processed successfully as a supported type"
                )
        self.assertEqual(unsupported_count, 3)

    def test_11_v1_v2_task_joins_contain_165_unique_ids(self):
        """11. V1/V2 task joins contain exactly 165 unique task IDs."""
        v1_ids = set(self.v1_preds_by_id.keys())
        v2_ids = set(self.v2_preds_by_id.keys())

        self.assertEqual(len(v1_ids), 165)
        self.assertEqual(len(v2_ids), 165)
        self.assertEqual(v1_ids, v2_ids)

        transitions_path = os.path.join(self.v2_dir, "v1_v2_task_transitions.json")
        with open(transitions_path, "r", encoding="utf-8") as f:
            transitions = json.load(f)

        join_ids = {t["task_id"] for t in transitions}
        self.assertEqual(len(join_ids), 165)

    def test_12_transition_counts_sum_to_165(self):
        """12. Transition counts sum to 165."""
        comp_path = os.path.join(self.v2_dir, "v1_v2_error_comparison.json")
        with open(comp_path, "r", encoding="utf-8") as f:
            comp = json.load(f)

        overall_trans = comp["task_transitions"]["overall"]
        sum_transitions = (
            overall_trans["improvement"]
            + overall_trans["regression"]
            + overall_trans["stable_correct"]
            + overall_trans["stable_failure"]
        )
        self.assertEqual(sum_transitions, 165)
        self.assertEqual(overall_trans["total"], 165)
        self.assertEqual(overall_trans["improvement"], 19)
        self.assertEqual(overall_trans["regression"], 3)
        self.assertEqual(overall_trans["stable_correct"], 42)
        self.assertEqual(overall_trans["stable_failure"], 101)

    def test_13_attachment_transition_counts_sum_to_38(self):
        """13. Attachment transition counts sum to 38."""
        comp_path = os.path.join(self.v2_dir, "v1_v2_error_comparison.json")
        with open(comp_path, "r", encoding="utf-8") as f:
            comp = json.load(f)

        att_trans = comp["task_transitions"]["attachment_tasks"]
        sum_att = (
            att_trans["improvement"]
            + att_trans["regression"]
            + att_trans["stable_correct"]
            + att_trans["stable_failure"]
        )
        self.assertEqual(sum_att, 38)
        self.assertEqual(att_trans["total"], 38)
        self.assertEqual(att_trans["improvement"], 14)
        self.assertEqual(att_trans["regression"], 2)
        self.assertEqual(att_trans["stable_correct"], 2)
        self.assertEqual(att_trans["stable_failure"], 20)

    def test_14_non_attachment_transition_counts_sum_to_127(self):
        """14. Non-attachment transition counts sum to 127."""
        comp_path = os.path.join(self.v2_dir, "v1_v2_error_comparison.json")
        with open(comp_path, "r", encoding="utf-8") as f:
            comp = json.load(f)

        non_att_trans = comp["task_transitions"]["non_attachment_tasks"]
        sum_non_att = (
            non_att_trans["improvement"]
            + non_att_trans["regression"]
            + non_att_trans["stable_correct"]
            + non_att_trans["stable_failure"]
        )
        self.assertEqual(sum_non_att, 127)
        self.assertEqual(non_att_trans["total"], 127)
        self.assertEqual(non_att_trans["improvement"], 5)
        self.assertEqual(non_att_trans["regression"], 1)
        self.assertEqual(non_att_trans["stable_correct"], 40)
        self.assertEqual(non_att_trans["stable_failure"], 81)

    def test_15_public_generated_artifacts_contain_no_prohibited_content(self):
        """15. Public generated artifacts contain no full GAIA questions, ground-truth answers, or prompts."""
        prohibited_keys = {
            "question",
            "ground_truth",
            "prediction",
            "content",
            "raw_response",
            "prompt",
            "api_key",
            "tavily_api_key",
            "search_results",
        }

        def check_no_prohibited_keys(data, current_file=""):
            if isinstance(data, dict):
                for k, v in data.items():
                    self.assertNotIn(
                        k.lower(),
                        prohibited_keys,
                        f"Prohibited key '{k}' found in public file: {current_file}",
                    )
                    check_no_prohibited_keys(v, current_file)
            elif isinstance(data, list):
                for item in data:
                    check_no_prohibited_keys(item, current_file)

        json_files = [
            "error_analysis_level_1.json",
            "error_analysis_level_2.json",
            "error_analysis_level_3.json",
            "error_analysis_overall.json",
            "v1_v2_task_transitions.json",
            "v1_v2_error_comparison.json",
            "comparison_summary.json",
        ]
        for fname in json_files:
            fpath = os.path.join(self.v2_dir, fname)
            self.assertTrue(os.path.exists(fpath), f"Missing public artifact: {fpath}")
            with open(fpath, "r", encoding="utf-8") as f:
                content = json.load(f)
            check_no_prohibited_keys(content, fpath)

    def test_operational_vs_incomplete_generation_reconciliation(self):
        """Verifies that operational completion failures (62) reconcile exactly with root-cause taxonomy."""
        overall_path = os.path.join(self.v2_dir, "error_analysis_overall.json")
        with open(overall_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        comp_fails = data["operational_completion_failures"]
        incomplete_gen = data["taxonomy"]["incomplete_generation"]
        anomalies = data["taxonomy"]["provider_response_anomaly"]
        unsupported = data["taxonomy"]["unsupported_attachment"]

        self.assertEqual(comp_fails, 62)
        self.assertEqual(incomplete_gen, 54)
        self.assertEqual(anomalies, 7)

        diff = comp_fails - incomplete_gen
        self.assertEqual(diff, 8)
        self.assertNotEqual(comp_fails, incomplete_gen)


if __name__ == "__main__":
    unittest.main()

