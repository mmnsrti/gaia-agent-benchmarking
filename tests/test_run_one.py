import os
import unittest
from unittest.mock import patch, MagicMock
from evaluation.run_one import run_one
from evaluation.gaia_client import GAIAClient
from agent.llm import LLMResponse


class TestRunOneCompletion(unittest.TestCase):
    def setUp(self):
        self.sample_question = {
            "task_id": "test-task-1",
            "question": "What is 2+2?",
            "file_name": "",
        }

    @patch.object(GAIAClient, "get_questions")
    @patch("agent.llm.LLMClient.generate")
    @patch("evaluation.runner.get_git_metadata")
    def test_stop_with_non_empty_response_is_completion_success(self, mock_git, mock_generate, mock_get_questions):
        mock_get_questions.return_value = [self.sample_question]
        mock_git.return_value = {"git_commit": "abc", "git_branch": "main", "git_dirty": False}
        mock_generate.return_value = LLMResponse(text="4", finish_reason="STOP", thinking_tokens=100)

        record = run_one(index=0, log=False)
        self.assertEqual(record["schema_version"], 2)
        self.assertTrue(record["request_success"])
        self.assertTrue(record["completion_success"])
        self.assertEqual(record["finish_reason"], "STOP")
        self.assertEqual(record["raw_response"], "4")
        self.assertEqual(record["final_answer"], "4")

    @patch.object(GAIAClient, "get_questions")
    @patch("agent.llm.LLMClient.generate")
    @patch("evaluation.runner.get_git_metadata")
    def test_none_finish_reason_is_not_completion_success(self, mock_git, mock_generate, mock_get_questions):
        mock_get_questions.return_value = [self.sample_question]
        mock_git.return_value = {"git_commit": "abc", "git_branch": "main", "git_dirty": False}
        mock_generate.return_value = LLMResponse(text="4", finish_reason=None)

        record = run_one(index=0, log=False)
        self.assertEqual(record["schema_version"], 2)
        self.assertTrue(record["request_success"])
        self.assertFalse(record["completion_success"])
        self.assertIsNone(record["finish_reason"])

    @patch.object(GAIAClient, "get_questions")
    @patch("agent.llm.LLMClient.generate")
    @patch("evaluation.runner.get_git_metadata")
    def test_stop_with_empty_response_is_not_completion_success(self, mock_git, mock_generate, mock_get_questions):
        mock_get_questions.return_value = [self.sample_question]
        mock_git.return_value = {"git_commit": "abc", "git_branch": "main", "git_dirty": False}
        mock_generate.return_value = LLMResponse(text="   \n", finish_reason="STOP")

        record = run_one(index=0, log=False)
        self.assertEqual(record["schema_version"], 2)
        self.assertTrue(record["request_success"])
        self.assertFalse(record["completion_success"])
        self.assertEqual(record["finish_reason"], "STOP")

    @patch.object(GAIAClient, "get_questions")
    @patch("agent.llm.LLMClient.generate")
    @patch("evaluation.runner.get_git_metadata")
    def test_max_tokens_is_not_completion_success(self, mock_git, mock_generate, mock_get_questions):
        mock_get_questions.return_value = [self.sample_question]
        mock_git.return_value = {"git_commit": "abc", "git_branch": "main", "git_dirty": False}
        mock_generate.return_value = LLMResponse(text="incomplete", finish_reason="MAX_TOKENS")

        record = run_one(index=0, log=False)
        self.assertEqual(record["schema_version"], 2)
        self.assertTrue(record["request_success"])
        self.assertFalse(record["completion_success"])
        self.assertEqual(record["finish_reason"], "MAX_TOKENS")

    @patch.object(GAIAClient, "get_questions")
    @patch("agent.llm.LLMClient.generate")
    @patch("evaluation.runner.get_git_metadata")
    def test_api_exception_produces_request_and_completion_failure(self, mock_git, mock_generate, mock_get_questions):
        mock_get_questions.return_value = [self.sample_question]
        mock_git.return_value = {"git_commit": "abc", "git_branch": "main", "git_dirty": False}
        mock_generate.side_effect = RuntimeError("Service unavailable")

        record = run_one(index=0, log=False)
        self.assertEqual(record["schema_version"], 2)
        self.assertFalse(record["request_success"])
        self.assertFalse(record["completion_success"])
        self.assertEqual(record["error_type"], "RuntimeError")
        self.assertIn("Service unavailable", record["error_message"])
        self.assertIsNone(record["raw_response"])
        self.assertIsNone(record["final_answer"])

    @patch.object(GAIAClient, "get_questions")
    @patch("agent.llm.LLMClient.generate")
    @patch("evaluation.runner.get_git_metadata")
    def test_function_call_part_propagated_to_prediction_record(self, mock_git, mock_generate, mock_get_questions):
        mock_get_questions.return_value = [self.sample_question]
        mock_git.return_value = {"git_commit": "abc", "git_branch": "main", "git_dirty": False}
        mock_generate.return_value = LLMResponse(
            text="",
            raw_text="",
            finish_reason="STOP",
            response_part_types=["function_call"],
            response_part_count=1,
            has_text_part=False,
            has_function_call_part=True,
        )

        record = run_one(index=0, log=False)
        self.assertEqual(record["schema_version"], 2)
        self.assertTrue(record["request_success"])
        self.assertFalse(record["completion_success"])
        self.assertEqual(record["finish_reason"], "STOP")
        self.assertEqual(record["response_part_types"], ["function_call"])
        self.assertEqual(record["response_part_count"], 1)
        self.assertFalse(record["has_text_part"])
        self.assertTrue(record["has_function_call_part"])

    @patch.object(GAIAClient, "get_questions")
    @patch("agent.llm.LLMClient.generate")
    @patch("evaluation.runner.get_git_metadata")
    def test_mixed_text_and_function_call_propagated_to_prediction_record(self, mock_git, mock_generate, mock_get_questions):
        mock_get_questions.return_value = [self.sample_question]
        mock_git.return_value = {"git_commit": "abc", "git_branch": "main", "git_dirty": False}
        mock_generate.return_value = LLMResponse(
            text="Final Answer: 42",
            raw_text="Final Answer: 42",
            finish_reason="STOP",
            response_part_types=["text", "function_call"],
            response_part_count=2,
            has_text_part=True,
            has_function_call_part=True,
        )

        record = run_one(index=0, log=False)
        self.assertEqual(record["schema_version"], 2)
        self.assertTrue(record["request_success"])
        self.assertTrue(record["completion_success"])
        self.assertEqual(record["final_answer"], "42")
        self.assertEqual(record["response_part_types"], ["text", "function_call"])
        self.assertEqual(record["response_part_count"], 2)
        self.assertTrue(record["has_text_part"])
        self.assertTrue(record["has_function_call_part"])


if __name__ == "__main__":
    unittest.main()
