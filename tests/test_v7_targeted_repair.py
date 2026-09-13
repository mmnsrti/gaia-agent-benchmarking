import json
import unittest
from typing import Any, List, Optional

from agent.agent import GAIASelfEvaluationAgent, GAIATargetedRepairAgent, GAIAVerificationAgent
from agent.llm import LLMResponse
from evaluation.dataset import GAIATask
from evaluation.evaluate import calculate_metrics
from evaluation.runner import execute_task
from evaluation.targeted_repair_metrics import calculate_targeted_repair_metrics
from prompts.targeted_repair import (
    TARGETED_REPAIR_PROMPT_VERSION,
    build_targeted_repair_prompt,
    parse_targeted_repair_result,
)
from tools.file_tool import FileResult
from tools.web_search import WebSearchResult


class StubSearchTool:
    def __init__(self, success: bool = True):
        self.success = success
        self.calls = 0

    def search(self, question: str) -> WebSearchResult:
        self.calls += 1
        return WebSearchResult(query=question, success=self.success, results=[])


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
        raise AssertionError("DIRECT-route V7 targeted repair must not execute Python")


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


def response(text: str, finish_reason: str = "STOP") -> LLMResponse:
    return LLMResponse(text=text, raw_text=text, finish_reason=finish_reason)


def standard_v7_responses(
    self_eval_assessment: str = "SUSPECT",
    self_eval_risk: str = "REASONING",
    repair_text: Optional[str] = None,
) -> List[Any]:
    responses = [
        response("ROUTE: DIRECT"),
        response("FINAL: 41"),
        response("VERDICT: KEEP"),
        response(f"ASSESSMENT: {self_eval_assessment}\nRISK_TYPE: {self_eval_risk}\nCONFIDENCE: 0.85"),
    ]
    if repair_text is not None:
        responses.append(response(repair_text))
    return responses


class TestV7TargetedRepairParser(unittest.TestCase):
    """Tests for targeted repair output parsing and strict schema enforcement."""

    def test_valid_keep_variations(self):
        valid_keeps = [
            "REPAIR_ACTION: KEEP",
            "  REPAIR_ACTION : KEEP  ",
            "repair_action: keep",
            "REPAIR_ACTION: KEEP\n",
            "\nREPAIR_ACTION: KEEP\n",
        ]
        for payload in valid_keeps:
            with self.subTest(payload=payload):
                parsed = parse_targeted_repair_result(payload, current_answer="41")
                self.assertTrue(parsed.is_valid)
                self.assertEqual(parsed.status, "VALID_KEEP")
                self.assertEqual(parsed.action, "KEEP")
                self.assertIsNone(parsed.final_answer)

    def test_valid_replace_variations(self):
        valid_replaces = [
            ("REPAIR_ACTION: REPLACE\nFINAL: 42", "42"),
            ("  REPAIR_ACTION : REPLACE \n FINAL : 3.14159 ", "3.14159"),
            ("repair_action: replace\nfinal: Paris, France", "Paris, France"),
            ("REPAIR_ACTION: REPLACE\nFINAL: answer with spaces and punctuation (e.g. 10%)", "answer with spaces and punctuation (e.g. 10%)"),
        ]
        for payload, expected_final in valid_replaces:
            with self.subTest(payload=payload):
                parsed = parse_targeted_repair_result(payload, current_answer="41")
                self.assertTrue(parsed.is_valid)
                self.assertEqual(parsed.status, "VALID_REPLACE")
                self.assertEqual(parsed.action, "REPLACE")
                self.assertEqual(parsed.final_answer, expected_final)

    def test_parser_rejects_schema_and_content_failures(self):
        invalid_payloads = [
            ("", "empty_repair_response"),
            ("   \n\t", "empty_repair_response"),
            ("FINAL: 42", "missing_repair_field"),
            ("REPAIR_ACTION: REVISE\nFINAL: 42", "unknown_repair_action"),
            ("REPAIR_ACTION: PASS", "unknown_repair_action"),
            ("REPAIR_ACTION: SUSPECT", "unknown_repair_action"),
            ("REPAIR_ACTION: REPLACE", "replace_missing_final"),
            ("REPAIR_ACTION: REPLACE\nFINAL: ", "replace_empty_final"),
            ("REPAIR_ACTION: REPLACE\nFINAL:    \n\t", "replace_empty_final"),
            ("REPAIR_ACTION: KEEP\nFINAL: 42", "keep_with_final"),
            ("REPAIR_ACTION: KEEP\nSome reasoning text", "malformed_repair_text"),
            ("```\nREPAIR_ACTION: KEEP\n```", "markdown_code_fence"),
            ("```text\nREPAIR_ACTION: REPLACE\nFINAL: 42\n```", "markdown_code_fence"),
            ("Here is my repair:\nREPAIR_ACTION: KEEP", "malformed_repair_text"),
            ("REPAIR_ACTION: KEEP\nREPAIR_ACTION: KEEP", "duplicate_repair_field"),
            ("REPAIR_ACTION: REPLACE\nFINAL: 42\nFINAL: 43", "unexpected_repair_content"),
            ("REPAIR_ACTION: REPLACE\nFINAL: line 1\nline 2", "unexpected_repair_content"),
        ]
        for payload, expected_error in invalid_payloads:
            with self.subTest(payload=payload, expected_error=expected_error):
                parsed = parse_targeted_repair_result(payload, current_answer="41")
                self.assertFalse(parsed.is_valid)
                self.assertEqual(parsed.status, "INVALID")
                self.assertEqual(parsed.error_type, expected_error)

    def test_parser_rejects_same_answer(self):
        parsed = parse_targeted_repair_result(
            "REPAIR_ACTION: REPLACE\nFINAL: 41",
            current_answer="41",
        )
        self.assertFalse(parsed.is_valid)
        self.assertEqual(parsed.status, "INVALID")
        self.assertEqual(parsed.error_type, "replace_same_answer")

        # Also normalized comparison (whitespace stripped)
        parsed_ws = parse_targeted_repair_result(
            "REPAIR_ACTION: REPLACE\nFINAL:   41  ",
            current_answer="41",
        )
        self.assertFalse(parsed_ws.is_valid)
        self.assertEqual(parsed_ws.status, "INVALID")
        self.assertEqual(parsed_ws.error_type, "replace_same_answer")


class TestV7PromptBuilderAndFirewall(unittest.TestCase):
    """Tests that prompt builder adheres to strict information firewall."""

    def test_prompt_includes_permitted_context(self):
        prompt = build_targeted_repair_prompt(
            question="What is 40 + 2?",
            current_answer="41",
            self_eval_assessment="SUSPECT",
            self_eval_risk_type="CALCULATION",
            self_eval_confidence=0.85,
            execution_summary="Route: DIRECT\nSearch: success",
            web_evidence="The sum of 40 and 2 is 42.",
            file_evidence="Evidence file content.",
            attachment_filename="math.txt",
        )
        self.assertIn("What is 40 + 2?", prompt)
        self.assertIn("41", prompt)
        self.assertIn("SUSPECT", prompt)
        self.assertIn("CALCULATION", prompt)
        self.assertIn("0.85", prompt)
        self.assertIn("The sum of 40 and 2 is 42.", prompt)
        self.assertIn("Evidence file content.", prompt)
        self.assertIn("math.txt", prompt)
        self.assertIn("REPAIR_ACTION: KEEP", prompt)
        self.assertIn("REPAIR_ACTION: REPLACE", prompt)
        self.assertIn("targeted-repair-v1", TARGETED_REPAIR_PROMPT_VERSION)

    def test_scorer_firewall_prompt_omits_forbidden_material(self):
        prompt = build_targeted_repair_prompt(
            question="What is 40 + 2?",
            current_answer="41",
            self_eval_assessment="SUSPECT",
            self_eval_risk_type="REASONING",
            self_eval_confidence=0.8,
            execution_summary="Route: DIRECT",
        )
        lower_prompt = prompt.lower()
        self.assertNotIn("ground_truth", lower_prompt)
        self.assertNotIn("groundtruth", lower_prompt)
        self.assertNotIn("scorer", lower_prompt)
        self.assertNotIn("gaia_question_scorer", lower_prompt)
        self.assertNotIn("true_positive", lower_prompt)
        self.assertNotIn("accuracy", lower_prompt)
        self.assertNotIn("correctness", lower_prompt)
        self.assertNotIn("VERDICT: KEEP", prompt)
        self.assertNotIn("VERDICT: REVISE", prompt)


class TestV7RuntimeAndTriggerLogic(unittest.TestCase):
    """Tests for V7 runtime execution, trigger logic, and generation budget."""

    def make_agent(self, responses: List[Any]):
        self.search = StubSearchTool()
        self.llm = SequencedLLM(responses)
        return GAIATargetedRepairAgent(llm_client=self.llm, search_tool=self.search)

    def test_pass_assessment_bypasses_repair(self):
        agent = self.make_agent(standard_v7_responses(self_eval_assessment="PASS", self_eval_risk="NONE"))
        result = agent.run("Question")
        self.assertEqual(result.final_answer, "41")
        self.assertFalse(result.repair_eligible)
        self.assertFalse(result.repair_triggered)
        self.assertFalse(result.repair_attempted)
        self.assertEqual(result.repair_generation_attempts, 0)
        self.assertEqual(result.llm_generation_attempts, 4)
        self.assertEqual(len(self.llm.calls), 4)

    def test_empty_answer_bypasses_repair(self):
        agent = self.make_agent([
            response("ROUTE: DIRECT"),
            response(""),
        ])
        result = agent.run("Question")
        self.assertEqual(result.final_answer, "")
        self.assertFalse(result.repair_eligible)
        self.assertFalse(result.repair_triggered)
        self.assertFalse(result.repair_attempted)
        self.assertEqual(result.repair_generation_attempts, 0)
        self.assertEqual(result.llm_generation_attempts, 2)
        self.assertEqual(len(self.llm.calls), 2)

    def test_invalid_self_eval_bypasses_repair(self):
        responses = [
            response("ROUTE: DIRECT"),
            response("FINAL: 41"),
            response("VERDICT: KEEP"),
            response("MALFORMED SELF EVALUATION"),
        ]
        agent = self.make_agent(responses)
        result = agent.run("Question")
        self.assertEqual(result.final_answer, "41")
        self.assertFalse(result.repair_eligible)
        self.assertFalse(result.repair_triggered)
        self.assertFalse(result.repair_attempted)
        self.assertEqual(result.repair_generation_attempts, 0)
        self.assertEqual(result.llm_generation_attempts, 4)
        self.assertEqual(len(self.llm.calls), 4)

    def test_valid_suspect_triggers_repair_keep(self):
        agent = self.make_agent(standard_v7_responses(
            self_eval_assessment="SUSPECT",
            self_eval_risk="REASONING",
            repair_text="REPAIR_ACTION: KEEP",
        ))
        result = agent.run("Question")
        self.assertEqual(result.final_answer, "41")
        self.assertEqual(result.pre_repair_answer, "41")
        self.assertEqual(result.post_repair_answer, "41")
        self.assertTrue(result.repair_eligible)
        self.assertTrue(result.repair_triggered)
        self.assertTrue(result.repair_attempted)
        self.assertTrue(result.repair_success)
        self.assertEqual(result.repair_action, "KEEP")
        self.assertFalse(result.repair_answer_changed)
        self.assertEqual(result.repair_generation_attempts, 1)
        self.assertEqual(result.llm_generation_attempts, 5)
        self.assertEqual(len(self.llm.calls), 5)
        # Check that repair was called without attachments and with max_retries=0
        self.assertEqual(self.llm.calls[4]["max_retries"], 0)
        self.assertIsNone(self.llm.calls[4]["attachment_parts"])

    def test_valid_suspect_triggers_repair_replace(self):
        agent = self.make_agent(standard_v7_responses(
            self_eval_assessment="SUSPECT",
            self_eval_risk="REASONING",
            repair_text="REPAIR_ACTION: REPLACE\nFINAL: 42",
        ))
        result = agent.run("Question")
        self.assertEqual(result.final_answer, "42")
        self.assertEqual(result.pre_repair_answer, "41")
        self.assertEqual(result.post_repair_answer, "42")
        self.assertTrue(result.repair_eligible)
        self.assertTrue(result.repair_triggered)
        self.assertTrue(result.repair_attempted)
        self.assertTrue(result.repair_success)
        self.assertEqual(result.repair_action, "REPLACE")
        self.assertTrue(result.repair_answer_changed)
        self.assertEqual(result.repair_generation_attempts, 1)
        self.assertEqual(result.llm_generation_attempts, 5)
        self.assertEqual(len(self.llm.calls), 5)


class TestV7FailureSafety(unittest.TestCase):
    """Tests that any repair stage error preserves pre_repair_answer."""

    def make_agent(self, repair_response: Any):
        responses = [
            response("ROUTE: DIRECT"),
            response("FINAL: 41"),
            response("VERDICT: KEEP"),
            response("ASSESSMENT: SUSPECT\nRISK_TYPE: REASONING\nCONFIDENCE: 0.85"),
            repair_response,
        ]
        self.search = StubSearchTool()
        self.llm = SequencedLLM(responses)
        return GAIATargetedRepairAgent(llm_client=self.llm, search_tool=self.search)

    def test_timeout_fallback_preserves_answer(self):
        agent = self.make_agent(Exception("Read timed out"))
        result = agent.run("Question")
        self.assertEqual(result.final_answer, "41")
        self.assertEqual(result.pre_repair_answer, "41")
        self.assertEqual(result.post_repair_answer, "41")
        self.assertFalse(result.repair_success)
        self.assertFalse(result.repair_answer_changed)
        self.assertEqual(result.repair_error_type, "provider_timeout")
        self.assertEqual(result.llm_generation_attempts, 5)

    def test_malformed_function_call_preserves_answer(self):
        agent = self.make_agent(response("", finish_reason="MALFORMED_FUNCTION_CALL"))
        result = agent.run("Question")
        self.assertEqual(result.final_answer, "41")
        self.assertFalse(result.repair_success)
        self.assertFalse(result.repair_answer_changed)
        self.assertEqual(result.repair_error_type, "malformed_function_call_finish_reason")

    def test_parser_error_preserves_answer(self):
        agent = self.make_agent(response("I am unable to repair this answer."))
        result = agent.run("Question")
        self.assertEqual(result.final_answer, "41")
        self.assertFalse(result.repair_success)
        self.assertFalse(result.repair_answer_changed)
        self.assertEqual(result.repair_error_type, "malformed_repair_text")

    def test_redundant_replace_error_preserves_answer(self):
        agent = self.make_agent(response("REPAIR_ACTION: REPLACE\nFINAL: 41"))
        result = agent.run("Question")
        self.assertEqual(result.final_answer, "41")
        self.assertFalse(result.repair_success)
        self.assertFalse(result.repair_answer_changed)
        self.assertEqual(result.repair_error_type, "replace_same_answer")


class TestV7ToolIsolationAndBoundedness(unittest.TestCase):
    """Tests tool isolation and strict generation bounds for V7."""

    def test_no_extra_tools_during_repair(self):
        search = StubSearchTool()
        file_tool = CountingFileTool()
        python_tool = CountingPythonTool()
        llm = SequencedLLM(standard_v7_responses(
            self_eval_assessment="SUSPECT",
            self_eval_risk="REASONING",
            repair_text="REPAIR_ACTION: REPLACE\nFINAL: 42",
        ))
        agent = GAIATargetedRepairAgent(
            llm_client=llm,
            search_tool=search,
            file_tool=file_tool,
            python_tool=python_tool,
        )
        result = agent.run("Question", file_path="evidence.txt")
        self.assertEqual(result.final_answer, "42")
        self.assertEqual(search.calls, 1)  # Only during worker
        self.assertEqual(file_tool.calls, 1)  # Only during worker
        self.assertEqual(python_tool.calls, 0)  # Direct route, 0 python
        self.assertEqual(len(llm.calls), 5)  # Exactly 5 generations

    def test_generation_budget_invariant(self):
        # Even with complex paths, generation attempts must never exceed 5
        agent = GAIATargetedRepairAgent(
            llm_client=SequencedLLM(standard_v7_responses(
                repair_text="REPAIR_ACTION: KEEP",
            )),
            search_tool=StubSearchTool(),
        )
        result = agent.run("Question")
        self.assertLessEqual(result.llm_generation_attempts, 5)


class TestV7VersionDispatchAndSubclassResolution(unittest.TestCase):
    """Tests that runner.py resolves GAIATargetedRepairAgent as v7, not v6."""

    def test_subclass_resolution_order(self):
        agent = GAIATargetedRepairAgent(
            llm_client=SequencedLLM(standard_v7_responses(repair_text="REPAIR_ACTION: KEEP")),
            search_tool=StubSearchTool(),
        )
        self.assertIsInstance(agent, GAIATargetedRepairAgent)
        self.assertIsInstance(agent, GAIASelfEvaluationAgent)
        self.assertIsInstance(agent, GAIAVerificationAgent)

        # execute_task auto-infer version
        record = execute_task(
            task_id="dispatch-test",
            question="Question",
            level=1,
            agent=agent,
            project_version="v7",
        )
        self.assertEqual(record["project_version"], "v7")
        self.assertEqual(record["schema_version"], 6)
        self.assertEqual(record["repair_action"], "KEEP")
        self.assertNotIn("repair_prompt", record)
        self.assertNotIn("repair_raw_response", record)

    def test_v6_parent_isolation(self):
        v6_agent = GAIASelfEvaluationAgent(
            llm_client=SequencedLLM([
                response("ROUTE: DIRECT"),
                response("FINAL: 42"),
                response("VERDICT: KEEP"),
                response("ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.9"),
            ]),
            search_tool=StubSearchTool(),
        )
        record = execute_task(
            task_id="v6-dispatch-test",
            question="Question",
            level=1,
            agent=v6_agent,
            project_version="v6",
        )
        self.assertEqual(record["project_version"], "v6")
        self.assertEqual(record["schema_version"], 5)
        self.assertIsNone(record["repair_action"])
        self.assertFalse(record["repair_attempted"])


class TestV7DiagnosticAnchoring(unittest.TestCase):
    """Tests that V6 self-eval metrics are anchored to pre_repair_correct."""

    def test_anchoring_prevents_successful_repair_turning_tp_into_fp(self):
        # Scenario:
        # Pre-repair answer: "41" (INCORRECT, gt is "42")
        # Self-eval says SUSPECT (this is a true positive failure detection!)
        # Repair says REPLACE -> "42" (now CORRECT)
        # If evaluated against post-repair ("42"), self-eval would look like a False Positive!
        # It MUST be evaluated against pre-repair ("41"), so it remains a True Positive.
        predictions = [{
            "task_id": "task-anchor-1",
            "final_answer": "42",
            "pre_repair_answer": "41",
            "post_repair_answer": "42",
            "repair_eligible": True,
            "repair_triggered": True,
            "repair_attempted": True,
            "repair_success": True,
            "repair_action": "REPLACE",
            "repair_answer_changed": True,
            "self_eval_eligible": True,
            "self_eval_attempted": True,
            "self_eval_success": True,
            "self_eval_assessment": "SUSPECT",
            "self_eval_risk_type": "CALCULATION",
            "self_eval_confidence": 0.9,
            "self_eval_answer_unchanged": True,
            "request_success": True,
            "completion_success": True,
            "project_version": "v7",
        }]
        tasks = {
            "task-anchor-1": GAIATask(
                task_id="task-anchor-1",
                question="What is 40 + 2?",
                final_answer="42",
                level=1,
            )
        }
        result = calculate_metrics(predictions, tasks, level=1, project_version="v7", expected_task_count=1)
        summary = result["summary"]
        # In summary, self_eval true positive must be 1, false positive must be 0!
        self.assertEqual(summary["self_eval_true_positive"], 1)
        self.assertEqual(summary["self_eval_false_positive"], 0)
        self.assertEqual(summary["self_eval_precision"], 1.0)
        # And repair metrics:
        self.assertEqual(summary["repair_improvements"], 1)
        self.assertEqual(summary["repair_regressions"], 0)
        self.assertEqual(summary["pre_repair_correct_tasks"], 0)
        self.assertEqual(summary["post_repair_correct_tasks"], 1)
        self.assertEqual(summary["net_repair_correct_delta"], 1)


class TestV7WithinRunRepairMetrics(unittest.TestCase):
    """Tests the within-run repair transition and diagnostic metrics."""

    def test_transition_and_rate_calculations(self):
        records = [
            # Improvement: was wrong, repaired to correct
            {
                "task_id": "1",
                "pre_repair_answer": "wrong",
                "post_repair_answer": "correct",
                "pre_repair_correct": False,
                "post_repair_correct": True,
                "repair_eligible": True,
                "repair_triggered": True,
                "repair_attempted": True,
                "repair_success": True,
                "repair_action": "REPLACE",
                "repair_answer_changed": True,
                "self_eval_risk_type": "REASONING",
                "repair_transition": "IMPROVEMENT",
            },
            # Regression (Harm): was correct, repaired to wrong
            {
                "task_id": "2",
                "pre_repair_answer": "correct",
                "post_repair_answer": "wrong",
                "pre_repair_correct": True,
                "post_repair_correct": False,
                "repair_eligible": True,
                "repair_triggered": True,
                "repair_attempted": True,
                "repair_success": True,
                "repair_action": "REPLACE",
                "repair_answer_changed": True,
                "self_eval_risk_type": "CALCULATION",
                "repair_transition": "REGRESSION",
            },
            # Stable correct: was correct, KEEP action
            {
                "task_id": "3",
                "pre_repair_answer": "correct",
                "post_repair_answer": "correct",
                "pre_repair_correct": True,
                "post_repair_correct": True,
                "repair_eligible": True,
                "repair_triggered": True,
                "repair_attempted": True,
                "repair_success": True,
                "repair_action": "KEEP",
                "repair_answer_changed": False,
                "self_eval_risk_type": "EVIDENCE",
                "repair_transition": "STABLE_CORRECT",
            },
            # Stable failure: was wrong, KEEP or failed repair
            {
                "task_id": "4",
                "pre_repair_answer": "wrong",
                "post_repair_answer": "wrong",
                "pre_repair_correct": False,
                "post_repair_correct": False,
                "repair_eligible": True,
                "repair_triggered": True,
                "repair_attempted": True,
                "repair_success": True,
                "repair_action": "KEEP",
                "repair_answer_changed": False,
                "self_eval_risk_type": "FORMAT",
                "repair_transition": "STABLE_FAILURE",
            },
            # Not triggered: self_eval PASS
            {
                "task_id": "5",
                "pre_repair_answer": "correct",
                "post_repair_answer": "correct",
                "pre_repair_correct": True,
                "post_repair_correct": True,
                "repair_eligible": False,
                "repair_triggered": False,
                "repair_attempted": False,
                "repair_success": False,
                "repair_action": None,
                "repair_answer_changed": False,
                "self_eval_risk_type": "NONE",
                "repair_transition": "NOT_TRIGGERED",
            },
        ]
        metrics = calculate_targeted_repair_metrics(records, total_benchmark_tasks=5)
        self.assertEqual(metrics["repair_eligible_count"], 4)
        self.assertEqual(metrics["repair_triggered_count"], 4)
        self.assertEqual(metrics["repair_attempted_count"], 4)
        self.assertEqual(metrics["repair_improvements"], 1)
        self.assertEqual(metrics["repair_regressions"], 1)
        self.assertEqual(metrics["repair_stable_correct"], 1)
        self.assertEqual(metrics["repair_stable_failure"], 1)
        self.assertEqual(metrics["repair_not_triggered"], 1)
        self.assertEqual(metrics["pre_repair_correct_tasks"], 3)
        self.assertEqual(metrics["post_repair_correct_tasks"], 3)
        self.assertEqual(metrics["net_repair_correct_delta"], 0)
        self.assertEqual(metrics["repair_harm_count"], 1)
        self.assertEqual(metrics["repair_harm_rate"], 0.5)
        self.assertEqual(metrics["repair_keep_count"], 2)
        self.assertEqual(metrics["repair_replace_count"], 2)

    def test_zero_denominators_safety(self):
        metrics = calculate_targeted_repair_metrics([], total_benchmark_tasks=0)
        self.assertEqual(metrics["repair_triggered_count"], 0)
        self.assertEqual(metrics["repair_trigger_rate"], 0.0)
        self.assertIsNone(metrics["repair_valid_output_rate"])
        self.assertIsNone(metrics["repair_correction_rate"])
        self.assertIsNone(metrics["repair_harm_rate"])


class TestV7HarmAndConservativeKeep(unittest.TestCase):
    """Tests illustrating the utility of conservative KEEP under false-alarm SUSPECT."""

    def test_conservative_keep_prevents_harm_on_false_positive(self):
        # When self-eval has a false alarm on a correct answer:
        # Case A: Repair KEEP -> Stays correct (0 harm)
        records_keep = [{
            "pre_repair_answer": "correct",
            "post_repair_answer": "correct",
            "pre_repair_correct": True,
            "post_repair_correct": True,
            "repair_eligible": True,
            "repair_triggered": True,
            "repair_attempted": True,
            "repair_success": True,
            "repair_action": "KEEP",
            "repair_answer_changed": False,
            "self_eval_risk_type": "REASONING",
            "repair_transition": "STABLE_CORRECT",
        }]
        m_keep = calculate_targeted_repair_metrics(records_keep, total_benchmark_tasks=1)
        self.assertEqual(m_keep["repair_harm_count"], 0)
        self.assertEqual(m_keep["repair_regressions"], 0)
        self.assertEqual(m_keep["repair_stable_correct"], 1)

        # Case B: Repair REPLACE with wrong answer -> Regression (1 harm)
        records_replace = [{
            "pre_repair_answer": "correct",
            "post_repair_answer": "wrong_hallucination",
            "pre_repair_correct": True,
            "post_repair_correct": False,
            "repair_eligible": True,
            "repair_triggered": True,
            "repair_attempted": True,
            "repair_success": True,
            "repair_action": "REPLACE",
            "repair_answer_changed": True,
            "self_eval_risk_type": "REASONING",
            "repair_transition": "REGRESSION",
        }]
        m_replace = calculate_targeted_repair_metrics(records_replace, total_benchmark_tasks=1)
        self.assertEqual(m_replace["repair_harm_count"], 1)
        self.assertEqual(m_replace["repair_regressions"], 1)
        self.assertEqual(m_replace["repair_stable_correct"], 0)


if __name__ == "__main__":
    unittest.main()
