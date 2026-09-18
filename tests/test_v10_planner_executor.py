"""V10 Deterministic Pre-Benchmark Smoke Test Suite (24 Scenarios).

Validates all planning modes, parser edges, fallback paths, budget bounds,
downstream propagation, and paired harness invariants with zero network calls.
"""

import hashlib
import json
import os
import unittest
from typing import Any, List, Optional

from agent.agent import (
    GAIARouterAgent,
    GAIAVerificationAgent,
    GAIASelfEvaluationAgent,
    GAIATargetedRepairAgent,
    GAIAUpstreamCandidateRecoveryAgent,
    GAIAPlannerExecutorAgent,
    UpstreamContext,
)
from agent.llm import LLMResponse
from evaluation.dataset import GAIATask
from evaluation.evaluate import calculate_metrics
import ast
import inspect
import tempfile
import textwrap
from unittest.mock import patch

from evaluation.runner import execute_task
from evaluation.run_v10_paired import (
    run_paired_ablation,
    hash_shared_search_context,
    hash_shared_file_context,
)
from evaluation.evaluate_v10_paired import evaluate_paired_ablation, calculate_paired_metrics
from prompts.planner import (
    PLANNER_PROMPT_VERSION,
    build_planner_prompt,
    parse_planner_result,
    build_fallback_plan,
    PlanSpec,
    PlannerParseResult,
)
from prompts.executor import (
    EXECUTOR_DIRECT_PROMPT_VERSION,
    EXECUTOR_PYTHON_PROMPT_VERSION,
    format_plan_block,
    build_direct_executor_prompt,
    build_python_executor_prompt,
)
from tools.file_tool import FileResult
from tools.web_search import WebSearchResult, SearchResultItem
from tools.python_tool import PythonResult


class StubSearchTool:
    def __init__(self, success: bool = True, snippet: str = "Tavily search evidence snippet"):
        self.success = success
        self.snippet = snippet
        self.calls = 0

    def search(self, question: str) -> WebSearchResult:
        self.calls += 1
        item = SearchResultItem(
            title="Search Result",
            url="https://example.com/evidence",
            content=self.snippet,
        )
        return WebSearchResult(query=question, success=self.success, results=[item])


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


class TestV10DeterministicSmoke(unittest.TestCase):
    """Deterministic validation of the 24 pre-benchmark smoke scenarios."""

    # Scenario 1: Valid DIRECT plan format
    def test_scenario_01_valid_direct_plan(self):
        raw = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Identify the population of France from census\n"
            "EVIDENCE_NEEDED: 2023 census figures from search evidence\n"
            "PLAN:\n"
            "1. Inspect search results for official census agency\n"
            "2. Identify the recorded total population figure\n"
            "3. Format as integer number\n"
            "ANSWER_TYPE: number\n"
        )
        parsed = parse_planner_result(raw)
        self.assertTrue(parsed.success)
        self.assertFalse(parsed.fallback_used)
        self.assertEqual(parsed.plan.mode, "DIRECT")
        self.assertEqual(len(parsed.plan.steps), 3)
        self.assertEqual(parsed.plan.answer_type, "number")

    # Scenario 2: Valid PYTHON plan format
    def test_scenario_02_valid_python_plan(self):
        raw = (
            "MODE: PYTHON\n"
            "OBJECTIVE: Compute compound interest over 10 years\n"
            "EVIDENCE_NEEDED: Principal and interest rate from question\n"
            "PLAN:\n"
            "1. Define principal, rate, and compounding intervals\n"
            "2. Implement formula A = P * (1 + r/n)**(n*t)\n"
            "3. Compute total accumulated value\n"
            "4. Round to 2 decimal places and print FINAL_ANSWER:\n"
            "ANSWER_TYPE: number\n"
        )
        parsed = parse_planner_result(raw)
        self.assertTrue(parsed.success)
        self.assertFalse(parsed.fallback_used)
        self.assertEqual(parsed.plan.mode, "PYTHON")
        self.assertEqual(len(parsed.plan.steps), 4)
        self.assertEqual(parsed.plan.answer_type, "number")

    # Scenario 3: Malformed planner: missing MODE key
    def test_scenario_03_missing_mode_key(self):
        raw = (
            "OBJECTIVE: Identify country\n"
            "PLAN:\n"
            "1. Search\n"
            "ANSWER_TYPE: short text\n"
        )
        parsed = parse_planner_result(raw)
        self.assertFalse(parsed.success)
        self.assertTrue(parsed.fallback_used)
        self.assertEqual(parsed.plan.mode, "DIRECT")
        self.assertEqual(parsed.error_type, "PlannerMissingKeyError")

    # Scenario 4: Malformed planner: unsupported mode
    def test_scenario_04_unsupported_mode(self):
        raw = (
            "MODE: SQL\n"
            "OBJECTIVE: Query database\n"
            "EVIDENCE_NEEDED: Table\n"
            "PLAN:\n"
            "1. Run SELECT * FROM data\n"
            "ANSWER_TYPE: number\n"
        )
        parsed = parse_planner_result(raw)
        self.assertFalse(parsed.success)
        self.assertTrue(parsed.fallback_used)
        self.assertEqual(parsed.plan.mode, "DIRECT")
        self.assertEqual(parsed.error_type, "PlannerInvalidModeError")

    # Scenario 5: Malformed planner: empty plan (0 steps)
    def test_scenario_05_empty_plan_steps(self):
        raw = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Answer question\n"
            "EVIDENCE_NEEDED: None\n"
            "PLAN:\n"
            "ANSWER_TYPE: short text\n"
        )
        parsed = parse_planner_result(raw)
        self.assertFalse(parsed.success)
        self.assertTrue(parsed.fallback_used)
        self.assertEqual(parsed.plan.mode, "DIRECT")
        self.assertEqual(len(parsed.plan.steps), 1)
        self.assertEqual(parsed.error_type, "PlannerEmptyPlanError")

    # Scenario 6: Malformed planner: missing ANSWER_TYPE key
    def test_scenario_06_missing_answer_type_key(self):
        raw = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Answer question\n"
            "EVIDENCE_NEEDED: Facts\n"
            "PLAN:\n"
            "1. Synthesize facts\n"
        )
        parsed = parse_planner_result(raw)
        self.assertFalse(parsed.success)
        self.assertTrue(parsed.fallback_used)
        self.assertEqual(parsed.plan.answer_type, "short text")
        self.assertEqual(parsed.error_type, "PlannerMissingKeyError")

    # Scenario 7: Provider timeout during planner API call
    def test_scenario_07_provider_timeout_during_planner(self):
        llm = SequencedLLM([
            TimeoutError("LLM generation request timed out after 60s"),  # Planner call fails
            make_resp("FINAL: 42"),                                     # Executor direct call
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),               # Verifier
            make_resp("ASSESSMENT: CORRECT\nRISK_TYPE: NONE\nCONFIDENCE: 0.95"), # Self-eval
        ])
        agent = GAIAPlannerExecutorAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("What is 40 + 2?")
        self.assertTrue(res.planner_attempted)
        self.assertFalse(res.planner_success)
        self.assertTrue(res.planner_fallback_used)
        self.assertEqual(res.planner_mode, "DIRECT")
        self.assertEqual(res.final_answer, "42")
        self.assertLessEqual(res.llm_generation_attempts, 5)

    # Scenario 8: Provider 500 error during planner API call
    def test_scenario_08_provider_500_during_planner(self):
        llm = SequencedLLM([
            RuntimeError("500 Internal Server Error"),                  # Planner call fails
            make_resp("FINAL: 84"),                                     # Executor direct call
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.9"),                # Verifier
            make_resp("ASSESSMENT: CORRECT\nRISK_TYPE: NONE\nCONFIDENCE: 0.9"), # Self-eval
        ])
        agent = GAIAPlannerExecutorAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("What is 42 * 2?")
        self.assertTrue(res.planner_attempted)
        self.assertFalse(res.planner_success)
        self.assertTrue(res.planner_fallback_used)
        self.assertEqual(res.planner_mode, "DIRECT")
        self.assertEqual(res.final_answer, "84")

    # Scenario 9: Minimum boundary plan: exactly 1 step
    def test_scenario_09_minimum_boundary_plan_1_step(self):
        raw = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Give color of sky\n"
            "EVIDENCE_NEEDED: Direct knowledge\n"
            "PLAN:\n"
            "1. Output blue\n"
            "ANSWER_TYPE: short text\n"
        )
        parsed = parse_planner_result(raw)
        self.assertTrue(parsed.success)
        self.assertFalse(parsed.fallback_used)
        self.assertEqual(len(parsed.plan.steps), 1)

    # Scenario 10: Maximum boundary plan: exactly 5 steps
    def test_scenario_10_maximum_boundary_plan_5_steps(self):
        raw = (
            "MODE: PYTHON\n"
            "OBJECTIVE: Solve complex math\n"
            "EVIDENCE_NEEDED: Input coefficients\n"
            "PLAN:\n"
            "1. Parse inputs\n"
            "2. Set up polynomial\n"
            "3. Compute roots\n"
            "4. Filter positive roots\n"
            "5. Print smallest root\n"
            "ANSWER_TYPE: number\n"
        )
        parsed = parse_planner_result(raw)
        self.assertTrue(parsed.success)
        self.assertFalse(parsed.fallback_used)
        self.assertEqual(len(parsed.plan.steps), 5)

    # Scenario 11: Planner success + Executor DIRECT success
    def test_scenario_11_planner_and_executor_direct_success(self):
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Calculate answer\n"
            "EVIDENCE_NEEDED: Question details\n"
            "PLAN:\n"
            "1. Add numbers\n"
            "ANSWER_TYPE: number\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),                                    # Planner
            make_resp("FINAL: 42"),                                     # Executor DIRECT
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),               # Verifier
            make_resp("ASSESSMENT: CORRECT\nRISK_TYPE: NONE\nCONFIDENCE: 0.95"), # Self-eval
        ])
        agent = GAIAPlannerExecutorAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("What is 40 + 2?")
        self.assertTrue(res.planner_success)
        self.assertEqual(res.planner_mode, "DIRECT")
        self.assertEqual(res.candidate_answer, "42")
        self.assertFalse(res.candidate_recovery_triggered)
        self.assertEqual(res.final_answer, "42")

    # Scenario 12: Planner success + Executor PYTHON success
    def test_scenario_12_planner_and_executor_python_success(self):
        planner_text = (
            "MODE: PYTHON\n"
            "OBJECTIVE: Compute factorials sum\n"
            "EVIDENCE_NEEDED: Math module\n"
            "PLAN:\n"
            "1. Import math\n"
            "2. Sum factorials\n"
            "3. Print FINAL_ANSWER\n"
            "ANSWER_TYPE: number\n"
        )
        python_code_resp = "```python\nimport math\nprint('FINAL_ANSWER: 100')\n```"
        mock_py = MockPythonTool(success=True, output="FINAL_ANSWER: 100\n", exit_code=0)
        llm = SequencedLLM([
            make_resp(planner_text),                                    # Planner
            make_resp(python_code_resp),                                # Executor PYTHON
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),               # Verifier
            make_resp("ASSESSMENT: CORRECT\nRISK_TYPE: NONE\nCONFIDENCE: 0.95"), # Self-eval
        ])
        agent = GAIAPlannerExecutorAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=mock_py,
        )
        res = agent.run("Compute sum of factorials")
        self.assertTrue(res.planner_success)
        self.assertEqual(res.planner_mode, "PYTHON")
        self.assertEqual(res.candidate_answer, "100")
        self.assertEqual(mock_py.calls, 1)
        self.assertFalse(res.candidate_recovery_triggered)
        self.assertEqual(res.final_answer, "100")

    # Scenario 13: Planner success + Executor empty candidate ("")
    def test_scenario_13_executor_empty_candidate_triggers_recovery(self):
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Name country\n"
            "EVIDENCE_NEEDED: Geography\n"
            "PLAN:\n"
            "1. Recall capital\n"
            "ANSWER_TYPE: short text\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),                                    # Planner
            make_resp("FINAL: "),                                       # Executor DIRECT (empty candidate)
            make_resp("FINAL: France"),                                 # V9 Candidate Recovery
            make_resp("VERDICT: KEEP"),                                 # Verifier
            make_resp("ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.95"), # Self-eval
        ])
        agent = GAIAPlannerExecutorAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("What country has capital Paris?")
        self.assertTrue(res.candidate_recovery_triggered)
        self.assertEqual(res.pre_recovery_candidate, "")
        self.assertEqual(res.post_recovery_candidate, "France")
        self.assertEqual(res.final_answer, "France")

    # Scenario 14: Planner success + Executor Python script crash
    def test_scenario_14_executor_python_crash_triggers_recovery(self):
        planner_text = (
            "MODE: PYTHON\n"
            "OBJECTIVE: Compute calculation\n"
            "EVIDENCE_NEEDED: None\n"
            "PLAN:\n"
            "1. Divide by zero\n"
            "ANSWER_TYPE: number\n"
        )
        python_code_resp = "```python\nprint(1/0)\n```"
        mock_py = MockPythonTool(success=False, output="ZeroDivisionError: division by zero", exit_code=1)
        llm = SequencedLLM([
            make_resp(planner_text),                                    # Planner
            make_resp(python_code_resp),                                # Executor PYTHON
            make_resp("FINAL: Infinity"),                               # V9 Candidate Recovery
            make_resp("VERDICT: KEEP"),                                 # Verifier
            make_resp("ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.95"), # Self-eval
        ])
        agent = GAIAPlannerExecutorAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=mock_py,
        )
        res = agent.run("Compute 1 divided by 0")
        self.assertTrue(res.candidate_recovery_triggered)
        self.assertEqual(res.candidate_recovery_failure_class, "PYTHON_EXECUTION_FAILURE")
        self.assertEqual(res.post_recovery_candidate, "Infinity")
        self.assertEqual(res.final_answer, "Infinity")

    # Scenario 15: Candidate recovery after executor starvation
    def test_scenario_15_candidate_recovery_after_starvation(self):
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Find capital\n"
            "EVIDENCE_NEEDED: Maps\n"
            "PLAN:\n"
            "1. Find city\n"
            "ANSWER_TYPE: short text\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),                                    # Planner
            make_resp("FINAL: "),                                       # Executor (starvation)
            make_resp("FINAL: Paris"),                                  # Recovery
            make_resp("VERDICT: REVISE\nFINAL: Paris, France"),          # Verifier revises!
            make_resp("ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.90"), # Self-eval
        ])
        agent = GAIAPlannerExecutorAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("What is capital of France?")
        self.assertEqual(res.post_recovery_candidate, "Paris")
        self.assertEqual(res.pre_verification_answer, "Paris")
        self.assertEqual(res.final_answer, "Paris, France")

    # Scenario 16: Non-starved executor output bypasses recovery
    def test_scenario_16_non_starved_executor_bypasses_recovery(self):
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Color of sky\n"
            "EVIDENCE_NEEDED: None\n"
            "PLAN:\n"
            "1. Output blue\n"
            "ANSWER_TYPE: short text\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),                                    # Planner
            make_resp("FINAL: Blue"),                                   # Executor DIRECT
            make_resp("VERDICT: KEEP"),                                 # Verifier
            make_resp("ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.95"), # Self-eval
        ])
        agent = GAIAPlannerExecutorAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("What color is the clear sky?")
        self.assertFalse(res.candidate_recovery_triggered)
        self.assertFalse(res.candidate_recovery_attempted)
        self.assertEqual(res.candidate_answer, "Blue")
        self.assertEqual(res.final_answer, "Blue")

    # Scenario 17: Full pipeline execution (non-recovery path)
    def test_scenario_17_full_pipeline_non_recovery_path(self):
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: Math computation\n"
            "EVIDENCE_NEEDED: None\n"
            "PLAN:\n"
            "1. Calculate 5 * 5\n"
            "ANSWER_TYPE: number\n"
        )
        llm_agent = SequencedLLM([
            make_resp(planner_text),                                    # 1: Planner
            make_resp("FINAL: 24"),                                     # 2: Executor
            make_resp("VERDICT: REVISE\nFINAL: 25"),                    # 3: Verifier
            make_resp("ASSESSMENT: SUSPECT\nRISK_TYPE: CALCULATION\nCONFIDENCE: 0.80"), # 4: Self-eval
            make_resp("REPAIR_ACTION: REPLACE\nFINAL: 25"),             # 5: Repair
        ])
        agent = GAIAPlannerExecutorAgent(
            llm_client=llm_agent,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("What is 5 * 5?")
        self.assertLessEqual(res.llm_generation_attempts, 5)
        self.assertEqual(res.final_answer, "25")

        # Test runner execution and schema 8 assertion
        llm_runner = SequencedLLM([
            make_resp(planner_text),                                    # 1: Planner
            make_resp("FINAL: 25"),                                     # 2: Executor
            make_resp("VERDICT: KEEP"),                                 # 3: Verifier
            make_resp("ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.95"), # 4: Self-eval
        ])
        agent_runner = GAIAPlannerExecutorAgent(
            llm_client=llm_runner,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        task = GAIATask(
            task_id="test_task_v10_non_recovery",
            question="What is 5 * 5?",
            final_answer="25",
            level=1,
            file_name=None,
        )
        rec = execute_task(
            task_id=task.task_id,
            question=task.question,
            agent=agent_runner,
            level=task.level,
            project_version="v10",
        )
        self.assertEqual(rec["schema_version"], 8)
        self.assertTrue(rec["planner_attempted"])
        self.assertLessEqual(rec["llm_generation_attempts"], 5)

    # Scenario 18: Full pipeline execution (recovery path)
    def test_scenario_18_full_pipeline_recovery_path(self):
        planner_text = (
            "MODE: DIRECT\n"
            "OBJECTIVE: History query\n"
            "EVIDENCE_NEEDED: None\n"
            "PLAN:\n"
            "1. Recall year\n"
            "ANSWER_TYPE: number\n"
        )
        llm_agent = SequencedLLM([
            make_resp(planner_text),                                    # 1: Planner
            make_resp("FINAL: "),                                       # 2: Executor (starved)
            make_resp("FINAL: 1969"),                                   # 3: Recovery
            make_resp("VERDICT: KEEP"),                                 # 4: Verifier
            make_resp("ASSESSMENT: SUSPECT\nRISK_TYPE: REASONING\nCONFIDENCE: 0.80"), # 5: Self-eval
            make_resp("REPAIR_ACTION: REPLACE\nFINAL: 1969"),           # 6: Repair
        ])
        agent = GAIAPlannerExecutorAgent(
            llm_client=llm_agent,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("What year did Apollo 11 land?")
        self.assertTrue(res.candidate_recovery_triggered)
        self.assertLessEqual(res.llm_generation_attempts, 6)
        self.assertEqual(res.final_answer, "1969")

        # Test runner execution and schema 8 assertion
        llm_runner = SequencedLLM([
            make_resp(planner_text),                                    # 1: Planner
            make_resp("FINAL: "),                                       # 2: Executor (starved)
            make_resp("FINAL: 1969"),                                   # 3: Recovery
            make_resp("VERDICT: KEEP"),                                 # 4: Verifier
            make_resp("ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.95"), # 5: Self-eval
        ])
        agent_runner = GAIAPlannerExecutorAgent(
            llm_client=llm_runner,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        task = GAIATask(
            task_id="test_task_v10_recovery",
            question="What year did Apollo 11 land?",
            final_answer="1969",
            level=1,
            file_name=None,
        )
        rec = execute_task(
            task_id=task.task_id,
            question=task.question,
            agent=agent_runner,
            level=task.level,
            project_version="v10",
        )
        self.assertEqual(rec["schema_version"], 8)
        self.assertTrue(rec["planner_attempted"])
        self.assertTrue(rec["candidate_recovery_triggered"])
        self.assertLessEqual(rec["llm_generation_attempts"], 6)

    # Scenario 19: Strict Tool Budgets & Isolation
    def test_scenario_19_strict_tool_budgets_and_isolation(self):
        st = StubSearchTool()
        ft = CountingFileTool()
        pt = MockPythonTool(success=True, output="FINAL_ANSWER: 77")
        planner_text = (
            "MODE: PYTHON\n"
            "OBJECTIVE: Run python calculation\n"
            "EVIDENCE_NEEDED: None\n"
            "PLAN:\n"
            "1. Compute and print answer\n"
            "ANSWER_TYPE: number\n"
        )
        llm = SequencedLLM([
            make_resp(planner_text),
            make_resp("```python\nprint('FINAL_ANSWER: 77')\n```"),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.95"),
            make_resp("ASSESSMENT: CORRECT\nRISK_TYPE: NONE\nCONFIDENCE: 0.95"),
        ])
        agent = GAIAPlannerExecutorAgent(
            llm_client=llm,
            search_tool=st,
            file_tool=ft,
            python_tool=pt,
        )
        res = agent.run("Calculate answer", file_path="dummy.txt")
        self.assertEqual(st.calls, 1, "Search tool must be called at most once")
        self.assertEqual(ft.calls, 1, "File tool must be called at most once")
        self.assertEqual(pt.calls, 1, "Python tool must be called at most once")
        self.assertEqual(res.final_answer, "77")

    # Scenario 20: Information Firewall Audit
    def test_scenario_20_information_firewall_audit(self):
        forbidden_substrings = [
            "ground_truth",
            "ground truth",
            "test_label",
            "gaia_question_scorer",
            "reference_answer",
        ]
        planner_prompt = build_planner_prompt("What is 2 + 2?", "Evidence snippet", "File text", "file.txt")
        direct_prompt = build_direct_executor_prompt("What is 2 + 2?", "Plan text", "Evidence snippet", "File text", "file.txt")
        python_prompt = build_python_executor_prompt("What is 2 + 2?", "Plan text", "Evidence snippet", "File text", "file.txt")

        for p_name, prompt in [("planner", planner_prompt), ("direct", direct_prompt), ("python", python_prompt)]:
            p_lower = prompt.lower()
            for token in forbidden_substrings:
                self.assertNotIn(token, p_lower, f"Forbidden token '{token}' found in {p_name} prompt")

    # Scenario 21: Shared Context Delivery: Search Hash Invariance
    def test_scenario_21_search_hash_invariance(self):
        st = StubSearchTool(success=True, snippet="Unique search evidence 12345")
        v9_llm = SequencedLLM([
            make_resp("DECISION: DIRECT"),
            make_resp("FINAL_ANSWER: 42"),
        ])
        v10_llm = SequencedLLM([
            make_resp("MODE: DIRECT\nOBJECTIVE: Answer\nEVIDENCE_NEEDED: None\nPLAN:\n1. Output answer\nANSWER_TYPE: number"),
            make_resp("FINAL_ANSWER: 42"),
        ])
        ft = CountingFileTool()
        pt = MockPythonTool()
        v9_agent = GAIAUpstreamCandidateRecoveryAgent(
            llm_client=v9_llm,
            search_tool=st,
            file_tool=ft,
            python_tool=pt,
        )
        v10_agent = GAIAPlannerExecutorAgent(
            llm_client=v10_llm,
            search_tool=st,
            file_tool=ft,
            python_tool=pt,
        )

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".jsonl") as f:
            out_file = f.name

        mock_tasks = [
            GAIATask(task_id="search_hash_t1", question="Query needing web search?", final_answer="42", level=1),
        ]
        try:
            with patch("evaluation.run_v10_paired.load_gaia_tasks", return_value=mock_tasks):
                run_paired_ablation(
                    output_file=out_file,
                    resume=False,
                    delay=0.0,
                    v9_agent=v9_agent,
                    v10_agent=v10_agent,
                )

            with open(out_file, "r", encoding="utf-8") as f:
                rec = json.loads(f.readline())

            self.assertEqual(st.calls, 1, "Exactly 1 search call should occur during context acquisition")
            self.assertEqual(rec["v9_shared_context_search_hash"], rec["v10_shared_context_search_hash"])
            self.assertEqual(rec["shared_context_search_hash"], rec["v9_shared_context_search_hash"])
            tasks_by_id = {"search_hash_t1": mock_tasks[0]}
            metrics = calculate_paired_metrics([rec], tasks_by_id)
            self.assertEqual(metrics["summary"]["shared_search_hash_mismatch_count"], 0)
        finally:
            if os.path.exists(out_file):
                os.remove(out_file)

    # Scenario 22: Shared Context Delivery: File Hash Invariance
    def test_scenario_22_file_hash_invariance(self):
        st = StubSearchTool(success=True)
        ft = CountingFileTool(success=True, content="Document text for hashing ABCDE")
        pt = MockPythonTool()
        v9_llm = SequencedLLM([
            make_resp("DECISION: DIRECT"),
            make_resp("FINAL_ANSWER: 100"),
        ])
        v10_llm = SequencedLLM([
            make_resp("MODE: DIRECT\nOBJECTIVE: Parse file\nEVIDENCE_NEEDED: doc\nPLAN:\n1. Read doc\nANSWER_TYPE: number"),
            make_resp("FINAL_ANSWER: 100"),
        ])
        v9_agent = GAIAUpstreamCandidateRecoveryAgent(
            llm_client=v9_llm,
            search_tool=st,
            file_tool=ft,
            python_tool=pt,
        )
        v10_agent = GAIAPlannerExecutorAgent(
            llm_client=v10_llm,
            search_tool=st,
            file_tool=ft,
            python_tool=pt,
        )

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".jsonl") as f:
            out_file = f.name

        mock_tasks = [
            GAIATask(task_id="file_hash_t1", question="What does file say?", final_answer="100", level=1, file_name="doc.txt"),
        ]
        try:
            with patch("evaluation.run_v10_paired.load_gaia_tasks", return_value=mock_tasks), \
                 patch("evaluation.run_v10_paired.resolve_attachment_path", return_value="doc.txt"):
                run_paired_ablation(
                    output_file=out_file,
                    resume=False,
                    delay=0.0,
                    v9_agent=v9_agent,
                    v10_agent=v10_agent,
                )

            with open(out_file, "r", encoding="utf-8") as f:
                rec = json.loads(f.readline())

            self.assertEqual(ft.calls, 1, "Exactly 1 file processing call should occur during context acquisition")
            self.assertEqual(rec["v9_shared_context_file_hash"], rec["v10_shared_context_file_hash"])
            self.assertEqual(rec["shared_context_file_hash"], rec["v9_shared_context_file_hash"])
            tasks_by_id = {"file_hash_t1": mock_tasks[0]}
            metrics = calculate_paired_metrics([rec], tasks_by_id)
            self.assertEqual(metrics["summary"]["shared_file_hash_mismatch_count"], 0)
        finally:
            if os.path.exists(out_file):
                os.remove(out_file)

    # Scenario 23: Paired Upstream Transition Scoring
    def test_scenario_23_paired_upstream_transition_scoring(self):
        import tempfile
        records = [
            # 1. UPSTREAM_IMPROVEMENT: V9 failed, V10 correct
            {
                "task_id": "t1",
                "v9_upstream_candidate": "wrong",
                "v10_upstream_candidate": "correct_answer",
                "v9_router_mode": "DIRECT",
                "v10_planner_mode": "DIRECT",
                "v9_python_executed": False,
                "v10_python_executed": False,
            },
            # 2. UPSTREAM_REGRESSION: V9 correct, V10 failed
            {
                "task_id": "t2",
                "v9_upstream_candidate": "correct_answer",
                "v10_upstream_candidate": "wrong",
                "v9_router_mode": "DIRECT",
                "v10_planner_mode": "DIRECT",
                "v9_python_executed": False,
                "v10_python_executed": False,
            },
            # 3. UPSTREAM_STABLE_CORRECT: Both correct
            {
                "task_id": "t3",
                "v9_upstream_candidate": "correct_answer",
                "v10_upstream_candidate": "correct_answer",
                "v9_router_mode": "DIRECT",
                "v10_planner_mode": "DIRECT",
                "v9_python_executed": False,
                "v10_python_executed": False,
            },
            # 4. UPSTREAM_STABLE_FAILURE: Both failed
            {
                "task_id": "t4",
                "v9_upstream_candidate": "wrong_1",
                "v10_upstream_candidate": "wrong_2",
                "v9_router_mode": "DIRECT",
                "v10_planner_mode": "DIRECT",
                "v9_python_executed": False,
                "v10_python_executed": False,
            },
        ]
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".jsonl") as f:
            raw_path = f.name
            for r in records:
                f.write(json.dumps(r) + "\n")

        # Mock load_gaia_tasks inside evaluate_v10_paired
        from unittest.mock import patch
        mock_tasks = [
            GAIATask(task_id="t1", question="Q1", final_answer="correct_answer", level=1),
            GAIATask(task_id="t2", question="Q2", final_answer="correct_answer", level=1),
            GAIATask(task_id="t3", question="Q3", final_answer="correct_answer", level=1),
            GAIATask(task_id="t4", question="Q4", final_answer="correct_answer", level=1),
        ]
        with patch("evaluation.evaluate_v10_paired.load_gaia_tasks", return_value=mock_tasks):
            result = evaluate_paired_ablation(raw_path)
            summary = result["summary"]
            self.assertEqual(summary["upstream_improvements"], 1)
            self.assertEqual(summary["upstream_regressions"], 1)
            self.assertEqual(summary["upstream_stable_correct"], 1)
            self.assertEqual(summary["upstream_stable_failure"], 1)
            self.assertEqual(summary["delta_upstream"], 0)

        if os.path.exists(raw_path):
            os.remove(raw_path)

    # Scenario 24: Paired Harness Ground-Truth Firewall
    def test_scenario_24_paired_harness_ground_truth_firewall(self):
        import tempfile
        from unittest.mock import patch
        st = StubSearchTool(snippet="Some evidence")
        ft = CountingFileTool()
        pt = MockPythonTool()

        v9_llm = SequencedLLM([
            make_resp("DIRECT"),                                       # Router
            make_resp("FINAL: v9_candidate"),                          # Worker
        ])
        v10_llm = SequencedLLM([
            make_resp("MODE: DIRECT\nOBJECTIVE: test\nEVIDENCE_NEEDED: none\nPLAN:\n1. do it\nANSWER_TYPE: text\n"), # Planner
            make_resp("FINAL: v10_candidate"),                         # Executor
        ])
        v9_agent = GAIAUpstreamCandidateRecoveryAgent(
            llm_client=v9_llm,
            search_tool=st,
            file_tool=ft,
            python_tool=pt,
        )
        v10_agent = GAIAPlannerExecutorAgent(
            llm_client=v10_llm,
            search_tool=st,
            file_tool=ft,
            python_tool=pt,
        )

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".jsonl") as f:
            out_file = f.name

        mock_tasks = [
            GAIATask(task_id="firewall_test_t1", question="What is 10 + 20?", final_answer="SECRET_GT_30", level=1),
        ]
        with patch("evaluation.run_v10_paired.load_gaia_tasks", return_value=mock_tasks):
            run_paired_ablation(
                output_file=out_file,
                resume=False,
                delay=0.0,
                v9_agent=v9_agent,
                v10_agent=v10_agent,
            )

        with open(out_file, "r", encoding="utf-8") as f:
            content = f.read()

        # The runtime traces must strictly contain ZERO occurrences of the secret ground truth!
        self.assertNotIn("SECRET_GT_30", content, "Ground truth leaked into runtime traces!")
        self.assertNotIn("gaia_question_scorer", content)

        if os.path.exists(out_file):
            os.remove(out_file)


class TestV10HardenedInvariants(unittest.TestCase):
    """Focused tests for hardened implementation invariants beyond the 24 smoke scenarios."""

    def test_single_gaiarouteragent_run_definition(self):
        """Asserts that GAIARouterAgent contains exactly 1 'def run(' definition in source code."""
        src = inspect.getsource(GAIARouterAgent)
        run_count = src.count("def run(")
        self.assertEqual(run_count, 1, f"Expected exactly 1 run() definition in GAIARouterAgent, found {run_count}")

    def test_max_v7_gens_assignments_ast(self):
        """Asserts via AST that GAIATargetedRepairAgent.run contains exactly 2 max_v7_gens assignments:
        one in skipped-repair path and one in post-repair path.
        """
        src = textwrap.dedent(inspect.getsource(GAIATargetedRepairAgent.run))
        tree = ast.parse(src)
        assignments = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "max_v7_gens":
                        assignments.append(node)

        self.assertEqual(
            len(assignments),
            2,
            f"Expected exactly 2 max_v7_gens assignments in GAIATargetedRepairAgent.run, found {len(assignments)}",
        )

    def test_no_adjacent_duplicate_max_v7_gens_assignments(self):
        """Asserts that no statement block contains adjacent duplicate assignments to max_v7_gens."""
        src = textwrap.dedent(inspect.getsource(GAIATargetedRepairAgent.run))
        tree = ast.parse(src)
        adjacent_duplicates = 0
        for node in ast.walk(tree):
            for field_name, field_val in ast.iter_fields(node):
                if isinstance(field_val, list):
                    prev_is_max_v7_assign = False
                    for item in field_val:
                        is_max_v7_assign = False
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Name) and target.id == "max_v7_gens":
                                    is_max_v7_assign = True
                                    break
                        if is_max_v7_assign and prev_is_max_v7_assign:
                            adjacent_duplicates += 1
                        prev_is_max_v7_assign = is_max_v7_assign

        self.assertEqual(
            adjacent_duplicates,
            0,
            f"Found {adjacent_duplicates} adjacent duplicate max_v7_gens assignments in GAIATargetedRepairAgent.run",
        )

    def test_native_multimodal_file_context_hash(self):
        """Asserts that native_bytes contribute deterministically to shared-context file hash."""
        file_res_1 = FileResult(
            file_name="image.png",
            file_extension=".png",
            success=True,
            content_mode="native_multimodal",
            mime_type="image/png",
            native_bytes=b"RAW_PNG_DATA_VERSION_A",
        )
        file_res_2 = FileResult(
            file_name="image.png",
            file_extension=".png",
            success=True,
            content_mode="native_multimodal",
            mime_type="image/png",
            native_bytes=b"RAW_PNG_DATA_VERSION_B",
        )
        ctx_1 = UpstreamContext(
            question="Analyze image",
            file_path="image.png",
            file_res=file_res_1,
            file_evidence="[Attached file provided as native multimodal input: image.png (image/png)]",
            attachment_filename="image.png",
        )
        ctx_2 = UpstreamContext(
            question="Analyze image",
            file_path="image.png",
            file_res=file_res_2,
            file_evidence="[Attached file provided as native multimodal input: image.png (image/png)]",
            attachment_filename="image.png",
        )
        hash_1 = hash_shared_file_context(ctx_1)
        hash_2 = hash_shared_file_context(ctx_2)
        self.assertNotEqual(hash_1, hash_2, "Different native_bytes must yield different file context hashes")

        # Invariance check: same native_bytes must yield identical hash
        hash_1_again = hash_shared_file_context(ctx_1)
        self.assertEqual(hash_1, hash_1_again)

    def test_strict_planner_numbering_starts_at_1(self):
        """Plan starting with step 2 is rejected."""
        raw = "MODE: DIRECT\nOBJECTIVE: Obj\nEVIDENCE_NEEDED: None\nPLAN:\n2. Step two\nANSWER_TYPE: text"
        res = parse_planner_result(raw)
        self.assertFalse(res.success)
        self.assertTrue(res.fallback_used)
        self.assertEqual(res.error_message, "non_consecutive_plan_steps")
        self.assertEqual(res.error_type, "PlannerStepNumberingError")

    def test_strict_planner_numbering_is_consecutive(self):
        """Plan skipping step 2 is rejected."""
        raw = "MODE: DIRECT\nOBJECTIVE: Obj\nEVIDENCE_NEEDED: None\nPLAN:\n1. Step one\n3. Step three\nANSWER_TYPE: text"
        res = parse_planner_result(raw)
        self.assertFalse(res.success)
        self.assertTrue(res.fallback_used)
        self.assertEqual(res.error_message, "non_consecutive_plan_steps")
        self.assertEqual(res.error_type, "PlannerStepNumberingError")

    def test_strict_planner_duplicate_step_numbers_rejected(self):
        """Plan with duplicate step 1 is rejected."""
        raw = "MODE: DIRECT\nOBJECTIVE: Obj\nEVIDENCE_NEEDED: None\nPLAN:\n1. Step one\n1. Duplicate step\nANSWER_TYPE: text"
        res = parse_planner_result(raw)
        self.assertFalse(res.success)
        self.assertTrue(res.fallback_used)
        self.assertEqual(res.error_message, "non_consecutive_plan_steps")
        self.assertEqual(res.error_type, "PlannerStepNumberingError")

    def test_strict_planner_unnumbered_lines_rejected(self):
        """Plan with unnumbered line is rejected."""
        raw = "MODE: DIRECT\nOBJECTIVE: Obj\nEVIDENCE_NEEDED: None\nPLAN:\nFirst do this\nANSWER_TYPE: text"
        res = parse_planner_result(raw)
        self.assertFalse(res.success)
        self.assertTrue(res.fallback_used)
        self.assertEqual(res.error_message, "non_consecutive_plan_steps")
        self.assertEqual(res.error_type, "PlannerStepNumberingError")

    def test_strict_planner_bullet_only_steps_rejected(self):
        """Plan with bullets is rejected."""
        raw = "MODE: DIRECT\nOBJECTIVE: Obj\nEVIDENCE_NEEDED: None\nPLAN:\n- Bullet step one\n- Bullet step two\nANSWER_TYPE: text"
        res = parse_planner_result(raw)
        self.assertFalse(res.success)
        self.assertTrue(res.fallback_used)
        self.assertEqual(res.error_message, "non_consecutive_plan_steps")
        self.assertEqual(res.error_type, "PlannerStepNumberingError")

    def test_strict_planner_exceeding_5_steps_rejected(self):
        """Plan with >5 steps is rejected."""
        raw = "MODE: DIRECT\nOBJECTIVE: Obj\nEVIDENCE_NEEDED: None\nPLAN:\n1. S1\n2. S2\n3. S3\n4. S4\n5. S5\n6. S6\nANSWER_TYPE: text"
        res = parse_planner_result(raw)
        self.assertFalse(res.success)
        self.assertTrue(res.fallback_used)
        self.assertEqual(res.error_message, "plan_step_count_exceeded")
        self.assertEqual(res.error_type, "PlannerStepCountError")

    def test_strict_planner_mode_parsing(self):
        """Non-exact mode statements must trigger DIRECT fallback."""
        prose_raw = "MODE: I think DIRECT is best\nOBJECTIVE: Obj\nEVIDENCE_NEEDED: None\nPLAN:\n1. Step\nANSWER_TYPE: text"
        res = parse_planner_result(prose_raw)
        self.assertFalse(res.success)
        self.assertTrue(res.fallback_used)
        self.assertEqual(res.plan.mode, "DIRECT")
        self.assertEqual(res.error_type, "PlannerInvalidModeError")

        valid_direct = "MODE: DIRECT\nOBJECTIVE: Obj\nEVIDENCE_NEEDED: None\nPLAN:\n1. Step\nANSWER_TYPE: text"
        self.assertTrue(parse_planner_result(valid_direct).success)

        valid_python = "MODE: PYTHON\nOBJECTIVE: Obj\nEVIDENCE_NEEDED: None\nPLAN:\n1. Step\nANSWER_TYPE: text"
        self.assertTrue(parse_planner_result(valid_python).success)

    def test_truncated_or_unexpected_planner_finish_reason(self):
        """Planner with non-STOP finish reason triggers fallback to DIRECT with 1 planner and 1 executor call."""
        raw_plan = "MODE: DIRECT\nOBJECTIVE: Compute\nEVIDENCE_NEEDED: None\nPLAN:\n1. Step\nANSWER_TYPE: text"
        llm = SequencedLLM([
            make_resp(raw_plan, finish_reason="MAX_TOKENS"),  # Truncated planner response
            make_resp("FINAL: recovered_value"),               # Fallback executor direct
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.9"),         # Verifier
            make_resp("ASSESSMENT: CORRECT\nRISK_TYPE: NONE\nCONFIDENCE: 0.9"), # Self-eval
        ])
        agent = GAIAPlannerExecutorAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        res = agent.run("Calculate answer")
        self.assertTrue(res.planner_attempted)
        self.assertFalse(res.planner_success)
        self.assertFalse(res.planner_parse_success)
        self.assertTrue(res.planner_fallback_used)
        self.assertEqual(res.planner_error_type, "unexpected_finish_reason")
        self.assertEqual(res.planner_mode, "DIRECT")
        self.assertEqual(res.planner_generation_attempts, 1)
        self.assertEqual(res.executor_generation_attempts, 1)
        self.assertEqual(res.final_answer, "recovered_value")
        self.assertLessEqual(res.llm_generation_attempts, 5)

    def test_total_token_telemetry(self):
        """Asserts planner_total_tokens and executor_total_tokens are recorded in AgentResult and runner output."""
        llm = SequencedLLM([
            make_resp("MODE: DIRECT\nOBJECTIVE: Obj\nEVIDENCE_NEEDED: None\nPLAN:\n1. Step\nANSWER_TYPE: number", input_tokens=150, output_tokens=50, thinking_tokens=20),
            make_resp("FINAL_ANSWER: 99", input_tokens=200, output_tokens=30, thinking_tokens=10),
            make_resp("VERDICT: KEEP\nCONFIDENCE: 0.9", input_tokens=100, output_tokens=20),
            make_resp("ASSESSMENT: CORRECT\nRISK_TYPE: NONE\nCONFIDENCE: 0.9", input_tokens=100, output_tokens=20),
        ])
        agent = GAIAPlannerExecutorAgent(
            llm_client=llm,
            search_tool=StubSearchTool(),
            file_tool=CountingFileTool(),
            python_tool=MockPythonTool(),
        )
        rec = execute_task(
            task_id="token_test_t1",
            question="What is 99?",
            level=1,
            agent=agent,
            llm=llm,
            project_version="v10",
        )
        self.assertEqual(rec["planner_input_tokens"], 150)
        self.assertEqual(rec["planner_output_tokens"], 50)
        self.assertEqual(rec["planner_total_tokens"], 220)  # 150 + 50 + 20
        self.assertEqual(rec["executor_input_tokens"], 200)
        self.assertEqual(rec["executor_output_tokens"], 30)
        self.assertEqual(rec["executor_total_tokens"], 240)  # 200 + 30 + 10


if __name__ == "__main__":
    unittest.main()
