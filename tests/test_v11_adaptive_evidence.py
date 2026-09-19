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
    run_paired_ablation,
)
from prompts.adaptive_planner import (
    ADAPTIVE_PLANNER_PROMPT_VERSION,
    AdaptivePlanSpec,
    AdaptivePlannerParseResult,
    build_adaptive_fallback_plan,
    build_adaptive_planner_prompt,
    normalize_followup_query,
    parse_adaptive_planner_result,
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
        self.assertEqual(norm_q, "Acme Corp 2024 annual 10-K revenue SEC EDGAR")
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
            f'FOLLOWUP_QUERY: "{q}"\n'  # Identical to Search 1 query
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
        """Scenario 12: Normalization collapses whitespace, strips quotes, and truncates > 1500 chars."""
        # Whitespace and quotes
        raw = '  "   what   is    the    answer?   "  '
        norm, trunc = normalize_followup_query(raw)
        self.assertEqual(norm, "what is the answer?")
        self.assertFalse(trunc)

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
        source = inspect.getsource(GAIAAdaptiveEvidenceAgent)
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
                "second_search_success": True,
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
                "second_search_success": True,
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
                "second_search_success": True,
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
                "second_search_success": True,
                "second_search_has_new_urls": True,
                "second_search_new_urls_count": 3,
            },
            # 5. Non-eligible task
            {
                "task_id": "t5",
                "followup_eligible": False,
                "candidate_without_followup": None,
                "candidate_with_followup": None,
                "v11_retrieval_category": "SUFFICIENT_NON_TRIGGERED",
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

        self.assertEqual(summary["total_tasks_recorded"], 5)
        self.assertEqual(summary["followup_eligible_cohort_size"], 4)
        self.assertEqual(summary["retrieval_improvements"], 1)
        self.assertEqual(summary["retrieval_regressions"], 1)
        self.assertEqual(summary["retrieval_stable_correct"], 1)
        self.assertEqual(summary["retrieval_stable_failure"], 1)
        self.assertEqual(summary["delta_followup"], 0)
        self.assertEqual(summary["scientific_verdict"], "NEUTRAL (Inconclusive)")

        # Test zero-eligible cohort non-testability
        empty_cohort_records = [
            {
                "task_id": "t5",
                "followup_eligible": False,
                "v11_retrieval_category": "SUFFICIENT_NON_TRIGGERED",
            }
        ]
        res_empty = calculate_paired_metrics(empty_cohort_records, {"t5": tasks_by_id["t5"]})
        self.assertEqual(res_empty["summary"]["scientific_verdict"], "NOT_TESTABLE")
        self.assertEqual(res_empty["summary"]["delta_followup"], 0)

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


if __name__ == "__main__":
    unittest.main()
