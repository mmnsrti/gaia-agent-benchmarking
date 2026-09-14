import unittest
import os
import json
import tempfile
from unittest.mock import patch, MagicMock
from evaluation.run_level import is_provider_collapse, run_level
from evaluation.dataset import GAIATask


class TestRunLevelHardening(unittest.TestCase):
    def test_ordinary_task_failures_do_not_trigger_provider_collapse(self):
        ordinary_records = [
            {"worker_error_type": "malformed_function_call_finish_reason", "request_success": True},
            {"router_error_type": "missing_route_marker", "request_success": True},
            {"router_error_type": "ambiguous_route_text", "request_success": True},
            {"worker_error_type": "empty_worker_response", "request_success": True},
            {"verifier_error_type": "malformed_verdict", "request_success": True},
            {"self_eval_error_type": "malformed_assessment", "request_success": True},
            {"repair_error_type": "malformed_repair_action", "request_success": True},
            {"active_verification_error_type": "unexpected_verification_content", "request_success": True},
            {"active_verification_search_error_type": "search_empty_results", "request_success": True},
            {"python_error_type": "syntax_error", "request_success": True},
            {"file_error_type": "unsupported_file_extension", "request_success": True},
            {"final_answer": None, "completion_success": False, "request_success": True},
            {"finish_reason": "MAX_TOKENS", "completion_success": False, "request_success": True},
        ]
        for rec in ordinary_records:
            is_collapse, reason = is_provider_collapse(rec)
            self.assertFalse(
                is_collapse,
                f"Record {rec} should NOT be detected as provider collapse, but got: {reason}",
            )

    def test_explicit_provider_collapse_detected_across_stages(self):
        provider_collapse_records = [
            {"router_error_type": "provider_api_error"},
            {"worker_error_type": "provider_api_error"},
            {"verifier_error_type": "provider_api_error"},
            {"self_eval_error_type": "provider_api_error"},
            {"repair_error_type": "provider_api_error"},
            {"active_verification_error_type": "provider_api_error"},
            {"search_error_type": "search_rate_limit"},
            {"search_error_type": "search_auth_error"},
            {"error_message": "429 RESOURCE_EXHAUSTED: Quota exceeded"},
            {"error_message": "401 UNAUTHENTICATED: Invalid API key"},
            {"worker_error_type": "429: GenerateRequestsPerDayPerProjectPerModel-FreeTier"},
            {"active_verification_search_error_type": "search_rate_limit"},
        ]
        for rec in provider_collapse_records:
            is_collapse, reason = is_provider_collapse(rec)
            self.assertTrue(
                is_collapse,
                f"Record {rec} MUST be detected as provider collapse, but was not!",
            )
            self.assertTrue(len(reason) > 0)

    def test_benchmark_halts_on_provider_collapse_and_preserves_healthy_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "predictions.jsonl")

            mock_tasks = [
                GAIATask(task_id="t1", question="Q1", level=1, final_answer="A1"),
                GAIATask(task_id="t2", question="Q2", level=1, final_answer="A2"),
                GAIATask(task_id="t3", question="Q3", level=1, final_answer="A3"),
            ]

            # Task 1 succeeds normally
            rec1 = {
                "task_id": "t1",
                "request_success": True,
                "completion_success": True,
                "final_answer": "A1",
                "latency_seconds": 0.5,
            }
            # Task 2 encounters ordinary failure (e.g. malformed function call) -> should NOT halt
            rec2 = {
                "task_id": "t2",
                "request_success": True,
                "completion_success": False,
                "final_answer": None,
                "worker_error_type": "malformed_function_call_finish_reason",
                "latency_seconds": 0.5,
            }
            # Task 3 encounters explicit provider API error -> MUST halt
            rec3 = {
                "task_id": "t3",
                "request_success": False,
                "completion_success": False,
                "final_answer": None,
                "router_error_type": "provider_api_error",
                "error_message": "429 RESOURCE_EXHAUSTED",
                "latency_seconds": 0.5,
            }

            with patch("evaluation.run_level.load_gaia_tasks", return_value=mock_tasks), \
                 patch("evaluation.run_level.execute_task", side_effect=[rec1, rec2, rec3]), \
                 patch("evaluation.run_level.LLMClient"):
                run_level(
                    level=1,
                    output_file=out_file,
                    resume=False,
                    auto_eval=False,
                    version="v8",
                )

            self.assertTrue(os.path.exists(out_file))
            with open(out_file, "r", encoding="utf-8") as f:
                saved = [json.loads(line) for line in f if line.strip()]

            # Healthy task 1 and ordinary failure task 2 are preserved
            self.assertEqual(len(saved), 2)
            self.assertEqual(saved[0]["task_id"], "t1")
            self.assertEqual(saved[1]["task_id"], "t2")
            # Collapsed task 3 was NOT saved as completed
            self.assertNotIn("t3", [r["task_id"] for r in saved])


if __name__ == "__main__":
    unittest.main()
