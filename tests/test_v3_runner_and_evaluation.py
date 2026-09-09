import os
import json
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

from agent.agent import GAIAAgent, GAIAWebAgent, GAIAFileAgent, GAIAPythonAgent
from agent.llm import LLMResponse
from evaluation.dataset import GAIATask
from evaluation.evaluate import calculate_metrics, evaluate_predictions
import evaluation.run_level as run_level_module
import evaluation.run_one as run_one_module
import evaluation.evaluate as evaluate_module


class TestV3RunnerAndEvaluationIntegration(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.sample_dataset_path = os.path.join(self.test_dir, "metadata.jsonl")

        self.sample_tasks = [
            {
                "task_id": "task-v3-001",
                "Question": "What is 10 + 20?",
                "Level": 1,
                "Final answer": "30",
                "file_name": "",
                "file_path": "",
            },
            {
                "task_id": "task-v3-002",
                "Question": "What is the sum in numbers.csv?",
                "Level": 1,
                "Final answer": "100",
                "file_name": "numbers.csv",
                "file_path": "data/gaia/2023/validation/numbers.csv",
            },
            {
                "task_id": "task-v3-003",
                "Question": "What is 50 * 2?",
                "Level": 1,
                "Final answer": "100",
                "file_name": "",
                "file_path": "",
            },
        ]

        with open(self.sample_dataset_path, "w", encoding="utf-8") as f:
            for t in self.sample_tasks:
                f.write(json.dumps(t) + "\n")

        self.tasks_by_id = {
            t["task_id"]: GAIATask(
                task_id=t["task_id"],
                question=t["Question"],
                level=t["Level"],
                final_answer=t["Final answer"],
                file_name=t["file_name"] or None,
                file_path=t["file_path"] or None,
            )
            for t in self.sample_tasks
        }

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------
    # 1-3. run_level CLI and Agent Construction Tests
    # -------------------------------------------------------------
    def test_cli_version_choices(self):
        """1, 4, 5. Verify run_level, run_one, and evaluate CLI choices include v0, v1, v2, v3."""
        import re
        for mod, name in [
            (run_level_module, "run_level.py"),
            (run_one_module, "run_one.py"),
            (evaluate_module, "evaluate.py"),
        ]:
            with open(os.path.abspath(mod.__file__), "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn('choices=["v0", "v1", "v2", "v3"]', content, f"Missing choices in {name}")

    @patch("agent.llm.LLMClient.generate")
    @patch("evaluation.runner.get_git_metadata")
    def test_run_level_constructs_correct_agent_classes(self, mock_git, mock_gen):
        """2-3. Verify run_level constructs GAIAPythonAgent for v3, GAIAFileAgent for v2,
        GAIAWebAgent for v1, and GAIAAgent for v0 without fallthrough."""
        mock_git.return_value = {"git_commit": "abc", "git_branch": "v3", "git_dirty": False}
        mock_gen.return_value = LLMResponse(text="FINAL: 30", finish_reason="STOP")

        captured_agents = {}

        def mock_execute_task(**kwargs):
            agent = kwargs.get("agent")
            captured_agents[kwargs.get("project_version")] = agent
            return {
                "schema_version": 2,
                "run_id": "test-run",
                "timestamp": "2026-01-01T00:00:00Z",
                "project_version": kwargs.get("project_version"),
                "git_commit": "abc",
                "git_branch": "test",
                "git_dirty": False,
                "task_id": kwargs.get("task_id"),
                "level": kwargs.get("level"),
                "question": kwargs.get("question"),
                "attachment_required": False,
                "file_name": None,
                "model": "gemini",
                "temperature": None,
                "max_output_tokens": 2048,
                "thinking_level": "medium",
                "prompt_version": "test",
                "primary_prompt_version": "test",
                "fallback_prompt_version": None,
                "prompt": "test",
                "raw_response": "30",
                "normalized_response": "30",
                "final_answer": "30",
                "finish_reason": "STOP",
                "input_tokens": 10,
                "output_tokens": 10,
                "thinking_tokens": 0,
                "total_tokens": 20,
                "response_id": "resp-1",
                "model_version": "v1",
                "response_part_types": ["text"],
                "response_part_count": 1,
                "has_text_part": True,
                "has_function_call_part": False,
                "latency_seconds": 1.0,
                "request_success": True,
                "completion_success": True,
                "error_type": None,
                "error_message": None,
            }

        with patch("evaluation.run_level.execute_task", side_effect=mock_execute_task):
            for v in ["v3", "v2", "v1", "v0"]:
                out_file = os.path.join(self.test_dir, f"preds_{v}.jsonl")
                run_level_module.run_level(
                    level=1,
                    data_path=self.sample_dataset_path,
                    limit=1,
                    output_file=out_file,
                    resume=False,
                    auto_eval=False,
                    version=v,
                )

        # 2. Verify v3 constructs GAIAPythonAgent
        self.assertIsInstance(captured_agents["v3"], GAIAPythonAgent)
        # 3. Verify v3 does NOT fall through to GAIAAgent
        self.assertNotEqual(type(captured_agents["v3"]), GAIAAgent)
        self.assertEqual(type(captured_agents["v3"]), GAIAPythonAgent)

        # Verify other versions
        self.assertIsInstance(captured_agents["v2"], GAIAFileAgent)
        self.assertEqual(type(captured_agents["v2"]), GAIAFileAgent)

        self.assertIsInstance(captured_agents["v1"], GAIAWebAgent)
        self.assertEqual(type(captured_agents["v1"]), GAIAWebAgent)

        self.assertEqual(type(captured_agents["v0"]), GAIAAgent)

    def test_evaluate_cli_deduplicated_version_argument(self):
        """6. Verify duplicate --version argument is gone from evaluate.py."""
        import re
        evaluate_py_path = os.path.abspath(evaluate_module.__file__)
        if evaluate_py_path.endswith(".pyc"):
            evaluate_py_path = evaluate_py_path[:-1]
        with open(evaluate_py_path, "r", encoding="utf-8") as f:
            content = f.read()

        version_args = re.findall(r'add_argument\(\s*["\']--version["\']', content)
        self.assertEqual(len(version_args), 1, f"Expected exactly 1 '--version' argument in evaluate.py, found {len(version_args)}")

    def test_run_level_deduplicated_imports(self):
        """Verify duplicate imports in run_level.py and evaluate.py are removed."""
        for mod, mod_name in [(run_level_module, "run_level.py"), (evaluate_module, "evaluate.py")]:
            fpath = os.path.abspath(mod.__file__)
            if fpath.endswith(".pyc"):
                fpath = fpath[:-1]
            with open(fpath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            import_lines = [l.strip() for l in lines if l.strip().startswith("from ") or l.strip().startswith("import ")]
            self.assertEqual(len(import_lines), len(set(import_lines)), f"Duplicate import lines found in {mod_name}")

    # -------------------------------------------------------------
    # 7-16. Metrics & Evaluation Aggregation Tests for V3
    # -------------------------------------------------------------
    def test_v3_metrics_calculation_and_aggregation(self):
        """Tests 7-16 covering V3 metrics calculation, prompt provenance, rates, and privacy."""
        predictions = [
            # Task 1: Python requested, executed, success, correct
            {
                "task_id": "task-v3-001",
                "level": 1,
                "project_version": "v3",
                "prompt_version": "python-execution-v1",
                "primary_prompt_version": "python-execution-v1",
                "fallback_prompt_version": None,
                "final_answer": "30",
                "request_success": True,
                "completion_success": True,
                "latency_seconds": 2.0,
                "attachment_required": False,
                "python_prompt_version": "python-execution-v1",
                "llm_generation_count": 1,
                "python_requested": True,
                "python_executed": True,
                "python_execution_count": 1,
                "python_success": True,
                "python_timeout": False,
                "python_exit_code": 0,
                "python_error_type": None,
                "python_latency_seconds": 0.5,
                "python_stdout_length": 25,
                "python_stderr_length": 0,
                "python_output_truncated": False,
                "python_fallback": False,
            },
            # Task 2: Python requested, executed, failed (timeout), fallback, incorrect
            {
                "task_id": "task-v3-002",
                "level": 1,
                "project_version": "v3",
                "prompt_version": "python-execution-v1",
                "primary_prompt_version": "python-execution-v1",
                "fallback_prompt_version": None,
                "final_answer": "999",  # incorrect
                "request_success": True,
                "completion_success": True,
                "latency_seconds": 3.0,
                "attachment_required": True,
                "python_prompt_version": "python-execution-v1",
                "llm_generation_count": 1,
                "python_requested": True,
                "python_executed": True,
                "python_execution_count": 1,
                "python_success": False,
                "python_timeout": True,
                "python_exit_code": None,
                "python_error_type": "TimeoutError",
                "python_latency_seconds": 2.0,
                "python_stdout_length": 0,
                "python_stderr_length": 50,
                "python_output_truncated": False,
                "python_fallback": True,
            },
            # Task 3: Direct answer (Option A), Python NOT requested, NOT executed, correct
            {
                "task_id": "task-v3-003",
                "level": 1,
                "project_version": "v3",
                "prompt_version": "python-execution-v1",
                "primary_prompt_version": "python-execution-v1",
                "fallback_prompt_version": None,
                "final_answer": "100",  # correct
                "request_success": True,
                "completion_success": True,
                "latency_seconds": 1.5,
                "attachment_required": False,
                "python_prompt_version": "python-execution-v1",
                "llm_generation_count": 1,
                "python_requested": False,
                "python_executed": False,
                "python_execution_count": 0,
                "python_success": False,
                "python_timeout": False,
                "python_exit_code": None,
                "python_error_type": None,
                "python_latency_seconds": None,
                "python_stdout_length": 0,
                "python_stderr_length": 0,
                "python_output_truncated": False,
                "python_fallback": False,
            },
        ]

        result = calculate_metrics(
            predictions=predictions,
            tasks_by_id=self.tasks_by_id,
            level=1,
            project_version="v3",
        )

        summary = result["summary"]
        detailed = result["detailed"]

        # 7. V3 summary reports project_version == "v3"
        self.assertEqual(summary["project_version"], "v3")

        # 8. V3 summary reports correct Python prompt provenance
        self.assertEqual(summary["prompt_version"], "python-execution-v1")
        self.assertEqual(summary["primary_prompt_version"], "python-execution-v1")
        self.assertIsNone(summary["fallback_prompt_version"])

        # 9. Python execution count aggregates correctly (2 executed out of 3 tasks)
        self.assertTrue(summary["python_enabled"])
        self.assertEqual(summary["python_requested_count"], 2)
        self.assertEqual(summary["python_execution_count"], 2)

        # 10. Python success rate uses executed tasks as denominator: 1 success / 2 executed = 0.50
        self.assertEqual(summary["python_success_count"], 1)
        self.assertEqual(summary["python_success_rate"], 0.5)

        # 11. Python execution rate uses total tasks as denominator: 2 executed / 3 total = 0.6667
        self.assertEqual(summary["python_execution_rate"], round(2 / 3, 4))

        # 12. Python-executed accuracy: 1 correct / 2 executed = 0.50
        self.assertEqual(summary["python_executed_correct"], 1)
        self.assertEqual(summary["python_executed_accuracy"], 0.5)

        # 13. Python-not-executed accuracy: 1 correct / 1 not executed = 1.0
        self.assertEqual(summary["python_not_executed_count"], 1)
        self.assertEqual(summary["python_not_executed_correct"], 1)
        self.assertEqual(summary["python_not_executed_accuracy"], 1.0)

        # 14. Python timeouts and fallbacks aggregate correctly
        self.assertEqual(summary["python_failure_count"], 1)
        self.assertEqual(summary["python_timeout_count"], 1)
        self.assertEqual(summary["python_fallback_count"], 1)
        self.assertEqual(summary["average_python_latency_seconds"], 1.25)  # (0.5 + 2.0) / 2

        # 15. Private detailed eval contains operational Python metadata
        self.assertEqual(len(detailed), 3)
        for d in detailed:
            self.assertIn("python_prompt_version", d)
            self.assertIn("llm_generation_count", d)
            self.assertIn("python_requested", d)
            self.assertIn("python_executed", d)
            self.assertIn("python_execution_count", d)
            self.assertIn("python_success", d)
            self.assertIn("python_timeout", d)
            self.assertIn("python_exit_code", d)
            self.assertIn("python_error_type", d)
            self.assertIn("python_latency_seconds", d)
            self.assertIn("python_stdout_length", d)
            self.assertIn("python_stderr_length", d)
            self.assertIn("python_output_truncated", d)
            self.assertIn("python_fallback", d)

        # 16. Public summary contains NO generated Python code, stdout, stderr, or attachments
        summary_keys = set(summary.keys())
        for forbidden in ["code", "python_code", "raw_stdout", "raw_stderr", "stdout", "stderr", "attachment_content"]:
            self.assertNotIn(forbidden, summary_keys)
        summary_str = json.dumps(summary)
        self.assertNotIn("print(", summary_str)
        self.assertNotIn("import ", summary_str)

    # -------------------------------------------------------------
    # 17. V0/V1/V2 evaluation results/provenance remain unchanged
    # -------------------------------------------------------------
    def test_v0_v1_v2_provenance_unchanged(self):
        """17. Verify V0, V1, V2 evaluation results and prompt provenance remain unchanged."""
        # V0 test
        v0_preds = [
            {
                "task_id": "task-v3-001",
                "level": 1,
                "project_version": "v0",
                "prompt_version": "baseline-v1",
                "final_answer": "30",
                "request_success": True,
                "completion_success": True,
            }
        ]
        res_v0 = calculate_metrics(v0_preds, self.tasks_by_id, level=1, project_version="v0")
        self.assertEqual(res_v0["summary"]["project_version"], "v0")
        self.assertEqual(res_v0["summary"]["prompt_version"], "baseline-v1")
        self.assertFalse(res_v0["summary"].get("python_enabled", False))

        # V1 test
        v1_preds = [
            {
                "task_id": "task-v3-001",
                "level": 1,
                "project_version": "v1",
                "prompt_version": "web-search-v1",
                "primary_prompt_version": "web-search-v1",
                "fallback_prompt_version": "baseline-v1",
                "search_enabled": True,
                "search_provider": "tavily",
                "search_call_count": 1,
                "search_success": True,
                "final_answer": "30",
                "request_success": True,
                "completion_success": True,
            }
        ]
        res_v1 = calculate_metrics(v1_preds, self.tasks_by_id, level=1, project_version="v1")
        self.assertEqual(res_v1["summary"]["project_version"], "v1")
        self.assertEqual(res_v1["summary"]["prompt_version"], "web-search-v1")
        self.assertEqual(res_v1["summary"]["primary_prompt_version"], "web-search-v1")
        self.assertEqual(res_v1["summary"]["fallback_prompt_version"], "baseline-v1")
        self.assertTrue(res_v1["summary"].get("search_enabled", False))
        self.assertFalse(res_v1["summary"].get("python_enabled", False))

        # V2 test (file attachment)
        v2_preds = [
            {
                "task_id": "task-v3-002",
                "level": 1,
                "project_version": "v2",
                "prompt_version": "file-search-v1",
                "primary_prompt_version": "file-search-v1",
                "fallback_prompt_version": "web-search-v1",
                "attachment_required": True,
                "file_enabled": True,
                "file_processing_attempted": True,
                "file_processing_success": True,
                "final_answer": "100",
                "request_success": True,
                "completion_success": True,
            }
        ]
        res_v2 = calculate_metrics(v2_preds, self.tasks_by_id, level=1, project_version="v2")
        self.assertEqual(res_v2["summary"]["project_version"], "v2")
        self.assertEqual(res_v2["summary"]["prompt_version"], "file-search-v1")
        self.assertEqual(res_v2["summary"]["primary_prompt_version"], "file-search-v1")
        self.assertEqual(res_v2["summary"]["fallback_prompt_version"], "web-search-v1")
        self.assertTrue(res_v2["summary"].get("file_enabled", False))
        self.assertFalse(res_v2["summary"].get("python_enabled", False))


if __name__ == "__main__":
    unittest.main()
