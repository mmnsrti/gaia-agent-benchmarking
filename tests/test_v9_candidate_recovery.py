import json
import unittest
from typing import Any, List, Optional

from agent.agent import (
    GAIARouterAgent,
    GAIAVerificationAgent,
    GAIASelfEvaluationAgent,
    GAIATargetedRepairAgent,
    GAIAUpstreamCandidateRecoveryAgent,
    classify_candidate_recovery_failure,
    is_candidate_recovery_eligible,
    ELIGIBLE_RECOVERY_FAILURE_CLASSES,
)
from agent.llm import LLMResponse
from evaluation.dataset import GAIATask
from evaluation.evaluate import calculate_metrics
from evaluation.runner import execute_task
from evaluation.candidate_recovery_metrics import calculate_candidate_recovery_metrics
from prompts.candidate_recovery import (
    CANDIDATE_RECOVERY_PROMPT_VERSION,
    build_candidate_recovery_prompt,
    parse_candidate_recovery_result,
)
from tools.file_tool import FileResult
from tools.web_search import WebSearchResult, SearchResultItem


class StubSearchTool:
    def __init__(self, success: bool = True, snippet: str = "Search evidence snippet"):
        self.success = success
        self.snippet = snippet
        self.calls = 0

    def search(self, question: str) -> WebSearchResult:
        self.calls += 1
        item = SearchResultItem(
            title="Evidence",
            url="https://example.com",
            content=self.snippet,
        )
        return WebSearchResult(query=question, success=self.success, results=[item])


class CountingFileTool:
    def __init__(self):
        self.calls = 0

    def process(self, file_path: str) -> FileResult:
        self.calls += 1
        return FileResult(
            file_name="attachment.txt",
            file_extension=".txt",
            success=True,
            content_mode="text",
            text_content="Existing file attachment context.",
            processor="test",
        )


class MockPythonTool:
    def __init__(self, success: bool = True, output: str = "", timed_out: bool = False, exit_code: int = 0):
        self.calls = 0
        self.success = success
        self.output = output
        self.timed_out = timed_out
        self.exit_code = exit_code

    def execute(self, code: str, *args, **kwargs) -> Any:
        self.calls += 1
        from tools.python_tool import PythonResult
        return PythonResult(
            success=self.success,
            executed=True,
            exit_code=self.exit_code,
            stdout=self.output,
            stderr="",
            error_type=None if self.success else "ExecutionError",
            timed_out=self.timed_out,
            latency_seconds=0.01,
            code=code,
            code_length=len(code),
            stdout_length=len(self.output),
            stderr_length=0,
        )


class SequencedLLM:
    """No-network test double that records generation calls."""

    def __init__(self, responses: List[Any]):
        self.responses = list(responses)
        self.calls = []
        self.model = "gemini-3.5-flash-lite"
        self.temperature = None
        self.max_output_tokens = 2048
        self.thinking_level = "medium"

    def generate(
        self,
        prompt: str,
        attachment_parts: Optional[Any] = None,
        max_retries: int = 3,
    ) -> LLMResponse:
        self.calls.append({
            "prompt": prompt,
            "attachment_parts": attachment_parts,
            "max_retries": max_retries,
        })
        if not self.responses:
            raise RuntimeError("SequencedLLM ran out of mock responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_resp(
    text: str,
    finish_reason: str = "STOP",
    input_tokens: int = 100,
    output_tokens: int = 20,
    thinking_tokens: int = 0,
    has_text_part: Optional[bool] = None,
    has_function_call_part: bool = False,
    response_part_types: Optional[List[str]] = None,
) -> LLMResponse:
    if has_text_part is None:
        has_text_part = bool(text and text.strip())
    if response_part_types is None:
        types = []
        if thinking_tokens > 0:
            types.append("thought")
        if has_text_part:
            types.append("text")
        if has_function_call_part:
            types.append("function_call")
        response_part_types = types
    return LLMResponse(
        text=text,
        raw_text=text,
        finish_reason=finish_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        total_tokens=input_tokens + output_tokens + thinking_tokens,
        has_text_part=has_text_part,
        has_function_call_part=has_function_call_part,
        response_part_types=response_part_types,
    )


class TestCandidateRecoveryParser(unittest.TestCase):
    """Tests for Candidate Recovery output parsing and taxonomy enforcement."""

    def test_valid_candidates(self):
        valid_cases = [
            ("FINAL: 42", "42"),
            ("  FINAL : 3.14159 ", "3.14159"),
            ("final: Paris, France", "Paris, France"),
            ("FINAL: answer with spaces and punctuation (e.g. 10%)", "answer with spaces and punctuation (e.g. 10%)"),
            ("\nFINAL: recovered_value\n", "recovered_value"),
        ]
        for payload, expected in valid_cases:
            with self.subTest(payload=payload):
                parsed = parse_candidate_recovery_result(payload)
                self.assertTrue(parsed.is_valid)
                self.assertEqual(parsed.status, "VALID")
                self.assertEqual(parsed.candidate, expected)
                self.assertIsNone(parsed.error_type)

    def test_parser_error_taxonomy(self):
        invalid_cases = [
            ("", "empty_recovery_response"),
            ("   \n\t", "empty_recovery_response"),
            ("```text\nFINAL: 42\n```", "markdown_code_fence"),
            ("```python\nx = 42\n```", "markdown_code_fence"),
            ("The answer is 42", "missing_final_marker"),
            ("ANSWER: 42", "missing_final_marker"),
            ("FINAL:", "empty_final_value"),
            ("FINAL:    \n\t", "empty_final_value"),
            ("FINAL: 42\nExtra line after final", "multiline_candidate"),
        ]
        for payload, expected_err in invalid_cases:
            with self.subTest(payload=payload, expected_err=expected_err):
                parsed = parse_candidate_recovery_result(payload)
                self.assertFalse(parsed.is_valid)
                self.assertEqual(parsed.status, "INVALID")
                self.assertIsNone(parsed.candidate)
                self.assertEqual(parsed.error_type, expected_err)


class TestFailureClassificationAndPrecedence(unittest.TestCase):
    """Tests for exact 10-step failure classification precedence."""

    def test_provider_error_ineligible(self):
        from agent.agent import AgentResult
        res = AgentResult(raw_response="", final_answer="", worker_error_type="provider_timeout")
        fc = classify_candidate_recovery_failure(res, worker_mode="DIRECT")
        self.assertEqual(fc, "PROVIDER_ERROR")
        self.assertFalse(is_candidate_recovery_eligible(fc))

    def test_python_output_missing_marker(self):
        from agent.agent import AgentResult
        from tools.python_tool import PythonResult
        py_res = PythonResult(success=False, executed=True, code="print('done')", error_type="MissingFinalAnswerMarker", stdout="Calculation complete without marker")
        res = AgentResult(raw_response="", final_answer="", python_result=py_res, python_executed=True, worker_mode="PYTHON")
        fc = classify_candidate_recovery_failure(res, worker_mode="PYTHON")
        self.assertEqual(fc, "PYTHON_OUTPUT_MISSING_MARKER")
        self.assertTrue(is_candidate_recovery_eligible(fc))

    def test_python_execution_failure(self):
        from agent.agent import AgentResult
        from tools.python_tool import PythonResult
        py_res = PythonResult(success=False, executed=True, code="1/0", error_type="ZeroDivisionError", exit_code=1)
        res = AgentResult(raw_response="", final_answer="", python_result=py_res, python_executed=True, worker_mode="PYTHON")
        fc = classify_candidate_recovery_failure(res, worker_mode="PYTHON")
        self.assertEqual(fc, "PYTHON_EXECUTION_FAILURE")
        self.assertTrue(is_candidate_recovery_eligible(fc))

    def test_python_code_extraction_failure(self):
        from agent.agent import AgentResult
        # Route was PYTHON, but no python executed and error_type indicates code extraction failure
        res = AgentResult(raw_response="Here is some text with no python block", final_answer="", worker_mode="PYTHON", python_requested=False)
        fc = classify_candidate_recovery_failure(res, worker_mode="PYTHON")
        self.assertEqual(fc, "PYTHON_CODE_EXTRACTION_FAILURE")
        self.assertTrue(is_candidate_recovery_eligible(fc))

    def test_malformed_function_call(self):
        from agent.agent import AgentResult
        llm_resp = make_resp("", finish_reason="MALFORMED_FUNCTION_CALL")
        res = AgentResult(raw_response="", final_answer="", llm_response=llm_resp)
        fc = classify_candidate_recovery_failure(res, worker_mode="DIRECT")
        self.assertEqual(fc, "MALFORMED_FUNCTION_CALL")
        self.assertTrue(is_candidate_recovery_eligible(fc))

    def test_function_call_only(self):
        from agent.agent import AgentResult
        llm_resp = make_resp("", has_text_part=False, has_function_call_part=True, response_part_types=["function_call"])
        res = AgentResult(raw_response="", final_answer="", llm_response=llm_resp)
        fc = classify_candidate_recovery_failure(res, worker_mode="DIRECT")
        self.assertEqual(fc, "FUNCTION_CALL_ONLY")
        self.assertTrue(is_candidate_recovery_eligible(fc))

    def test_thought_only(self):
        from agent.agent import AgentResult
        llm_resp = make_resp("", output_tokens=0, thinking_tokens=150)
        res = AgentResult(raw_response="", final_answer="", llm_response=llm_resp)
        fc = classify_candidate_recovery_failure(res, worker_mode="DIRECT")
        self.assertEqual(fc, "THOUGHT_ONLY")
        self.assertTrue(is_candidate_recovery_eligible(fc))

    def test_direct_extraction_failure(self):
        from agent.agent import AgentResult
        llm_resp = make_resp("I believe the solution involves adding the numbers together.")
        res = AgentResult(raw_response=llm_resp.text, final_answer="", llm_response=llm_resp, worker_raw_response=llm_resp.text, worker_mode="DIRECT")
        fc = classify_candidate_recovery_failure(res, worker_mode="DIRECT")
        self.assertEqual(fc, "DIRECT_EXTRACTION_FAILURE")
        self.assertTrue(is_candidate_recovery_eligible(fc))

    def test_empty_response(self):
        from agent.agent import AgentResult
        llm_resp = make_resp("")
        res = AgentResult(raw_response="", final_answer="", llm_response=llm_resp, worker_raw_response="")
        fc = classify_candidate_recovery_failure(res, worker_mode="DIRECT")
        self.assertEqual(fc, "EMPTY_RESPONSE")
        self.assertTrue(is_candidate_recovery_eligible(fc))

    def test_unknown_no_candidate(self):
        # Case where worker_mode is None or unrecognized and text is non-empty
        from agent.agent import AgentResult
        res = AgentResult(raw_response="Unrouted text output", final_answer="", worker_raw_response="Unrouted text output")
        fc = classify_candidate_recovery_failure(res, worker_mode=None)
        self.assertEqual(fc, "UNKNOWN_NO_CANDIDATE")
        self.assertFalse(is_candidate_recovery_eligible(fc))

    def test_precedence_function_call_over_empty_response(self):
        from agent.agent import AgentResult
        # Empty text, but has function call part
        llm_resp = make_resp("", has_text_part=False, has_function_call_part=True)
        res = AgentResult(final_answer="", llm_response=llm_resp, raw_response="")
        fc = classify_candidate_recovery_failure(res, worker_mode="DIRECT")
        self.assertEqual(fc, "FUNCTION_CALL_ONLY")
        self.assertNotEqual(fc, "EMPTY_RESPONSE")

    def test_precedence_thought_only_over_empty_response(self):
        from agent.agent import AgentResult
        # Empty text, but positive thinking tokens
        llm_resp = make_resp("", output_tokens=0, thinking_tokens=200)
        res = AgentResult(final_answer="", llm_response=llm_resp, raw_response="")
        fc = classify_candidate_recovery_failure(res, worker_mode="DIRECT")
        self.assertEqual(fc, "THOUGHT_ONLY")
        self.assertNotEqual(fc, "EMPTY_RESPONSE")


class TestV9ControlledSmokeScenarios(unittest.TestCase):
    """Verifies all 18 preregistered smoke scenarios with deterministic mocks."""

    def _create_agent(self, responses: List[Any], search_success: bool = True):
        llm = SequencedLLM(responses)
        agent = GAIAUpstreamCandidateRecoveryAgent(
            llm_client=llm,
            search_tool=StubSearchTool(success=search_success),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(success=True, output=""),
        )
        return agent, llm

    def test_scenario_1_normal_direct_worker_bypass(self):
        # Normal DIRECT worker candidate -> bypass recovery (eligible=False, triggered=False, preserved=100%)
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp("FINAL: 42"),
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95"),
        ]
        agent, llm = self._create_agent(responses)
        result = agent.run("What is 40 + 2?")

        self.assertEqual(result.pre_recovery_candidate, "42")
        self.assertEqual(result.post_recovery_candidate, "42")
        self.assertFalse(result.candidate_recovery_eligible)
        self.assertFalse(result.candidate_recovery_triggered)
        self.assertFalse(result.candidate_recovery_attempted)
        self.assertTrue(result.candidate_recovery_non_triggered_preserved)
        self.assertEqual(result.final_answer, "42")
        # 4 generations: router (1) + worker (1) + verifier (1) + self_eval (1)
        self.assertEqual(result.llm_generation_attempts, 4)

    def test_scenario_2_normal_python_worker_bypass(self):
        # Normal PYTHON worker candidate -> bypass recovery
        responses = [
            make_resp("ROUTE: PYTHON"),
            make_resp("```python\nprint('FINAL_ANSWER: 100')\n```"),
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95"),
        ]
        agent, llm = self._create_agent(responses)
        agent.python_tool = MockPythonTool(success=True, output="FINAL_ANSWER: 100")
        result = agent.run("Calculate 10 * 10")

        self.assertEqual(result.pre_recovery_candidate, "100")
        self.assertEqual(result.post_recovery_candidate, "100")
        self.assertFalse(result.candidate_recovery_eligible)
        self.assertFalse(result.candidate_recovery_triggered)
        self.assertEqual(result.final_answer, "100")
        self.assertEqual(result.llm_generation_attempts, 4)

    def test_scenario_3_python_output_missing_marker(self):
        # Python executed successfully but output lacked FINAL: marker
        responses = [
            make_resp("ROUTE: PYTHON"),
            make_resp("```python\nprint('Computed answer is 42')\n```"),
            make_resp("FINAL: 42"),  # Recovery generation
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95"),
        ]
        agent, llm = self._create_agent(responses)
        agent.python_tool = MockPythonTool(success=True, output="Computed answer is 42")
        result = agent.run("Calculate something")

        self.assertEqual(result.pre_recovery_candidate, "")
        self.assertTrue(result.candidate_recovery_eligible)
        self.assertTrue(result.candidate_recovery_triggered)
        self.assertTrue(result.candidate_recovery_attempted)
        self.assertTrue(result.candidate_recovery_success)
        self.assertTrue(result.candidate_recovery_recovered)
        self.assertEqual(result.candidate_recovery_failure_class, "PYTHON_OUTPUT_MISSING_MARKER")
        self.assertEqual(result.post_recovery_candidate, "42")
        self.assertEqual(result.final_answer, "42")
        self.assertEqual(result.llm_generation_attempts, 5)

    def test_scenario_4_python_execution_failure(self):
        # Python script raised an error -> recovery triggers
        responses = [
            make_resp("ROUTE: PYTHON"),
            make_resp("```python\nimport non_existent_mod\n```"),
            make_resp("FINAL: fallback_value"),  # Recovery generation
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.90"),
        ]
        agent, llm = self._create_agent(responses)
        agent.python_tool = MockPythonTool(success=False, output="ModuleNotFoundError: non_existent_mod", exit_code=1)
        result = agent.run("Run code")

        self.assertTrue(result.candidate_recovery_triggered)
        self.assertEqual(result.candidate_recovery_failure_class, "PYTHON_EXECUTION_FAILURE")
        self.assertEqual(result.post_recovery_candidate, "fallback_value")
        self.assertEqual(result.final_answer, "fallback_value")

    def test_scenario_5_python_code_extraction_failure(self):
        # Worker failed to output a valid python block
        responses = [
            make_resp("ROUTE: PYTHON"),
            make_resp("I forgot to include code blocks."),
            make_resp("FINAL: recovered_text"),  # Recovery generation
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.90"),
        ]
        agent, llm = self._create_agent(responses)
        result = agent.run("Run code")

        self.assertTrue(result.candidate_recovery_triggered)
        self.assertEqual(result.candidate_recovery_failure_class, "PYTHON_CODE_EXTRACTION_FAILURE")
        self.assertEqual(result.post_recovery_candidate, "recovered_text")

    def test_scenario_6_malformed_function_call(self):
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp("", finish_reason="MALFORMED_FUNCTION_CALL"),
            make_resp("FINAL: recovered_from_mfc"),  # Recovery generation
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.90"),
        ]
        agent, llm = self._create_agent(responses)
        result = agent.run("Query")

        self.assertTrue(result.candidate_recovery_triggered)
        self.assertEqual(result.candidate_recovery_failure_class, "MALFORMED_FUNCTION_CALL")
        self.assertEqual(result.post_recovery_candidate, "recovered_from_mfc")

    def test_scenario_7_function_call_only(self):
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp("", has_text_part=False, has_function_call_part=True, response_part_types=["function_call"]),
            make_resp("FINAL: recovered_from_fco"),  # Recovery generation
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.90"),
        ]
        agent, llm = self._create_agent(responses)
        result = agent.run("Query")

        self.assertTrue(result.candidate_recovery_triggered)
        self.assertEqual(result.candidate_recovery_failure_class, "FUNCTION_CALL_ONLY")
        self.assertEqual(result.post_recovery_candidate, "recovered_from_fco")

    def test_scenario_8_thought_only(self):
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp("", output_tokens=0, thinking_tokens=120),
            make_resp("FINAL: recovered_from_to"),  # Recovery generation
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.90"),
        ]
        agent, llm = self._create_agent(responses)
        result = agent.run("Query")

        self.assertTrue(result.candidate_recovery_triggered)
        self.assertEqual(result.candidate_recovery_failure_class, "THOUGHT_ONLY")
        self.assertEqual(result.post_recovery_candidate, "recovered_from_to")

    def test_scenario_9_direct_extraction_failure(self):
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp("FINAL: "),
            make_resp("FINAL: Paris"),  # Recovery generation
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.90"),
        ]
        agent, llm = self._create_agent(responses)
        result = agent.run("What is capital of France?")

        self.assertTrue(result.candidate_recovery_triggered)
        self.assertEqual(result.candidate_recovery_failure_class, "DIRECT_EXTRACTION_FAILURE")
        self.assertEqual(result.post_recovery_candidate, "Paris")

    def test_scenario_10_empty_response(self):
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp(""),
            make_resp("FINAL: recovered_from_empty"),  # Recovery generation
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.90"),
        ]
        agent, llm = self._create_agent(responses)
        result = agent.run("Question")

        self.assertTrue(result.candidate_recovery_triggered)
        self.assertEqual(result.candidate_recovery_failure_class, "EMPTY_RESPONSE")
        self.assertEqual(result.post_recovery_candidate, "recovered_from_empty")

    def test_scenario_11_provider_timeout_bypass(self):
        # Provider error in router or worker must NOT trigger recovery
        responses = [
            make_resp("ROUTE: DIRECT"),
            Exception("provider_timeout: deadline exceeded"),
        ]
        agent, llm = self._create_agent(responses)
        result = agent.run("Question")

        self.assertFalse(result.candidate_recovery_eligible)
        self.assertFalse(result.candidate_recovery_triggered)
        self.assertEqual(result.candidate_recovery_failure_class, "PROVIDER_ERROR")
        self.assertEqual(result.final_answer, "")

    def test_scenario_12_provider_api_error_bypass(self):
        responses = [
            Exception("provider_api_error: 500 internal server error"),
        ]
        agent, llm = self._create_agent(responses)
        result = agent.run("Question")

        self.assertFalse(result.candidate_recovery_eligible)
        self.assertFalse(result.candidate_recovery_triggered)
        self.assertEqual(result.candidate_recovery_failure_class, "PROVIDER_ERROR")

    def test_scenario_13_precedence_function_call_only(self):
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp("", has_text_part=False, has_function_call_part=True),
            make_resp("FINAL: recovered_fc"),
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.90"),
        ]
        agent, llm = self._create_agent(responses)
        result = agent.run("Question")

        self.assertEqual(result.candidate_recovery_failure_class, "FUNCTION_CALL_ONLY")

    def test_scenario_14_precedence_thought_only(self):
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp("", output_tokens=0, thinking_tokens=80),
            make_resp("FINAL: recovered_thought"),
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.90"),
        ]
        agent, llm = self._create_agent(responses)
        result = agent.run("Question")

        self.assertEqual(result.candidate_recovery_failure_class, "THOUGHT_ONLY")

    def test_scenario_15_recovery_output_empty(self):
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp(""),
            make_resp("   \n"),  # Recovery generation returns whitespace
        ]
        agent, llm = self._create_agent(responses)
        result = agent.run("Question")

        self.assertTrue(result.candidate_recovery_triggered)
        self.assertTrue(result.candidate_recovery_attempted)
        self.assertFalse(result.candidate_recovery_success)
        self.assertEqual(result.candidate_recovery_error_type, "empty_recovery_response")
        self.assertEqual(result.post_recovery_candidate, "")
        self.assertEqual(result.final_answer, "")
        # Downstream verifier is not eligible because candidate is empty
        self.assertFalse(result.verifier_attempted)

    def test_scenario_16_recovery_output_malformed_code_fence(self):
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp(""),
            make_resp("```\nFINAL: 42\n```"),  # Recovery violates code fence constraint
        ]
        agent, llm = self._create_agent(responses)
        result = agent.run("Question")

        self.assertTrue(result.candidate_recovery_triggered)
        self.assertFalse(result.candidate_recovery_success)
        self.assertEqual(result.candidate_recovery_error_type, "markdown_code_fence")
        self.assertEqual(result.post_recovery_candidate, "")
        self.assertEqual(result.final_answer, "")

    def test_scenario_17_recovery_provider_exception(self):
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp(""),
            RuntimeError("Provider network disconnect during recovery"),
        ]
        agent, llm = self._create_agent(responses)
        result = agent.run("Question")

        self.assertTrue(result.candidate_recovery_triggered)
        self.assertTrue(result.candidate_recovery_attempted)
        self.assertFalse(result.candidate_recovery_success)
        self.assertEqual(result.candidate_recovery_error_type, "provider_api_error")
        self.assertEqual(result.post_recovery_candidate, "")
        self.assertEqual(result.final_answer, "")

    def test_scenario_18_budget_enforcement_and_zero_tools(self):
        # Verify maximum 6 generations budget and zero added tool calls
        search_tool = StubSearchTool(success=True)
        file_tool = CountingFileTool()
        python_tool = MockPythonTool(success=True, output="")
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp(""),
            make_resp("FINAL: recovered_value"),
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: SUSPECT\nCONFIDENCE: 0.85\nRISK_TYPE: REASONING"),
            make_resp("REPAIR_ACTION: REPLACE\nFINAL: final_repaired_value"),
        ]
        llm = SequencedLLM(responses)
        agent = GAIAUpstreamCandidateRecoveryAgent(
            llm_client=llm,
            search_tool=search_tool,
            file_tool=file_tool,
            python_tool=python_tool,
        )
        result = agent.run("Full pipeline test", file_path="sample.txt")

        self.assertLessEqual(result.llm_generation_attempts, 6)
        self.assertEqual(result.llm_generation_attempts, 6)
        self.assertEqual(result.candidate_recovery_searches_added, 0)
        self.assertEqual(result.candidate_recovery_python_runs_added, 0)
        # Verify search was only called once at the start of GAIAAgent
        self.assertEqual(search_tool.calls, 1)
        # Verify file tool was called once
        self.assertEqual(file_tool.calls, 1)
        # Python tool was never called on DIRECT route
        self.assertEqual(python_tool.calls, 0)
        self.assertEqual(result.final_answer, "final_repaired_value")


class TestV9PipelineIntegration(unittest.TestCase):
    """Verifies complete end-to-end integration through runner and evaluator."""

    def test_recovered_candidate_flows_into_downstream_safeguards(self):
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp(""),  # Upstream starved
            make_resp("FINAL: tentative_candidate"),  # Recovery
            make_resp("VERDICT: REVISE\nFINAL: refined_candidate"),  # V5 verifier
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95"),  # V6 evaluator
        ]
        llm = SequencedLLM(responses)
        agent = GAIAUpstreamCandidateRecoveryAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        result = agent.run("Integration question")

        self.assertEqual(result.pre_recovery_candidate, "")
        self.assertEqual(result.post_recovery_candidate, "tentative_candidate")
        self.assertEqual(result.pre_verification_answer, "tentative_candidate")
        self.assertEqual(result.post_verification_answer, "refined_candidate")
        self.assertEqual(result.final_answer, "refined_candidate")

    def test_execute_task_v9_integration(self):
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp(""),
            make_resp("FINAL: recovered_42"),
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95"),
        ]
        llm = SequencedLLM(responses)
        record = execute_task(
            task_id="task_test_001",
            question="What is 40 + 2?",
            level=1,
            llm=llm,
            project_version="v9",
        )

        self.assertEqual(record["schema_version"], 7)
        self.assertEqual(record["project_version"], "v9")
        self.assertTrue(record["completion_success"])
        self.assertEqual(record["final_answer"], "recovered_42")
        self.assertTrue(record["candidate_recovery_triggered"])
        self.assertTrue(record["candidate_recovery_recovered"])
        self.assertEqual(record["post_recovery_candidate"], "recovered_42")

    def test_non_triggered_preservation_invariant(self):
        responses = [
            make_resp("ROUTE: DIRECT"),
            make_resp("FINAL: direct_ans"),
            make_resp("VERDICT: KEEP"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95"),
        ]
        llm = SequencedLLM(responses)
        agent = GAIAUpstreamCandidateRecoveryAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        result = agent.run("Preservation question")

        self.assertFalse(result.candidate_recovery_triggered)
        self.assertTrue(result.candidate_recovery_non_triggered_preserved)
        self.assertEqual(result.post_recovery_candidate, result.pre_recovery_candidate)


class TestCandidateRecoveryMetrics(unittest.TestCase):
    """Tests metric calculations including reachability and safeguard effects."""

    def test_calculate_metrics(self):
        records = [
            # Record 1: Non-triggered (already had candidate), correct
            {
                "task_id": "t1",
                "ground_truth": "42",
                "pre_recovery_candidate": "42",
                "post_recovery_candidate": "42",
                "pre_verification_answer": "42",
                "final_answer": "42",
                "completion_success": True,
                "candidate_recovery_eligible": False,
                "candidate_recovery_triggered": False,
                "candidate_recovery_attempted": False,
                "candidate_recovery_success": False,
                "candidate_recovery_recovered": False,
                "candidate_recovery_failure_class": None,
                "candidate_recovery_non_triggered_preserved": True,
            },
            # Record 2: Triggered, recovered correct, final correct
            {
                "task_id": "t2",
                "ground_truth": "Paris",
                "pre_recovery_candidate": "",
                "post_recovery_candidate": "Paris",
                "pre_verification_answer": "Paris",
                "final_answer": "Paris",
                "completion_success": True,
                "candidate_recovery_eligible": True,
                "candidate_recovery_triggered": True,
                "candidate_recovery_attempted": True,
                "candidate_recovery_success": True,
                "candidate_recovery_recovered": True,
                "candidate_recovery_failure_class": "DIRECT_EXTRACTION_FAILURE",
                "candidate_recovery_non_triggered_preserved": True,
            },
            # Record 3: Triggered, recovered wrong, final wrong
            {
                "task_id": "t3",
                "ground_truth": "Berlin",
                "pre_recovery_candidate": "",
                "post_recovery_candidate": "London",
                "pre_verification_answer": "London",
                "final_answer": "London",
                "completion_success": True,
                "candidate_recovery_eligible": True,
                "candidate_recovery_triggered": True,
                "candidate_recovery_attempted": True,
                "candidate_recovery_success": True,
                "candidate_recovery_recovered": True,
                "candidate_recovery_failure_class": "EMPTY_RESPONSE",
                "candidate_recovery_non_triggered_preserved": True,
            },
            # Record 4: Triggered, recovery attempted but failed
            {
                "task_id": "t4",
                "ground_truth": "Rome",
                "pre_recovery_candidate": "",
                "post_recovery_candidate": "",
                "pre_verification_answer": "",
                "final_answer": "",
                "completion_success": False,
                "candidate_recovery_eligible": True,
                "candidate_recovery_triggered": True,
                "candidate_recovery_attempted": True,
                "candidate_recovery_success": False,
                "candidate_recovery_recovered": False,
                "candidate_recovery_failure_class": "PYTHON_EXECUTION_FAILURE",
                "candidate_recovery_non_triggered_preserved": True,
            },
        ]
        metrics = calculate_candidate_recovery_metrics(records, total_benchmark_tasks=4)

        self.assertEqual(metrics["reachability_pre_recovery_count"], 1)
        self.assertEqual(metrics["reachability_post_recovery_count"], 3)
        self.assertEqual(metrics["reachability_rate_pre_recovery"], 0.25)
        self.assertEqual(metrics["reachability_rate_post_recovery"], 0.75)
        self.assertEqual(metrics["reachability_net_gain"], 2)
        self.assertEqual(metrics["candidate_recovery_triggered_count"], 3)
        self.assertEqual(metrics["candidate_recovery_recovered_count"], 2)
        self.assertEqual(metrics["candidate_recovery_non_triggered_preservation_rate"], 1.0)
        self.assertEqual(metrics["candidate_recovery_downstream_safeguard_breakdown"]["RECOVERY_CORRECT_FINAL_CORRECT"], 1)
        self.assertEqual(metrics["candidate_recovery_downstream_safeguard_breakdown"]["RECOVERY_WRONG_FINAL_WRONG"], 1)


if __name__ == "__main__":
    unittest.main()
