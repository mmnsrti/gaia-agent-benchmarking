import json
import unittest
from typing import Any, List, Optional

from agent.agent import (
    GAIATargetedRepairAgent,
    GAIAActiveEvidenceVerificationAgent,
)
from agent.llm import LLMResponse
from evaluation.active_verification_metrics import calculate_active_verification_metrics
from evaluation.runner import execute_task
from prompts.active_evidence_verification import (
    ACTIVE_EVIDENCE_VERIFICATION_PROMPT_VERSION,
    build_active_evidence_query,
    build_active_evidence_verification_prompt,
    parse_active_evidence_verification_result,
)
from tools.file_tool import FileResult
from tools.web_search import SearchResultItem, WebSearchResult


class StubSearchTool:
    def __init__(self, success: bool = True, results: Optional[List[SearchResultItem]] = None):
        self.success = success
        self.results = results if results is not None else []
        self.calls = 0
        self.last_query = None

    def search(self, question: str) -> WebSearchResult:
        self.calls += 1
        self.last_query = question
        return WebSearchResult(
            query=question,
            success=self.success,
            results=list(self.results),
        )


class CountingFileTool:
    def __init__(self):
        self.calls = 0

    def process(self, file_path: str) -> FileResult:
        self.calls += 1
        return FileResult(
            file_name="evidence.txt",
            file_extension=".txt",
            success=True,
            content_mode="text",
            text_content="Existing attachment context.",
            processor="test",
        )


class CountingPythonTool:
    def __init__(self):
        self.calls = 0

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        raise AssertionError("DIRECT-route V8 active verification must not execute Python")


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
            raise RuntimeError(f"SequencedLLM ran out of mock responses. Call count: {len(self.calls)}")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def response(text: str, finish_reason: str = "STOP") -> LLMResponse:
    return LLMResponse(text=text, raw_text=text, finish_reason=finish_reason)


def standard_v8_responses(
    self_eval_assessment: str = "SUSPECT",
    self_eval_risk: str = "EVIDENCE",
    repair_text: Optional[str] = "REPAIR_ACTION: KEEP",
    adjudication_text: Optional[str] = None,
) -> List[Any]:
    """Generates standard upstream responses + optional V8 adjudication."""
    res = [
        response("ROUTE: DIRECT"),
        response("FINAL: 41"),
        response("VERDICT: KEEP"),
        response(f"ASSESSMENT: {self_eval_assessment}\nRISK_TYPE: {self_eval_risk}\nCONFIDENCE: 0.85"),
    ]
    if self_eval_assessment == "SUSPECT":
        if repair_text is not None:
            res.append(response(repair_text))
    if adjudication_text is not None:
        res.append(response(adjudication_text))
    return res


def sample_search_items() -> List[SearchResultItem]:
    return [
        SearchResultItem(
            title="Official Documentation",
            url="https://example.com/doc",
            content="According to official measurements, the exact result is 42.",
            score=0.95,
        )
    ]


class TestV8Parser(unittest.TestCase):
    """Tests for active evidence verification output parsing and strict schema enforcement."""

    def test_valid_keep_variations(self):
        valid_keeps = [
            "VERIFICATION_ACTION: KEEP",
            "  VERIFICATION_ACTION : KEEP  ",
            "verification_action: keep",
            "VERIFICATION_ACTION: KEEP\n",
            "\nVERIFICATION_ACTION: KEEP\n",
        ]
        for payload in valid_keeps:
            with self.subTest(payload=payload):
                parsed = parse_active_evidence_verification_result(payload, current_answer="41")
                self.assertTrue(parsed.is_valid)
                self.assertEqual(parsed.status, "VALID_KEEP")
                self.assertEqual(parsed.action, "KEEP")
                self.assertIsNone(parsed.final_answer)

    def test_valid_replace_variations(self):
        valid_replaces = [
            ("VERIFICATION_ACTION: REPLACE\nFINAL: 42", "42"),
            ("  VERIFICATION_ACTION : REPLACE \n FINAL : 3.14159 ", "3.14159"),
            ("verification_action: replace\nfinal: Paris, France", "Paris, France"),
            ("VERIFICATION_ACTION: REPLACE\nFINAL: answer with spaces and punctuation (e.g. 10%)", "answer with spaces and punctuation (e.g. 10%)"),
        ]
        for payload, expected_final in valid_replaces:
            with self.subTest(payload=payload):
                parsed = parse_active_evidence_verification_result(payload, current_answer="41")
                self.assertTrue(parsed.is_valid)
                self.assertEqual(parsed.status, "VALID_REPLACE")
                self.assertEqual(parsed.action, "REPLACE")
                self.assertEqual(parsed.final_answer, expected_final)

    def test_invalid_rejections(self):
        invalids = [
            ("", "empty_verification_response"),
            ("   \n\t  ", "empty_verification_response"),
            ("```\nVERIFICATION_ACTION: KEEP\n```", "markdown_code_fence"),
            ("```text\nVERIFICATION_ACTION: REPLACE\nFINAL: 42\n```", "markdown_code_fence"),
            ("Here is the decision:\nVERIFICATION_ACTION: KEEP", "malformed_verification_text"),
            ("VERIFICATION_ACTION: KEEP\nBecause evidence matches.", "malformed_verification_text"),
            ("VERIFICATION_ACTION: REPLACE\nFINAL: 42\nEXTRA_FIELD: 99", "unexpected_verification_content"),
            ("VERIFICATION_ACTION: KEEP\nFINAL: 41", "keep_with_final"),
            ("VERIFICATION_ACTION: REPLACE", "replace_missing_final"),
            ("VERIFICATION_ACTION: REPLACE\nFINAL:", "replace_empty_final"),
            ("VERIFICATION_ACTION: REPLACE\nFINAL:   ", "replace_empty_final"),
            ("VERIFICATION_ACTION: REPLACE\nFINAL: 41", "replace_same_answer"),
            ("ACTION: KEEP", "unexpected_verification_field"),
            ("VERIFICATION_ACTION: MAYBE", "unknown_verification_action"),
            ("VERIFICATION_ACTION: KEEP\nVERIFICATION_ACTION: KEEP", "duplicate_verification_field"),
            ("FINAL: 42\nFINAL: 42", "duplicate_verification_field"),
            ("Just 42", "malformed_verification_text"),
        ]
        for payload, expected_error in invalids:
            with self.subTest(payload=payload):
                parsed = parse_active_evidence_verification_result(payload, current_answer="41")
                self.assertFalse(parsed.is_valid)
                self.assertEqual(parsed.status, "INVALID")
                self.assertEqual(parsed.error_type, expected_error)


class TestV8DeterministicQuery(unittest.TestCase):
    """Tests for deterministic query construction."""

    def test_query_formatting(self):
        q = "What is the speed of light in vacuum?"
        ans = "299,792,458 m/s"
        formatted = build_active_evidence_query(q, ans)
        self.assertIn(q, formatted)
        self.assertIn("Candidate answer to independently verify:", formatted)
        self.assertIn(ans, formatted)
        self.assertTrue(formatted.startswith(q))
        self.assertTrue(formatted.endswith(ans))

    def test_query_truncation_delegated_to_search_tool(self):
        long_q = "A" * 2000
        ans = "42"
        query = build_active_evidence_query(long_q, ans)
        self.assertGreater(len(query), 1500)
        tool = StubSearchTool()
        res = tool.search(query)
        self.assertTrue(res.search_query_truncated)
        self.assertEqual(len(res.provider_query), 1500)


class TestV8Triggering(unittest.TestCase):
    """Tests for active evidence verification eligibility guards."""

    def _build_agent(self, responses, search_results=None):
        llm = SequencedLLM(responses)
        search = StubSearchTool(success=True, results=search_results or sample_search_items())
        agent = GAIAActiveEvidenceVerificationAgent(
            llm_client=llm,
            search_tool=search,
        )
        agent.file_tool = CountingFileTool()
        agent.python_tool = CountingPythonTool()
        return agent, llm, search

    def test_eligible_triggers_search_and_adjudication(self):
        responses = standard_v8_responses(
            self_eval_assessment="SUSPECT",
            self_eval_risk="EVIDENCE",
            adjudication_text="VERIFICATION_ACTION: REPLACE\nFINAL: 42",
        )
        agent, llm, search = self._build_agent(responses)
        result = agent.run("What is the answer?")

        self.assertTrue(result.active_verification_eligible)
        self.assertTrue(result.active_verification_triggered)
        self.assertTrue(result.active_verification_search_attempted)
        self.assertTrue(result.active_verification_search_success)
        self.assertTrue(result.active_verification_search_usable)
        self.assertTrue(result.active_verification_adjudication_attempted)
        self.assertTrue(result.active_verification_adjudication_success)
        self.assertEqual(result.active_verification_action, "REPLACE")
        self.assertEqual(result.final_answer, "42")
        self.assertTrue(result.active_verification_answer_changed)
        # Search calls: 1 upstream + 1 active verification = 2
        self.assertEqual(search.calls, 2)
        # LLM generations: 1 router + 1 worker + 1 verifier + 1 self_eval + 1 repair + 1 adjudication = 6
        self.assertEqual(len(llm.calls), 6)

    def test_bypass_on_pass(self):
        responses = [
            response("ROUTE: DIRECT"),
            response("FINAL: 41"),
            response("VERDICT: KEEP"),
            response("ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.95"),
        ]
        agent, llm, search = self._build_agent(responses)
        result = agent.run("What is the answer?")

        self.assertFalse(result.active_verification_eligible)
        self.assertFalse(result.active_verification_triggered)
        self.assertFalse(result.active_verification_search_attempted)
        self.assertFalse(result.active_verification_adjudication_attempted)
        self.assertEqual(result.final_answer, "41")
        # Only 1 upstream search
        self.assertEqual(search.calls, 1)
        # Only 4 upstream generations
        self.assertEqual(len(llm.calls), 4)

    def test_bypass_on_suspect_non_evidence_risks(self):
        non_evidence_risks = ["REASONING", "FORMAT", "EXECUTION", "CALCULATION", "UNKNOWN"]
        for risk in non_evidence_risks:
            with self.subTest(risk=risk):
                responses = standard_v8_responses(
                    self_eval_assessment="SUSPECT",
                    self_eval_risk=risk,
                    repair_text="REPAIR_ACTION: KEEP",
                    adjudication_text=None,
                )
                agent, llm, search = self._build_agent(responses)
                result = agent.run("What is the answer?")

                self.assertFalse(result.active_verification_eligible)
                self.assertFalse(result.active_verification_triggered)
                self.assertFalse(result.active_verification_search_attempted)
                self.assertFalse(result.active_verification_adjudication_attempted)
                self.assertEqual(result.final_answer, "41")
                # 1 upstream search
                self.assertEqual(search.calls, 1)
                # 5 upstream generations (includes repair)
                self.assertEqual(len(llm.calls), 5)

    def test_bypass_on_invalid_self_eval(self):
        responses = [
            response("ROUTE: DIRECT"),
            response("FINAL: 41"),
            response("VERDICT: KEEP"),
            response("I cannot evaluate this answer."),  # Malformed self_eval
        ]
        agent, llm, search = self._build_agent(responses)
        result = agent.run("What is the answer?")

        self.assertFalse(result.active_verification_eligible)
        self.assertFalse(result.active_verification_triggered)
        self.assertFalse(result.active_verification_search_attempted)
        self.assertEqual(result.final_answer, "41")
        self.assertEqual(search.calls, 1)

    def test_bypass_on_empty_answer(self):
        responses = [
            response("ROUTE: DIRECT"),
            response(""),  # Empty candidate
        ]
        agent, llm, search = self._build_agent(responses)
        result = agent.run("What is the answer?")

        self.assertFalse(result.active_verification_eligible)
        self.assertFalse(result.active_verification_triggered)
        self.assertFalse(result.active_verification_search_attempted)
        self.assertEqual(result.final_answer, "")


class TestV8SearchBehavior(unittest.TestCase):
    """Tests for active search execution and usable evidence policy."""

    def test_search_failure_preserves_answer_and_bypasses_adjudication(self):
        responses = standard_v8_responses(
            self_eval_assessment="SUSPECT",
            self_eval_risk="EVIDENCE",
            adjudication_text=None,
        )
        llm = SequencedLLM(responses)
        # Search tool succeeds on first upstream call, fails on second active call
        class FailingActiveSearch:
            def __init__(self):
                self.calls = 0
            def search(self, q):
                self.calls += 1
                if self.calls == 1:
                    return WebSearchResult(query=q, success=True, results=[])
                return WebSearchResult(query=q, success=False, error_type="provider_timeout")

        search = FailingActiveSearch()
        agent = GAIAActiveEvidenceVerificationAgent(llm_client=llm, search_tool=search)
        agent.file_tool = CountingFileTool()
        agent.python_tool = CountingPythonTool()

        result = agent.run("What is the answer?")

        self.assertTrue(result.active_verification_eligible)
        self.assertTrue(result.active_verification_search_attempted)
        self.assertFalse(result.active_verification_search_success)
        self.assertFalse(result.active_verification_search_usable)
        self.assertEqual(result.active_verification_search_error_type, "provider_timeout")
        self.assertFalse(result.active_verification_adjudication_attempted)
        self.assertEqual(result.final_answer, "41")
        self.assertFalse(result.active_verification_answer_changed)
        # No extra adjudication generation was called
        self.assertEqual(len(llm.calls), 5)

    def test_zero_results_preserves_answer_and_bypasses_adjudication(self):
        responses = standard_v8_responses(
            self_eval_assessment="SUSPECT",
            self_eval_risk="EVIDENCE",
            adjudication_text=None,
        )
        llm = SequencedLLM(responses)
        # Search tool returns success=True but results=[]
        search = StubSearchTool(success=True, results=[])
        agent = GAIAActiveEvidenceVerificationAgent(llm_client=llm, search_tool=search)
        agent.file_tool = CountingFileTool()
        agent.python_tool = CountingPythonTool()

        result = agent.run("What is the answer?")

        self.assertTrue(result.active_verification_eligible)
        self.assertTrue(result.active_verification_search_attempted)
        self.assertTrue(result.active_verification_search_success)
        self.assertFalse(result.active_verification_search_usable)
        self.assertEqual(result.active_verification_search_error_type, "zero_search_results")
        self.assertFalse(result.active_verification_adjudication_attempted)
        self.assertEqual(result.final_answer, "41")
        self.assertFalse(result.active_verification_answer_changed)
        self.assertEqual(len(llm.calls), 5)


class TestV8FailurePreservation(unittest.TestCase):
    """Tests proving all failure modes preserve the Frozen V7 answer verbatim."""

    def _run_with_adjudication_response(self, adj_resp):
        responses = standard_v8_responses(
            self_eval_assessment="SUSPECT",
            self_eval_risk="EVIDENCE",
            adjudication_text=None,
        )
        responses.append(adj_resp)
        llm = SequencedLLM(responses)
        search = StubSearchTool(success=True, results=sample_search_items())
        agent = GAIAActiveEvidenceVerificationAgent(llm_client=llm, search_tool=search)
        agent.file_tool = CountingFileTool()
        agent.python_tool = CountingPythonTool()
        return agent.run("What is the answer?")

    def test_timeout_preserves_answer(self):
        result = self._run_with_adjudication_response(Exception("Deadline exceeded timeout"))
        self.assertEqual(result.final_answer, "41")
        self.assertFalse(result.active_verification_adjudication_success)
        self.assertEqual(result.active_verification_error_type, "provider_timeout")
        self.assertFalse(result.active_verification_answer_changed)

    def test_malformed_function_call_preserves_answer(self):
        result = self._run_with_adjudication_response(
            response("some output", finish_reason="MALFORMED_FUNCTION_CALL")
        )
        self.assertEqual(result.final_answer, "41")
        self.assertFalse(result.active_verification_adjudication_success)
        self.assertEqual(result.active_verification_error_type, "malformed_function_call_finish_reason")
        self.assertFalse(result.active_verification_answer_changed)

    def test_malformed_schema_preserves_answer(self):
        result = self._run_with_adjudication_response(response("I think the answer is 42."))
        self.assertEqual(result.final_answer, "41")
        self.assertFalse(result.active_verification_adjudication_success)
        self.assertEqual(result.active_verification_error_type, "malformed_verification_text")
        self.assertFalse(result.active_verification_answer_changed)

    def test_same_answer_replace_preserves_answer(self):
        result = self._run_with_adjudication_response(
            response("VERIFICATION_ACTION: REPLACE\nFINAL: 41")
        )
        self.assertEqual(result.final_answer, "41")
        self.assertFalse(result.active_verification_adjudication_success)
        self.assertEqual(result.active_verification_error_type, "replace_same_answer")
        self.assertFalse(result.active_verification_answer_changed)


class TestV8Budgets(unittest.TestCase):
    """Tests asserting strict budget invariants in V8."""

    def test_budget_caps(self):
        responses = standard_v8_responses(
            self_eval_assessment="SUSPECT",
            self_eval_risk="EVIDENCE",
            adjudication_text="VERIFICATION_ACTION: KEEP",
        )
        llm = SequencedLLM(responses)
        search = StubSearchTool(success=True, results=sample_search_items())
        agent = GAIAActiveEvidenceVerificationAgent(llm_client=llm, search_tool=search)
        agent.file_tool = CountingFileTool()
        agent.python_tool = CountingPythonTool()

        result = agent.run("What is the answer?")

        # Search calls: exactly 2 (1 upstream + 1 active verification)
        self.assertEqual(search.calls, 2)
        # LLM calls: exactly 6 (Router, Worker, Verifier, Self-Eval, Repair, Adjudication)
        self.assertEqual(len(llm.calls), 6)
        self.assertEqual(result.llm_generation_attempts, 6)
        # Python calls from V8: exactly 0
        self.assertEqual(agent.python_tool.calls, 0)
        # File calls: exactly 0 from V8
        self.assertEqual(agent.file_tool.calls, 0)


class TestV8FrozenV7Preservation(unittest.TestCase):
    """Tests ensuring Frozen V7 behavior is preserved identically."""

    def test_ineligible_task_identical_to_v7(self):
        v7_responses = [
            response("ROUTE: DIRECT"),
            response("FINAL: 41"),
            response("VERDICT: KEEP"),
            response("ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.95"),
        ]
        v8_responses = list(v7_responses)

        search1 = StubSearchTool(success=True, results=[])
        search2 = StubSearchTool(success=True, results=[])

        v7_agent = GAIATargetedRepairAgent(llm_client=SequencedLLM(v7_responses), search_tool=search1)
        v8_agent = GAIAActiveEvidenceVerificationAgent(llm_client=SequencedLLM(v8_responses), search_tool=search2)

        res_v7 = v7_agent.run("What is 2+2?")
        res_v8 = v8_agent.run("What is 2+2?")

        self.assertEqual(res_v8.final_answer, res_v7.final_answer)
        self.assertEqual(res_v8.llm_generation_attempts, res_v7.llm_generation_attempts)
        self.assertEqual(search2.calls, search1.calls)


class TestV8PrivacyFirewall(unittest.TestCase):
    """Tests guaranteeing the adjudication prompt does not leak forbidden state."""

    def test_firewall_prompt_construction(self):
        prompt = build_active_evidence_verification_prompt(
            question="What is the population of Paris?",
            current_answer="2.1 million",
            new_evidence="Latest census confirms 2.16 million.",
            web_evidence="Old search results from 2010.",
            file_evidence="Census report attached.",
            attachment_filename="census.pdf",
            risk_type="EVIDENCE",
            confidence=0.90,
            execution_summary="Ran direct worker.",
        )

        forbidden_tokens = [
            "ground_truth",
            "reference_answer",
            "official_scorer",
            "is_correct",
            "pre_repair_correct",
            "post_repair_correct",
            "traceback",
            "stdout",
            "stderr",
            "def run_code",
            "import os",
        ]
        for token in forbidden_tokens:
            self.assertNotIn(token, prompt.lower())

        self.assertIn("What is the population of Paris?", prompt)
        self.assertIn("2.1 million", prompt)
        self.assertIn("Latest census confirms 2.16 million.", prompt)
        self.assertIn("VERIFICATION_ACTION: KEEP", prompt)
        self.assertIn("VERIFICATION_ACTION: REPLACE", prompt)


class TestV8Metrics(unittest.TestCase):
    """Tests for pure post-hoc active evidence verification metrics."""

    def test_metrics_computation(self):
        records = [
            # 1. Triggered: wrong -> correct (IMPROVEMENT)
            {
                "task_id": "t1",
                "active_verification_eligible": True,
                "active_verification_triggered": True,
                "active_verification_search_attempted": True,
                "active_verification_search_success": True,
                "active_verification_search_usable": True,
                "active_verification_adjudication_attempted": True,
                "active_verification_adjudication_success": True,
                "active_verification_action": "REPLACE",
                "active_verification_answer_changed": True,
                "pre_active_verification_correct": False,
                "correct": True,
                "self_eval_assessment": "SUSPECT",
                "self_eval_risk_type": "EVIDENCE",
                "self_eval_success": True,
                "pre_repair_answer": "wrong",
            },
            # 2. Triggered: correct -> wrong (REGRESSION)
            {
                "task_id": "t2",
                "active_verification_eligible": True,
                "active_verification_triggered": True,
                "active_verification_search_attempted": True,
                "active_verification_search_success": True,
                "active_verification_search_usable": True,
                "active_verification_adjudication_attempted": True,
                "active_verification_adjudication_success": True,
                "active_verification_action": "REPLACE",
                "active_verification_answer_changed": True,
                "pre_active_verification_correct": True,
                "correct": False,
                "self_eval_assessment": "SUSPECT",
                "self_eval_risk_type": "EVIDENCE",
                "self_eval_success": True,
                "pre_repair_answer": "right",
            },
            # 3. Triggered: correct -> correct (STABLE_CORRECT via KEEP)
            {
                "task_id": "t3",
                "active_verification_eligible": True,
                "active_verification_triggered": True,
                "active_verification_search_attempted": True,
                "active_verification_search_success": True,
                "active_verification_search_usable": True,
                "active_verification_adjudication_attempted": True,
                "active_verification_adjudication_success": True,
                "active_verification_action": "KEEP",
                "active_verification_answer_changed": False,
                "pre_active_verification_correct": True,
                "correct": True,
                "self_eval_assessment": "SUSPECT",
                "self_eval_risk_type": "EVIDENCE",
                "self_eval_success": True,
                "pre_repair_answer": "right",
            },
            # 4. Triggered: wrong -> wrong (STABLE_FAILURE via KEEP)
            {
                "task_id": "t4",
                "active_verification_eligible": True,
                "active_verification_triggered": True,
                "active_verification_search_attempted": True,
                "active_verification_search_success": True,
                "active_verification_search_usable": True,
                "active_verification_adjudication_attempted": True,
                "active_verification_adjudication_success": True,
                "active_verification_action": "KEEP",
                "active_verification_answer_changed": False,
                "pre_active_verification_correct": False,
                "correct": False,
                "self_eval_assessment": "SUSPECT",
                "self_eval_risk_type": "EVIDENCE",
                "self_eval_success": True,
                "pre_repair_answer": "wrong",
            },
            # 5. Ineligible: PASS (NOT_TRIGGERED)
            {
                "task_id": "t5",
                "active_verification_eligible": False,
                "active_verification_triggered": False,
                "pre_active_verification_correct": True,
                "correct": True,
                "self_eval_assessment": "PASS",
                "self_eval_risk_type": "NONE",
                "self_eval_success": True,
                "pre_repair_answer": "right",
            },
        ]

        metrics = calculate_active_verification_metrics(records)

        self.assertEqual(metrics["benchmark_tasks_count"], 5)
        self.assertEqual(metrics["improvements"], 1)
        self.assertEqual(metrics["regressions"], 1)
        self.assertEqual(metrics["stable_correct"], 1)
        self.assertEqual(metrics["stable_failure"], 1)
        self.assertEqual(metrics["net_active_verification_delta"], 0)
        # correction rate: 1 improvement / 2 initially wrong eligible = 0.5
        self.assertEqual(metrics["correction_rate"], 0.5)
        # harm rate: 1 regression / 2 initially correct eligible = 0.5
        self.assertEqual(metrics["harm_rate"], 0.5)
        self.assertEqual(metrics["active_verification_eligible_count"], 4)
        self.assertEqual(metrics["active_verification_triggered_count"], 4)
        self.assertEqual(metrics["active_verification_search_usable_count"], 4)
        self.assertEqual(metrics["active_verification_valid_adjudication_count"], 4)
        self.assertEqual(metrics["active_verification_keep_count"], 2)
        self.assertEqual(metrics["active_verification_replace_count"], 2)
        self.assertEqual(metrics["usable_evidence_rate"], 1.0)
        self.assertEqual(metrics["adjudication_coverage"], 1.0)
        self.assertEqual(metrics["change_rate"], 0.5)


class TestV8RunnerIntegration(unittest.TestCase):
    """Tests execute_task with V8 agent and serialization."""

    def test_runner_v8_serialization(self):
        responses = standard_v8_responses(
            self_eval_assessment="SUSPECT",
            self_eval_risk="EVIDENCE",
            adjudication_text="VERIFICATION_ACTION: REPLACE\nFINAL: 42",
        )
        llm = SequencedLLM(responses)
        search = StubSearchTool(success=True, results=sample_search_items())
        agent = GAIAActiveEvidenceVerificationAgent(llm_client=llm, search_tool=search)

        record = execute_task(
            task_id="test-v8-task",
            question="What is 40 + 2?",
            level=1,
            agent=agent,
            llm=llm,
            project_version="v8",
            schema_version=7,
        )

        self.assertEqual(record["schema_version"], 7)
        self.assertEqual(record["project_version"], "v8")
        self.assertEqual(record["final_answer"], "42")
        self.assertTrue(record["active_verification_eligible"])
        self.assertTrue(record["active_verification_triggered"])
        self.assertEqual(record["active_verification_action"], "REPLACE")
        self.assertTrue(record["active_verification_answer_changed"])
        self.assertEqual(record["llm_generation_attempts"], 6)
