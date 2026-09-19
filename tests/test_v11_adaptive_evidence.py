"""V11 Deterministic Smoke Test Suite (28 Preregistered Scenarios + Hardening).

Validates all Planner v2 grammar rules, adaptive search trigger and fallback paths,
resource bounds, downstream propagation, and paired harness invariants with zero network calls.
"""

import ast
import hashlib
import inspect
import json
import os
import tempfile
import unittest
import unittest.mock
from typing import Any, Dict, List, Optional

from agent.agent import (
    AgentResult,
    GAIAAdaptiveEvidenceAgent,
    GAIAPlannerExecutorAgent,
    UpstreamContext,
)
from agent.llm import LLMResponse
from evaluation.dataset import GAIATask
from evaluation.evaluate import calculate_metrics
from evaluation.evaluate_v11_paired import calculate_paired_metrics, evaluate_paired_retrieval
from evaluation.runner import execute_task
from evaluation.run_v11_paired import (
    hash_shared_file_context,
    hash_shared_search_context,
    hash_shared_plan,
    run_paired_ablation,
    validate_paired_resume_artifacts,
)
from prompts.adaptive_planner import (
    ADAPTIVE_PLANNER_PROMPT_VERSION,
    AdaptivePlanSpec,
    AdaptivePlannerParseResult,
    build_adaptive_fallback_plan,
    build_adaptive_planner_prompt,
    normalize_followup_query,
    parse_adaptive_planner_result,
    canonical_execution_plan_payload,
    hash_canonical_execution_plan,
)
from agent.agent import (
    _execute_v11_executor_from_plan,
    _plan_v11_from_context,
    _evaluate_v11_followup_control,
    _execute_v11_followup_search,
    _build_v11_executor_evidence,
)
from prompts.executor import (
    EXECUTOR_DIRECT_PROMPT_VERSION,
    EXECUTOR_PYTHON_PROMPT_VERSION,
    build_direct_executor_prompt,
    build_python_executor_prompt,
    format_plan_block,
)
from tools.file_tool import FileResult
from tools.python_tool import PythonResult
from tools.web_search import SearchResultItem, WebSearchResult


class StubSearchTool:
    """Mock search tool allowing distinct Search 1 and Search 2 responses."""

    def __init__(
        self,
        success: bool = True,
        snippet: str = "Primary search evidence snippet",
        second_success: bool = True,
        second_snippet: str = "Follow-up search evidence snippet",
        second_urls: Optional[List[str]] = None,
        raise_on_second: bool = False,
        empty_second: bool = False,
    ):
        self.calls = 0
        self.queries: List[str] = []
        self.success = success
        self.snippet = snippet
        self.second_success = second_success
        self.second_snippet = second_snippet
        self.second_urls = second_urls or ["https://example.com/followup-doc"]
        self.raise_on_second = raise_on_second
        self.empty_second = empty_second

    def search(self, query: str) -> WebSearchResult:
        self.calls += 1
        self.queries.append(query)
        if self.calls == 1:
            item = SearchResultItem(
                title="Primary Result",
                url="https://example.com/primary-doc",
                content=self.snippet,
            )
            return WebSearchResult(query=query, success=self.success, results=[item])
        else:
            if self.raise_on_second:
                raise RuntimeError("Simulated Tavily HTTP 500 error")
            if self.empty_second:
                return WebSearchResult(query=query, success=True, results=[])
            if not self.second_success:
                return WebSearchResult(
                    query=query,
                    success=False,
                    results=[],
                    error_type="HTTPError",
                    error_message="Simulated HTTP 429 rate limit",
                )
            items = [
                SearchResultItem(
                    title=f"Follow-up Result {i+1}",
                    url=u,
                    content=self.second_snippet,
                )
                for i, u in enumerate(self.second_urls)
            ]
            return WebSearchResult(query=query, success=True, results=items)


class CountingFileTool:
    def __init__(self, success: bool = True, content: str = "Attached document content."):
        self.calls = 0
        self.success = success
        self.content = content

    def process(self, file_path: str) -> FileResult:
        self.calls += 1
        return FileResult(
            file_name=os.path.basename(file_path),
            file_extension=os.path.splitext(file_path)[1] or ".txt",
            success=self.success,
            content_mode="text",
            text_content=self.content if self.success else None,
            processor="test_file_processor",
            error_type=None if self.success else "FileReadError",
            error_message=None if self.success else "Failed to read file",
        )


class MockPythonTool:
    def __init__(self, success: bool = True, output: str = "", exit_code: int = 0, timed_out: bool = False):
        self.calls = 0
        self.success = success
        self.output = output
        self.exit_code = exit_code
        self.timed_out = timed_out

    def execute(self, code: str, *args, **kwargs) -> PythonResult:
        self.calls += 1
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
        self.calls: List[Dict[str, Any]] = []
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
            raise RuntimeError(f"SequencedLLM ran out of mock responses after {len(self.calls)} calls")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_resp(
    text: str,
    finish_reason: str = "STOP",
    input_tokens: int = 100,
    output_tokens: int = 25,
    thinking_tokens: int = 10,
) -> LLMResponse:
    return LLMResponse(
        text=text,
        raw_text=text,
        finish_reason=finish_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        total_tokens=input_tokens + output_tokens + thinking_tokens,
        has_text_part=bool(text and text.strip()),
        has_function_call_part=False,
        response_part_types=["text"] if text else [],
    )


class TestV11AdaptiveEvidence(unittest.TestCase):
    """Deterministic validation of the 28 preregistered smoke scenarios and invariants."""

    # -------------------------------------------------------------------------
    # Group 1: Planner v2 Contract & Grammar (Scenarios 1-8)
    # -------------------------------------------------------------------------

    def test_scenario_01_valid_sufficient_none(self):
        """Scenario 1: Valid SUFFICIENT + NONE parses cleanly."""
        raw = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Identify the capital of France\n"
            "EVIDENCE_NEEDED: Capital city name from search evidence\n"
            "PLAN:\n"
            "1. Inspect search results for Paris\n"
            "2. Format final answer\n"
            "ANSWER_TYPE: string\n"
            "EVIDENCE_STATUS: SUFFICIENT\n"
            "FOLLOWUP_QUERY: NONE\n"
        )
        parsed = parse_adaptive_planner_result(raw)
        self.assertTrue(parsed.success)
        self.assertFalse(parsed.fallback_used)
        self.assertEqual(parsed.plan.mode, "DIRECT")
        self.assertEqual(parsed.plan.evidence_status, "SUFFICIENT")
        self.assertEqual(parsed.plan.followup_query, "NONE")
        self.assertEqual(len(parsed.plan.plan_steps), 2)
        self.assertEqual(parsed.plan.answer_type, "string")

    def test_scenario_02_valid_insufficient_query(self):
        """Scenario 2: Valid INSUFFICIENT + Query preserves query and flags requested_followup."""
        raw = (
            "MODE: PYTHON\n"
            "OBJECTIVE: Calculate 2024 operating revenue\n"
            "EVIDENCE_NEEDED: SEC 10-K filing financial data\n"
            "PLAN:\n"
            "1. Retrieve SEC numbers\n"
            "2. Compute sum of quarterly revenue\n"
            "ANSWER_TYPE: number\n"
            "EVIDENCE_STATUS: INSUFFICIENT\n"
            "FOLLOWUP_QUERY: \"Acme Corp 2024 annual 10-K revenue SEC EDGAR\"\n"
        )
        parsed = parse_adaptive_planner_result(raw)
        self.assertTrue(parsed.success)
        self.assertFalse(parsed.fallback_used)
        self.assertEqual(parsed.plan.mode, "PYTHON")
        self.assertEqual(parsed.plan.evidence_status, "INSUFFICIENT")
        self.assertEqual(parsed.plan.followup_query, '"Acme Corp 2024 annual 10-K revenue SEC EDGAR"')
        norm_q, trunc = normalize_followup_query(parsed.plan.followup_query)
        self.assertEqual(norm_q, '"Acme Corp 2024 annual 10-K revenue SEC EDGAR"')
        self.assertFalse(trunc)

    def test_scenario_03_invalid_evidence_status(self):
        """Scenario 3: EVIDENCE_STATUS: PARTIAL is rejected by parser."""
        raw = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Look up fact\n"
            "EVIDENCE_NEEDED: Fact\n"
            "PLAN:\n"
            "1. Step one\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: PARTIAL\n"
            "FOLLOWUP_QUERY: NONE\n"
        )
        parsed = parse_adaptive_planner_result(raw)
        self.assertFalse(parsed.success)
        self.assertTrue(parsed.fallback_used)
        self.assertEqual(parsed.error_type, "PlannerInvalidEvidenceStatusError")
        self.assertEqual(parsed.plan.evidence_status, "SUFFICIENT")
        self.assertEqual(parsed.plan.followup_query, "NONE")

    def test_scenario_04_sufficient_with_non_none_query(self):
        """Scenario 4: SUFFICIENT with non-NONE query is rejected."""
        raw = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Look up fact\n"
            "EVIDENCE_NEEDED: Fact\n"
            "PLAN:\n"
            "1. Step one\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: SUFFICIENT\n"
            "FOLLOWUP_QUERY: \"extra query not allowed\"\n"
        )
        parsed = parse_adaptive_planner_result(raw)
        self.assertFalse(parsed.success)
        self.assertTrue(parsed.fallback_used)
        self.assertEqual(parsed.error_type, "PlannerInvalidFollowupQueryError")
        self.assertEqual(parsed.plan.evidence_status, "SUFFICIENT")
        self.assertEqual(parsed.plan.followup_query, "NONE")

    def test_scenario_05_insufficient_with_none_query(self):
        """Scenario 5: INSUFFICIENT with NONE query is rejected."""
        raw = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Look up fact\n"
            "EVIDENCE_NEEDED: Fact\n"
            "PLAN:\n"
            "1. Step one\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: INSUFFICIENT\n"
            "FOLLOWUP_QUERY: NONE\n"
        )
        parsed = parse_adaptive_planner_result(raw)
        self.assertFalse(parsed.success)
        self.assertTrue(parsed.fallback_used)
        self.assertEqual(parsed.error_type, "PlannerInvalidFollowupQueryError")
        self.assertEqual(parsed.plan.evidence_status, "SUFFICIENT")

    def test_scenario_06_missing_followup_query(self):
        """Scenario 6: Missing FOLLOWUP_QUERY marker is rejected."""
        raw = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Look up fact\n"
            "EVIDENCE_NEEDED: Fact\n"
            "PLAN:\n"
            "1. Step one\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: SUFFICIENT\n"
        )
        parsed = parse_adaptive_planner_result(raw)
        self.assertFalse(parsed.success)
        self.assertTrue(parsed.fallback_used)
        self.assertEqual(parsed.error_type, "PlannerMissingKeyError")

    def test_scenario_07_parser_fallback_contract(self):
        """Scenario 7: Fallback plan adheres strictly to SUFFICIENT and NONE."""
        fallback = build_adaptive_fallback_plan()
        self.assertEqual(fallback.mode, "DIRECT")
        self.assertEqual(fallback.evidence_status, "SUFFICIENT")
        self.assertEqual(fallback.followup_query, "NONE")
        self.assertEqual(fallback.answer_type, "short text")
        self.assertEqual(len(fallback.plan_steps), 1)

    def test_scenario_08_planner_failure_safety_invariant(self):
        """Scenario 8: Planner API failure cleanly uses fallback and NEVER triggers Search 2."""
        llm = SequencedLLM([
            RuntimeError("Planner model call failed"),
            make_resp("FINAL: 42"),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95\nRISK_TYPE: NONE"),
        ])
        search_tool = StubSearchTool()
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=search_tool,
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("What is 40 + 2?")
        self.assertTrue(res.planner_attempted)
        self.assertFalse(res.planner_success)
        self.assertTrue(res.planner_fallback_used)
        self.assertFalse(res.second_search_triggered)
        self.assertFalse(res.second_search_attempted)
        self.assertEqual(search_tool.calls, 1)  # Only Search 1 executed
        self.assertEqual(res.final_answer, "42")

    # -------------------------------------------------------------------------
    # Group 2: Follow-Up Search Control & Fallbacks (Scenarios 9-14)
    # -------------------------------------------------------------------------

    def test_scenario_09_valid_trigger_execution(self):
        """Scenario 9: Valid INSUFFICIENT planner decision triggers exactly one Search 2 call."""
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Find release date\n"
            "EVIDENCE_NEEDED: Official press release\n"
            "PLAN:\n"
            "1. Inspect press release date\n"
            "2. Emit date\n"
            "ANSWER_TYPE: date\n"
            "EVIDENCE_STATUS: INSUFFICIENT\n"
            "FOLLOWUP_QUERY: \"Project Antigravity official public announcement date 2026\"\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),
            make_resp("FINAL: 2026-05-15"),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95\nRISK_TYPE: NONE"),
        ])
        search_tool = StubSearchTool(
            second_urls=["https://example.com/antigravity-announcement"],
            second_snippet="Project Antigravity was announced on May 15, 2026.",
        )
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=search_tool,
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("When was Project Antigravity announced?")
        self.assertTrue(res.second_search_triggered)
        self.assertTrue(res.second_search_attempted)
        self.assertTrue(res.second_search_success)
        self.assertFalse(res.second_search_empty_results)
        self.assertFalse(res.second_search_skipped_duplicate_query)
        self.assertEqual(search_tool.calls, 2)
        self.assertEqual(res.second_search_new_urls_count, 1)
        self.assertTrue(res.second_search_has_new_urls)

        # Verify executor prompt received both evidence blocks
        executor_prompt = llm.calls[1]["prompt"]
        self.assertIn("=== PRIMARY WEB SEARCH EVIDENCE ===", executor_prompt)
        self.assertIn("=== FOLLOW-UP WEB SEARCH EVIDENCE ===", executor_prompt)
        self.assertIn("Project Antigravity was announced on May 15, 2026", executor_prompt)

    def test_scenario_10_sufficient_search_bypass(self):
        """Scenario 10: SUFFICIENT planner decision executes 0 Search 2 calls."""
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Find capital\n"
            "EVIDENCE_NEEDED: Direct knowledge\n"
            "PLAN:\n"
            "1. State Paris\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: SUFFICIENT\n"
            "FOLLOWUP_QUERY: NONE\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),
            make_resp("FINAL: Paris"),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95\nRISK_TYPE: NONE"),
        ])
        search_tool = StubSearchTool()
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=search_tool,
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("What is the capital of France?")
        self.assertFalse(res.second_search_triggered)
        self.assertFalse(res.second_search_attempted)
        self.assertEqual(search_tool.calls, 1)

        executor_prompt = llm.calls[1]["prompt"]
        self.assertIn("=== PRIMARY WEB SEARCH EVIDENCE ===", executor_prompt)
        self.assertNotIn("=== FOLLOW-UP WEB SEARCH EVIDENCE ===", executor_prompt)

    def test_scenario_11_duplicate_query_skip(self):
        """Scenario 11: Duplicate query is skipped and logged without executing Search 2."""
        q = "What is the population of Tokyo in 2025?"
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Find Tokyo population\n"
            "EVIDENCE_NEEDED: Tokyo pop figures\n"
            "PLAN:\n"
            "1. Look up Tokyo\n"
            "ANSWER_TYPE: number\n"
            "EVIDENCE_STATUS: INSUFFICIENT\n"
            f"FOLLOWUP_QUERY: {q}\n"  # Identical to Search 1 query
        )
        llm = SequencedLLM([
            make_resp(planner_text),
            make_resp("FINAL: 14000000"),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95\nRISK_TYPE: NONE"),
        ])
        search_tool = StubSearchTool()
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=search_tool,
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run(q)
        self.assertTrue(res.second_search_triggered)
        self.assertTrue(res.second_search_skipped_duplicate_query)
        self.assertFalse(res.second_search_attempted)
        self.assertEqual(search_tool.calls, 1)  # Only Search 1 executed

    def test_scenario_12_query_normalization_and_truncation(self):
        """Scenario 12: Normalization collapses whitespace, preserves quotes, and truncates > 1500 chars."""
        # Whitespace and quotes preservation
        raw = '  "   what   is    the    answer?   "  '
        norm, trunc = normalize_followup_query(raw)
        self.assertEqual(norm, '" what is the answer? "')
        self.assertFalse(trunc)

        # Unquoted whitespace collapse
        raw2 = '   what   is    the    answer?   '
        norm2, trunc2 = normalize_followup_query(raw2)
        self.assertEqual(norm2, "what is the answer?")
        self.assertFalse(trunc2)

        # > 1500 chars truncation
        long_q = "search term " * 200  # 2400 chars
        norm_long, trunc_long = normalize_followup_query(long_q, max_len=1500)
        self.assertEqual(len(norm_long), 1500)
        self.assertTrue(trunc_long)

    def test_scenario_13_search2_provider_failure_fallback(self):
        """Scenario 13: Simulated Tavily error cleanly falls back to primary evidence."""
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Find data\n"
            "EVIDENCE_NEEDED: Extra data\n"
            "PLAN:\n"
            "1. Synthesize\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: INSUFFICIENT\n"
            "FOLLOWUP_QUERY: \"distinct search query\"\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),
            make_resp("FINAL: fallback_answer"),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95\nRISK_TYPE: NONE"),
        ])
        search_tool = StubSearchTool(second_success=False)
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=search_tool,
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("Sample question")
        self.assertTrue(res.second_search_triggered)
        self.assertTrue(res.second_search_attempted)
        self.assertFalse(res.second_search_success)
        self.assertEqual(res.second_search_error_type, "HTTPError")
        self.assertEqual(res.final_answer, "fallback_answer")

        # Executor must receive primary evidence fallback
        executor_prompt = llm.calls[1]["prompt"]
        self.assertIn("=== PRIMARY WEB SEARCH EVIDENCE ===", executor_prompt)
        self.assertNotIn("=== FOLLOW-UP WEB SEARCH EVIDENCE ===", executor_prompt)

    def test_scenario_14_search2_empty_results_fallback(self):
        """Scenario 14: Simulated empty snippet list cleanly falls back to primary evidence."""
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Find data\n"
            "EVIDENCE_NEEDED: Extra data\n"
            "PLAN:\n"
            "1. Synthesize\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: INSUFFICIENT\n"
            "FOLLOWUP_QUERY: \"distinct search query\"\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),
            make_resp("FINAL: fallback_answer"),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95\nRISK_TYPE: NONE"),
        ])
        search_tool = StubSearchTool(empty_second=True)
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=search_tool,
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("Sample question")
        self.assertTrue(res.second_search_triggered)
        self.assertTrue(res.second_search_attempted)
        self.assertTrue(res.second_search_empty_results)
        self.assertEqual(res.final_answer, "fallback_answer")

    # -------------------------------------------------------------------------
    # Group 3: Resource & Tool Budgets (Scenarios 15-20)
    # -------------------------------------------------------------------------

    def test_scenario_15_non_triggered_search_budget(self):
        """Scenario 15: Non-triggered task executes exactly 1 search call."""
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Test\n"
            "EVIDENCE_NEEDED: Test\n"
            "PLAN:\n"
            "1. Test\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: SUFFICIENT\n"
            "FOLLOWUP_QUERY: NONE\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),
            make_resp("FINAL: ans"),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95\nRISK_TYPE: NONE"),
        ])
        search_tool = StubSearchTool()
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=search_tool,
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("Question")
        self.assertEqual(search_tool.calls, 1)
        self.assertEqual(res.total_search_call_count, 1)

    def test_scenario_16_triggered_search_budget(self):
        """Scenario 16: Triggered task executes at most 2 search calls."""
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Test\n"
            "EVIDENCE_NEEDED: Test\n"
            "PLAN:\n"
            "1. Test\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: INSUFFICIENT\n"
            "FOLLOWUP_QUERY: \"secondary query\"\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),
            make_resp("FINAL: ans"),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95\nRISK_TYPE: NONE"),
        ])
        search_tool = StubSearchTool()
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=search_tool,
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("Question")
        self.assertEqual(search_tool.calls, 2)
        self.assertEqual(res.total_search_call_count, 2)
        self.assertLessEqual(res.total_search_call_count, 2)

    def test_scenario_17_search3_impossibility(self):
        """Scenario 17: Under no code path can a third search call be initiated."""
        source = inspect.getsource(_execute_v11_followup_search)
        parsed = ast.parse(source)

        search_calls = 0
        for node in ast.walk(parsed):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "search":
                    search_calls += 1

        self.assertEqual(search_calls, 1)

    def test_scenario_18_file_processing_invariant(self):
        """Scenario 18: File processing remains capped at <= 1 per task."""
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Test\n"
            "EVIDENCE_NEEDED: Test\n"
            "PLAN:\n"
            "1. Test\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: INSUFFICIENT\n"
            "FOLLOWUP_QUERY: \"query\"\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),
            make_resp("FINAL: ans"),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95\nRISK_TYPE: NONE"),
        ])
        file_tool = CountingFileTool()
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=file_tool,
            python_tool=MockPythonTool(),
        )
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Hello file")
            temp_path = f.name
        try:
            res = agent.run("Question", file_path=temp_path)
            self.assertEqual(file_tool.calls, 1)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_scenario_19_python_execution_invariant(self):
        """Scenario 19: Python execution remains capped at <= 1 per task."""
        planner_text = (
            "MODE: PYTHON\n"
            "OBJECTIVE: Compute\n"
            "EVIDENCE_NEEDED: Formula\n"
            "PLAN:\n"
            "1. Run code\n"
            "ANSWER_TYPE: number\n"
            "EVIDENCE_STATUS: SUFFICIENT\n"
            "FOLLOWUP_QUERY: NONE\n"
        )
        executor_code = "```python\nprint('FINAL: 99')\n```"
        llm = SequencedLLM([
            make_resp(planner_text),
            make_resp(executor_code),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95\nRISK_TYPE: NONE"),
        ])
        py_tool = MockPythonTool(success=True, output="FINAL: 99")
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=py_tool,
        )
        res = agent.run("Compute something")
        self.assertEqual(py_tool.calls, 1)

    def test_scenario_20_upstream_slot_invariant(self):
        """Scenario 20: Total upstream LLM generation slots strictly equal 2 (Planner + Executor)."""
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Test\n"
            "EVIDENCE_NEEDED: Test\n"
            "PLAN:\n"
            "1. Step\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: INSUFFICIENT\n"
            "FOLLOWUP_QUERY: \"secondary\"\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),
            make_resp("FINAL: ans"),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95\nRISK_TYPE: NONE"),
        ])
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("Question")
        # Slot 1: Planner v2
        self.assertEqual(res.planner_prompt_version, ADAPTIVE_PLANNER_PROMPT_VERSION)
        # Slot 2: Executor
        self.assertEqual(res.executor_prompt_version, EXECUTOR_DIRECT_PROMPT_VERSION)
        # Verify 2 upstream calls
        self.assertEqual(len(llm.calls), 4)  # 2 upstream + Verifier + Self-Eval

    # -------------------------------------------------------------------------
    # Group 4: Downstream Safeguards & Generation Caps (Scenarios 21-24)
    # -------------------------------------------------------------------------

    def test_scenario_21_non_recovery_generation_cap(self):
        """Scenario 21: Non-recovery path executes <= 5 logical generations."""
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Test\n"
            "EVIDENCE_NEEDED: Test\n"
            "PLAN:\n"
            "1. Step\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: INSUFFICIENT\n"
            "FOLLOWUP_QUERY: \"secondary\"\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),                           # 1. Planner
            make_resp("FINAL: 100"),                           # 2. Executor
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),      # 3. Verifier
            make_resp("ASSESSMENT: SUSPECT\nRISK_TYPE: REASONING\nCONFIDENCE: 0.4"), # 4. Self-Eval
            make_resp("REPAIR_ACTION: REPLACE\nFINAL: 101"),   # 5. Targeted Repair
        ])
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("Question")
        self.assertLessEqual(res.llm_generation_attempts, 5)
        self.assertFalse(res.candidate_recovery_attempted)
        self.assertEqual(res.final_answer, "101")

    def test_scenario_22_candidate_recovery_generation_cap(self):
        """Scenario 22: Candidate recovery path executes <= 6 logical generations."""
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Test\n"
            "EVIDENCE_NEEDED: Test\n"
            "PLAN:\n"
            "1. Step\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: SUFFICIENT\n"
            "FOLLOWUP_QUERY: NONE\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),                           # 1. Planner
            make_resp("FINAL: "),                              # 2. Executor (empty candidate)
            make_resp("FINAL: recovered_100"),                 # 3. Candidate Recovery
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),      # 4. Verifier
            make_resp("ASSESSMENT: SUSPECT\nRISK_TYPE: FORMAT\nCONFIDENCE: 0.3"), # 5. Self-Eval
            make_resp("REPAIR_ACTION: REPLACE\nFINAL: repaired_100"), # 6. Targeted Repair
        ])
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("Question")
        self.assertTrue(res.candidate_recovery_attempted)
        self.assertLessEqual(res.llm_generation_attempts, 6)
        self.assertEqual(res.final_answer, "repaired_100")

    def test_scenario_23_recovery_bypass_on_non_empty_candidate(self):
        """Scenario 23: Non-empty candidate passes through recovery with 100.0% preservation."""
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Test\n"
            "EVIDENCE_NEEDED: Test\n"
            "PLAN:\n"
            "1. Step\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: SUFFICIENT\n"
            "FOLLOWUP_QUERY: NONE\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),
            make_resp("FINAL: existing_candidate"),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95\nRISK_TYPE: NONE"),
        ])
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("Question")
        self.assertFalse(res.candidate_recovery_attempted)
        self.assertEqual(res.pre_recovery_candidate, "existing_candidate")
        self.assertEqual(res.post_recovery_candidate, "existing_candidate")

    def test_scenario_24_frozen_downstream_pipeline_integrity(self):
        """Scenario 24: Sequence of Recovery -> Verifier -> Self-Eval -> Repair is preserved verbatim."""
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Test\n"
            "EVIDENCE_NEEDED: Test\n"
            "PLAN:\n"
            "1. Step\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: SUFFICIENT\n"
            "FOLLOWUP_QUERY: NONE\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),
            make_resp("FINAL: "),                             # Empty candidate triggers recovery
            make_resp("FINAL: rec_cand"),                     # Recovery
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),     # Verifier
            make_resp("ASSESSMENT: SUSPECT\nRISK_TYPE: REASONING\nCONFIDENCE: 0.3"), # Self-eval
            make_resp("REPAIR_ACTION: KEEP"),                 # Repair
        ])
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("Question")
        self.assertEqual(res.candidate_recovery_prompt_version, "candidate-recovery-v1")
        self.assertEqual(res.verifier_prompt_version, "answer-verifier-v1")
        self.assertEqual(res.self_eval_prompt_version, "self-evaluator-v1")
        self.assertEqual(res.repair_prompt_version, "targeted-repair-v1")

    # -------------------------------------------------------------------------
    # Group 5: Primary Paired Ablation Harness (Scenarios 25-28)
    # -------------------------------------------------------------------------

    def test_scenario_25_identical_context_and_plan_invariant(self):
        """Scenario 25: Branch A and Branch B receive identical context and plan hashes."""
        shared_ctx = UpstreamContext(
            question="What is the answer?",
            search_res=WebSearchResult(query="What is the answer?", success=True, results=[
                SearchResultItem(title="T1", url="https://example.com", content="Snippet 1")
            ]),
            web_evidence="Snippet 1",
            file_evidence=None,
            file_res=None,
            attachment_filename=None,
            attachment_parts=None,
        )
        s1_hash = hash_shared_search_context(shared_ctx)
        f_hash = hash_shared_file_context(shared_ctx)
        self.assertTrue(bool(s1_hash))
        self.assertTrue(bool(f_hash))
        self.assertEqual(s1_hash, hash_shared_search_context(shared_ctx))
        self.assertEqual(f_hash, hash_shared_file_context(shared_ctx))

    def test_scenario_26_single_search2_execution(self):
        """Scenario 26: Search 2 is executed exactly once for follow-up-eligible paired task."""
        search_tool = StubSearchTool(
            second_urls=["https://example.com/new-source"],
            second_snippet="Decisive second evidence snippet",
        )
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Test\n"
            "EVIDENCE_NEEDED: Test\n"
            "PLAN:\n"
            "1. Step\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: INSUFFICIENT\n"
            "FOLLOWUP_QUERY: \"secondary query\"\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),         # Planner
            make_resp("FINAL: ans_without"), # Branch A Executor
            make_resp("FINAL: ans_with"),    # Branch B Executor
        ])
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=search_tool,
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as out_f:
            out_file = out_f.name

        try:
            task = GAIATask(
                task_id="test-task-paired-1",
                question="Test question?",
                level=1,
                final_answer="ans_with",
            )
            with unittest.mock.patch("evaluation.run_v11_paired.load_gaia_tasks", return_value=[task]):
                run_paired_ablation(
                    output_file=out_file,
                    resume=False,
                    delay=0.0,
                    agent=agent,
                )

            self.assertEqual(search_tool.calls, 2)

            with open(out_file, "r", encoding="utf-8") as f:
                rec = json.loads(f.readline())

            self.assertTrue(rec["followup_eligible"])
            self.assertTrue(rec["second_search_triggered"])
            self.assertTrue(rec["second_search_attempted"])
            self.assertEqual(rec["candidate_without_followup"], "ans_without")
            self.assertEqual(rec["candidate_with_followup"], "ans_with")
            self.assertEqual(rec["schema_version"], 9)
        finally:
            if os.path.exists(out_file):
                os.remove(out_file)

    def test_scenario_27_zero_runtime_ground_truth(self):
        """Scenario 27: Paired harness contains zero references to ground truth answers."""
        import evaluation.run_v11_paired as rvp
        source = inspect.getsource(rvp)

        disallowed = [
            "gaia_question_scorer",
            "check_exact_match",
            "task.final_answer",
            "ground_truth",
            "correct_candidate",
        ]
        for term in disallowed:
            self.assertNotIn(term, source, f"Forbidden ground-truth reference '{term}' found in run_v11_paired.py")

    def test_scenario_28_post_hoc_transition_computation(self):
        """Scenario 28: Post-hoc evaluation produces exact transition matrix and Delta_followup."""
        records = [
            # 1. RETRIEVAL_IMPROVEMENT: A wrong, B correct
            {
                "task_id": "t1",
                "followup_eligible": True,
                "candidate_without_followup": "wrong",
                "candidate_with_followup": "correct",
                "v11_retrieval_category": "FOLLOWUP_ELIGIBLE_SEARCH2_SUCCESS",
                "second_search_attempted": True,
                "second_search_success": True,
                "second_search_empty_results": False,
                "second_search_has_new_urls": True,
                "second_search_new_urls_count": 2,
            },
            # 2. RETRIEVAL_REGRESSION: A correct, B wrong
            {
                "task_id": "t2",
                "followup_eligible": True,
                "candidate_without_followup": "correct",
                "candidate_with_followup": "wrong",
                "v11_retrieval_category": "FOLLOWUP_ELIGIBLE_SEARCH2_SUCCESS",
                "second_search_attempted": True,
                "second_search_success": True,
                "second_search_empty_results": False,
                "second_search_has_new_urls": True,
                "second_search_new_urls_count": 1,
            },
            # 3. RETRIEVAL_STABLE_CORRECT: A correct, B correct
            {
                "task_id": "t3",
                "followup_eligible": True,
                "candidate_without_followup": "correct",
                "candidate_with_followup": "correct",
                "v11_retrieval_category": "FOLLOWUP_ELIGIBLE_SEARCH2_SUCCESS",
                "second_search_attempted": True,
                "second_search_success": True,
                "second_search_empty_results": False,
                "second_search_has_new_urls": False,
                "second_search_new_urls_count": 0,
            },
            # 4. RETRIEVAL_STABLE_FAILURE: A wrong, B wrong
            {
                "task_id": "t4",
                "followup_eligible": True,
                "candidate_without_followup": "wrong",
                "candidate_with_followup": "wrong",
                "v11_retrieval_category": "FOLLOWUP_ELIGIBLE_SEARCH2_SUCCESS",
                "second_search_attempted": True,
                "second_search_success": True,
                "second_search_empty_results": False,
                "second_search_has_new_urls": True,
                "second_search_new_urls_count": 3,
            },
        ]

        tasks_by_id = {
            "t1": GAIATask("t1", "Q1", 1, final_answer="correct"),
            "t2": GAIATask("t2", "Q2", 1, final_answer="correct"),
            "t3": GAIATask("t3", "Q3", 1, final_answer="correct"),
            "t4": GAIATask("t4", "Q4", 1, final_answer="correct"),
            "t5": GAIATask("t5", "Q5", 1, final_answer="correct"),
        }

        res = calculate_paired_metrics(records, tasks_by_id)
        summary = res["summary"]

        self.assertEqual(summary["total_tasks_recorded"], 4)
        self.assertEqual(summary["followup_eligible_cohort_size"], 4)
        self.assertEqual(summary["retrieval_improvements"], 1)
        self.assertEqual(summary["retrieval_regressions"], 1)
        self.assertEqual(summary["retrieval_stable_correct"], 1)
        self.assertEqual(summary["retrieval_stable_failure"], 1)
        self.assertEqual(summary["delta_followup"], 0)
        self.assertEqual(summary["scientific_verdict"], "NEUTRAL (Inconclusive)")
        self.assertEqual(summary["search_novelty_diagnostics"]["attempted_searches_count"], 4)
        self.assertEqual(summary["search_novelty_diagnostics"]["successful_searches_count"], 4)
        self.assertEqual(summary["search_novelty_diagnostics"]["has_new_urls_count"], 3)
        self.assertEqual(summary["search_novelty_diagnostics"]["has_new_urls_proportion"], 0.75)

        # Test zero-eligible cohort non-testability
        empty_cohort_records = []
        res_empty = calculate_paired_metrics(empty_cohort_records, tasks_by_id)
        self.assertEqual(res_empty["summary"]["scientific_verdict"], "NOT_TESTABLE")
        self.assertEqual(res_empty["summary"]["total_tasks_recorded"], 0)
        self.assertEqual(res_empty["summary"]["followup_eligible_cohort_size"], 0)
        self.assertEqual(res_empty["summary"]["delta_followup"], 0)

        # Test contamination error on non-eligible record in raw file
        contaminated_records = [
            {
                "task_id": "t5",
                "followup_eligible": False,
                "v11_retrieval_category": "SUFFICIENT_NON_TRIGGERED",
            }
        ]
        with self.assertRaises(ValueError):
            calculate_paired_metrics(contaminated_records, tasks_by_id)

    # -------------------------------------------------------------------------
    # Additional Hardening Tests
    # -------------------------------------------------------------------------

    def test_runner_schema_version_9(self):
        """Hardening: execute_task with project_version='v11' returns schema_version=9."""
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Test\n"
            "EVIDENCE_NEEDED: Test\n"
            "PLAN:\n"
            "1. Step\n"
            "ANSWER_TYPE: text\n"
            "EVIDENCE_STATUS: SUFFICIENT\n"
            "FOLLOWUP_QUERY: NONE\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),
            make_resp("FINAL: 42"),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95\nRISK_TYPE: NONE"),
        ])
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        task_dict = execute_task(
            task_id="test-v11-task",
            question="What is 40 + 2?",
            level=1,
            agent=agent,
            project_version="v11",
            schema_version=2,  # Should be upgraded to 9
        )
        self.assertEqual(task_dict["schema_version"], 9)
        self.assertEqual(task_dict["project_version"], "v11")
        self.assertTrue("second_search_triggered" in task_dict)
        self.assertTrue("total_search_call_count" in task_dict)

    def test_subclass_precedence(self):
        """Hardening: GAIAAdaptiveEvidenceAgent is identified as v11, not v10."""
        agent = GAIAAdaptiveEvidenceAgent(llm_client=SequencedLLM([]))
        self.assertTrue(getattr(agent, "_is_v11", False))
        self.assertTrue(isinstance(agent, GAIAPlannerExecutorAgent))

    def test_executor_prompt_omits_evidence_status_and_query(self):
        """Hardening: Executor prompt omits EVIDENCE_STATUS and FOLLOWUP_QUERY."""
        plan_spec = AdaptivePlanSpec(
            mode="DIRECT",
            objective="Direct lookup",
            evidence_status="INSUFFICIENT",
            evidence_needed="Census facts",
            followup_query="2023 census official figures",
            plan_steps=["1. Look up census", "2. Output number"],
            answer_type="number",
            raw_plan="...",
        )
        block = format_plan_block(plan_spec)
        self.assertIn("MODE: DIRECT", block)
        self.assertIn("OBJECTIVE: Direct lookup", block)
        self.assertIn("EVIDENCE_NEEDED: Census facts", block)
        self.assertIn("1. Look up census", block)
        self.assertIn("ANSWER_TYPE: number", block)
        self.assertNotIn("EVIDENCE_STATUS", block)
        self.assertNotIn("FOLLOWUP_QUERY", block)

    def test_plan_hash_hardening(self):
        """Hardening 1: Canonical plan hash includes execution fields only and ignores control fields."""
        base_plan = AdaptivePlanSpec(
            mode="DIRECT",
            objective="Determine capital",
            evidence_needed="Country capital data",
            plan_steps=["Step 1: Check facts", "Step 2: Output city"],
            answer_type="string",
            evidence_status="SUFFICIENT",
            followup_query="NONE",
            raw_plan="RAW TEXT 1",
            is_fallback=False,
            validation_error=None,
        )
        differing_control_plan = AdaptivePlanSpec(
            mode="DIRECT",
            objective="Determine capital",
            evidence_needed="Country capital data",
            plan_steps=["Step 1: Check facts", "Step 2: Output city"],
            answer_type="string",
            evidence_status="INSUFFICIENT",
            followup_query="some new query",
            raw_plan="DIFFERENT RAW TEXT",
            is_fallback=True,
            validation_error="Some error",
        )
        differing_exec_plan = AdaptivePlanSpec(
            mode="PYTHON",
            objective="Determine capital",
            evidence_needed="Country capital data",
            plan_steps=["Step 1: Check facts", "Step 2: Output city"],
            answer_type="string",
            evidence_status="SUFFICIENT",
            followup_query="NONE",
            raw_plan="RAW TEXT 1",
            is_fallback=False,
            validation_error=None,
        )

        payload_base = canonical_execution_plan_payload(base_plan)
        payload_diff_ctrl = canonical_execution_plan_payload(differing_control_plan)
        payload_diff_exec = canonical_execution_plan_payload(differing_exec_plan)

        # Ensure retrieval-control and diagnostic fields are excluded
        for p in (payload_base, payload_diff_ctrl, payload_diff_exec):
            self.assertNotIn("evidence_status", p)
            self.assertNotIn("followup_query", p)
            self.assertNotIn("raw_plan", p)
            self.assertNotIn("is_fallback", p)
            self.assertNotIn("validation_error", p)
            self.assertEqual(set(p.keys()), {"mode", "objective", "evidence_needed", "plan_steps", "answer_type"})

        # Differing control fields produce identical hash
        self.assertEqual(payload_base, payload_diff_ctrl)
        hash_base = hash_canonical_execution_plan(base_plan)
        hash_diff_ctrl = hash_canonical_execution_plan(differing_control_plan)
        self.assertEqual(hash_base, hash_diff_ctrl)

        # Differing execution fields produce different hash
        hash_diff_exec = hash_canonical_execution_plan(differing_exec_plan)
        self.assertNotEqual(hash_base, hash_diff_exec)

    def test_normalization_and_exact_duplicate_comparison(self):
        """Hardening 2: Normalization preserves quotes, collapses spaces, and duplicate comparison is exact."""
        # 1. Quotes preserved and whitespace collapsed
        norm, trunc = normalize_followup_query('   "quoted   term"   and   \'single\'   ')
        self.assertEqual(norm, '"quoted term" and \'single\'')
        self.assertFalse(trunc)

        # 2. Long query truncation at 1500
        long_q = "a" * 1600
        norm_long, trunc_long = normalize_followup_query(long_q)
        self.assertEqual(len(norm_long), 1500)
        self.assertTrue(trunc_long)

        # 3. Exact case-sensitive duplicate comparison in _evaluate_v11_followup_control
        # Exact match -> duplicate
        spec1 = AdaptivePlanSpec(
            mode="DIRECT", objective="O", evidence_needed="E", plan_steps=["1"],
            answer_type="text", evidence_status="INSUFFICIENT", followup_query="tokyo population",
            raw_plan="...",
        )
        ctrl1 = _evaluate_v11_followup_control(
            plan_spec=spec1,
            parse_success=True,
            search1_query_candidate="  tokyo   population  ",
        )
        self.assertTrue(ctrl1["followup_query_duplicate"])
        self.assertFalse(ctrl1["followup_eligible"])

        # Case-differing -> NOT duplicate
        spec2 = AdaptivePlanSpec(
            mode="DIRECT", objective="O", evidence_needed="E", plan_steps=["1"],
            answer_type="text", evidence_status="INSUFFICIENT", followup_query="Tokyo Population",
            raw_plan="...",
        )
        ctrl2 = _evaluate_v11_followup_control(
            plan_spec=spec2,
            parse_success=True,
            search1_query_candidate="tokyo population",
        )
        self.assertFalse(ctrl2["followup_query_duplicate"])
        self.assertTrue(ctrl2["followup_eligible"])

        # Quote-differing -> NOT duplicate
        spec3 = AdaptivePlanSpec(
            mode="DIRECT", objective="O", evidence_needed="E", plan_steps=["1"],
            answer_type="text", evidence_status="INSUFFICIENT", followup_query='"tokyo population"',
            raw_plan="...",
        )
        ctrl3 = _evaluate_v11_followup_control(
            plan_spec=spec3,
            parse_success=True,
            search1_query_candidate="tokyo population",
        )
        self.assertFalse(ctrl3["followup_query_duplicate"])
        self.assertTrue(ctrl3["followup_eligible"])

    def test_search2_mutual_exclusion(self):
        """Hardening 3: Mutual exclusion between success and empty results across search outcomes."""
        primary_urls = ["https://example.com/p1"]

        # Case 1: Search 2 with results (>0)
        tool_ok = StubSearchTool(second_success=True, second_urls=["https://example.com/p2"])
        tool_ok.calls = 1  # Simulate Search 1 already performed
        res1 = _execute_v11_followup_search(tool_ok, "followup query", primary_urls)
        self.assertTrue(res1["second_search_success"])
        self.assertFalse(res1["second_search_empty_results"])
        self.assertFalse(res1["second_search_success"] and res1["second_search_empty_results"])
        self.assertEqual(res1["v11_retrieval_category"], "FOLLOWUP_ELIGIBLE_SEARCH2_SUCCESS")

        # Case 2: Search 2 empty results
        tool_empty = StubSearchTool(second_success=True, empty_second=True)
        tool_empty.calls = 1  # Simulate Search 1 already performed
        res2 = _execute_v11_followup_search(tool_empty, "followup query", primary_urls)
        self.assertFalse(res2["second_search_success"])
        self.assertTrue(res2["second_search_empty_results"])
        self.assertFalse(res2["second_search_success"] and res2["second_search_empty_results"])
        self.assertEqual(res2["v11_retrieval_category"], "FOLLOWUP_ELIGIBLE_SEARCH2_EMPTY_RESULTS")

        # Case 3: Search 2 provider error
        tool_err = StubSearchTool(second_success=False)
        tool_err.calls = 1  # Simulate Search 1 already performed
        res3 = _execute_v11_followup_search(tool_err, "followup query", primary_urls)
        self.assertFalse(res3["second_search_success"])
        self.assertFalse(res3["second_search_empty_results"])
        self.assertFalse(res3["second_search_success"] and res3["second_search_empty_results"])
        self.assertEqual(res3["v11_retrieval_category"], "FOLLOWUP_ELIGIBLE_SEARCH2_PROVIDER_FAILURE")

        # Case 4: Search 2 exception raised
        tool_exc = StubSearchTool(raise_on_second=True)
        tool_exc.calls = 1  # Simulate Search 1 already performed
        res4 = _execute_v11_followup_search(tool_exc, "followup query", primary_urls)
        self.assertFalse(res4["second_search_success"])
        self.assertFalse(res4["second_search_empty_results"])
        self.assertFalse(res4["second_search_success"] and res4["second_search_empty_results"])
        self.assertEqual(res4["v11_retrieval_category"], "FOLLOWUP_ELIGIBLE_SEARCH2_PROVIDER_FAILURE")

    def test_paired_raw_cohort_three_tasks(self):
        """Hardening 4: Paired raw file contains only eligible tasks while enrollment ledger logs all."""
        tasks = [
            GAIATask(task_id="task-eligible", question="Q1 eligible?", level=1, final_answer="A1"),
            GAIATask(task_id="task-sufficient", question="Q2 sufficient?", level=1, final_answer="A2"),
            GAIATask(task_id="task-duplicate", question="Q3 duplicate?", level=1, final_answer="A3"),
        ]

        p1 = (
            "MODE: DIRECT\nOBJECTIVE: O1\nEVIDENCE_NEEDED: E1\nPLAN:\n1. Step\n"
            "ANSWER_TYPE: text\nEVIDENCE_STATUS: INSUFFICIENT\nFOLLOWUP_QUERY: new query\n"
        )
        p2 = (
            "MODE: DIRECT\nOBJECTIVE: O2\nEVIDENCE_NEEDED: E2\nPLAN:\n1. Step\n"
            "ANSWER_TYPE: text\nEVIDENCE_STATUS: SUFFICIENT\nFOLLOWUP_QUERY: NONE\n"
        )
        p3 = (
            "MODE: DIRECT\nOBJECTIVE: O3\nEVIDENCE_NEEDED: E3\nPLAN:\n1. Step\n"
            "ANSWER_TYPE: text\nEVIDENCE_STATUS: INSUFFICIENT\nFOLLOWUP_QUERY: Q3 duplicate?\n"
        )

        llm = SequencedLLM([
            make_resp(p1),
            make_resp("FINAL: ans_A"),
            make_resp("FINAL: ans_B"),
            make_resp(p2),
            make_resp(p3),
        ])
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as out_f:
            out_file = out_f.name
        enrollment_file = f"{out_file[:-6]}.enrollment.jsonl"

        try:
            with unittest.mock.patch("evaluation.run_v11_paired.load_gaia_tasks", return_value=tasks):
                run_paired_ablation(
                    output_file=out_file,
                    resume=False,
                    delay=0.0,
                    agent=agent,
                )

            with open(out_file, "r", encoding="utf-8") as f:
                raw_lines = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(raw_lines), 1)
            self.assertEqual(raw_lines[0]["task_id"], "task-eligible")
            self.assertTrue(raw_lines[0]["followup_eligible"])

            with open(enrollment_file, "r", encoding="utf-8") as f:
                enroll_lines = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(enroll_lines), 3)

            rec_map = {r["task_id"]: r for r in enroll_lines}
            self.assertTrue(rec_map["task-eligible"]["followup_eligible"])
            self.assertTrue(rec_map["task-eligible"]["paired_record_written"])

            self.assertFalse(rec_map["task-sufficient"]["followup_eligible"])
            self.assertFalse(rec_map["task-sufficient"]["paired_record_written"])

            self.assertFalse(rec_map["task-duplicate"]["followup_eligible"])
            self.assertFalse(rec_map["task-duplicate"]["paired_record_written"])
        finally:
            if os.path.exists(out_file):
                os.remove(out_file)
            if os.path.exists(enrollment_file):
                os.remove(enrollment_file)

    def test_provider_failure_retention_at_harness_level(self):
        """Hardening 5: Provider failure on Search 2 writes record with clean Branch B fallback."""
        tasks = [
            GAIATask(task_id="task-fail", question="Provider fail question?", level=1, final_answer="ans"),
        ]
        p = (
            "MODE: DIRECT\nOBJECTIVE: O\nEVIDENCE_NEEDED: E\nPLAN:\n1. Step\n"
            "ANSWER_TYPE: text\nEVIDENCE_STATUS: INSUFFICIENT\nFOLLOWUP_QUERY: secondary query\n"
        )
        llm = SequencedLLM([
            make_resp(p),
            make_resp("FINAL: ans_A"),
            make_resp("FINAL: ans_B_fallback"),
        ])
        search_tool = StubSearchTool(raise_on_second=True)
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=search_tool,
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as out_f:
            out_file = out_f.name
        enrollment_file = f"{out_file[:-6]}.enrollment.jsonl"

        try:
            with unittest.mock.patch("evaluation.run_v11_paired.load_gaia_tasks", return_value=tasks):
                run_paired_ablation(
                    output_file=out_file,
                    resume=False,
                    delay=0.0,
                    agent=agent,
                )

            with open(out_file, "r", encoding="utf-8") as f:
                records = [json.loads(line) for line in f if line.strip()]

            self.assertEqual(len(records), 1)
            rec = records[0]
            self.assertTrue(rec["followup_eligible"])
            self.assertFalse(rec["second_search_success"])
            self.assertEqual(rec["v11_retrieval_category"], "FOLLOWUP_ELIGIBLE_SEARCH2_PROVIDER_FAILURE")
            self.assertEqual(rec["candidate_without_followup"], "ans_A")
            self.assertEqual(rec["candidate_with_followup"], "ans_B_fallback")
        finally:
            if os.path.exists(out_file):
                os.remove(out_file)
            if os.path.exists(enrollment_file):
                os.remove(enrollment_file)

    def test_empty_result_retention_at_harness_level(self):
        """Hardening 6: Empty results on Search 2 writes record with clean Branch B fallback."""
        tasks = [
            GAIATask(task_id="task-empty", question="Empty search question?", level=1, final_answer="ans"),
        ]
        p = (
            "MODE: DIRECT\nOBJECTIVE: O\nEVIDENCE_NEEDED: E\nPLAN:\n1. Step\n"
            "ANSWER_TYPE: text\nEVIDENCE_STATUS: INSUFFICIENT\nFOLLOWUP_QUERY: secondary query\n"
        )
        llm = SequencedLLM([
            make_resp(p),
            make_resp("FINAL: ans_A"),
            make_resp("FINAL: ans_B_empty_fallback"),
        ])
        search_tool = StubSearchTool(empty_second=True)
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=search_tool,
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as out_f:
            out_file = out_f.name
        enrollment_file = f"{out_file[:-6]}.enrollment.jsonl"

        try:
            with unittest.mock.patch("evaluation.run_v11_paired.load_gaia_tasks", return_value=tasks):
                run_paired_ablation(
                    output_file=out_file,
                    resume=False,
                    delay=0.0,
                    agent=agent,
                )

            with open(out_file, "r", encoding="utf-8") as f:
                records = [json.loads(line) for line in f if line.strip()]

            self.assertEqual(len(records), 1)
            rec = records[0]
            self.assertTrue(rec["followup_eligible"])
            self.assertFalse(rec["second_search_success"])
            self.assertTrue(rec["second_search_empty_results"])
            self.assertEqual(rec["v11_retrieval_category"], "FOLLOWUP_ELIGIBLE_SEARCH2_EMPTY_RESULTS")
            self.assertEqual(rec["candidate_without_followup"], "ans_A")
            self.assertEqual(rec["candidate_with_followup"], "ans_B_empty_fallback")
        finally:
            if os.path.exists(out_file):
                os.remove(out_file)
            if os.path.exists(enrollment_file):
                os.remove(enrollment_file)

    def test_zero_eligible_end_to_end_and_evaluator_safety(self):
        """Hardening 7: Evaluator handles empty raw file, missing files, and contamination safely."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_raw = os.path.join(tmpdir, "paired_raw.jsonl")
            with open(empty_raw, "w", encoding="utf-8") as f:
                pass  # Empty file

            # Empty raw file produces NOT_TESTABLE
            with unittest.mock.patch("evaluation.evaluate_v11_paired.load_gaia_tasks", return_value=[]):
                eval_res = evaluate_paired_retrieval(input_file=empty_raw)
            self.assertEqual(eval_res["summary"]["scientific_verdict"], "NOT_TESTABLE")
            self.assertEqual(eval_res["summary"]["total_tasks_recorded"], 0)
            self.assertEqual(eval_res["summary"]["followup_eligible_cohort_size"], 0)
            self.assertEqual(eval_res["summary"]["delta_followup"], 0)

            # Missing file raises FileNotFoundError
            non_existent = os.path.join(tmpdir, "non_existent.jsonl")
            with self.assertRaises(FileNotFoundError):
                evaluate_paired_retrieval(input_file=non_existent)

            # Contaminated file (record with followup_eligible=False) raises ValueError
            contaminated_raw = os.path.join(tmpdir, "contaminated.jsonl")
            with open(contaminated_raw, "w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "task_id": "bad-task",
                    "followup_eligible": False,
                    "v11_retrieval_category": "SUFFICIENT_NON_TRIGGERED",
                }) + "\n")
            with unittest.mock.patch("evaluation.evaluate_v11_paired.load_gaia_tasks", return_value=[]):
                with self.assertRaises(ValueError):
                    evaluate_paired_retrieval(input_file=contaminated_raw)

            # Missing enrollment ledger on resume raises RuntimeError
            existing_raw = os.path.join(tmpdir, "existing_output.jsonl")
            with open(existing_raw, "w", encoding="utf-8") as f:
                f.write(json.dumps({"task_id": "t1"}) + "\n")
            with self.assertRaises(RuntimeError):
                run_paired_ablation(
                    output_file=existing_raw,
                    resume=True,
                    agent=GAIAAdaptiveEvidenceAgent(llm_client=SequencedLLM([])),
                )

    def test_shared_executor_semantics(self):
        """Hardening 8: _execute_v11_executor_from_plan executes DIRECT and PYTHON modes."""
        plan_direct = AdaptivePlanSpec(
            mode="DIRECT",
            objective="Direct lookup",
            evidence_needed="Evidence",
            plan_steps=["Step 1"],
            answer_type="string",
            evidence_status="SUFFICIENT",
            followup_query="NONE",
            raw_plan="...",
        )
        plan_python = AdaptivePlanSpec(
            mode="PYTHON",
            objective="Compute sum",
            evidence_needed="Numbers",
            plan_steps=["Step 1"],
            answer_type="number",
            evidence_status="SUFFICIENT",
            followup_query="NONE",
            raw_plan="...",
        )

        llm_direct = SequencedLLM([make_resp("FINAL: 100")])
        agent_direct = GAIAAdaptiveEvidenceAgent(
            llm_client=llm_direct,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res_direct = _execute_v11_executor_from_plan(
            agent=agent_direct,
            question="What is 50*2?",
            plan_spec=plan_direct,
            combined_web_evidence="Evidence text",
            file_evidence="",
            attachment_filename="",
            attachment_parts=None,
        )
        self.assertEqual(res_direct.candidate_answer, "100")
        self.assertFalse(res_direct.python_executed)
        self.assertTrue(res_direct.executor_success)

        python_code_resp = "```python\nprint(42)\n```\nFINAL: 42"
        llm_python = SequencedLLM([make_resp(python_code_resp)])
        py_tool = MockPythonTool(success=True, output="42\n")
        agent_python = GAIAAdaptiveEvidenceAgent(
            llm_client=llm_python,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=py_tool,
        )
        res_python = _execute_v11_executor_from_plan(
            agent=agent_python,
            question="Calculate 40 + 2",
            plan_spec=plan_python,
            combined_web_evidence="Evidence text",
            file_evidence="",
            attachment_filename="",
            attachment_parts=None,
        )
        self.assertEqual(res_python.candidate_answer, "42")
        self.assertTrue(res_python.python_executed)
        self.assertEqual(py_tool.calls, 1)

    def test_non_normal_planner_finish_reason(self):
        """Hardening 9: Non-normal planner finish_reason triggers fallback without Search 2."""
        llm = SequencedLLM([
            make_resp("Partial text...", finish_reason="MAX_TOKENS"),
            make_resp("FINAL: fallback_answer"),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: PASS\nCONFIDENCE: 0.95\nRISK_TYPE: NONE"),
        ])
        search_tool = StubSearchTool()
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=search_tool,
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("What is the capital of Peru?")
        self.assertTrue(res.planner_fallback_used)
        self.assertEqual(res.planner_error_type, "unexpected_finish_reason")
        self.assertFalse(res.second_search_triggered)
        self.assertFalse(res.second_search_attempted)
        self.assertEqual(res.second_search_call_count, 0)
        self.assertEqual(search_tool.calls, 1)
        self.assertEqual(res.final_answer, "fallback_answer")

    def test_v11_source_hygiene_ast(self):
        """Hardening 10: Source hygiene ensures exactly one definition per module-level function."""
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        paired_runner_path = os.path.join(repo_root, "evaluation", "run_v11_paired.py")
        with open(paired_runner_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename="run_v11_paired.py")

        fn_defs = [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        # No duplicate function definitions at module level
        self.assertEqual(len(fn_defs), len(set(fn_defs)), f"Duplicate module-level functions found: {fn_defs}")

        # Invariant checks for specific key functions
        self.assertEqual(fn_defs.count("hash_shared_plan"), 1)
        self.assertEqual(fn_defs.count("hash_shared_search_context"), 1)
        self.assertEqual(fn_defs.count("hash_shared_file_context"), 1)
        self.assertEqual(fn_defs.count("execute_plan_branch"), 1)
        self.assertEqual(fn_defs.count("run_paired_ablation"), 1)
        self.assertEqual(fn_defs.count("validate_paired_resume_artifacts"), 1)

        # Functional validation of hash_shared_plan
        spec = AdaptivePlanSpec(
            mode="DIRECT",
            objective="Obj",
            evidence_needed="Ev",
            plan_steps=["Step 1"],
            answer_type="string",
            evidence_status="INSUFFICIENT",
            followup_query="Query",
            raw_plan="...",
        )
        self.assertEqual(hash_shared_plan(spec), hash_canonical_execution_plan(spec))

    def test_frozen_targeted_repair_runtime_ast(self):
        """Hardening 11: Frozen Targeted Repair runtime has 0 _is_v11 references and 2 max_v7_gens assignments."""
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        agent_path = os.path.join(repo_root, "agent", "agent.py")
        with open(agent_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename="agent.py")

        repair_class = None
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "GAIATargetedRepairAgent":
                repair_class = node
                break
        self.assertIsNotNone(repair_class, "GAIATargetedRepairAgent not found in agent.py")

        # Ensure _is_v11 does not appear anywhere in GAIATargetedRepairAgent
        for subnode in ast.walk(repair_class):
            if isinstance(subnode, ast.Constant) and subnode.value == "_is_v11":
                self.fail("Forbidden '_is_v11' constant found in GAIATargetedRepairAgent")
            if isinstance(subnode, ast.Name) and subnode.id == "_is_v11":
                self.fail("Forbidden '_is_v11' name found in GAIATargetedRepairAgent")

        # Find run method
        run_fn = None
        for item in repair_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "run":
                run_fn = item
                break
        self.assertIsNotNone(run_fn, "GAIATargetedRepairAgent.run not found")

        # Count assignments to max_v7_gens in run
        gens_assignments = []
        for subnode in ast.walk(run_fn):
            if isinstance(subnode, ast.Assign):
                for target in subnode.targets:
                    if isinstance(target, ast.Name) and target.id == "max_v7_gens":
                        gens_assignments.append(subnode)
        self.assertEqual(
            len(gens_assignments),
            2,
            f"Expected exactly 2 assignments to max_v7_gens in GAIATargetedRepairAgent.run, found {len(gens_assignments)}",
        )

    def test_resume_crash_window_ledger_only_eligible(self):
        """Hardening 12: Resume fails closed when an eligible task is in ledger but missing from raw file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_path = os.path.join(tmpdir, "paired.jsonl")
            ledger_path = os.path.join(tmpdir, "paired.enrollment.jsonl")

            # Create empty raw file
            with open(raw_path, "w", encoding="utf-8") as rf:
                pass

            # Write eligible task to ledger claiming paired_record_written=True
            with open(ledger_path, "w", encoding="utf-8") as lf:
                lf.write(json.dumps({
                    "task_id": "t-eligible-missing-from-raw",
                    "followup_eligible": True,
                    "paired_record_written": True,
                }) + "\n")

            with self.assertRaises(RuntimeError) as ctx:
                validate_paired_resume_artifacts(raw_path, ledger_path)
            self.assertIn("missing from raw file", str(ctx.exception))

            # Also verify run_paired_ablation raises RuntimeError
            with self.assertRaises(RuntimeError):
                run_paired_ablation(
                    output_file=raw_path,
                    resume=True,
                    agent=GAIAAdaptiveEvidenceAgent(llm_client=SequencedLLM([])),
                )

    def test_resume_crash_window_raw_only_task(self):
        """Hardening 13: Resume fails closed when a task is in raw file but missing from enrollment ledger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_path = os.path.join(tmpdir, "paired.jsonl")
            ledger_path = os.path.join(tmpdir, "paired.enrollment.jsonl")

            with open(raw_path, "w", encoding="utf-8") as rf:
                rf.write(json.dumps({
                    "task_id": "t-raw-only",
                    "followup_eligible": True,
                }) + "\n")

            # Ledger exists but is empty
            with open(ledger_path, "w", encoding="utf-8") as lf:
                pass

            with self.assertRaises(RuntimeError) as ctx:
                validate_paired_resume_artifacts(raw_path, ledger_path)
            self.assertIn("missing from enrollment ledger", str(ctx.exception))

            with self.assertRaises(RuntimeError):
                run_paired_ablation(
                    output_file=raw_path,
                    resume=True,
                    agent=GAIAAdaptiveEvidenceAgent(llm_client=SequencedLLM([])),
                )

    def test_resume_contamination_detection(self):
        """Hardening 14: Resume fails closed on contaminated records across raw and ledger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_path = os.path.join(tmpdir, "paired.jsonl")
            ledger_path = os.path.join(tmpdir, "paired.enrollment.jsonl")

            # Case A: Raw has non-eligible task directly
            with open(raw_path, "w", encoding="utf-8") as rf:
                rf.write(json.dumps({"task_id": "bad-raw", "followup_eligible": False}) + "\n")
            with open(ledger_path, "w", encoding="utf-8") as lf:
                lf.write(json.dumps({"task_id": "bad-raw", "followup_eligible": False, "paired_record_written": False}) + "\n")

            with self.assertRaises(RuntimeError) as ctx_a:
                validate_paired_resume_artifacts(raw_path, ledger_path)
            self.assertIn("Contaminated raw paired file", str(ctx_a.exception))

            # Case B: Ledger non-eligible task has paired_record_written=True
            with open(raw_path, "w", encoding="utf-8") as rf:
                pass
            with open(ledger_path, "w", encoding="utf-8") as lf:
                lf.write(json.dumps({"task_id": "t-inconsistent", "followup_eligible": False, "paired_record_written": True}) + "\n")

            with self.assertRaises(RuntimeError) as ctx_b:
                validate_paired_resume_artifacts(raw_path, ledger_path)
            self.assertIn("Contamination discrepancy", str(ctx_b.exception))

    def test_resume_duplicate_task_id_detection(self):
        """Hardening 15: Resume fails closed when duplicate task IDs exist in either artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_path = os.path.join(tmpdir, "paired.jsonl")
            ledger_path = os.path.join(tmpdir, "paired.enrollment.jsonl")

            # Case A: Duplicate in raw file
            with open(raw_path, "w", encoding="utf-8") as rf:
                rf.write(json.dumps({"task_id": "dup-task", "followup_eligible": True}) + "\n")
                rf.write(json.dumps({"task_id": "dup-task", "followup_eligible": True}) + "\n")
            with open(ledger_path, "w", encoding="utf-8") as lf:
                lf.write(json.dumps({"task_id": "dup-task", "followup_eligible": True, "paired_record_written": True}) + "\n")

            with self.assertRaises(RuntimeError) as ctx_a:
                validate_paired_resume_artifacts(raw_path, ledger_path)
            self.assertIn("Duplicate task_id 'dup-task' in raw paired file", str(ctx_a.exception))

            # Case B: Duplicate in enrollment ledger
            with open(raw_path, "w", encoding="utf-8") as rf:
                rf.write(json.dumps({"task_id": "dup-task", "followup_eligible": True}) + "\n")
            with open(ledger_path, "w", encoding="utf-8") as lf:
                lf.write(json.dumps({"task_id": "dup-task", "followup_eligible": True, "paired_record_written": True}) + "\n")
                lf.write(json.dumps({"task_id": "dup-task", "followup_eligible": True, "paired_record_written": True}) + "\n")

            with self.assertRaises(RuntimeError) as ctx_b:
                validate_paired_resume_artifacts(raw_path, ledger_path)
            self.assertIn("Duplicate task_id 'dup-task' in enrollment ledger", str(ctx_b.exception))

    def test_resume_clean_skips_completed_tasks(self):
        """Hardening 16: Clean resume validates existing artifacts and skips completed tasks without re-executing."""
        tasks = [
            GAIATask(task_id="task-done-non-eligible", question="Q1 done?", level=1, final_answer="A1"),
            GAIATask(task_id="task-done-eligible", question="Q2 done?", level=1, final_answer="A2"),
            GAIATask(task_id="task-new-eligible", question="Q3 new?", level=1, final_answer="A3"),
        ]

        # LLM only needs responses for task-new-eligible!
        # If task 1 or 2 were re-executed, LLM would be called more times or exhaust responses
        p_new = (
            "MODE: DIRECT\nOBJECTIVE: O3\nEVIDENCE_NEEDED: E3\nPLAN:\n1. Step\n"
            "ANSWER_TYPE: text\nEVIDENCE_STATUS: INSUFFICIENT\nFOLLOWUP_QUERY: new query\n"
        )
        llm = SequencedLLM([
            make_resp(p_new),
            make_resp("FINAL: ans_A"),
            make_resp("FINAL: ans_B"),
        ])
        agent = GAIAAdaptiveEvidenceAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as out_f:
            out_file = out_f.name
        enrollment_file = f"{out_file[:-6]}.enrollment.jsonl"

        try:
            # Seed valid prior artifacts
            with open(out_file, "w", encoding="utf-8") as rf:
                rf.write(json.dumps({
                    "schema_version": 9,
                    "task_id": "task-done-eligible",
                    "level": 1,
                    "question": "Q2 done?",
                    "file_name": None,
                    "shared_primary_search_hash": "s1",
                    "shared_file_hash": "f1",
                    "shared_plan_hash": "p1",
                    "planner_evidence_status": "INSUFFICIENT",
                    "planner_followup_query": "q",
                    "planner_requested_followup": True,
                    "followup_query_valid": True,
                    "followup_query_duplicate": False,
                    "followup_eligible": True,
                    "second_search_triggered": True,
                    "second_search_attempted": True,
                    "second_search_success": True,
                    "second_search_empty_results": False,
                    "second_search_skipped_duplicate_query": False,
                    "second_search_query": "q",
                    "second_search_provider_query": "q",
                    "second_search_query_truncated": False,
                    "second_search_latency_seconds": 0.1,
                    "second_search_result_count": 1,
                    "second_search_error_type": None,
                    "second_search_error_message": None,
                    "second_search_new_urls_count": 1,
                    "second_search_urls": ["u2"],
                    "primary_search_urls": ["u1"],
                    "second_search_has_new_urls": True,
                    "followup_search_hash": "h2",
                    "candidate_without_followup": "prev_A",
                    "candidate_with_followup": "prev_B",
                    "python_without_followup": False,
                    "python_with_followup": False,
                    "planner_mode": "DIRECT",
                    "plan_step_count": 1,
                    "planner_parse_success": True,
                    "planner_fallback_used": False,
                    "v11_retrieval_category": "FOLLOWUP_ELIGIBLE_SEARCH2_SUCCESS",
                }) + "\n")

            with open(enrollment_file, "w", encoding="utf-8") as lf:
                lf.write(json.dumps({
                    "schema_version": 9,
                    "task_id": "task-done-non-eligible",
                    "level": 1,
                    "question": "Q1 done?",
                    "file_name": None,
                    "shared_primary_search_hash": "s0",
                    "shared_file_hash": "f0",
                    "shared_plan_hash": "p0",
                    "planner_evidence_status": "SUFFICIENT",
                    "planner_followup_query": "NONE",
                    "planner_requested_followup": False,
                    "followup_query_valid": False,
                    "followup_query_duplicate": False,
                    "followup_eligible": False,
                    "second_search_triggered": False,
                    "second_search_attempted": False,
                    "second_search_success": False,
                    "second_search_empty_results": False,
                    "second_search_skipped_duplicate_query": False,
                    "second_search_query": None,
                    "second_search_provider_query": None,
                    "second_search_query_truncated": False,
                    "second_search_latency_seconds": None,
                    "second_search_result_count": None,
                    "second_search_error_type": None,
                    "second_search_error_message": None,
                    "second_search_new_urls_count": None,
                    "second_search_urls": None,
                    "primary_search_urls": ["u1"],
                    "second_search_has_new_urls": None,
                    "followup_search_hash": None,
                    "candidate_without_followup": None,
                    "candidate_with_followup": None,
                    "python_without_followup": False,
                    "python_with_followup": False,
                    "planner_mode": "DIRECT",
                    "plan_step_count": 1,
                    "planner_parse_success": True,
                    "planner_fallback_used": False,
                    "v11_retrieval_category": "SUFFICIENT_NON_TRIGGERED",
                    "paired_record_written": False,
                }) + "\n")
                lf.write(json.dumps({
                    "schema_version": 9,
                    "task_id": "task-done-eligible",
                    "level": 1,
                    "question": "Q2 done?",
                    "file_name": None,
                    "shared_primary_search_hash": "s1",
                    "shared_file_hash": "f1",
                    "shared_plan_hash": "p1",
                    "planner_evidence_status": "INSUFFICIENT",
                    "planner_followup_query": "q",
                    "planner_requested_followup": True,
                    "followup_query_valid": True,
                    "followup_query_duplicate": False,
                    "followup_eligible": True,
                    "second_search_triggered": True,
                    "second_search_attempted": True,
                    "second_search_success": True,
                    "second_search_empty_results": False,
                    "second_search_skipped_duplicate_query": False,
                    "second_search_query": "q",
                    "second_search_provider_query": "q",
                    "second_search_query_truncated": False,
                    "second_search_latency_seconds": 0.1,
                    "second_search_result_count": 1,
                    "second_search_error_type": None,
                    "second_search_error_message": None,
                    "second_search_new_urls_count": 1,
                    "second_search_urls": ["u2"],
                    "primary_search_urls": ["u1"],
                    "second_search_has_new_urls": True,
                    "followup_search_hash": "h2",
                    "candidate_without_followup": "prev_A",
                    "candidate_with_followup": "prev_B",
                    "python_without_followup": False,
                    "python_with_followup": False,
                    "planner_mode": "DIRECT",
                    "plan_step_count": 1,
                    "planner_parse_success": True,
                    "planner_fallback_used": False,
                    "v11_retrieval_category": "FOLLOWUP_ELIGIBLE_SEARCH2_SUCCESS",
                    "paired_record_written": True,
                }) + "\n")

            # Run with resume=True
            with unittest.mock.patch("evaluation.run_v11_paired.load_gaia_tasks", return_value=tasks):
                run_paired_ablation(
                    output_file=out_file,
                    resume=True,
                    delay=0.0,
                    agent=agent,
                )

            # Check that only 3 LLM calls occurred (for task-new-eligible only!)
            self.assertEqual(len(llm.responses), 0, "All queued responses for task-new-eligible should have been consumed")

            # Verify final raw file has task-done-eligible and task-new-eligible
            with open(out_file, "r", encoding="utf-8") as rf:
                raw_records = [json.loads(line) for line in rf if line.strip()]
            self.assertEqual(len(raw_records), 2)
            self.assertEqual({r["task_id"] for r in raw_records}, {"task-done-eligible", "task-new-eligible"})

            # Verify final enrollment ledger has all 3 tasks
            with open(enrollment_file, "r", encoding="utf-8") as lf:
                ledger_records = [json.loads(line) for line in lf if line.strip()]
            self.assertEqual(len(ledger_records), 3)
            self.assertEqual(
                {r["task_id"] for r in ledger_records},
                {"task-done-non-eligible", "task-done-eligible", "task-new-eligible"},
            )
        finally:
            if os.path.exists(out_file):
                os.remove(out_file)
            if os.path.exists(enrollment_file):
                os.remove(enrollment_file)


if __name__ == "__main__":
    unittest.main()
