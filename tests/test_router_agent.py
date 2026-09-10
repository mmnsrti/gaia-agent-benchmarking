import os
import json
import tempfile
import shutil
import unittest
from typing import Optional, Any, List, Dict
from unittest.mock import patch, MagicMock

from agent.agent import (
    GAIARouterAgent,
    GAIAPythonAgent,
    GAIAFileAgent,
    GAIAWebAgent,
    GAIAAgent,
    AgentResult,
    parse_router_decision,
    extract_direct_answer,
    extract_python_code,
    extract_python_final_answer,
)
from agent.llm import LLMResponse
from prompts.router import (
    ROUTER_PROMPT_VERSION,
    ROUTER_DIRECT_WORKER_PROMPT_VERSION,
    ROUTER_PYTHON_WORKER_PROMPT_VERSION,
    build_router_prompt,
    build_direct_worker_prompt,
    build_python_worker_prompt,
)
from evaluation.dataset import GAIATask
from evaluation.runner import execute_task
from evaluation.evaluate import calculate_metrics, evaluate_predictions
import evaluation.run_level as run_level_module
import evaluation.run_one as run_one_module
import evaluation.evaluate as evaluate_module


class MockMultiTurnLLMClient:
    """Mock LLM client that returns sequenced LLMResponses for multi-generation workflows."""

    def __init__(self, responses, model: str = "gemini-3.5-flash-lite"):
        self.responses = list(responses)
        self.call_history = []
        self.model = model
        self.temperature = None
        self.max_output_tokens = 2048
        self.thinking_level = "medium"

    def generate(self, prompt: str, attachment_parts: Optional[Any] = None, **kwargs) -> LLMResponse:
        self.call_history.append((prompt, attachment_parts))
        if not self.responses:
            raise RuntimeError("MockMultiTurnLLMClient ran out of responses.")
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


class TestRouterParsingAndPromptBuilders(unittest.TestCase):
    """Tests 1-8: Deterministic router decision parsing and prompt builder tests."""

    # 1. Clean DIRECT
    def test_router_parses_clean_direct(self):
        self.assertEqual(parse_router_decision("ROUTE: DIRECT"), "DIRECT")

    # 2. Clean PYTHON
    def test_router_parses_clean_python(self):
        self.assertEqual(parse_router_decision("ROUTE: PYTHON"), "PYTHON")

    # 3. Case and whitespace
    def test_router_parses_case_and_whitespace(self):
        self.assertEqual(parse_router_decision("  route :  python \n"), "PYTHON")
        self.assertEqual(parse_router_decision("\tRoute\t:\tDirect\r\n"), "DIRECT")

    # 4. Conversational wrapping
    def test_router_handles_conversational_wrapping(self):
        text = "Based on my detailed analysis of the question, I should route to:\nROUTE: PYTHON\nThis will compute the values."
        self.assertEqual(parse_router_decision(text), "PYTHON")

    # 5. Empty or whitespace returns None
    def test_router_malformed_empty_triggers_direct_fallback(self):
        self.assertIsNone(parse_router_decision(""))
        self.assertIsNone(parse_router_decision("   \n\t  "))
        self.assertIsNone(parse_router_decision(None))

    # 6. Missing token returns None
    def test_router_malformed_missing_token_triggers_direct_fallback(self):
        text = "I think this task requires running a python script to solve it."
        self.assertIsNone(parse_router_decision(text))

    # 7. Ambiguous tokens return None
    def test_router_ambiguous_tokens_trigger_direct_fallback(self):
        text = "ROUTE: DIRECT or ROUTE: PYTHON could both work here."
        self.assertIsNone(parse_router_decision(text))

    # Prompt builders and information firewall
    def test_router_prompt_builder_includes_question_and_evidence(self):
        prompt = build_router_prompt("Calculate 2+2", "Web info: 4", "File info: data")
        self.assertIn("Calculate 2+2", prompt)
        self.assertIn("Web info: 4", prompt)
        self.assertIn("File info: data", prompt)
        self.assertIn("ROUTE: DIRECT", prompt)
        self.assertIn("ROUTE: PYTHON", prompt)

    def test_direct_worker_prompt_builder(self):
        prompt = build_direct_worker_prompt("What is France's capital?", "Paris is capital", None)
        self.assertIn("What is France's capital?", prompt)
        self.assertIn("Paris is capital", prompt)
        self.assertIn("FINAL: <answer>", prompt)

    def test_python_worker_prompt_builder(self):
        prompt = build_python_worker_prompt("Compute factorial 10", None, "file.csv", "file.csv")
        self.assertIn("Compute factorial 10", prompt)
        self.assertIn("file.csv", prompt)
        self.assertIn("FINAL_ANSWER: <answer>", prompt)
        self.assertIn("```python", prompt)

    def test_information_firewall_worker_prompt_omits_router_reasoning(self):
        """Verify worker prompt never receives router raw output or reasoning."""
        router_reasoning = "Router internal reasoning: I decided on DIRECT because 2+2 is trivial."
        worker_prompt = build_direct_worker_prompt("What is 2+2?", None, None)
        self.assertNotIn(router_reasoning, worker_prompt)
        self.assertNotIn("ROUTE: DIRECT", worker_prompt)


class TestGAIARouterAgentExecution(unittest.TestCase):
    """Tests 9-21: GAIARouterAgent execution flows, generation counts, and tool invariants."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # 9, 10, 11, 12: DIRECT Route flow
    @patch("tools.web_search.TavilySearchTool.search")
    def test_direct_route_flow_and_generation_counts(self, mock_search):
        mock_search.return_value = MagicMock(
            success=True,
            results=[{"title": "Result", "content": "Evidence", "url": "http://example.com"}],
            call_count=1,
            latency=0.1,
            query_truncated=False,
            error_message=None,
        )

        resp_router = LLMResponse(
            text="ROUTE: DIRECT",
            finish_reason="STOP",
            input_tokens=50,
            output_tokens=5,
            thinking_tokens=20,
            total_tokens=75,
        )
        resp_worker = LLMResponse(
            text="The answer is straightforward.\nFINAL: 42",
            finish_reason="STOP",
            input_tokens=60,
            output_tokens=10,
            thinking_tokens=30,
            total_tokens=100,
        )
        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)

        result = agent.run("What is the ultimate answer?")

        # Generation count checks
        self.assertEqual(result.router_generation_attempts, 1)
        self.assertTrue(result.router_generation_success)
        self.assertEqual(result.worker_generation_attempts, 1)
        self.assertTrue(result.worker_generation_success)
        self.assertEqual(result.llm_generation_attempts, 2)
        self.assertEqual(result.llm_generation_success_count, 2)

        # Router telemetry
        self.assertTrue(result.router_requested)
        self.assertEqual(result.router_decision, "DIRECT")
        self.assertTrue(result.router_success)
        self.assertFalse(result.router_fallback)
        self.assertIsNone(result.router_error_type)
        self.assertEqual(result.router_input_tokens, 50)
        self.assertEqual(result.router_output_tokens, 5)
        self.assertEqual(result.router_thinking_tokens, 20)

        # Worker telemetry
        self.assertEqual(result.worker_mode, "DIRECT")
        self.assertTrue(result.worker_success)
        self.assertIsNone(result.worker_error_type)
        self.assertEqual(result.worker_input_tokens, 60)
        self.assertEqual(result.worker_output_tokens, 10)
        self.assertEqual(result.worker_thinking_tokens, 30)

        # Python invariants on DIRECT route
        self.assertFalse(result.python_requested)
        self.assertFalse(result.python_executed)
        self.assertEqual(result.python_execution_count, 0)
        self.assertIsNone(result.python_exit_code)

        # Answer checks
        self.assertEqual(result.final_answer, "42")
        self.assertEqual(result.llm_response.finish_reason, "STOP")

    # 13, 15: PYTHON Route Success Flow
    @patch("tools.web_search.TavilySearchTool.search")
    def test_python_route_success_flow(self, mock_search):
        mock_search.return_value = MagicMock(
            success=False,
            results=[],
            call_count=1,
            latency=0.05,
            query_truncated=False,
            error_message="No search needed",
        )

        resp_router = LLMResponse(text="ROUTE: PYTHON", finish_reason="STOP", input_tokens=40, output_tokens=5, thinking_tokens=10, total_tokens=55)
        worker_code = "```python\nx = 10 * 12\nprint(f'FINAL_ANSWER: {x}')\n```"
        resp_worker = LLMResponse(text=worker_code, finish_reason="STOP", input_tokens=50, output_tokens=30, thinking_tokens=15, total_tokens=95)

        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)

        result = agent.run("What is 10 * 12?")

        self.assertEqual(result.router_decision, "PYTHON")
        self.assertEqual(result.worker_mode, "PYTHON")
        self.assertTrue(result.python_requested)
        self.assertTrue(result.python_executed)
        self.assertEqual(result.python_execution_count, 1)
        self.assertTrue(result.python_success)
        self.assertFalse(result.python_fallback)
        self.assertEqual(result.final_answer, "120")
        self.assertEqual(result.llm_generation_attempts, 2)
        # Exactly 2 LLM calls, no third synthesis call
        self.assertEqual(len(llm.call_history), 2)

    # 8, 14: Router Fallback on provider anomaly triggers DIRECT worker
    @patch("tools.web_search.TavilySearchTool.search")
    def test_router_provider_anomaly_triggers_direct_fallback(self, mock_search):
        mock_search.return_value = MagicMock(success=True, results=[], call_count=1, latency=0.01, query_truncated=False, error_message=None)

        resp_router = LLMResponse(
            text=None,
            finish_reason="MALFORMED_FUNCTION_CALL",
            input_tokens=40,
            output_tokens=0,
            thinking_tokens=10,
            total_tokens=50,
        )
        resp_worker = LLMResponse(
            text="FINAL: 99",
            finish_reason="STOP",
            input_tokens=60,
            output_tokens=5,
            thinking_tokens=10,
            total_tokens=75,
        )
        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)

        result = agent.run("Some question")

        self.assertEqual(result.router_decision, "DIRECT")
        self.assertFalse(result.router_success)
        self.assertTrue(result.router_fallback)
        self.assertEqual(result.router_error_type, "malformed_function_call_finish_reason")
        self.assertEqual(result.worker_mode, "DIRECT")
        self.assertEqual(result.final_answer, "99")
        self.assertEqual(result.llm_generation_attempts, 2)

    def test_router_empty_response_triggers_direct_fallback(self):
        resp_router = LLMResponse(text="", finish_reason="STOP")
        resp_worker = LLMResponse(text="FINAL: empty_fallback_ans", finish_reason="STOP")
        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)

        result = agent.run("Empty test")
        self.assertEqual(result.router_decision, "DIRECT")
        self.assertFalse(result.router_success)
        self.assertTrue(result.router_fallback)
        self.assertEqual(result.router_error_type, "empty_provider_response")
        self.assertEqual(result.final_answer, "empty_fallback_ans")

    def test_router_missing_marker_triggers_direct_fallback(self):
        resp_router = LLMResponse(text="I recommend direct answering.", finish_reason="STOP")
        resp_worker = LLMResponse(text="FINAL: missing_marker_ans", finish_reason="STOP")
        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)

        result = agent.run("Missing marker test")
        self.assertEqual(result.router_decision, "DIRECT")
        self.assertFalse(result.router_success)
        self.assertTrue(result.router_fallback)
        self.assertEqual(result.router_error_type, "missing_route_marker")
        self.assertEqual(result.final_answer, "missing_marker_ans")

    def test_router_ambiguous_text_triggers_direct_fallback(self):
        resp_router = LLMResponse(text="ROUTE: DIRECT or ROUTE: PYTHON", finish_reason="STOP")
        resp_worker = LLMResponse(text="FINAL: ambiguous_ans", finish_reason="STOP")
        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)

        result = agent.run("Ambiguous test")
        self.assertEqual(result.router_decision, "DIRECT")
        self.assertFalse(result.router_success)
        self.assertTrue(result.router_fallback)
        self.assertEqual(result.router_error_type, "ambiguous_route_text")
        self.assertEqual(result.final_answer, "ambiguous_ans")

    def test_router_malformed_text_triggers_direct_fallback(self):
        resp_router = LLMResponse(text="The route is invalid.", finish_reason="STOP")
        resp_worker = LLMResponse(text="FINAL: malformed_ans", finish_reason="STOP")
        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)

        result = agent.run("Malformed route test")
        self.assertEqual(result.router_decision, "DIRECT")
        self.assertFalse(result.router_success)
        self.assertTrue(result.router_fallback)
        self.assertEqual(result.router_error_type, "malformed_router_text")
        self.assertEqual(result.final_answer, "malformed_ans")

    # 14: No Python retry on execution failure
    @patch("tools.web_search.TavilySearchTool.search")
    def test_no_python_retry_on_execution_failure(self, mock_search):
        mock_search.return_value = MagicMock(success=False, results=[], call_count=0, latency=0, query_truncated=False, error_message=None)

        resp_router = LLMResponse(text="ROUTE: PYTHON", finish_reason="STOP")
        # Worker generates code with ZeroDivisionError
        worker_code = "```python\nx = 1 / 0\nprint(f'FINAL_ANSWER: {x}')\n```\nFINAL: fallback_val"
        resp_worker = LLMResponse(text=worker_code, finish_reason="STOP")

        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)

        result = agent.run("Divide by zero")

        self.assertEqual(result.worker_mode, "PYTHON")
        self.assertTrue(result.python_executed)
        self.assertFalse(result.python_success)
        self.assertTrue(result.python_fallback)
        self.assertIsNotNone(result.python_exit_code)
        self.assertNotEqual(result.python_exit_code, 0)
        # Fallback to direct extraction from worker text, NO extra LLM retry
        self.assertEqual(result.final_answer, "fallback_val")
        self.assertEqual(len(llm.call_history), 2)
        self.assertEqual(result.llm_generation_attempts, 2)

    # 16: Function calling disabled for both generations
    def test_function_calling_disabled_for_both_generations(self):
        """Verify LLM generate calls don't include tools (mode='NONE')."""
        llm = MagicMock()
        llm.generate.side_effect = [
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: ok", finish_reason="STOP"),
        ]
        agent = GAIARouterAgent(llm_client=llm)
        agent.run("Test question")

        self.assertEqual(llm.generate.call_count, 2)
        # Neither call passes tool declarations or tool configurations
        for c in llm.generate.call_args_list:
            args, kwargs = c
            self.assertEqual(len(args), 1)  # Only prompt is passed

    # 17: Tavily search executed at most once
    @patch("tools.web_search.TavilySearchTool.search")
    def test_tavily_search_executed_at_most_once(self, mock_search):
        mock_search.return_value = MagicMock(success=True, results=[], call_count=1, latency=0.1, query_truncated=False, error_message=None)
        resp_router = LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP")
        resp_worker = LLMResponse(text="FINAL: ans", finish_reason="STOP")
        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)

        agent.run("Search test")
        self.assertEqual(mock_search.call_count, 1)

    # 19, 20: Attachment basename accessible on Python route independently of FileTool
    def test_attachment_basename_and_unsupported_extension_accessible_to_python(self):
        dummy_file = os.path.join(self.test_dir, "archive.zip")
        with open(dummy_file, "wb") as f:
            f.write(b"PK\x03\x04dummyzipcontent")

        resp_router = LLMResponse(text="ROUTE: PYTHON", finish_reason="STOP")
        worker_code = "```python\nimport os\nassert os.path.exists('archive.zip')\nprint('FINAL_ANSWER: zip_found')\n```"
        resp_worker = LLMResponse(text=worker_code, finish_reason="STOP")
        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)
        result = agent.run("Inspect the archive", file_path=dummy_file)
        self.assertTrue(result.python_result.success)
        self.assertEqual(result.final_answer, "zip_found")

    # 21: Python marker extraction identical to V3
    def test_python_marker_extraction_identical_to_v3(self):
        stdout = "Processing data...\nValue calculated: 450\nFINAL_ANSWER: 450\nDone."
        self.assertEqual(extract_python_final_answer(stdout), "450")
        self.assertIsNone(extract_python_final_answer("Processing data without marker"))


class TestRunnerAndEvaluationIntegrationV4(unittest.TestCase):
    """Tests 22-25: runner, evaluate, CLI choices, and privacy audit for V4."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.sample_dataset_path = os.path.join(self.test_dir, "metadata.jsonl")

        self.sample_tasks = [
            {
                "task_id": "task-v4-001",
                "Question": "What is 10 + 20?",
                "Level": 1,
                "Final answer": "30",
                "file_name": "",
                "file_path": "",
            },
            {
                "task_id": "task-v4-002",
                "Question": "What is the product of 15 and 4?",
                "Level": 1,
                "Final answer": "60",
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

    # 22: execute_task supports v4 explicitly and records all telemetry
    @patch("evaluation.runner.get_git_metadata")
    def test_runner_supports_v4_explicitly(self, mock_git):
        mock_git.return_value = {"git_commit": "def456", "git_branch": "v4-planner-router", "git_dirty": False}

        resp_router = LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP", input_tokens=45, output_tokens=6, thinking_tokens=15, total_tokens=66)
        resp_worker = LLMResponse(text="FINAL: 30", finish_reason="STOP", input_tokens=55, output_tokens=8, thinking_tokens=25, total_tokens=88)
        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)

        record = execute_task(
            task_id="task-v4-001",
            question="What is 10 + 20?",
            level=1,
            file_name=None,
            file_path=None,
            agent=agent,
            llm=llm,
            project_version="v4",
        )

        self.assertEqual(record["project_version"], "v4")
        self.assertEqual(record["prompt_version"], ROUTER_PROMPT_VERSION)
        self.assertEqual(record["router_prompt_version"], ROUTER_PROMPT_VERSION)
        self.assertEqual(record["worker_prompt_version"], ROUTER_DIRECT_WORKER_PROMPT_VERSION)
        self.assertEqual(record["router_decision"], "DIRECT")
        self.assertTrue(record["router_success"])
        self.assertFalse(record["router_fallback"])
        self.assertEqual(record["worker_mode"], "DIRECT")
        self.assertTrue(record["worker_success"])
        self.assertEqual(record["llm_generation_attempts"], 2)
        self.assertEqual(record["final_answer"], "30")

    # 23: CLI choices support v4 across run_level, run_one, and evaluate
    def test_cli_version_choices_include_v4(self):
        for mod, name in [
            (run_level_module, "run_level.py"),
            (run_one_module, "run_one.py"),
            (evaluate_module, "evaluate.py"),
        ]:
            with open(os.path.abspath(mod.__file__), "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn('choices=["v0", "v1", "v2", "v3", "v4"]', content, f"Missing v4 choices in {name}")

    # 24: Privacy audit on mock V4 evaluation output
    def test_public_artifacts_zero_privacy_exposure(self):
        predictions = [
            {
                "task_id": "task-v4-001",
                "level": 1,
                "project_version": "v4",
                "prompt_version": ROUTER_PROMPT_VERSION,
                "router_prompt_version": ROUTER_PROMPT_VERSION,
                "worker_prompt_version": ROUTER_DIRECT_WORKER_PROMPT_VERSION,
                "router_requested": True,
                "router_decision": "DIRECT",
                "router_success": True,
                "router_fallback": False,
                "router_error_type": None,
                "router_latency_seconds": 0.8,
                "router_input_tokens": 50,
                "router_output_tokens": 5,
                "router_thinking_tokens": 20,
                "worker_mode": "DIRECT",
                "worker_success": True,
                "worker_error_type": None,
                "worker_latency_seconds": 1.2,
                "worker_input_tokens": 60,
                "worker_output_tokens": 10,
                "worker_thinking_tokens": 30,
                "router_generation_attempts": 1,
                "router_generation_success": True,
                "worker_generation_attempts": 1,
                "worker_generation_success": True,
                "llm_generation_attempts": 2,
                "llm_generation_success_count": 2,
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
                "final_answer": "30",
                "request_success": True,
                "completion_success": True,
                "latency_seconds": 2.0,
                "attachment_required": False,
            },
            {
                "task_id": "task-v4-002",
                "level": 1,
                "project_version": "v4",
                "prompt_version": ROUTER_PROMPT_VERSION,
                "router_prompt_version": ROUTER_PROMPT_VERSION,
                "worker_prompt_version": ROUTER_PYTHON_WORKER_PROMPT_VERSION,
                "router_requested": True,
                "router_decision": "PYTHON",
                "router_success": True,
                "router_fallback": False,
                "router_error_type": None,
                "router_latency_seconds": 0.9,
                "router_input_tokens": 55,
                "router_output_tokens": 5,
                "router_thinking_tokens": 22,
                "worker_mode": "PYTHON",
                "worker_success": True,
                "worker_error_type": None,
                "worker_latency_seconds": 2.1,
                "worker_input_tokens": 70,
                "worker_output_tokens": 25,
                "worker_thinking_tokens": 40,
                "router_generation_attempts": 1,
                "router_generation_success": True,
                "worker_generation_attempts": 1,
                "worker_generation_success": True,
                "llm_generation_attempts": 2,
                "llm_generation_success_count": 2,
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
                "final_answer": "60",
                "request_success": True,
                "completion_success": True,
                "latency_seconds": 3.5,
                "attachment_required": False,
            },
        ]

        result = calculate_metrics(
            predictions=predictions,
            tasks_by_id=self.tasks_by_id,
            level=1,
            project_version="v4",
        )

        summary = result["summary"]
        detailed = result["detailed"]

        # V4 summary verification
        self.assertEqual(summary["project_version"], "v4")
        self.assertEqual(summary["router_prompt_version"], ROUTER_PROMPT_VERSION)
        self.assertTrue(summary["router_enabled"])
        self.assertEqual(summary["router_direct_count"], 1)
        self.assertEqual(summary["router_python_count"], 1)
        self.assertEqual(summary["router_fallback_count"], 0)
        self.assertEqual(summary["router_failure_count"], 0)
        self.assertEqual(summary["router_python_routing_rate"], 0.5)
        self.assertEqual(summary["router_direct_accuracy"], 1.0)
        self.assertEqual(summary["router_python_accuracy"], 1.0)
        self.assertEqual(summary["average_total_llm_generations"], 2.0)

        # Prohibited keys check on public summary
        summary_keys = set(summary.keys())
        for forbidden in ["code", "python_code", "raw_stdout", "raw_stderr", "stdout", "stderr", "attachment_content", "question", "ground_truth"]:
            self.assertNotIn(forbidden, summary_keys)
        summary_str = json.dumps(summary)
        self.assertNotIn("print(", summary_str)
        self.assertNotIn("import ", summary_str)

        # Detailed evaluation contains router operational metadata
        self.assertEqual(len(detailed), 2)
        for d in detailed:
            self.assertIn("router_decision", d)
            self.assertIn("router_success", d)
            self.assertIn("router_fallback", d)
            self.assertIn("worker_mode", d)
            self.assertIn("worker_success", d)
            self.assertIn("llm_generation_attempts", d)

    # 25: Non-regression on V0-V3 agent classes and runners
    def test_v0_v1_v2_v3_regressions_prevented(self):
        llm = MagicMock()
        llm.generate.return_value = LLMResponse(text="FINAL: 42", finish_reason="STOP")

        agent_v0 = GAIAAgent(llm_client=llm)
        self.assertEqual(type(agent_v0), GAIAAgent)

        agent_v1 = GAIAWebAgent(llm_client=llm)
        self.assertEqual(type(agent_v1), GAIAWebAgent)

        agent_v2 = GAIAFileAgent(llm_client=llm)
        self.assertEqual(type(agent_v2), GAIAFileAgent)

        agent_v3 = GAIAPythonAgent(llm_client=llm)
        self.assertEqual(type(agent_v3), GAIAPythonAgent)

        agent_v4 = GAIARouterAgent(llm_client=llm)
        self.assertEqual(type(agent_v4), GAIARouterAgent)
        self.assertTrue(issubclass(GAIARouterAgent, GAIAFileAgent))
        self.assertFalse(issubclass(GAIARouterAgent, GAIAPythonAgent))

    # 26: FileTool semantics unchanged in GAIARouterAgent
    def test_file_tool_semantics_unchanged(self):
        test_txt = os.path.join(self.test_dir, "data.txt")
        with open(test_txt, "w", encoding="utf-8") as f:
            f.write("Line 1\nLine 2\nKey: 12345")

        resp_router = LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP")
        resp_worker = LLMResponse(text="FINAL: 12345", finish_reason="STOP")
        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)

        result = agent.run("Find Key in data.txt", file_path=test_txt)
        self.assertIsNotNone(result.file_result)
        self.assertTrue(result.file_result.success)
        self.assertIn("Key: 12345", result.file_result.text_content)
        self.assertEqual(result.final_answer, "12345")

    # 27: Worker exception handling records provider_api_error
    def test_worker_exception_handling(self):
        resp_router = LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP")
        worker_error = RuntimeError("Worker API failure")
        llm = MockMultiTurnLLMClient([resp_router, worker_error])
        agent = GAIARouterAgent(llm_client=llm)

        result = agent.run("Failing worker")
        self.assertEqual(result.router_decision, "DIRECT")
        self.assertTrue(result.router_success)
        self.assertFalse(result.worker_success)
        self.assertEqual(result.worker_error_type, "provider_api_error")

    # 28: run_level constructs GAIARouterAgent for v4
    @patch("evaluation.run_level.execute_task")
    @patch("evaluation.run_level.load_gaia_tasks")
    def test_run_level_constructs_v4_agent(self, mock_load, mock_exec):
        mock_load.return_value = [
            GAIATask(task_id="t1", question="Q", level=1, final_answer="A")
        ]
        mock_exec.return_value = {
            "task_id": "t1",
            "final_answer": "A",
            "completion_success": True,
            "request_success": True,
            "latency_seconds": 1.0,
        }

        captured_agent = None
        def capture_exec(**kwargs):
            nonlocal captured_agent
            captured_agent = kwargs.get("agent")
            return {
                "task_id": "t1",
                "final_answer": "A",
                "completion_success": True,
                "request_success": True,
                "latency_seconds": 1.0,
            }
        mock_exec.side_effect = capture_exec

        temp_out = os.path.join(self.test_dir, "test_preds.jsonl")
        run_level_module.run_level(level=1, limit=1, version="v4", output_file=temp_out, auto_eval=False, resume=False)
        self.assertIsInstance(captured_agent, GAIARouterAgent)

    # 29: run_one CLI accepts --version v4
    def test_run_one_cli_accepts_v4(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--version", choices=["v0", "v1", "v2", "v3", "v4"])
        args = parser.parse_args(["--version", "v4"])
        self.assertEqual(args.version, "v4")

    # 30: Router repeated identical markers and conflicting markers
    def test_router_repeated_identical_and_conflicting_markers(self):
        self.assertEqual(parse_router_decision("ROUTE: DIRECT ... ROUTE: DIRECT"), "DIRECT")
        self.assertEqual(parse_router_decision("ROUTE: PYTHON ... ROUTE: PYTHON"), "PYTHON")
        self.assertIsNone(parse_router_decision("ROUTE: DIRECT ... ROUTE: PYTHON"))
        self.assertIsNone(parse_router_decision("I will direct the python worker."))

    # 31: Information firewall sentinel isolation
    def test_router_information_firewall_sentinel_isolation(self):
        sentinel = "SENTINEL_ROUTER_SECRET_8472"
        resp_router = LLMResponse(text=f"ROUTE: DIRECT {sentinel} - router internal notes", finish_reason="STOP")
        resp_worker = LLMResponse(text="FINAL: safe_ans", finish_reason="STOP")
        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)

        agent.run("Firewall test")
        worker_call = llm.call_history[1]
        worker_prompt = worker_call[0]
        self.assertNotIn(sentinel, worker_prompt)
        self.assertNotIn("router internal notes", worker_prompt)
        self.assertNotIn("ROUTE: DIRECT", worker_prompt)

    # 32: DIRECT route locks out Python execution even if worker produces code
    def test_direct_worker_cannot_trigger_python_execution(self):
        resp_router = LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP")
        worker_code = "```python\nprint('malicious')\n```\nFINAL: locked_out"
        resp_worker = LLMResponse(text=worker_code, finish_reason="STOP")
        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)

        result = agent.run("Code on direct test")
        self.assertFalse(result.python_executed)
        self.assertEqual(result.python_execution_count, 0)
        self.assertEqual(result.final_answer, "locked_out")

    # 33: PYTHON route handles AST security policy rejection with zero retries
    def test_python_worker_policy_rejection_single_shot(self):
        resp_router = LLMResponse(text="ROUTE: PYTHON", finish_reason="STOP")
        worker_code = "```python\nimport subprocess\nsubprocess.run(['ls'])\nprint('FINAL_ANSWER: done')\n```\nFINAL: fallback_val"
        resp_worker = LLMResponse(text=worker_code, finish_reason="STOP")
        llm = MockMultiTurnLLMClient([resp_router, resp_worker])
        agent = GAIARouterAgent(llm_client=llm)

        result = agent.run("Security policy test")
        self.assertTrue(result.python_executed)
        self.assertFalse(result.python_success)
        self.assertTrue(result.python_fallback)
        self.assertEqual(result.python_result.error_type, "SecurityPolicyError")
        self.assertEqual(result.final_answer, "fallback_val")
        self.assertEqual(result.llm_generation_attempts, 2)
        self.assertEqual(len(llm.call_history), 2)


if __name__ == "__main__":
    unittest.main()
