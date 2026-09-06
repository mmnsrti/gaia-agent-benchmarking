import os
import json
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

import pandas as pd

from evaluation.dataset import (
    GAIATask,
    load_gaia_tasks,
    resolve_gaia_data_path,
    EXPECTED_VALIDATION_COUNTS,
)
from evaluation.runner import execute_task
from evaluation.run_level import run_level
from evaluation.metrics import (
    question_scorer,
    gaia_question_scorer,
    normalize_number_str,
    split_string,
    normalize_str,
    normalize_answer,
    check_exact_match,
    SCORER_NAME,
    SCORER_COMMIT,
)
from evaluation.evaluate import calculate_metrics, evaluate_predictions
from agent.llm import LLMResponse


class TestEvaluationPipeline(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.sample_dataset_path = os.path.join(self.test_dir, "metadata.jsonl")
        self.sample_parquet_path = os.path.join(self.test_dir, "metadata.parquet")

        # Synthetic benchmark tasks using official GAIA schema capitalization
        self.sample_tasks_official = [
            {
                "task_id": "task-l1-001",
                "Question": "What is the capital of Italy?",
                "Level": 1,
                "Final answer": "Rome",
                "file_name": "",
                "file_path": "",
                "Annotator Metadata": {"steps": 2},
            },
            {
                "task_id": "task-l1-002",
                "Question": "What is 1000 + 500?",
                "Level": 1,
                "Final answer": "1,500",
                "file_name": "numbers.xlsx",
                "file_path": "data/gaia/2023/validation/numbers.xlsx",
                "Annotator Metadata": {"steps": 3},
            },
            {
                "task_id": "task-l2-001",
                "Question": "Who was the 16th US President?",
                "Level": 2,
                "Final answer": "Abraham Lincoln",
                "file_name": "presidents.pdf",
                "file_path": "data/gaia/2023/validation/presidents.pdf",
                "Annotator Metadata": None,
            },
        ]

        # Write sample JSONL
        with open(self.sample_dataset_path, "w", encoding="utf-8") as f:
            for t in self.sample_tasks_official:
                f.write(json.dumps(t) + "\n")

        # Write sample Parquet
        df = pd.DataFrame(self.sample_tasks_official)
        df.to_parquet(self.sample_parquet_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------
    # 1. Dataset Schema & Loader Compatibility
    # -------------------------------------------------------------
    def test_load_official_gaia_schema_jsonl(self):
        tasks = load_gaia_tasks(self.sample_dataset_path, level=1)
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0].task_id, "task-l1-001")
        self.assertEqual(tasks[0].question, "What is the capital of Italy?")
        self.assertEqual(tasks[0].level, 1)
        self.assertEqual(tasks[0].final_answer, "Rome")
        self.assertFalse(tasks[0].has_attachment)
        self.assertIsNone(tasks[0].file_name)
        self.assertIsNone(tasks[0].file_path)
        self.assertEqual(tasks[0].annotator_metadata, {"steps": 2})

        self.assertTrue(tasks[1].has_attachment)
        self.assertEqual(tasks[1].file_name, "numbers.xlsx")
        self.assertEqual(tasks[1].file_path, "data/gaia/2023/validation/numbers.xlsx")

    def test_load_official_gaia_schema_parquet(self):
        tasks = load_gaia_tasks(self.sample_parquet_path, level=1)
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0].task_id, "task-l1-001")
        self.assertEqual(tasks[0].final_answer, "Rome")

        tasks_l2 = load_gaia_tasks(self.sample_parquet_path, level=2)
        self.assertEqual(len(tasks_l2), 1)
        self.assertEqual(tasks_l2[0].task_id, "task-l2-001")
        self.assertEqual(tasks_l2[0].final_answer, "Abraham Lincoln")

    def test_load_normalized_course_schema_aliases(self):
        alias_file = os.path.join(self.test_dir, "aliases.jsonl")
        with open(alias_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "task_id": "t-alias-1",
                "question": "Alias question?",
                "level": 3,
                "final_answer": "Alias Target",
                "file": "file.png",
            }) + "\n")

        tasks = load_gaia_tasks(alias_file)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].task_id, "t-alias-1")
        self.assertEqual(tasks[0].question, "Alias question?")
        self.assertEqual(tasks[0].level, 3)
        self.assertEqual(tasks[0].final_answer, "Alias Target")
        self.assertEqual(tasks[0].file_name, "file.png")

    def test_require_ground_truth_raises_on_missing_answer(self):
        missing_gt_file = os.path.join(self.test_dir, "missing_gt.jsonl")
        with open(missing_gt_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "task_id": "test_missing",
                "Question": "What is the secret?",
                "Level": 1,
                "Final answer": "",  # Empty
            }) + "\n")

        # With require_ground_truth=True, should raise ValueError
        with self.assertRaises(ValueError) as ctx:
            load_gaia_tasks(missing_gt_file, require_ground_truth=True)
        self.assertIn("missing or empty", str(ctx.exception))

        # With require_ground_truth=False, should succeed with None
        tasks = load_gaia_tasks(missing_gt_file, require_ground_truth=False)
        self.assertEqual(len(tasks), 1)
        self.assertIsNone(tasks[0].final_answer)

    def test_missing_dataset_raises_informative_error(self):
        missing_path = os.path.join(self.test_dir, "nonexistent.parquet")
        with self.assertRaises(FileNotFoundError) as ctx:
            load_gaia_tasks(missing_path)
        self.assertIn("Local GAIA dataset not found", str(ctx.exception))
        self.assertIn("data/gaia/", str(ctx.exception))

    # -------------------------------------------------------------
    # 2. Official Scorer Compatibility & Quirks
    # -------------------------------------------------------------
    def test_official_scorer_numeric_answers(self):
        # Exact and float equivalence
        self.assertTrue(gaia_question_scorer("1000", "1000"))
        self.assertTrue(gaia_question_scorer("1000.0", "1000"))
        self.assertTrue(gaia_question_scorer("3.0", "3"))
        self.assertTrue(gaia_question_scorer("3", "3.0"))

        # Currency and comma normalization
        self.assertTrue(gaia_question_scorer("$1,000", "1000"))
        self.assertTrue(gaia_question_scorer("1,500.00", "1500"))
        self.assertTrue(gaia_question_scorer("1,500", "1500"))

        # Official quirk: comma in ground truth causes list split, so '1500' vs '1,500' length mismatches
        self.assertFalse(gaia_question_scorer("1500", "1,500"))

        # Percentage handling
        self.assertTrue(gaia_question_scorer("50%", "50"))
        self.assertTrue(gaia_question_scorer("50", "50%"))

        # Numeric mismatch
        self.assertFalse(gaia_question_scorer("1001", "1000"))
        self.assertFalse(gaia_question_scorer("Paris", "1000"))

    def test_official_scorer_string_answers(self):
        # Exact string match
        self.assertTrue(gaia_question_scorer("Paris", "Paris"))

        # Case insensitivity
        self.assertTrue(gaia_question_scorer("paris", "Paris"))
        self.assertTrue(gaia_question_scorer("PARIS", "paris"))

        # Complete whitespace removal (official quirk e.g. seagull vs sea gull)
        self.assertTrue(gaia_question_scorer("sea gull", "seagull"))
        self.assertTrue(gaia_question_scorer("seagull", "sea gull"))
        self.assertTrue(gaia_question_scorer(" New   York ", "New York"))

        # Punctuation removal for regular strings
        self.assertTrue(gaia_question_scorer("hello, world!", "hello world"))
        self.assertTrue(gaia_question_scorer("U.S.A.", "usa"))

        # String mismatch
        self.assertFalse(gaia_question_scorer("Berlin", "Paris"))

    def test_official_scorer_list_answers(self):
        # Comma separated
        self.assertTrue(gaia_question_scorer("apple, banana, cherry", "apple, banana, cherry"))
        self.assertTrue(gaia_question_scorer("apple,banana,cherry", "apple, banana, cherry"))

        # Semicolon separated
        self.assertTrue(gaia_question_scorer("apple; banana; cherry", "apple, banana, cherry"))
        self.assertTrue(gaia_question_scorer("apple, banana, cherry", "apple; banana; cherry"))

        # Numeric list elements
        self.assertTrue(gaia_question_scorer("1, 2, 3", "1, 2, 3"))
        self.assertTrue(gaia_question_scorer("$1, $2, $3", "1, 2, 3"))

        # List length mismatch returns False
        self.assertFalse(gaia_question_scorer("apple, banana", "apple, banana, cherry"))
        self.assertFalse(gaia_question_scorer("apple, banana, cherry", "apple, banana"))

        # Official quirk: punctuation is NOT removed for list elements (remove_punct=False)
        self.assertTrue(gaia_question_scorer("U.S.A., France", "U.S.A., France"))
        self.assertFalse(gaia_question_scorer("USA, France", "U.S.A., France"))

    def test_official_scorer_none_prediction(self):
        # None model prediction evaluated against string
        self.assertFalse(gaia_question_scorer(None, "Rome"))
        # Model answer None matching ground truth None
        self.assertTrue(gaia_question_scorer(None, "None"))

    def test_scorer_provenance_metadata(self):
        self.assertEqual(SCORER_NAME, "official-gaia-leaderboard")
        self.assertEqual(SCORER_COMMIT, "9f133d71362e77b3539f1514f31b9c101a545fec")

    # -------------------------------------------------------------
    # 3. Evaluation Integrity & Error Handling
    # -------------------------------------------------------------
    def test_duplicate_task_id_raises_value_error(self):
        tasks_by_id = {
            "t1": GAIATask("t1", "Q1", 1, "Rome"),
        }
        predictions = [
            {"task_id": "t1", "final_answer": "Rome", "completion_success": True},
            {"task_id": "t1", "final_answer": "Rome", "completion_success": True},  # Duplicate
        ]
        with self.assertRaises(ValueError) as ctx:
            calculate_metrics(predictions, tasks_by_id, level=1)
        self.assertIn("Duplicate prediction detected for task_id 't1'", str(ctx.exception))

    def test_unmatched_task_id_raises_value_error(self):
        tasks_by_id = {
            "t1": GAIATask("t1", "Q1", 1, "Rome"),
        }
        predictions = [
            {"task_id": "unknown_task_999", "final_answer": "Rome", "completion_success": True},
        ]
        with self.assertRaises(ValueError) as ctx:
            calculate_metrics(predictions, tasks_by_id, level=1)
        self.assertIn("cannot be matched to ground truth dataset", str(ctx.exception))

    def test_missing_ground_truth_raises_value_error(self):
        tasks_by_id = {
            "t1": GAIATask("t1", "Q1", 1, None),  # Missing ground truth
        }
        predictions = [
            {"task_id": "t1", "final_answer": "Rome", "completion_success": True},
        ]
        with self.assertRaises(ValueError) as ctx:
            calculate_metrics(predictions, tasks_by_id, level=1)
        self.assertIn("Ground truth answer is missing or empty", str(ctx.exception))

    def test_evaluate_predictions_missing_dataset_raises_file_not_found(self):
        pred_file = os.path.join(self.test_dir, "preds.jsonl")
        with open(pred_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"task_id": "task-l1-001", "level": 1, "final_answer": "Rome", "completion_success": True}) + "\n")

        with self.assertRaises(FileNotFoundError):
            evaluate_predictions(
                predictions_path=pred_file,
                data_path=os.path.join(self.test_dir, "missing_data.parquet"),
                level=1,
            )

    # -------------------------------------------------------------
    # 4. Partial vs Complete Benchmark Tracking
    # -------------------------------------------------------------
    def test_partial_run_marking(self):
        tasks_by_id = {
            "task-l1-001": GAIATask("task-l1-001", "Q1", 1, "Rome"),
            "task-l1-002": GAIATask("task-l1-002", "Q2", 1, "1,500"),
        }
        # Only 2 predictions for Level 1 (expected is 53)
        predictions = [
            {"task_id": "task-l1-001", "final_answer": "Rome", "request_success": True, "completion_success": True},
            {"task_id": "task-l1-002", "final_answer": "1500", "request_success": True, "completion_success": True},
        ]

        res = calculate_metrics(predictions, tasks_by_id, level=1)
        summary = res["summary"]

        self.assertEqual(summary["total_tasks"], 2)
        self.assertEqual(summary["selected_task_count"], 2)
        self.assertEqual(summary["expected_task_count"], 53)
        self.assertFalse(summary["is_complete_benchmark"])

    def test_complete_benchmark_marking(self):
        tasks_by_id = {
            f"t_{i}": GAIATask(f"t_{i}", f"Q_{i}", 1, f"Ans_{i}")
            for i in range(53)
        }
        predictions = [
            {"task_id": f"t_{i}", "final_answer": f"Ans_{i}", "request_success": True, "completion_success": True}
            for i in range(53)
        ]

        res = calculate_metrics(predictions, tasks_by_id, level=1)
        summary = res["summary"]

        self.assertEqual(summary["total_tasks"], 53)
        self.assertEqual(summary["expected_task_count"], 53)
        self.assertTrue(summary["is_complete_benchmark"])

    def test_enforce_task_count_raises_on_partial_run(self):
        pred_file = os.path.join(self.test_dir, "partial_preds.jsonl")
        with open(pred_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "task_id": "task-l1-001",
                "final_answer": "Rome",
                "request_success": True,
                "completion_success": True,
                "level": 1,
            }) + "\n")

        with self.assertRaises(ValueError) as ctx:
            evaluate_predictions(
                predictions_path=pred_file,
                data_path=self.sample_parquet_path,
                level=1,
                enforce_task_count=True,
            )
        self.assertIn("Benchmark task count integrity check failed", str(ctx.exception))

    # -------------------------------------------------------------
    # 5. Safe Public Summary Secrets Verification
    # -------------------------------------------------------------
    def test_public_summary_omits_benchmark_secrets_and_raw_responses(self):
        tasks_by_id = {
            "task-secret-01": GAIATask("task-secret-01", "Confidential question text?", 1, "Classified answer 99", "secret.pdf"),
        }
        predictions = [
            {
                "task_id": "task-secret-01",
                "question": "Confidential question text?",
                "final_answer": "Classified answer 99",
                "raw_response": "Raw classified answer 99",
                "ground_truth": "Classified answer 99",
                "request_success": True,
                "completion_success": True,
                "latency_seconds": 1.5,
                "input_tokens": 10,
                "output_tokens": 5,
                "thinking_tokens": 20,
                "total_tokens": 35,
                "attachment_required": True,
            }
        ]

        summary_file = os.path.join(self.test_dir, "safe_summary.json")
        res = calculate_metrics(predictions, tasks_by_id, level=1)
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(res["summary"], f, indent=2)

        with open(summary_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Public summary MUST NOT leak any question or answer text or keys
        self.assertNotIn("Confidential question", content)
        self.assertNotIn("Classified answer", content)
        self.assertNotIn("Raw classified answer", content)
        self.assertNotIn("secret.pdf", content)
        for forbidden_key in ["question", "ground_truth", "final_answer", "raw_response", "predictions"]:
            self.assertNotIn(forbidden_key, res["summary"])

        # But it MUST contain reproducibility metadata
        self.assertIn("dataset_name", content)
        self.assertIn("GAIA", content)
        self.assertIn("2023", content)
        self.assertIn("validation", content)
        self.assertIn("official-gaia-leaderboard", content)
        self.assertIn("9f133d71362e77b3539f1514f31b9c101a545fec", content)
        self.assertIn("is_complete_benchmark", content)

    def test_evaluate_predictions_duplicate_task_id_raises_value_error(self):
        pred_file = os.path.join(self.test_dir, "duplicate_preds.jsonl")
        with open(pred_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"task_id": "task-l1-001", "level": 1, "final_answer": "Rome", "completion_success": True}) + "\n")
            f.write(json.dumps({"task_id": "task-l1-001", "level": 1, "final_answer": "Rome", "completion_success": True}) + "\n")

        with self.assertRaises(ValueError) as ctx:
            evaluate_predictions(
                predictions_path=pred_file,
                data_path=self.sample_parquet_path,
                level=1,
            )
        self.assertIn("Duplicate prediction detected for task_id 'task-l1-001'", str(ctx.exception))

    def test_evaluate_predictions_unknown_task_id_raises_value_error(self):
        pred_file = os.path.join(self.test_dir, "unknown_preds.jsonl")
        with open(pred_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"task_id": "unknown-task-999", "level": 1, "final_answer": "Rome", "completion_success": True}) + "\n")

        with self.assertRaises(ValueError) as ctx:
            evaluate_predictions(
                predictions_path=pred_file,
                data_path=self.sample_parquet_path,
                level=1,
            )
        self.assertIn("cannot be matched to ground truth dataset", str(ctx.exception))

    # -------------------------------------------------------------
    # 6. Level Runner Execution & Metadata Logging
    # -------------------------------------------------------------
    @patch("agent.llm.LLMClient.generate")
    @patch("evaluation.runner.get_git_metadata")
    def test_run_level_executes_and_saves_metadata(self, mock_git, mock_generate):
        mock_git.return_value = {"git_commit": "abcdef1", "git_branch": "v0", "git_dirty": False}
        mock_generate.side_effect = [
            LLMResponse(text="Rome", raw_text="  Rome  \n", finish_reason="STOP", input_tokens=10, output_tokens=2, thinking_tokens=20, total_tokens=32),
            LLMResponse(text="1500", raw_text="1500", finish_reason="STOP", input_tokens=15, output_tokens=3, thinking_tokens=40, total_tokens=58),
        ]

        output_predictions = os.path.join(self.test_dir, "predictions_l1.jsonl")
        run_level(
            level=1,
            data_path=self.sample_dataset_path,
            output_file=output_predictions,
            resume=False,
            auto_eval=False,
        )

        self.assertTrue(os.path.exists(output_predictions))
        with open(output_predictions, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["task_id"], "task-l1-001")
        self.assertEqual(lines[0]["level"], 1)
        self.assertEqual(lines[0]["raw_response"], "  Rome  \n")
        self.assertEqual(lines[0]["final_answer"], "Rome")
        self.assertTrue(lines[0]["completion_success"])
        self.assertFalse(lines[0]["attachment_required"])

        self.assertEqual(lines[1]["task_id"], "task-l1-002")
        self.assertTrue(lines[1]["attachment_required"])
        self.assertEqual(lines[1]["file_name"], "numbers.xlsx")

    @patch("agent.llm.LLMClient.generate")
    @patch("evaluation.runner.get_git_metadata")
    def test_run_level_resume_skips_completed(self, mock_git, mock_generate):
        mock_git.return_value = {"git_commit": "abc", "git_branch": "v0", "git_dirty": False}
        output_predictions = os.path.join(self.test_dir, "resume_predictions.jsonl")

        # Pre-seed with task-l1-001 completed
        preseed_record = {
            "task_id": "task-l1-001",
            "level": 1,
            "final_answer": "Rome",
            "completion_success": True,
        }
        with open(output_predictions, "w", encoding="utf-8") as f:
            f.write(json.dumps(preseed_record) + "\n")

        # Mock generator only called for task-l1-002
        mock_generate.return_value = LLMResponse(text="1500", finish_reason="STOP")

        run_level(
            level=1,
            data_path=self.sample_dataset_path,
            output_file=output_predictions,
            resume=True,
            auto_eval=False,
        )

        self.assertEqual(mock_generate.call_count, 1)
        with open(output_predictions, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(lines), 2)

    @patch("agent.llm.LLMClient.generate")
    @patch("evaluation.runner.get_git_metadata")
    def test_run_level_prunes_failed_request_and_retries(self, mock_git, mock_generate):
        mock_git.return_value = {"git_commit": "abc", "git_branch": "v0", "git_dirty": False}
        output_predictions = os.path.join(self.test_dir, "failed_resume_predictions.jsonl")

        # Pre-seed with task-l1-001 successful and task-l1-002 failed
        good_record = {
            "task_id": "task-l1-001",
            "level": 1,
            "final_answer": "Rome",
            "request_success": True,
            "completion_success": True,
        }
        failed_record = {
            "task_id": "task-l1-002",
            "level": 1,
            "final_answer": None,
            "request_success": False,
            "completion_success": False,
            "error_type": "ConnectionError",
            "error_message": "Timeout",
        }
        with open(output_predictions, "w", encoding="utf-8") as f:
            f.write(json.dumps(good_record) + "\n")
            f.write(json.dumps(failed_record) + "\n")

        # Mock generator called for task-l1-002 retry
        mock_generate.return_value = LLMResponse(text="1500", finish_reason="STOP")

        run_level(
            level=1,
            data_path=self.sample_dataset_path,
            output_file=output_predictions,
            resume=True,
            auto_eval=False,
        )

        self.assertEqual(mock_generate.call_count, 1)
        with open(output_predictions, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        # Failed record must be replaced by new successful record without duplicates
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["task_id"], "task-l1-001")
        self.assertEqual(lines[1]["task_id"], "task-l1-002")
        self.assertTrue(lines[1]["request_success"])

    @patch("agent.llm.LLMClient.generate")
    @patch("evaluation.runner.get_git_metadata")
    def test_run_level_halts_on_429_quota_exhausted(self, mock_git, mock_generate):
        mock_git.return_value = {"git_commit": "abc", "git_branch": "v0", "git_dirty": False}
        output_predictions = os.path.join(self.test_dir, "quota_halt_predictions.jsonl")

        # Mock generate raising a 429 ClientError on the very first task
        mock_generate.side_effect = RuntimeError("429 RESOURCE_EXHAUSTED: Quota exceeded")

        run_level(
            level=1,
            data_path=self.sample_dataset_path,
            output_file=output_predictions,
            resume=False,
            auto_eval=False,
        )

        # Should halt after task 1 and NOT attempt task 2
        self.assertEqual(mock_generate.call_count, 1)
        # 429 failure should NOT be logged to output file
        if os.path.exists(output_predictions):
            with open(output_predictions, "r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(lines), 0)


if __name__ == "__main__":
    unittest.main()
