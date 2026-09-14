"""V8 Controlled Smoke Validation Suite.

Executes deterministic controlled smoke scenarios covering the six core V8
behavioral cases (Cases A-F), validates operational invariants, budget caps,
telemetry serialization, failure preservation, and post-hoc transition attribution,
and emits public-safe smoke artifacts under experiments/v8/smoke/.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Add repository root to python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.agent import GAIAActiveEvidenceVerificationAgent
from agent.llm import LLMResponse
from evaluation.active_verification_metrics import calculate_active_verification_metrics
from evaluation.metrics import question_scorer
from evaluation.runner import execute_task
from prompts.active_evidence_verification import (
    ACTIVE_EVIDENCE_VERIFICATION_PROMPT_VERSION,
    build_active_evidence_query,
)
from tools.file_tool import FileResult
from tools.web_search import SearchResultItem, WebSearchResult


class CountingFileTool:
    """Mock file tool tracking calls."""

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
    """Mock python tool ensuring DIRECT V8 execution never executes Python."""

    def __init__(self):
        self.calls = 0

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        raise AssertionError("DIRECT-route V8 active verification must not execute Python")


class SmokeSearchTool:
    """Controlled search double recording calls and returning scenario-specific results."""

    def __init__(
        self,
        upstream_results: Optional[List[SearchResultItem]] = None,
        active_results: Optional[List[SearchResultItem]] = None,
        active_success: bool = True,
        active_error_type: Optional[str] = None,
        active_exception: Optional[Exception] = None,
    ):
        self.upstream_results = upstream_results if upstream_results is not None else [
            SearchResultItem(
                title="Upstream Evidence",
                url="https://example.com/upstream",
                content="Initial background information.",
                score=0.90,
            )
        ]
        self.active_results = active_results if active_results is not None else []
        self.active_success = active_success
        self.active_error_type = active_error_type
        self.active_exception = active_exception
        self.calls = 0
        self.queries = []

    def search(self, query: str) -> WebSearchResult:
        self.calls += 1
        self.queries.append(query)
        if self.calls == 1:
            return WebSearchResult(
                query=query,
                success=True,
                results=list(self.upstream_results),
            )
        # Second call: V8 active evidence verification search
        if self.active_exception:
            raise self.active_exception
        return WebSearchResult(
            query=query,
            success=self.active_success,
            results=list(self.active_results),
            error_type=self.active_error_type,
        )


class SmokeLLM:
    """No-network LLM test double recording all generation prompts and responses."""

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
            raise RuntimeError(f"SmokeLLM ran out of responses after {len(self.calls)} calls")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_resp(text: str, finish_reason: str = "STOP") -> LLMResponse:
    return LLMResponse(text=text, raw_text=text, finish_reason=finish_reason)


def run_v8_smoke() -> Dict[str, Any]:
    """Runs all controlled smoke scenarios and returns the audit result."""
    starting_commit = "37e0efddb9ae4999b1654bac4105d13ada5c573b"
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    smoke_dir = os.path.join(repo_root, "experiments", "v8", "smoke")
    os.makedirs(smoke_dir, exist_ok=True)

    smoke_cases_file = os.path.join(smoke_dir, "smoke_cases.jsonl")
    smoke_summary_file = os.path.join(smoke_dir, "smoke_summary.json")

    case_definitions = [
        {
            "case_id": "case_a_pass_bypass",
            "scenario": "Case A — PASS bypass",
            "question": "What is the capital city of France?",
            "ground_truth": "Paris",
            "llm_responses": [
                make_resp("ROUTE: DIRECT"),
                make_resp("FINAL: Paris"),
                make_resp("VERDICT: KEEP"),
                make_resp("ASSESSMENT: PASS\nRISK_TYPE: NONE\nCONFIDENCE: 0.95"),
            ],
            "search_tool": SmokeSearchTool(),
            "expected": {
                "eligible": False,
                "triggered": False,
                "search_attempted": False,
                "adjudication_attempted": False,
                "action": None,
                "answer_changed": False,
                "final_answer": "Paris",
                "max_v8_search": 0,
                "max_v8_gen": 0,
                "transition": "NOT_TRIGGERED",
            },
        },
        {
            "case_id": "case_b_reasoning_bypass",
            "scenario": "Case B — non-EVIDENCE SUSPECT bypass",
            "question": "What is 15 * 24?",
            "ground_truth": "360",
            "llm_responses": [
                make_resp("ROUTE: DIRECT"),
                make_resp("FINAL: 350"),
                make_resp("VERDICT: KEEP"),
                make_resp("ASSESSMENT: SUSPECT\nRISK_TYPE: REASONING\nCONFIDENCE: 0.85"),
                make_resp("REPAIR_ACTION: KEEP"),
            ],
            "search_tool": SmokeSearchTool(),
            "expected": {
                "eligible": False,
                "triggered": False,
                "search_attempted": False,
                "adjudication_attempted": False,
                "action": None,
                "answer_changed": False,
                "final_answer": "350",
                "max_v8_search": 0,
                "max_v8_gen": 0,
                "transition": "NOT_TRIGGERED",
            },
        },
        {
            "case_id": "case_c_eligible_evidence_keep",
            "scenario": "Case C — eligible EVIDENCE + usable evidence + valid KEEP",
            "question": "In what year was the first commercial Boeing 747 flight?",
            "ground_truth": "1970",
            "llm_responses": [
                make_resp("ROUTE: DIRECT"),
                make_resp("FINAL: 1970"),
                make_resp("VERDICT: KEEP"),
                make_resp("ASSESSMENT: SUSPECT\nRISK_TYPE: EVIDENCE\nCONFIDENCE: 0.80"),
                make_resp("REPAIR_ACTION: KEEP"),
                make_resp("VERIFICATION_ACTION: KEEP"),
            ],
            "search_tool": SmokeSearchTool(
                active_results=[
                    SearchResultItem(
                        title="Boeing 747 History",
                        url="https://example.com/747",
                        content="Pan Am operated the first commercial 747 flight on January 22, 1970.",
                        score=0.95,
                    )
                ],
                active_success=True,
            ),
            "expected": {
                "eligible": True,
                "triggered": True,
                "search_attempted": True,
                "search_success": True,
                "search_usable": True,
                "adjudication_attempted": True,
                "adjudication_success": True,
                "action": "KEEP",
                "answer_changed": False,
                "final_answer": "1970",
                "max_v8_search": 1,
                "max_v8_gen": 1,
                "transition": "STABLE_CORRECT",
            },
        },
        {
            "case_id": "case_d_eligible_evidence_replace",
            "scenario": "Case D — eligible EVIDENCE + usable evidence + valid REPLACE",
            "question": "What is the atomic number of Gold?",
            "ground_truth": "79",
            "llm_responses": [
                make_resp("ROUTE: DIRECT"),
                make_resp("FINAL: 78"),
                make_resp("VERDICT: KEEP"),
                make_resp("ASSESSMENT: SUSPECT\nRISK_TYPE: EVIDENCE\nCONFIDENCE: 0.75"),
                make_resp("REPAIR_ACTION: KEEP"),
                make_resp("VERIFICATION_ACTION: REPLACE\nFINAL: 79"),
            ],
            "search_tool": SmokeSearchTool(
                active_results=[
                    SearchResultItem(
                        title="Gold Element",
                        url="https://example.com/gold",
                        content="Gold is a chemical element with symbol Au and atomic number 79.",
                        score=0.98,
                    )
                ],
                active_success=True,
            ),
            "expected": {
                "eligible": True,
                "triggered": True,
                "search_attempted": True,
                "search_success": True,
                "search_usable": True,
                "adjudication_attempted": True,
                "adjudication_success": True,
                "action": "REPLACE",
                "answer_changed": True,
                "final_answer": "79",
                "max_v8_search": 1,
                "max_v8_gen": 1,
                "transition": "IMPROVEMENT",
            },
        },
        {
            "case_id": "case_e1_search_exception_preservation",
            "scenario": "Case E1 — search failure (timeout exception) preservation",
            "question": "What is the population of Tokyo in 2023?",
            "ground_truth": "14 million",
            "llm_responses": [
                make_resp("ROUTE: DIRECT"),
                make_resp("FINAL: 14 million"),
                make_resp("VERDICT: KEEP"),
                make_resp("ASSESSMENT: SUSPECT\nRISK_TYPE: EVIDENCE\nCONFIDENCE: 0.85"),
                make_resp("REPAIR_ACTION: KEEP"),
            ],
            "search_tool": SmokeSearchTool(
                active_exception=Exception("Connection timeout to search provider"),
            ),
            "expected": {
                "eligible": True,
                "triggered": True,
                "search_attempted": True,
                "search_success": False,
                "search_usable": False,
                "adjudication_attempted": False,
                "action": None,
                "answer_changed": False,
                "final_answer": "14 million",
                "max_v8_search": 1,
                "max_v8_gen": 0,
                "transition": "STABLE_CORRECT",
            },
        },
        {
            "case_id": "case_e2_search_zero_results_preservation",
            "scenario": "Case E2 — search success with zero results preservation",
            "question": "What is the rare isotope ratio of xyz-999?",
            "ground_truth": "0.0012",
            "llm_responses": [
                make_resp("ROUTE: DIRECT"),
                make_resp("FINAL: 0.0012"),
                make_resp("VERDICT: KEEP"),
                make_resp("ASSESSMENT: SUSPECT\nRISK_TYPE: EVIDENCE\nCONFIDENCE: 0.70"),
                make_resp("REPAIR_ACTION: KEEP"),
            ],
            "search_tool": SmokeSearchTool(
                active_success=True,
                active_results=[],
            ),
            "expected": {
                "eligible": True,
                "triggered": True,
                "search_attempted": True,
                "search_success": True,
                "search_usable": False,
                "search_result_count": 0,
                "search_error_type": "zero_search_results",
                "adjudication_attempted": False,
                "action": None,
                "answer_changed": False,
                "final_answer": "0.0012",
                "max_v8_search": 1,
                "max_v8_gen": 0,
                "transition": "STABLE_CORRECT",
            },
        },
        {
            "case_id": "case_f1_parser_failure_preservation",
            "scenario": "Case F1 — adjudication parser failure (malformed output) preservation",
            "question": "What is the diameter of Mars?",
            "ground_truth": "6779 km",
            "llm_responses": [
                make_resp("ROUTE: DIRECT"),
                make_resp("FINAL: 6779 km"),
                make_resp("VERDICT: KEEP"),
                make_resp("ASSESSMENT: SUSPECT\nRISK_TYPE: EVIDENCE\nCONFIDENCE: 0.80"),
                make_resp("REPAIR_ACTION: KEEP"),
                make_resp("Here is my thinking:\nMars is 6779 km.\nVERIFICATION_ACTION: KEEP"),
            ],
            "search_tool": SmokeSearchTool(
                active_results=[
                    SearchResultItem(
                        title="Mars Facts",
                        url="https://example.com/mars",
                        content="The diameter of Mars is 6,779 km.",
                        score=0.92,
                    )
                ],
                active_success=True,
            ),
            "expected": {
                "eligible": True,
                "triggered": True,
                "search_attempted": True,
                "search_success": True,
                "search_usable": True,
                "adjudication_attempted": True,
                "adjudication_success": False,
                "action": None,
                "error_type": "malformed_verification_text",
                "answer_changed": False,
                "final_answer": "6779 km",
                "max_v8_search": 1,
                "max_v8_gen": 1,
                "transition": "STABLE_CORRECT",
            },
        },
        {
            "case_id": "case_f2_provider_timeout_preservation",
            "scenario": "Case F2 — adjudication provider timeout preservation",
            "question": "What is the boiling point of ethanol?",
            "ground_truth": "78.37 C",
            "llm_responses": [
                make_resp("ROUTE: DIRECT"),
                make_resp("FINAL: 78.37 C"),
                make_resp("VERDICT: KEEP"),
                make_resp("ASSESSMENT: SUSPECT\nRISK_TYPE: EVIDENCE\nCONFIDENCE: 0.85"),
                make_resp("REPAIR_ACTION: KEEP"),
                Exception("504 Gateway Timeout: deadline exceeded"),
            ],
            "search_tool": SmokeSearchTool(
                active_results=[
                    SearchResultItem(
                        title="Ethanol properties",
                        url="https://example.com/ethanol",
                        content="Boiling point of ethanol is 78.37 C.",
                        score=0.96,
                    )
                ],
                active_success=True,
            ),
            "expected": {
                "eligible": True,
                "triggered": True,
                "search_attempted": True,
                "search_success": True,
                "search_usable": True,
                "adjudication_attempted": True,
                "adjudication_success": False,
                "action": None,
                "error_type": "provider_timeout",
                "answer_changed": False,
                "final_answer": "78.37 C",
                "max_v8_search": 1,
                "max_v8_gen": 1,
                "transition": "STABLE_CORRECT",
            },
        },
    ]

    records = []
    case_results = []
    all_cases_passed = True

    for cdef in case_definitions:
        case_id = cdef["case_id"]
        scenario = cdef["scenario"]
        question = cdef["question"]
        gt = cdef["ground_truth"]
        expected = cdef["expected"]

        llm = SmokeLLM(cdef["llm_responses"])
        search_tool = cdef["search_tool"]
        agent = GAIAActiveEvidenceVerificationAgent(
            llm_client=llm,
            search_tool=search_tool,
        )
        agent.file_tool = CountingFileTool()
        agent.python_tool = CountingPythonTool()

        # Execute end-to-end task through runner
        rec = execute_task(
            task_id=case_id,
            question=question,
            level=1,
            agent=agent,
            llm=llm,
            project_version="v8",
            schema_version=7,
        )

        # Post-hoc correctness scoring
        pre_corr = question_scorer(rec["pre_active_verification_answer"], gt)
        post_corr = question_scorer(rec["post_active_verification_answer"], gt)
        rec["pre_active_verification_correct"] = pre_corr
        rec["post_active_verification_correct"] = post_corr
        rec["correct"] = post_corr
        rec["ground_truth"] = gt

        # Transition attribution
        if not rec["active_verification_triggered"]:
            transition = "NOT_TRIGGERED"
        elif not pre_corr and post_corr:
            transition = "IMPROVEMENT"
        elif pre_corr and not post_corr:
            transition = "REGRESSION"
        elif pre_corr and post_corr:
            transition = "STABLE_CORRECT"
        else:
            transition = "STABLE_FAILURE"
        rec["transition_classification"] = transition

        # Tool calls checks
        v8_add_searches = 1 if rec["active_verification_search_attempted"] else 0
        v8_adj_gens = rec["active_verification_generation_attempts"]
        total_searches = search_tool.calls
        total_llm_gens = rec["llm_generation_attempts"]
        py_calls = agent.python_tool.calls
        file_rereads = agent.file_tool.calls

        rec["v8_additional_searches"] = v8_add_searches
        rec["v8_adjudication_generations"] = v8_adj_gens
        rec["total_search_calls_observed"] = total_searches
        rec["total_llm_generations_observed"] = total_llm_gens
        rec["v8_python_calls"] = py_calls
        rec["v8_file_rereads"] = file_rereads

        # Assertions
        case_passed = True
        failure_reasons = []

        if rec["active_verification_eligible"] != expected["eligible"]:
            case_passed = False
            failure_reasons.append(f"eligible: got {rec['active_verification_eligible']}, expected {expected['eligible']}")
        if rec["active_verification_triggered"] != expected["triggered"]:
            case_passed = False
            failure_reasons.append(f"triggered: got {rec['active_verification_triggered']}, expected {expected['triggered']}")
        if rec["active_verification_search_attempted"] != expected["search_attempted"]:
            case_passed = False
            failure_reasons.append(f"search_attempted: got {rec['active_verification_search_attempted']}, expected {expected['search_attempted']}")
        if "search_success" in expected and rec["active_verification_search_success"] != expected["search_success"]:
            case_passed = False
            failure_reasons.append(f"search_success: got {rec['active_verification_search_success']}, expected {expected['search_success']}")
        if "search_usable" in expected and rec["active_verification_search_usable"] != expected["search_usable"]:
            case_passed = False
            failure_reasons.append(f"search_usable: got {rec['active_verification_search_usable']}, expected {expected['search_usable']}")
        if rec["active_verification_adjudication_attempted"] != expected["adjudication_attempted"]:
            case_passed = False
            failure_reasons.append(f"adjudication_attempted: got {rec['active_verification_adjudication_attempted']}, expected {expected['adjudication_attempted']}")
        if "adjudication_success" in expected and rec["active_verification_adjudication_success"] != expected["adjudication_success"]:
            case_passed = False
            failure_reasons.append(f"adjudication_success: got {rec['active_verification_adjudication_success']}, expected {expected['adjudication_success']}")
        if rec["active_verification_action"] != expected["action"]:
            case_passed = False
            failure_reasons.append(f"action: got {rec['active_verification_action']}, expected {expected['action']}")
        if rec["active_verification_answer_changed"] != expected["answer_changed"]:
            case_passed = False
            failure_reasons.append(f"answer_changed: got {rec['active_verification_answer_changed']}, expected {expected['answer_changed']}")
        if rec["final_answer"] != expected["final_answer"]:
            case_passed = False
            failure_reasons.append(f"final_answer: got {rec['final_answer']}, expected {expected['final_answer']}")
        if rec["post_active_verification_answer"] != rec["final_answer"]:
            case_passed = False
            failure_reasons.append(f"post_active_answer mismatch: got {rec['post_active_verification_answer']} vs final {rec['final_answer']}")

        # Failure preservation invariant:
        if expected["action"] is None:
            if rec["post_active_verification_answer"] != rec["pre_active_verification_answer"]:
                case_passed = False
                failure_reasons.append("failure preservation violated: post != pre")
            if rec["active_verification_action"] == "KEEP":
                case_passed = False
                failure_reasons.append("automatic failure incorrectly counted as KEEP")

        # Query contract check for eligible cases
        if rec["active_verification_eligible"]:
            expected_query = build_active_evidence_query(question=question, current_answer=rec["pre_active_verification_answer"])
            if rec["active_verification_query"] != expected_query:
                case_passed = False
                failure_reasons.append("query contract mismatch")
            if search_tool.queries and search_tool.queries[-1] != expected_query:
                case_passed = False
                failure_reasons.append("query passed to search tool mismatch")

        # Budget caps
        if v8_add_searches > 1:
            case_passed = False
            failure_reasons.append(f"V8 additional searches {v8_add_searches} > 1")
        if v8_adj_gens > 1:
            case_passed = False
            failure_reasons.append(f"V8 adjudication generations {v8_adj_gens} > 1")
        if total_searches > 2:
            case_passed = False
            failure_reasons.append(f"total search calls {total_searches} > 2")
        if total_llm_gens > 6:
            case_passed = False
            failure_reasons.append(f"total LLM generation attempts {total_llm_gens} > 6")
        if py_calls != 0:
            case_passed = False
            failure_reasons.append(f"V8 python calls {py_calls} != 0")
        if file_rereads != 0:
            case_passed = False
            failure_reasons.append(f"V8 file rereads {file_rereads} != 0")

        # Telemetry serialization checks
        required_telemetry_keys = [
            "pre_active_verification_answer",
            "post_active_verification_answer",
            "active_verification_eligible",
            "active_verification_triggered",
            "active_verification_query",
            "active_verification_search_attempted",
            "active_verification_search_success",
            "active_verification_search_usable",
            "active_verification_search_error_type",
            "active_verification_search_result_count",
            "active_verification_adjudication_attempted",
            "active_verification_adjudication_success",
            "active_verification_action",
            "active_verification_error_type",
            "active_verification_finish_reason",
            "active_verification_generation_attempts",
            "active_verification_generation_success",
            "active_verification_answer_changed",
            "active_verification_total_stage_latency_seconds",
        ]
        missing_keys = [k for k in required_telemetry_keys if k not in rec]
        if missing_keys:
            case_passed = False
            failure_reasons.append(f"missing telemetry keys: {missing_keys}")

        # Privacy firewall checks: ensure prompt and raw_response are omitted from serialized record
        forbidden_leakage = [
            "active_verification_prompt",
            "active_verification_raw_response",
        ]
        leaked_keys = [k for k in forbidden_leakage if k in rec]
        if leaked_keys:
            case_passed = False
            failure_reasons.append(f"privacy leakage: forbidden keys serialized: {leaked_keys}")

        # Attribution check
        if transition != expected["transition"]:
            case_passed = False
            failure_reasons.append(f"transition: got {transition}, expected {expected['transition']}")

        if not case_passed:
            all_cases_passed = False

        rec["case_passed"] = case_passed
        rec["failure_reasons"] = failure_reasons
        records.append(rec)

        case_results.append({
            "case_id": case_id,
            "scenario": scenario,
            "eligible": rec["active_verification_eligible"],
            "triggered": rec["active_verification_triggered"],
            "search_attempted": rec["active_verification_search_attempted"],
            "search_usable": rec["active_verification_search_usable"],
            "adjudication_attempted": rec["active_verification_adjudication_attempted"],
            "action": rec["active_verification_action"],
            "answer_changed": rec["active_verification_answer_changed"],
            "generation_attempts": rec["active_verification_generation_attempts"],
            "search_count": search_tool.calls,
            "failure_type": rec["active_verification_error_type"] or rec["active_verification_search_error_type"],
            "transition": transition,
            "pass_fail": "PASS" if case_passed else "FAIL",
            "reasons": failure_reasons,
        })

    # Within-run metrics calculation
    within_run_metrics = calculate_active_verification_metrics(records)

    # Invariant checks aggregation
    inv_pass_bypass = "PASS" if case_results[0]["pass_fail"] == "PASS" else "FAIL"
    inv_reasoning_bypass = "PASS" if case_results[1]["pass_fail"] == "PASS" else "FAIL"
    inv_keep = "PASS" if case_results[2]["pass_fail"] == "PASS" else "FAIL"
    inv_replace = "PASS" if case_results[3]["pass_fail"] == "PASS" else "FAIL"
    inv_search_failure = "PASS" if (case_results[4]["pass_fail"] == "PASS" and case_results[5]["pass_fail"] == "PASS") else "FAIL"
    inv_adjudication_failure = "PASS" if (case_results[6]["pass_fail"] == "PASS" and case_results[7]["pass_fail"] == "PASS") else "FAIL"

    # Verify query contract
    query_contract_pass = "PASS" if (
        case_results[2]["pass_fail"] == "PASS"
        and case_results[3]["pass_fail"] == "PASS"
        and records[2]["active_verification_query"] is not None
    ) else "FAIL"

    # Failure preservation check across all failures
    failure_preservation_ok = all(
        records[i]["post_active_verification_answer"] == records[i]["pre_active_verification_answer"]
        and records[i]["active_verification_answer_changed"] is False
        and records[i]["active_verification_action"] is None
        for i in [4, 5, 6, 7]
    )
    failure_preservation_pass = "PASS" if failure_preservation_ok else "FAIL"

    # Verify automatic failure is not counted as KEEP
    auto_fail_as_keep = any(
        records[i]["active_verification_action"] == "KEEP"
        for i in [4, 5, 6, 7]
    )

    # Telemetry serialization check
    telemetry_pass = "PASS" if all("pre_active_verification_answer" in r for r in records) else "FAIL"

    # Attribution check
    attribution_pass = "PASS" if all(r["transition_classification"] is not None for r in records) else "FAIL"

    # Budget observations
    v8_add_search_max = max(r["v8_additional_searches"] for r in records)
    v8_adj_gen_max = max(r["v8_adjudication_generations"] for r in records)
    total_search_max = max(r["total_search_calls_observed"] for r in records)
    total_llm_gen_max = max(r["total_llm_generations_observed"] for r in records)
    v8_py_calls = sum(r["v8_python_calls"] for r in records)
    v8_file_rereads = sum(r["v8_file_rereads"] for r in records)

    # Save smoke_cases.jsonl
    with open(smoke_cases_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    # Summary structure
    summary = {
        "starting_commit": starting_commit,
        "branch": "v8-active-evidence-verification",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(case_results),
        "passed_cases": sum(1 for c in case_results if c["pass_fail"] == "PASS"),
        "failed_cases": sum(1 for c in case_results if c["pass_fail"] == "FAIL"),
        "all_cases_passed": all_cases_passed,
        "scenario_matrix": case_results,
        "invariant_verifications": {
            "pass_bypass": inv_pass_bypass,
            "non_evidence_suspect_bypass": inv_reasoning_bypass,
            "eligible_evidence_keep": inv_keep,
            "eligible_evidence_replace": inv_replace,
            "search_failure_zero_results_preservation": inv_search_failure,
            "adjudication_provider_parser_failure_preservation": inv_adjudication_failure,
            "query_contract": query_contract_pass,
            "failure_preservation": failure_preservation_pass,
            "automatic_failure_incorrectly_counted_as_keep": "YES" if auto_fail_as_keep else "NO",
            "telemetry_serialization": telemetry_pass,
            "post_hoc_intervention_attribution": attribution_pass,
        },
        "budget_assertions": {
            "v8_additional_search_max_observed": v8_add_search_max,
            "v8_additional_search_max_allowed": 1,
            "v8_adjudication_generation_max_observed": v8_adj_gen_max,
            "v8_adjudication_generation_max_allowed": 1,
            "total_search_max_observed": total_search_max,
            "total_search_max_allowed": 2,
            "total_llm_generation_max_observed": total_llm_gen_max,
            "total_llm_generation_max_allowed": 6,
            "v8_python_calls_observed": v8_py_calls,
            "v8_python_calls_expected": 0,
            "v8_file_rereads_observed": v8_file_rereads,
            "v8_file_rereads_expected": 0,
        },
        "post_hoc_metrics": within_run_metrics,
        "final_verdict": "READY_FOR_CANONICAL_BENCHMARK" if all_cases_passed else "NOT_READY_FOR_CANONICAL_BENCHMARK",
        "blocking_issues": [],
    }

    with open(smoke_summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    result = run_v8_smoke()
    print("V8 Smoke Execution Finished.")
    print(f"Total: {result['total_cases']}, Passed: {result['passed_cases']}, Failed: {result['failed_cases']}")
    print(f"Final Verdict: {result['final_verdict']}")

