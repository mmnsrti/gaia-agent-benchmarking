import os
import json
import tempfile
import shutil
import unittest
from typing import Optional, Any, List, Dict
from unittest.mock import patch, MagicMock

from agent.agent import (
    GAIAVerificationAgent,
    GAIARouterAgent,
    GAIAPythonAgent,
    GAIAFileAgent,
    GAIAWebAgent,
    GAIAAgent,
    AgentResult,
    parse_router_decision,
)
from agent.llm import LLMResponse, LLMClient
from prompts.verification import (
    VERIFICATION_PROMPT_VERSION,
    build_verifier_prompt,
    parse_verifier_result,
    VerifierParseResult,
)
from evaluation.dataset import GAIATask
from evaluation.runner import execute_task
from evaluation.evaluate import calculate_metrics
import evaluation.run_level as run_level_module
import evaluation.run_one as run_one_module


class MockMultiTurnLLMClient:
    """Mock LLM client that returns sequenced LLMResponses for multi-generation workflows."""

    def __init__(self, responses, model: str = "gemini-3.5-flash-lite"):
        self.responses = list(responses)
        self.call_history: List[Any] = []
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


class TestVerifierPromptAndParser(unittest.TestCase):
    """Items 1-14: Deterministic verifier decision parsing and prompt builder tests."""

    # 1. Clean KEEP parse
    def test_01_parse_clean_keep(self):
        res = parse_verifier_result("VERDICT: KEEP")
        self.assertTrue(res.is_valid)
        self.assertEqual(res.verdict, "KEEP")
        self.assertIsNone(res.revised_answer)
        self.assertIsNone(res.error_type)

    # 2. Case-insensitive verdict: keep
    def test_02_parse_case_insensitive_keep(self):
        res = parse_verifier_result("verdict: keep")
        self.assertTrue(res.is_valid)
        self.assertEqual(res.verdict, "KEEP")

    # 3. Whitespace around KEEP
    def test_03_parse_whitespace_around_keep(self):
        res = parse_verifier_result("   \n  VERDICT :   KEEP   \n  ")
        self.assertTrue(res.is_valid)
        self.assertEqual(res.verdict, "KEEP")

    # 4. Inline VERDICT: KEEP
    def test_04_parse_inline_keep(self):
        res = parse_verifier_result("After careful checking, VERDICT: KEEP seems right.")
        self.assertTrue(res.is_valid)
        self.assertEqual(res.verdict, "KEEP")

    # 5. Conversational text around KEEP ignored
    def test_05_parse_conversational_text_around_keep(self):
        text = "The answer is mathematically sound and matches the table.\nVERDICT: KEEP\nNo changes needed."
        res = parse_verifier_result(text)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.verdict, "KEEP")

    # 6. Clean REVISE parse with FINAL: <answer>
    def test_06_parse_clean_revise(self):
        res = parse_verifier_result("VERDICT: REVISE\nFINAL: 42")
        self.assertTrue(res.is_valid)
        self.assertEqual(res.verdict, "REVISE")
        self.assertEqual(res.revised_answer, "42")
        self.assertIsNone(res.error_type)

    # 7. Case-insensitive verdict: revise and final: <answer>
    def test_07_parse_case_insensitive_revise(self):
        res = parse_verifier_result("verdict: revise\nfinal: Paris")
        self.assertTrue(res.is_valid)
        self.assertEqual(res.verdict, "REVISE")
        self.assertEqual(res.revised_answer, "Paris")

    # 8. Multiline revised answer with FINAL
    def test_08_parse_multiline_revised_answer(self):
        res = parse_verifier_result("VERDICT: REVISE\nFINAL: Line 1\nLine 2")
        self.assertTrue(res.is_valid)
        self.assertEqual(res.verdict, "REVISE")
        self.assertEqual(res.revised_answer, "Line 1\nLine 2")

    # 9. empty_verifier_response (None or "")
    def test_09_parse_empty_verifier_response(self):
        res_none = parse_verifier_result(None)
        self.assertFalse(res_none.is_valid)
        self.assertEqual(res_none.error_type, "empty_verifier_response")

        res_empty = parse_verifier_result("   \n\t  ")
        self.assertFalse(res_empty.is_valid)
        self.assertEqual(res_empty.error_type, "empty_verifier_response")

    # 10. missing_verdict (text without VERDICT marker)
    def test_10_parse_missing_verdict(self):
        res = parse_verifier_result("I think the answer is correct and should not be changed.")
        self.assertFalse(res.is_valid)
        self.assertEqual(res.error_type, "missing_verdict")

    # 11. ambiguous_verdict (conflicting KEEP and REVISE)
    def test_11_parse_ambiguous_verdict(self):
        res = parse_verifier_result("VERDICT: KEEP\nWait, actually VERDICT: REVISE\nFINAL: 10")
        self.assertFalse(res.is_valid)
        self.assertEqual(res.error_type, "ambiguous_verdict")

    # 12. malformed_verifier_text ("verdict" keyword with unparseable word)
    def test_12_parse_malformed_verifier_text(self):
        res = parse_verifier_result("VERDICT: MAYBE\nFINAL: 10")
        self.assertFalse(res.is_valid)
        self.assertEqual(res.error_type, "malformed_verifier_text")

    # 13. revise_missing_final (REVISE without FINAL:)
    def test_13_parse_revise_missing_final(self):
        res = parse_verifier_result("VERDICT: REVISE\nThe answer should be 42 instead.")
        self.assertFalse(res.is_valid)
        self.assertEqual(res.error_type, "revise_missing_final")

    # 14. revise_empty_final (REVISE with empty FINAL:)
    def test_14_parse_revise_empty_final(self):
        res = parse_verifier_result("VERDICT: REVISE\nFINAL:   \n  ")
        self.assertFalse(res.is_valid)
        self.assertEqual(res.error_type, "revise_empty_final")


class TestVerifierEligibilityAndFlow(unittest.TestCase):
    """Items 15-22: Eligibility and answer transition flow tests."""

    # 15. Candidate empty string -> verifier skipped
    def test_15_candidate_empty_string_skips_verifier(self):
        # router -> worker returns empty
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("What is the capital?")
        self.assertFalse(res.verifier_eligible)
        self.assertFalse(res.verifier_attempted)
        self.assertEqual(res.verifier_generation_attempts, 0)
        self.assertEqual(res.final_answer, "")
        self.assertEqual(res.post_verification_answer, "")
        self.assertEqual(len(mock_llm.call_history), 2)  # Router + Worker only

    # 16. Candidate whitespace only -> verifier skipped
    def test_16_candidate_whitespace_skips_verifier(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="   \n\t  ", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("What is the capital?")
        self.assertFalse(res.verifier_eligible)
        self.assertFalse(res.verifier_attempted)
        self.assertEqual(res.verifier_generation_attempts, 0)
        self.assertEqual(len(mock_llm.call_history), 2)

    # 17. Candidate None/empty -> verifier skipped
    def test_17_candidate_none_skips_verifier(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("What is the capital?")
        self.assertFalse(res.verifier_eligible)
        self.assertFalse(res.verifier_attempted)

    # 18. Upstream router error leading to empty candidate -> verifier skipped
    def test_18_upstream_error_skips_verifier(self):
        # Router fails with provider error, fallback to DIRECT worker, worker returns empty
        mock_llm = MockMultiTurnLLMClient([
            Exception("API connection timeout"),
            LLMResponse(text="", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("What is the capital?")
        self.assertTrue(res.router_fallback)
        self.assertFalse(res.verifier_eligible)
        self.assertFalse(res.verifier_attempted)
        self.assertEqual(res.verifier_generation_attempts, 0)

    # 19. Candidate non-empty -> verifier attempted
    def test_19_candidate_non_empty_attempts_verifier(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: Tokyo", finish_reason="STOP"),
            LLMResponse(text="VERDICT: KEEP", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("What is the capital of Japan?")
        self.assertTrue(res.verifier_eligible)
        self.assertTrue(res.verifier_attempted)
        self.assertEqual(res.verifier_generation_attempts, 1)
        self.assertEqual(len(mock_llm.call_history), 3)

    # 20. Pre-verification answer preserved on KEEP
    def test_20_pre_verification_answer_preserved_on_keep(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            LLMResponse(text="VERDICT: KEEP", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("Compute answer")
        self.assertEqual(res.pre_verification_answer, "42")
        self.assertEqual(res.post_verification_answer, "42")
        self.assertEqual(res.final_answer, "42")
        self.assertEqual(res.verifier_verdict, "KEEP")
        self.assertFalse(res.verifier_revised)
        self.assertFalse(res.verifier_fallback)

    # 21. Pre-verification answer replaced with revised answer on REVISE
    def test_21_pre_verification_answer_replaced_on_revise(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: 41", finish_reason="STOP"),
            LLMResponse(text="VERDICT: REVISE\nFINAL: 42", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("Compute answer")
        self.assertEqual(res.pre_verification_answer, "41")
        self.assertEqual(res.post_verification_answer, "42")
        self.assertEqual(res.final_answer, "42")
        self.assertEqual(res.verifier_verdict, "REVISE")
        self.assertTrue(res.verifier_revised)
        self.assertFalse(res.verifier_fallback)

    # 22. Revision whitespace stripped and FINAL ANSWER: prefix cleaned
    def test_22_revision_cleaned_properly(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: incorrect", finish_reason="STOP"),
            LLMResponse(text="VERDICT: REVISE\nFINAL: Final Answer: 100 kg  ", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("Compute weight")
        self.assertEqual(res.pre_verification_answer, "incorrect")
        self.assertEqual(res.post_verification_answer, "100 kg")
        self.assertEqual(res.final_answer, "100 kg")


class TestVerifierNonDestructiveFailurePolicy(unittest.TestCase):
    """Items 23-30: Verifier exception and fallback preservation tests."""

    # 23. Verifier provider timeout preserves answer
    def test_23_verifier_timeout_fallback(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            Exception("Request timed out / deadline exceeded"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("Question")
        self.assertEqual(res.pre_verification_answer, "42")
        self.assertEqual(res.post_verification_answer, "42")
        self.assertEqual(res.final_answer, "42")
        self.assertTrue(res.verifier_fallback)
        self.assertEqual(res.verifier_error_type, "provider_timeout")
        self.assertIsNone(res.verifier_verdict)

    # 24. Verifier provider API error preserves answer
    def test_24_verifier_api_error_fallback(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            Exception("HTTP 503 Service Unavailable"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("Question")
        self.assertEqual(res.pre_verification_answer, "42")
        self.assertEqual(res.post_verification_answer, "42")
        self.assertEqual(res.final_answer, "42")
        self.assertTrue(res.verifier_fallback)
        self.assertEqual(res.verifier_error_type, "provider_api_error")

    # 25. Verifier MALFORMED_FUNCTION_CALL finish reason
    def test_25_verifier_malformed_function_call_finish_reason(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            LLMResponse(text="", finish_reason="MALFORMED_FUNCTION_CALL"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("Question")
        self.assertEqual(res.post_verification_answer, "42")
        self.assertTrue(res.verifier_fallback)
        self.assertEqual(res.verifier_error_type, "malformed_function_call_finish_reason")

    # 26. Exception with malformed_function_call in message
    def test_26_verifier_malformed_function_call_exception(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            Exception("Model returned malformed_function_call payload"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("Question")
        self.assertEqual(res.post_verification_answer, "42")
        self.assertTrue(res.verifier_fallback)
        self.assertEqual(res.verifier_error_type, "malformed_function_call_finish_reason")

    # 27. Verifier empty response preserves answer
    def test_27_verifier_empty_response_fallback(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            LLMResponse(text="", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("Question")
        self.assertEqual(res.post_verification_answer, "42")
        self.assertTrue(res.verifier_fallback)
        self.assertEqual(res.verifier_error_type, "empty_verifier_response")

    # 28. Verifier missing verdict preserves answer
    def test_28_verifier_missing_verdict_fallback(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            LLMResponse(text="Everything looks fine to me.", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("Question")
        self.assertEqual(res.post_verification_answer, "42")
        self.assertTrue(res.verifier_fallback)
        self.assertEqual(res.verifier_error_type, "missing_verdict")

    # 29. Verifier ambiguous verdict preserves answer
    def test_29_verifier_ambiguous_verdict_fallback(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            LLMResponse(text="VERDICT: KEEP\nWait, VERDICT: REVISE\nFINAL: 99", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("Question")
        self.assertEqual(res.post_verification_answer, "42")
        self.assertTrue(res.verifier_fallback)
        self.assertEqual(res.verifier_error_type, "ambiguous_verdict")

    # 30. Verifier revise missing final preserves answer
    def test_30_verifier_revise_missing_final_fallback(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            LLMResponse(text="VERDICT: REVISE\nThe answer was calculated incorrectly.", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("Question")
        self.assertEqual(res.post_verification_answer, "42")
        self.assertTrue(res.verifier_fallback)
        self.assertEqual(res.verifier_error_type, "revise_missing_final")


class TestVerifierInvariantsAndAccounting(unittest.TestCase):
    """Items 31-38: Invariants, generation counts, and spy verification tests."""

    # 31. Generation count assertion: candidate empty -> attempts in (1, 2)
    def test_31_generation_count_candidate_empty(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("Question")
        self.assertEqual(res.llm_generation_attempts, 2)

    # 32. Generation count assertion: candidate non-empty -> attempts = 3
    def test_32_generation_count_candidate_non_empty(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            LLMResponse(text="VERDICT: KEEP", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        res = agent.run("Question")
        self.assertEqual(res.llm_generation_attempts, 3)

    # 33. Multi-turn LLM client spy verifies exactly 3 generate calls when eligible
    def test_33_spy_verifies_three_calls(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            LLMResponse(text="VERDICT: KEEP", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        agent.run("Question")
        self.assertEqual(len(mock_llm.call_history), 3)

    # 34. Multi-turn LLM client spy verifies exactly 2 generate calls when candidate empty
    def test_34_spy_verifies_two_calls_when_empty(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        agent.run("Question")
        self.assertEqual(len(mock_llm.call_history), 2)

    # 35. Multi-turn LLM client spy verifies exactly 1 generate call when router fails
    def test_35_spy_verifies_router_error_and_worker(self):
        # When router errors, router_fallback=True, worker is called (call #2)
        mock_llm = MockMultiTurnLLMClient([
            Exception("Router network error"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            LLMResponse(text="VERDICT: KEEP", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        agent.run("Question")
        self.assertEqual(len(mock_llm.call_history), 3)

    # 36. Tavily search called at most once
    def test_36_search_called_at_most_once(self):
        mock_search = MagicMock()
        mock_search.search.return_value = MagicMock(
            success=True,
            format_evidence_block=MagicMock(return_value="Some web info"),
            results=[],
        )
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            LLMResponse(text="VERDICT: KEEP", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm, tavily_tool=mock_search)
        agent.run("Question")
        self.assertEqual(mock_search.search.call_count, 1)

    # 37. Python executed at most once
    def test_37_python_executed_at_most_once(self):
        mock_python = MagicMock()
        mock_python.execute.return_value = MagicMock(success=True, stdout="FINAL_ANSWER: 42\n", timed_out=False, exit_code=0)
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: PYTHON", finish_reason="STOP"),
            LLMResponse(text="```python\nprint('FINAL_ANSWER: 42')\n```", finish_reason="STOP"),
            LLMResponse(text="VERDICT: KEEP", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm, python_tool=mock_python)
        res = agent.run("Question")
        self.assertEqual(mock_python.execute.call_count, 1)
        self.assertEqual(res.final_answer, "42")

    # 38. FileTool native bytes reused, no disk re-read
    def test_38_file_native_bytes_reused(self):
        mock_file = MagicMock()
        mock_file.process.return_value = MagicMock(
            success=True,
            file_name="image.png",
            text_content=None,
            native_bytes=b"PNG_BYTES",
            mime_type="image/png",
            latency_seconds=0.1,
            processor="image",
            content_mode="native_multimodal",
            content_truncated=False,
            original_content_length=9,
            provided_content_length=9,
            error_type=None,
            error_message=None,
        )
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: Red", finish_reason="STOP"),
            LLMResponse(text="VERDICT: KEEP", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm, file_tool=mock_file)
        agent.run("What color is the shape?", file_path="dummy.png")
        # FileTool called once in V4
        self.assertEqual(mock_file.process.call_count, 1)
        # Check call_history for call #3 (verifier) has attachment_parts
        verifier_prompt, verifier_parts = mock_llm.call_history[2]
        self.assertIsNotNone(verifier_parts)
        self.assertEqual(len(verifier_parts), 1)


class TestInformationFirewallAndConfig(unittest.TestCase):
    """Items 39-44: Information firewall and model configuration tests."""

    # 39. Verifier prompt contains question, candidate answer, web evidence, file evidence, filename
    def test_39_verifier_prompt_contents(self):
        prompt = build_verifier_prompt(
            question="What is the population of City X?",
            candidate_answer="500,000",
            web_evidence="City X has 500,000 residents in 2020.",
            file_evidence="Census Table: City X = 500000",
            attachment_filename="census.csv",
        )
        self.assertIn("What is the population of City X?", prompt)
        self.assertIn("500,000", prompt)
        self.assertIn("City X has 500,000 residents in 2020.", prompt)
        self.assertIn("Census Table: City X = 500000", prompt)
        self.assertIn("census.csv", prompt)

    # 40. Verifier prompt does NOT contain router raw output or route choice reasoning
    def test_40_verifier_prompt_excludes_router_reasoning(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT\nBecause this is a simple lookup question.", finish_reason="STOP"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            LLMResponse(text="VERDICT: KEEP", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        agent.run("Question")
        verifier_prompt, _ = mock_llm.call_history[2]
        self.assertNotIn("Because this is a simple lookup question", verifier_prompt)
        self.assertNotIn("ROUTE: DIRECT", verifier_prompt)

    # 41. Verifier prompt does NOT contain worker raw output or hidden reasoning
    def test_41_verifier_prompt_excludes_worker_hidden_reasoning(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="Let me think step by step: 20 + 22 = 42.\nFINAL: 42", finish_reason="STOP"),
            LLMResponse(text="VERDICT: KEEP", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        agent.run("Question")
        verifier_prompt, _ = mock_llm.call_history[2]
        self.assertNotIn("Let me think step by step", verifier_prompt)

    # 42. Verifier prompt does NOT contain generated python code or execution stdout/stderr
    def test_42_verifier_prompt_excludes_python_code_and_stdout(self):
        mock_python = MagicMock()
        mock_python.execute.return_value = MagicMock(
            success=True,
            stdout="SECRET_DEBUG_OUTPUT\nFINAL_ANSWER: 42\n",
            timed_out=False,
            exit_code=0,
        )
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: PYTHON", finish_reason="STOP"),
            LLMResponse(text="```python\n# SECRET_INTERNAL_CODE\nprint('SECRET_DEBUG_OUTPUT')\nprint('FINAL_ANSWER: 42')\n```", finish_reason="STOP"),
            LLMResponse(text="VERDICT: KEEP", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm, python_tool=mock_python)
        agent.run("Question")
        verifier_prompt, _ = mock_llm.call_history[2]
        self.assertNotIn("SECRET_INTERNAL_CODE", verifier_prompt)
        self.assertNotIn("SECRET_DEBUG_OUTPUT", verifier_prompt)

    # 43. Verifier prompt does NOT contain ground truth or scorer results
    def test_43_verifier_prompt_excludes_ground_truth(self):
        prompt = build_verifier_prompt(
            question="What is 2+2?",
            candidate_answer="4",
        )
        self.assertNotIn("ground_truth", prompt.lower())
        self.assertNotIn("scorer", prompt.lower())

    # 44. LLMClient configuration enforces mode="NONE"
    def test_44_llm_client_mode_none(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key"}):
            with patch("google.genai.Client") as mock_client:
                client = LLMClient()
                config = client._build_config()
                self.assertEqual(config.tool_config.function_calling_config.mode, "NONE")
                self.assertTrue(config.automatic_function_calling.disable)


class TestEvaluationIdentityAndTransitions(unittest.TestCase):
    """Items 45-49: Evaluation transition metrics, identity, and record runner tests."""

    # 45. calculate_metrics computes V5 transitions: improvements, regressions, stable_correct, stable_failure
    def test_45_calculate_metrics_transitions(self):
        predictions = [
            # 1. Improvement: pre incorrect ("wrong"), post correct ("42")
            {
                "task_id": "task-1",
                "final_answer": "42",
                "pre_verification_answer": "wrong",
                "post_verification_answer": "42",
                "verifier_eligible": True,
                "verifier_attempted": True,
                "verifier_verdict": "REVISE",
                "verifier_revised": True,
                "request_success": True,
                "completion_success": True,
                "project_version": "v5",
            },
            # 2. Regression: pre correct ("correct"), post incorrect ("wrong")
            {
                "task_id": "task-2",
                "final_answer": "wrong",
                "pre_verification_answer": "Paris",
                "post_verification_answer": "wrong",
                "verifier_eligible": True,
                "verifier_attempted": True,
                "verifier_verdict": "REVISE",
                "verifier_revised": True,
                "request_success": True,
                "completion_success": True,
                "project_version": "v5",
            },
            # 3. Stable Correct: pre correct ("Rome"), post correct ("Rome")
            {
                "task_id": "task-3",
                "final_answer": "Rome",
                "pre_verification_answer": "Rome",
                "post_verification_answer": "Rome",
                "verifier_eligible": True,
                "verifier_attempted": True,
                "verifier_verdict": "KEEP",
                "verifier_revised": False,
                "request_success": True,
                "completion_success": True,
                "project_version": "v5",
            },
            # 4. Stable Failure: pre incorrect ("Berlin"), post incorrect ("Berlin")
            {
                "task_id": "task-4",
                "final_answer": "Berlin",
                "pre_verification_answer": "Berlin",
                "post_verification_answer": "Berlin",
                "verifier_eligible": True,
                "verifier_attempted": True,
                "verifier_verdict": "KEEP",
                "verifier_revised": False,
                "request_success": True,
                "completion_success": True,
                "project_version": "v5",
            },
        ]
        tasks_by_id = {
            "task-1": GAIATask(task_id="task-1", question="Q1", final_answer="42", level=1),
            "task-2": GAIATask(task_id="task-2", question="Q2", final_answer="Paris", level=1),
            "task-3": GAIATask(task_id="task-3", question="Q3", final_answer="Rome", level=1),
            "task-4": GAIATask(task_id="task-4", question="Q4", final_answer="Madrid", level=1),
        }

        res = calculate_metrics(predictions, tasks_by_id, project_version="v5")
        summary = res["summary"]

        self.assertEqual(summary["verifier_improvements"], 1)
        self.assertEqual(summary["verifier_regressions"], 1)
        self.assertEqual(summary["verifier_stable_correct"], 1)
        self.assertEqual(summary["verifier_stable_failure"], 1)

    # 46. calculate_metrics asserts mathematical identity on net improvement
    def test_46_mathematical_identity_net_improvement(self):
        predictions = [
            # 2 improvements, 0 regressions -> net delta = +2
            {
                "task_id": "task-1",
                "final_answer": "42",
                "pre_verification_answer": "wrong",
                "post_verification_answer": "42",
                "verifier_eligible": True,
                "verifier_attempted": True,
                "verifier_verdict": "REVISE",
                "verifier_revised": True,
                "request_success": True,
                "completion_success": True,
                "project_version": "v5",
            },
            {
                "task_id": "task-2",
                "final_answer": "Paris",
                "pre_verification_answer": "wrong",
                "post_verification_answer": "Paris",
                "verifier_eligible": True,
                "verifier_attempted": True,
                "verifier_verdict": "REVISE",
                "verifier_revised": True,
                "request_success": True,
                "completion_success": True,
                "project_version": "v5",
            },
        ]
        tasks_by_id = {
            "task-1": GAIATask(task_id="task-1", question="Q1", final_answer="42", level=1),
            "task-2": GAIATask(task_id="task-2", question="Q2", final_answer="Paris", level=1),
        }
        res = calculate_metrics(predictions, tasks_by_id, project_version="v5")
        summary = res["summary"]
        self.assertEqual(summary["net_correct_delta"], 2)
        self.assertEqual(summary["verifier_improvements"] - summary["verifier_regressions"], 2)

    # 47. calculate_metrics asserts mathematical identity on net regression
    def test_47_mathematical_identity_net_regression(self):
        predictions = [
            # 0 improvements, 1 regression -> net delta = -1
            {
                "task_id": "task-1",
                "final_answer": "corrupted",
                "pre_verification_answer": "42",
                "post_verification_answer": "corrupted",
                "verifier_eligible": True,
                "verifier_attempted": True,
                "verifier_verdict": "REVISE",
                "verifier_revised": True,
                "request_success": True,
                "completion_success": True,
                "project_version": "v5",
            },
        ]
        tasks_by_id = {
            "task-1": GAIATask(task_id="task-1", question="Q1", final_answer="42", level=1),
        }
        res = calculate_metrics(predictions, tasks_by_id, project_version="v5")
        summary = res["summary"]
        self.assertEqual(summary["net_correct_delta"], -1)
        self.assertEqual(summary["verifier_improvements"] - summary["verifier_regressions"], -1)

    # 48. calculate_metrics asserts mathematical identity on zero delta
    def test_48_mathematical_identity_zero_delta(self):
        predictions = [
            # 1 improvement, 1 regression -> net delta = 0
            {
                "task_id": "task-1",
                "final_answer": "42",
                "pre_verification_answer": "wrong",
                "post_verification_answer": "42",
                "verifier_eligible": True,
                "verifier_attempted": True,
                "verifier_verdict": "REVISE",
                "verifier_revised": True,
                "request_success": True,
                "completion_success": True,
                "project_version": "v5",
            },
            {
                "task_id": "task-2",
                "final_answer": "wrong",
                "pre_verification_answer": "Paris",
                "post_verification_answer": "wrong",
                "verifier_eligible": True,
                "verifier_attempted": True,
                "verifier_verdict": "REVISE",
                "verifier_revised": True,
                "request_success": True,
                "completion_success": True,
                "project_version": "v5",
            },
        ]
        tasks_by_id = {
            "task-1": GAIATask(task_id="task-1", question="Q1", final_answer="42", level=1),
            "task-2": GAIATask(task_id="task-2", question="Q2", final_answer="Paris", level=1),
        }
        res = calculate_metrics(predictions, tasks_by_id, project_version="v5")
        summary = res["summary"]
        self.assertEqual(summary["net_correct_delta"], 0)
        self.assertEqual(summary["verifier_improvements"] - summary["verifier_regressions"], 0)

    # 49. runner.execute_task produces valid schema version 4 record for V5
    def test_49_runner_produces_v5_schema_record(self):
        mock_llm = MockMultiTurnLLMClient([
            LLMResponse(text="ROUTE: DIRECT", finish_reason="STOP"),
            LLMResponse(text="FINAL: 42", finish_reason="STOP"),
            LLMResponse(text="VERDICT: KEEP", finish_reason="STOP"),
        ])
        agent = GAIAVerificationAgent(llm_client=mock_llm)
        rec = execute_task(
            task_id="task-v5-test",
            question="What is the answer?",
            level=1,
            agent=agent,
            project_version="v5",
        )
        self.assertEqual(rec["schema_version"], 4)
        self.assertEqual(rec["project_version"], "v5")
        self.assertEqual(rec["llm_generation_attempts"], 3)
        self.assertTrue(rec["verifier_eligible"])
        self.assertTrue(rec["verifier_attempted"])
        self.assertEqual(rec["verifier_verdict"], "KEEP")
        self.assertFalse(rec["verifier_revised"])
        self.assertFalse(rec["verifier_fallback"])
        self.assertEqual(rec["pre_verification_answer"], "42")
        self.assertEqual(rec["post_verification_answer"], "42")
        self.assertEqual(rec["final_answer"], "42")


if __name__ == "__main__":
    unittest.main()

