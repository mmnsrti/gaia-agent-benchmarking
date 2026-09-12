import json
import math
import unittest
from typing import Any, List, Optional

from agent.agent import GAIASelfEvaluationAgent, GAIAVerificationAgent
from agent.llm import LLMResponse
from evaluation.dataset import GAIATask
from evaluation.evaluate import calculate_metrics
from evaluation.runner import execute_task
from evaluation.self_evaluation_metrics import calculate_self_evaluation_metrics
from prompts.self_evaluation import (
    SELF_EVALUATION_PROMPT_VERSION,
    build_execution_summary,
    build_self_evaluator_prompt,
    parse_self_evaluation_result,
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


class SequencedLLM:
    """No-network test double that records the exact V6 generation contract."""

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
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


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
        raise AssertionError("DIRECT-route V6 self-evaluation must not execute Python")


def response(text: str, finish_reason: str = "STOP") -> LLMResponse:
    return LLMResponse(text=text, raw_text=text, finish_reason=finish_reason)


def standard_v6_responses(self_evaluation: Any = None) -> List[Any]:
    if self_evaluation is None:
        self_evaluation = response("ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.91")
    return [
        response("ROUTE: DIRECT"),
        response("FINAL: 42"),
        response("VERDICT: KEEP"),
        self_evaluation,
    ]


class TestV6SelfEvaluationParser(unittest.TestCase):
    def test_valid_pass_and_confidence_bounds(self):
        for confidence in ("0.00", "1.00"):
            with self.subTest(confidence=confidence):
                parsed = parse_self_evaluation_result(
                    f" ASSESSMENT : PASS \n RISK_TYPE: NONE\n CONFIDENCE : {confidence} "
                )
                self.assertTrue(parsed.is_valid)
                self.assertEqual(parsed.status, "VALID_PASS")
                self.assertEqual(parsed.risk_type, "NONE")
                self.assertEqual(parsed.confidence, float(confidence))

    def test_valid_each_suspect_risk_type(self):
        for risk_type in ("EVIDENCE", "REASONING", "CALCULATION", "FORMAT", "EXECUTION", "UNKNOWN"):
            with self.subTest(risk_type=risk_type):
                parsed = parse_self_evaluation_result(
                    f"ASSESSMENT: SUSPECT\nRISK_TYPE: {risk_type}\nCONFIDENCE: 0.78"
                )
                self.assertTrue(parsed.is_valid)
                self.assertEqual(parsed.status, "VALID_SUSPECT")
                self.assertEqual(parsed.assessment, "SUSPECT")
                self.assertEqual(parsed.risk_type, risk_type)

    def test_parser_rejects_schema_and_content_failures(self):
        invalid_payloads = [
            "",
            "RISK_TYPE: NONE\nCONFIDENCE: 0.5",
            "ASSESSMENT: MAYBE\nRISK_TYPE: NONE\nCONFIDENCE: 0.5",
            "ASSESSMENT: PASS\nRISK_TYPE: OTHER\nCONFIDENCE: 0.5",
            "ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: -0.1",
            "ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 1.1",
            "ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: NaN",
            "ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: Infinity",
            "ASSESSMENT: PASS\nASSESSMENT: PASS\nCONFIDENCE: 0.5",
            "ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: not-a-number",
            "ASSESSMENT: PASS\nRISK_TYPE: FORMAT\nCONFIDENCE: 0.5",
            "ASSESSMENT: SUSPECT\nRISK_TYPE: NONE\nCONFIDENCE: 0.5",
            "Explanation first\nASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.5",
            "ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.5\nExplanation after",
            "```\nASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.5\n```",
            "ASSESSMENT: SUSPECT\nRISK_TYPE: REASONING\nCONFIDENCE: 0.5\nFINAL: replacement",
            "ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.5\nASSESSMENT: SUSPECT",
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                parsed = parse_self_evaluation_result(payload)
                self.assertFalse(parsed.is_valid)
                self.assertEqual(parsed.status, "INVALID")
                self.assertIsNotNone(parsed.error_type)


class TestV6PromptAndExecutionSummary(unittest.TestCase):
    def test_execution_summary_is_deterministic_and_safe(self):
        first = build_execution_summary(
            route="DIRECT",
            search_attempted=True,
            search_success=True,
            search_fallback=False,
            attachment_required=False,
            file_attempted=False,
            file_success=False,
            python_routed=False,
            python_attempted=False,
            python_success=False,
            execution_error_type=None,
            completion_success=False,
            finish_reason="MAX_TOKENS",
        )
        second = build_execution_summary(
            route="DIRECT",
            search_attempted=True,
            search_success=True,
            search_fallback=False,
            attachment_required=False,
            file_attempted=False,
            file_success=False,
            python_routed=False,
            python_attempted=False,
            python_success=False,
            execution_error_type=None,
            completion_success=False,
            finish_reason="MAX_TOKENS",
        )
        self.assertEqual(first, second)
        self.assertEqual(
            first,
            "Route: DIRECT\nSearch: success\nAttachment: not required\nPython: not routed\n"
            "Execution error category: none\nCompletion: false\nFinish reason: MAX_TOKENS",
        )

    def test_prompt_has_only_permitted_inputs(self):
        prompt = build_self_evaluator_prompt(
            question="What is 2 plus 2?",
            final_answer="4",
            execution_summary="Route: DIRECT",
            web_evidence="A trusted source says 2+2=4.",
            file_evidence="No file needed.",
            attachment_filename="evidence.txt",
        )
        self.assertIn("What is 2 plus 2?", prompt)
        self.assertIn("FINAL ANSWER (READ ONLY):\n4", prompt)
        self.assertIn("Route: DIRECT", prompt)
        self.assertNotIn("ground_truth", prompt.lower())
        self.assertNotIn("scorer result", prompt.lower())
        self.assertNotIn("VERDICT:", prompt)
        self.assertNotIn("KEEP", prompt)
        self.assertNotIn("REVISE", prompt)


class TestV6RuntimeInvariants(unittest.TestCase):
    def make_agent(self, responses: List[Any]):
        self.search = StubSearchTool()
        self.llm = SequencedLLM(responses)
        return GAIASelfEvaluationAgent(llm_client=self.llm, search_tool=self.search)

    def test_v5_isolation_and_v6_standard_path(self):
        v5_llm = SequencedLLM(standard_v6_responses()[:3])
        v5 = GAIAVerificationAgent(llm_client=v5_llm, search_tool=StubSearchTool())
        v5_result = v5.run("Question")
        self.assertEqual(v5_result.final_answer, "42")
        self.assertFalse(v5_result.self_eval_attempted)
        self.assertEqual(len(v5_llm.calls), 3)

        agent = self.make_agent(standard_v6_responses())
        result = agent.run("Question")
        self.assertEqual(result.final_answer, "42")
        self.assertEqual(result.pre_self_evaluation_answer, "42")
        self.assertEqual(result.post_self_evaluation_answer, "42")
        self.assertTrue(result.self_eval_answer_unchanged)
        self.assertTrue(result.self_eval_eligible)
        self.assertTrue(result.self_eval_attempted)
        self.assertTrue(result.self_eval_success)
        self.assertEqual(result.self_eval_assessment, "PASS")
        self.assertEqual(result.self_eval_risk_type, "NONE")
        self.assertEqual(result.llm_generation_attempts, 4)
        self.assertEqual(len(self.llm.calls), 4)
        self.assertEqual(self.llm.calls[3]["max_retries"], 0)
        self.assertIsNone(self.llm.calls[3]["attachment_parts"])
        self.assertEqual(self.search.calls, 1)

    def test_empty_and_whitespace_answers_bypass(self):
        for worker_text in ("", "   \n\t"):
            with self.subTest(worker_text=repr(worker_text)):
                agent = self.make_agent([response("ROUTE: DIRECT"), response(worker_text)])
                result = agent.run("Question")
                self.assertEqual(result.final_answer, "")
                self.assertFalse(result.self_eval_eligible)
                self.assertFalse(result.self_eval_attempted)
                self.assertEqual(result.self_eval_generation_attempts, 0)
                self.assertEqual(result.llm_generation_attempts, 2)
                self.assertEqual(len(self.llm.calls), 2)

    def test_nonempty_incomplete_answer_is_still_eligible(self):
        agent = self.make_agent([
            response("ROUTE: DIRECT"),
            response("FINAL: partial", finish_reason="MAX_TOKENS"),
            response("VERDICT: KEEP"),
            response("ASSESSMENT: SUSPECT\nRISK_TYPE: EXECUTION\nCONFIDENCE: 0.83"),
        ])
        result = agent.run("Question")
        self.assertEqual(result.final_answer, "partial")
        self.assertTrue(result.self_eval_eligible)
        self.assertTrue(result.self_eval_success)
        self.assertEqual(result.self_eval_risk_type, "EXECUTION")
        self.assertIn("Completion: false", result.self_eval_prompt)
        self.assertIn("Finish reason: MAX_TOKENS", result.self_eval_prompt)

    def test_v5_verdict_is_not_in_v6_prompt(self):
        agent = self.make_agent([
            response("ROUTE: DIRECT"),
            response("FINAL: 41"),
            response("VERDICT: REVISE\nFINAL: 42"),
            response("ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.70"),
        ])
        result = agent.run("Question without decision words")
        self.assertEqual(result.final_answer, "42")
        evaluator_prompt = self.llm.calls[3]["prompt"]
        self.assertNotIn("VERDICT:", evaluator_prompt)
        self.assertNotIn("KEEP", evaluator_prompt)
        self.assertNotIn("REVISE", evaluator_prompt)

    def test_answer_is_immutable_on_suspect_invalid_and_provider_failures(self):
        evaluator_events = [
            response("ASSESSMENT: SUSPECT\nRISK_TYPE: REASONING\nCONFIDENCE: 0.76"),
            response("This is malformed"),
            Exception("Request timed out"),
            response(""),
            response("ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.9", finish_reason="MAX_TOKENS"),
        ]
        for evaluator_event in evaluator_events:
            with self.subTest(event=repr(evaluator_event)):
                agent = self.make_agent(standard_v6_responses(evaluator_event))
                result = agent.run("Question")
                self.assertEqual(result.final_answer, "42")
                self.assertTrue(result.self_eval_answer_unchanged)
                self.assertEqual(result.post_self_evaluation_answer, "42")
                self.assertEqual(result.self_eval_generation_attempts, 1)
                self.assertEqual(len(self.llm.calls), 4)

    def test_no_extra_tools_or_evaluator_retry(self):
        agent = self.make_agent(standard_v6_responses(Exception("provider timeout")))
        result = agent.run("Question")
        self.assertEqual(self.search.calls, 1)  # inherited V5 search only
        self.assertEqual(len(self.llm.calls), 4)
        self.assertEqual(self.llm.calls[3]["max_retries"], 0)
        self.assertEqual(result.self_eval_error_type, "provider_timeout")
        self.assertFalse(result.self_eval_success)
        self.assertEqual(result.llm_generation_attempts, 4)

    def test_existing_file_and_python_limits_are_preserved(self):
        search = StubSearchTool()
        file_tool = CountingFileTool()
        python_tool = CountingPythonTool()
        llm = SequencedLLM(standard_v6_responses())
        agent = GAIASelfEvaluationAgent(
            llm_client=llm,
            search_tool=search,
            file_tool=file_tool,
            python_tool=python_tool,
        )
        result = agent.run("Question", file_path="evidence.txt")
        self.assertEqual(result.final_answer, "42")
        self.assertEqual(search.calls, 1)
        self.assertEqual(file_tool.calls, 1)
        self.assertEqual(python_tool.calls, 0)
        self.assertIsNone(llm.calls[3]["attachment_parts"])

    def test_public_runner_record_excludes_private_evaluator_material(self):
        search = StubSearchTool()
        llm = SequencedLLM(standard_v6_responses())
        record = execute_task(
            task_id="v6-safe-record",
            question="Question",
            level=1,
            agent=GAIASelfEvaluationAgent(llm_client=llm, search_tool=search),
            project_version="v6",
        )
        self.assertEqual(record["schema_version"], 5)
        self.assertEqual(record["project_version"], "v6")
        self.assertEqual(record["self_eval_prompt_version"], SELF_EVALUATION_PROMPT_VERSION)
        self.assertTrue(record["self_eval_answer_unchanged"])
        self.assertNotIn("self_eval_prompt", record)
        self.assertNotIn("self_eval_raw_response", record)
        self.assertEqual(record["llm_generation_attempts"], 4)


class TestV6DiagnosticMetrics(unittest.TestCase):
    def test_confusion_matrix_coverage_risk_and_brier(self):
        records = [
            {"eligible": True, "attempted": True, "success": True, "assessment": "SUSPECT", "risk_type": "REASONING", "confidence": 0.9, "correct": False},  # TP
            {"eligible": True, "attempted": True, "success": True, "assessment": "SUSPECT", "risk_type": "EVIDENCE", "confidence": 0.8, "correct": True},  # FP
            {"eligible": True, "attempted": True, "success": True, "assessment": "PASS", "risk_type": "NONE", "confidence": 0.9, "correct": True},  # TN
            {"eligible": True, "attempted": True, "success": True, "assessment": "PASS", "risk_type": "NONE", "confidence": 0.8, "correct": False},  # FN
            {"eligible": True, "attempted": True, "success": False, "assessment": None, "risk_type": None, "confidence": None, "correct": False},
            {"eligible": False, "attempted": False, "success": False, "assessment": None, "risk_type": None, "confidence": None, "correct": False},
        ]
        metrics = calculate_self_evaluation_metrics(records)
        self.assertEqual((metrics["true_positive"], metrics["false_positive"], metrics["true_negative"], metrics["false_negative"]), (1, 1, 1, 1))
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(metrics["recall"], 0.5)
        self.assertEqual(metrics["f1"], 0.5)
        self.assertEqual(metrics["false_alarm_rate"], 0.5)
        self.assertEqual(metrics["missed_error_rate"], 0.5)
        self.assertEqual(metrics["specificity"], 0.5)
        self.assertEqual(metrics["diagnostic_coverage"], 0.8)
        self.assertEqual(metrics["failure_or_invalid_count"], 1)
        self.assertEqual(metrics["pass_group_correctness_rate"], 0.5)
        self.assertEqual(metrics["suspect_group_error_rate"], 0.5)
        self.assertEqual(metrics["risk_type_distribution"], {"EVIDENCE": 1, "NONE": 2, "REASONING": 1})
        self.assertEqual(metrics["brier_diagnostic_score"], 0.325)

    def test_zero_denominators_are_explicit(self):
        no_positive_labels = calculate_self_evaluation_metrics([
            {"eligible": True, "attempted": True, "success": True, "assessment": "PASS", "risk_type": "NONE", "confidence": 1.0, "correct": True},
        ])
        self.assertIsNone(no_positive_labels["precision"])
        self.assertIsNone(no_positive_labels["recall"])
        self.assertIsNone(no_positive_labels["f1"])

        no_predicted_positive = calculate_self_evaluation_metrics([
            {"eligible": True, "attempted": True, "success": True, "assessment": "PASS", "risk_type": "NONE", "confidence": 0.9, "correct": False},
        ])
        self.assertIsNone(no_predicted_positive["precision"])
        self.assertEqual(no_predicted_positive["recall"], 0.0)
        self.assertIsNone(no_predicted_positive["f1"])
        self.assertEqual(calculate_self_evaluation_metrics([])["diagnostic_coverage"], 0.0)

    def test_calculate_metrics_joins_after_scoring_and_is_public_safe(self):
        predictions = [
            {
                "task_id": "a",
                "final_answer": "42",
                "request_success": True,
                "completion_success": True,
                "project_version": "v6",
                "self_eval_eligible": True,
                "self_eval_attempted": True,
                "self_eval_success": True,
                "self_eval_prompt_version": "self-evaluator-v1",
                "self_eval_assessment": "PASS",
                "self_eval_risk_type": "NONE",
                "self_eval_confidence": 0.95,
                "self_eval_answer_unchanged": True,
                "self_eval_prompt": "PRIVATE_EVALUATOR_PROMPT",
                "self_eval_raw_response": "PRIVATE_EVALUATOR_RESPONSE",
            },
            {
                "task_id": "b",
                "final_answer": "wrong",
                "request_success": True,
                "completion_success": True,
                "project_version": "v6",
                "self_eval_eligible": True,
                "self_eval_attempted": True,
                "self_eval_success": True,
                "self_eval_prompt_version": "self-evaluator-v1",
                "self_eval_assessment": "SUSPECT",
                "self_eval_risk_type": "REASONING",
                "self_eval_confidence": 0.8,
                "self_eval_answer_unchanged": True,
                "self_eval_prompt": "PRIVATE_EVALUATOR_PROMPT",
                "self_eval_raw_response": "PRIVATE_EVALUATOR_RESPONSE",
            },
        ]
        tasks = {
            "a": GAIATask(task_id="a", question="private question A", final_answer="42", level=1),
            "b": GAIATask(task_id="b", question="private question B", final_answer="Paris", level=1),
        }
        result = calculate_metrics(predictions, tasks, level=1, project_version="v6", expected_task_count=2)
        summary_text = json.dumps(result["summary"])
        self.assertTrue(result["summary"]["self_evaluation_enabled"])
        self.assertEqual(result["summary"]["self_eval_precision"], 1.0)
        self.assertEqual(result["summary"]["self_eval_recall"], 1.0)
        self.assertEqual(result["summary"]["self_eval_improvements"], 0)
        self.assertEqual(result["summary"]["self_eval_regressions"], 0)
        for forbidden in ("PRIVATE_EVALUATOR_PROMPT", "PRIVATE_EVALUATOR_RESPONSE", "private question", "ground_truth"):
            self.assertNotIn(forbidden, summary_text)
        self.assertNotIn("self_eval_prompt", result["detailed"][0])
        self.assertNotIn("self_eval_raw_response", result["detailed"][0])

    def test_metric_layer_rejects_answer_mutation(self):
        predictions = [{
            "task_id": "a",
            "final_answer": "42",
            "request_success": True,
            "completion_success": True,
            "project_version": "v6",
            "self_eval_eligible": True,
            "self_eval_attempted": True,
            "self_eval_success": True,
            "self_eval_assessment": "PASS",
            "self_eval_risk_type": "NONE",
            "self_eval_confidence": 0.9,
            "self_eval_answer_unchanged": False,
        }]
        tasks = {"a": GAIATask(task_id="a", question="Q", final_answer="42", level=1)}
        with self.assertRaisesRegex(AssertionError, "immutability"):
            calculate_metrics(predictions, tasks, level=1, project_version="v6", expected_task_count=1)


if __name__ == "__main__":
    unittest.main()
