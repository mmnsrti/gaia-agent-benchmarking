"""Unit tests for V1 Error Analysis, Transition Comparison, and Summary Aggregation."""

import json
import os
import unittest
from evaluation.analyze_errors import (
    classify_v1_failure,
    analyze_level_errors,
    build_overall_error_analysis,
    build_v0_v1_error_comparison,
    build_comparison_summary,
)


class TestV1ErrorAnalysis(unittest.TestCase):
    def setUp(self):
        self.v1_dir = "experiments/v1"
        self.v0_dir = "experiments/v0"

    def test_error_counts_sum_to_failed_tasks(self):
        """Verifies for each level and overall that error category counts sum exactly to failed_tasks."""
        for lvl in [1, 2, 3]:
            path = os.path.join(self.v1_dir, f"error_analysis_level_{lvl}.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                failed_tasks = data["failed_tasks"]
                category_sum = sum(data["error_counts"].values())
                self.assertEqual(
                    category_sum,
                    failed_tasks,
                    f"Level {lvl}: category count sum {category_sum} != failed tasks {failed_tasks}",
                )

        overall_path = os.path.join(self.v1_dir, "error_analysis_overall.json")
        if os.path.exists(overall_path):
            with open(overall_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            failed_tasks = data["failed_tasks"]
            category_sum = sum(data["error_counts"].values())
            self.assertEqual(
                category_sum,
                failed_tasks,
                f"Overall: category count sum {category_sum} != failed tasks {failed_tasks}",
            )

    def test_error_percentages_calculated_correctly(self):
        """Verifies that error percentages correctly reflect category count / failed tasks."""
        overall_path = os.path.join(self.v1_dir, "error_analysis_overall.json")
        if os.path.exists(overall_path):
            with open(overall_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            failed_tasks = data["failed_tasks"]
            percentages = data["error_percentages"]
            counts = data["error_counts"]

            for cat, count in counts.items():
                expected_pct = round((count / failed_tasks) * 100, 2)
                self.assertAlmostEqual(
                    percentages[cat],
                    expected_pct,
                    places=2,
                    msg=f"Category {cat} percentage mismatch",
                )

            # Sum of percentages should round to ~100%
            self.assertAlmostEqual(sum(percentages.values()), 100.0, delta=0.5)

    def test_overall_counts_equal_sum_of_levels(self):
        """Verifies that overall metrics match the exact sum of Levels 1, 2, and 3."""
        level_data = []
        for lvl in [1, 2, 3]:
            path = os.path.join(self.v1_dir, f"error_analysis_level_{lvl}.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    level_data.append(json.load(f))

        overall_path = os.path.join(self.v1_dir, "error_analysis_overall.json")
        if len(level_data) == 3 and os.path.exists(overall_path):
            with open(overall_path, "r", encoding="utf-8") as f:
                overall = json.load(f)

            self.assertEqual(overall["total_tasks"], sum(d["total_tasks"] for d in level_data))
            self.assertEqual(overall["correct_tasks"], sum(d["correct_tasks"] for d in level_data))
            self.assertEqual(overall["failed_tasks"], sum(d["failed_tasks"] for d in level_data))

            for cat in overall["error_counts"]:
                level_sum = sum(d["error_counts"].get(cat, 0) for d in level_data)
                self.assertEqual(
                    overall["error_counts"][cat],
                    level_sum,
                    f"Category {cat} overall count {overall['error_counts'][cat]} != sum {level_sum}",
                )

    def test_comparison_arithmetic(self):
        """Verifies transition delta calculations in v0_v1_error_comparison.json."""
        comp_path = os.path.join(self.v1_dir, "v0_v1_error_comparison.json")
        if os.path.exists(comp_path):
            with open(comp_path, "r", encoding="utf-8") as f:
                comp = json.load(f)

            v0 = comp["v0_historical"]
            v1 = comp["v1_canonical"]
            deltas = comp["transition_deltas"]

            expected_acc_delta = round((v1["accuracy"] - v0["accuracy"]) * 100, 2)
            self.assertEqual(deltas["accuracy_delta_percentage_points"], expected_acc_delta)
            self.assertEqual(deltas["net_solved_tasks"], v1["correct_tasks"] - v0["correct_tasks"])
            self.assertEqual(deltas["net_reduced_failures"], v0["failed_tasks"] - v1["failed_tasks"])

    def test_attachment_breakdown_consistency(self):
        """Verifies that attachment and non-attachment tasks partition the task space perfectly."""
        overall_path = os.path.join(self.v1_dir, "error_analysis_overall.json")
        if os.path.exists(overall_path):
            with open(overall_path, "r", encoding="utf-8") as f:
                overall = json.load(f)

            att = overall["attachment_stats"]
            non_att = overall["non_attachment_stats"]

            self.assertEqual(att["total_tasks"] + non_att["total_tasks"], overall["total_tasks"])
            self.assertEqual(att["correct_tasks"] + non_att["correct_tasks"], overall["correct_tasks"])
            self.assertEqual(att["failed_tasks"] + non_att["failed_tasks"], overall["failed_tasks"])

    def test_public_analysis_files_contain_no_prohibited_fields(self):
        """Ensures that public summary and error analysis files contain no leaked benchmark data."""
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

        for fname in os.listdir(self.v1_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.v1_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = json.load(f)
                check_no_prohibited_keys(content, fpath)

    def test_historical_and_matched_control_distinction(self):
        """Ensures that historical V0 and matched-control V0 are tracked distinctly."""
        comp_summary_path = os.path.join(self.v1_dir, "comparison_summary.json")
        if os.path.exists(comp_summary_path):
            with open(comp_summary_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.assertIn("v0_frozen_historical", data)
            self.assertIn("v0_matched_control", data)
            self.assertIn("v1_canonical", data)

            # Historical L1 is 14 / 53 = 26.42%
            hist_l1 = data["v0_frozen_historical"]["level_1"]
            self.assertEqual(hist_l1["correct_tasks"], 14)
            self.assertAlmostEqual(hist_l1["accuracy"], 0.2642, places=4)

            # Matched control L1 is 15 / 53 = 28.30%
            ctrl_l1 = data["v0_matched_control"]["level_1"]
            self.assertEqual(ctrl_l1["correct_tasks"], 15)
            self.assertAlmostEqual(ctrl_l1["accuracy"], 0.2830, places=4)

            # V1 canonical L1 is 28 / 53 = 52.83%
            v1_l1 = data["v1_canonical"]["level_1"]
            self.assertEqual(v1_l1["correct_tasks"], 28)
            self.assertAlmostEqual(v1_l1["accuracy"], 0.5283, places=4)

            # Ensure deltas are computed
            self.assertIn("controlled_deltas_percentage_points", data)
            self.assertIn("historical_deltas_percentage_points", data)

    def test_retrieval_failure_vs_retrieval_insufficient_distinction(self):
        """Verifies distinction between tool execution failure and empty/insufficient evidence."""
        # 1. Search execution failed (provider/tool level) -> retrieval_failure
        failed_search_eval = {"completion_success": True, "prediction": "foo", "ground_truth": "bar"}
        failed_search_pred = {"search_success": False, "search_result_count": 0, "finish_reason": "STOP"}
        self.assertEqual(classify_v1_failure(failed_search_eval, failed_search_pred), "retrieval_failure")

        # 2. Search fallback triggered -> retrieval_failure
        fallback_pred = {"search_success": True, "search_fallback": True, "search_result_count": 0, "finish_reason": "STOP"}
        self.assertEqual(classify_v1_failure(failed_search_eval, fallback_pred), "retrieval_failure")

        # 3. Search succeeded but returned 0 results -> retrieval_insufficient (NOT retrieval_failure)
        zero_results_pred = {"search_success": True, "search_fallback": False, "search_result_count": 0, "finish_reason": "STOP"}
        self.assertEqual(classify_v1_failure(failed_search_eval, zero_results_pred), "retrieval_insufficient")

        # 4. Search succeeded with results, but no evidence for ground truth -> retrieval_insufficient
        snippet_pred = {
            "search_success": True,
            "search_fallback": False,
            "search_result_count": 5,
            "search_results": [{"title": "Irrelevant", "content": "Unrelated topic"}],
            "question": "What is the capital?",
            "finish_reason": "STOP"
        }
        self.assertEqual(classify_v1_failure(failed_search_eval, snippet_pred), "retrieval_insufficient")

    def test_taxonomy_precedence(self):
        """Verifies hierarchical precedence across root-cause categories."""
        # requires_attachment takes precedence even if completion failed and search had 0 results
        att_eval = {"attachment_required": True, "completion_success": False, "ground_truth": "abc"}
        att_pred = {"search_success": False, "search_result_count": 0, "finish_reason": "MAX_TOKENS"}
        self.assertEqual(classify_v1_failure(att_eval, att_pred), "requires_attachment")

        # retrieval_failure takes precedence over incomplete_generation
        tool_err_eval = {"completion_success": False, "ground_truth": "abc"}
        tool_err_pred = {"search_success": False, "finish_reason": "MAX_TOKENS"}
        self.assertEqual(classify_v1_failure(tool_err_eval, tool_err_pred), "retrieval_failure")

        # incomplete_generation takes precedence over formatting or reasoning failure
        incomp_eval = {"completion_success": False, "prediction": "abc", "ground_truth": "abc"}
        incomp_pred = {"search_success": True, "finish_reason": "MAX_TOKENS", "search_result_count": 5}
        self.assertEqual(classify_v1_failure(incomp_eval, incomp_pred), "incomplete_generation")

    def test_completion_failures_vs_incomplete_generation_distinction(self):
        """Verifies that operational completion failures and root-cause incomplete generation are distinct."""
        overall_path = os.path.join(self.v1_dir, "error_analysis_overall.json")
        self.assertTrue(os.path.exists(overall_path))

        with open(overall_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        completion_failures = data["operational_metrics"]["completion_failures"]
        incomplete_generation = data["error_counts"]["incomplete_generation"]

        # Exactly 59 operational completion failures across 165 tasks
        self.assertEqual(completion_failures, 59)
        # Exactly 45 classified as root-cause incomplete_generation
        self.assertEqual(incomplete_generation, 45)

        # Difference (14) must equal attachment-required tasks that failed to complete
        difference = completion_failures - incomplete_generation
        self.assertEqual(difference, 14)

        # Operational metric and root-cause metric must NOT be forced equal
        self.assertNotEqual(completion_failures, incomplete_generation)

    def test_aggregate_benchmark_arithmetic(self):
        """Recomputes and verifies all benchmark accuracies and controlled deltas from summaries."""
        comp_summary_path = os.path.join(self.v1_dir, "comparison_summary.json")
        with open(comp_summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)

        v0_hist = summary["v0_frozen_historical"]
        v0_ctrl = summary["v0_matched_control"]
        v1 = summary["v1_canonical"]
        deltas = summary["controlled_deltas_percentage_points"]

        # V0 historical
        self.assertEqual(v0_hist["level_1"]["correct_tasks"], 14)
        self.assertEqual(v0_hist["level_1"]["total_tasks"], 53)
        self.assertEqual(v0_hist["level_2"]["correct_tasks"], 16)
        self.assertEqual(v0_hist["level_2"]["total_tasks"], 86)
        self.assertEqual(v0_hist["level_3"]["correct_tasks"], 3)
        self.assertEqual(v0_hist["level_3"]["total_tasks"], 26)
        self.assertEqual(v0_hist["overall"]["correct_tasks"], 33)
        self.assertEqual(v0_hist["overall"]["total_tasks"], 165)

        # V0 matched control
        self.assertEqual(v0_ctrl["level_1"]["correct_tasks"], 15)
        self.assertEqual(v0_ctrl["level_1"]["total_tasks"], 53)
        self.assertEqual(v0_ctrl["level_2"]["correct_tasks"], 17)
        self.assertEqual(v0_ctrl["level_2"]["total_tasks"], 86)
        self.assertEqual(v0_ctrl["level_3"]["correct_tasks"], 2)
        self.assertEqual(v0_ctrl["level_3"]["total_tasks"], 26)
        self.assertEqual(v0_ctrl["overall"]["correct_tasks"], 34)
        self.assertEqual(v0_ctrl["overall"]["total_tasks"], 165)

        # V1 canonical
        self.assertEqual(v1["level_1"]["correct_tasks"], 28)
        self.assertEqual(v1["level_1"]["total_tasks"], 53)
        self.assertEqual(v1["level_2"]["correct_tasks"], 24)
        self.assertEqual(v1["level_2"]["total_tasks"], 86)
        self.assertEqual(v1["level_3"]["correct_tasks"], 3)
        self.assertEqual(v1["level_3"]["total_tasks"], 26)
        self.assertEqual(v1["overall"]["correct_tasks"], 55)
        self.assertEqual(v1["overall"]["total_tasks"], 165)

        # Controlled deltas
        self.assertEqual(deltas["level_1"], 24.53)
        self.assertEqual(deltas["level_2"], 8.14)
        self.assertEqual(deltas["level_3"], 3.85)
        self.assertEqual(deltas["overall"], 12.72)


if __name__ == "__main__":
    unittest.main()


