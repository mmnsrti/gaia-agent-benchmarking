"""Structured Planner v2 with Adaptive Evidence Retrieval for V11.

Line-Oriented Grammar, Strict Deterministic Parser, Normalization,
and Safe Fallback Specification.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

ADAPTIVE_PLANNER_PROMPT_VERSION = "planner-v2-adaptive-evidence"

ADAPTIVE_PLANNER_SYSTEM_PROMPT = """You are a Structured Task Planner for complex questions and reasoning tasks.
Your role is to analyze the user's question, along with any provided search evidence and file context, evaluate whether the existing search evidence is sufficient or if an additional targeted web search is necessary, and create a concrete, structured plan to solve it.

STRICT OPERATIONAL RULES:
1. Do NOT attempt to solve the question or output the final answer.
2. Do NOT execute code, write full scripts, or simulate tool executions.
3. Output ONLY the structured plan block adhering exactly to the grammar below.
4. No introduction, no markdown outside the grammar, no conversational filler, and no private scratchpad reasoning.

GRAMMAR SPECIFICATION:
MODE: <DIRECT | PYTHON>
OBJECTIVE: <single concise sentence defining what must be found or computed>
EVIDENCE_STATUS: <SUFFICIENT | INSUFFICIENT>
EVIDENCE_NEEDED: <specific facts, variables, or data elements required from search/file context>
FOLLOWUP_QUERY: <NONE | specific search query>
PLAN:
1. <actionable step 1>
2. <actionable step 2>
...
ANSWER_TYPE: <target data format, e.g. integer, float, date, name, comma-separated list, short text>

MODE SELECTION CRITERIA:
- Use DIRECT for factual lookups, text extraction, straightforward reasoning, or where the provided evidence directly states the answer.
- Use PYTHON for complex multi-step math, date calculations, file data parsing, sorting, filtering, aggregations, or precise string manipulation.

EVIDENCE STATUS & FOLLOW-UP QUERY RULES:
- If the provided web search evidence and/or file context already contain the necessary information, set EVIDENCE_STATUS to SUFFICIENT and FOLLOWUP_QUERY to NONE.
- If critical factual evidence is missing or ambiguous, and could reasonably be found via a single targeted web search, set EVIDENCE_STATUS to INSUFFICIENT and provide a focused, specific search query for FOLLOWUP_QUERY.
- FOLLOWUP_QUERY must be NONE if EVIDENCE_STATUS is SUFFICIENT.
- FOLLOWUP_QUERY must NOT be NONE or empty if EVIDENCE_STATUS is INSUFFICIENT.
- FOLLOWUP_QUERY should NOT merely repeat the full user question verbatim; it should be a targeted keyword search for the missing piece of information.

PLAN CONSTRAINTS:
- The PLAN section must contain between 1 and 5 numbered steps (1 to 5).
- Each step must be a concrete, operational instruction.
"""


@dataclass
class AdaptivePlanSpec:
    mode: str  # "DIRECT" or "PYTHON"
    objective: str
    evidence_status: str  # "SUFFICIENT" or "INSUFFICIENT"
    evidence_needed: str
    followup_query: str  # "NONE" or targeted search query
    plan_steps: List[str]
    answer_type: str
    raw_plan: str
    is_fallback: bool = False
    validation_error: Optional[str] = None

    @property
    def steps(self) -> List[str]:
        return self.plan_steps


@dataclass
class AdaptivePlannerParseResult:
    success: bool
    plan_spec: AdaptivePlanSpec
    error_message: Optional[str] = None
    error_type: Optional[str] = None

    @property
    def plan(self) -> AdaptivePlanSpec:
        return self.plan_spec

    @property
    def fallback_used(self) -> bool:
        return not self.success or self.plan_spec.is_fallback


def build_adaptive_fallback_plan(
    question: str = "",
    raw_text: str = "",
    error_message: str = "parse_failed",
) -> AdaptivePlanSpec:
    """Constructs the deterministic safe fallback plan when planning or parsing fails.

    Critical safety invariant: Fallback specifies EVIDENCE_STATUS=SUFFICIENT and
    FOLLOWUP_QUERY=NONE so it can NEVER trigger Search 2.
    """
    return AdaptivePlanSpec(
        mode="DIRECT",
        objective="Answer the question directly using available evidence.",
        evidence_status="SUFFICIENT",
        evidence_needed="Existing web search or file context.",
        followup_query="NONE",
        plan_steps=["1. Extract the direct answer from the available evidence."],
        answer_type="short text",
        raw_plan=raw_text or "",
        is_fallback=True,
        validation_error=error_message,
    )


def canonical_execution_plan_payload(plan_spec: AdaptivePlanSpec) -> dict:
    """Extracts the execution-only fields of an AdaptivePlanSpec for canonical hashing.

    Excludes retrieval-control and parser metadata fields:
    - EVIDENCE_STATUS
    - FOLLOWUP_QUERY
    - raw_plan
    - is_fallback
    - validation_error
    """
    return {
        "mode": plan_spec.mode,
        "objective": plan_spec.objective,
        "evidence_needed": plan_spec.evidence_needed,
        "plan_steps": list(plan_spec.plan_steps),
        "answer_type": plan_spec.answer_type,
    }


def hash_canonical_execution_plan(plan_spec: AdaptivePlanSpec) -> str:
    """Computes a deterministic SHA-256 hash of the execution-only plan payload.

    Uses sorted keys, no whitespace separators, and ensure_ascii=False.
    """
    payload = canonical_execution_plan_payload(plan_spec)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def normalize_followup_query(query: Optional[str], max_len: int = 1500) -> Tuple[str, bool]:
    """Normalizes a follow-up search query string.

    1. Strip leading and trailing whitespace.
    2. Collapse internal repeated whitespace to a single space.
    3. Deterministically truncate to max_len characters if needed.

    Note: Wrapping quotes are intentionally preserved because quotes are valid
    search query operator syntax for exact phrase matching.

    Returns (normalized_query, is_truncated).
    """
    if not query:
        return "", False
    s = str(query).strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) > max_len:
        return s[:max_len], True
    return s, False


def parse_adaptive_planner_result(raw_text: Optional[str]) -> AdaptivePlannerParseResult:
    """Parses the Planner v2 output according to the line-oriented deterministic grammar.

    Enforces:
    - MODE must be either DIRECT or PYTHON.
    - OBJECTIVE must be non-empty.
    - EVIDENCE_STATUS must be either SUFFICIENT or INSUFFICIENT.
    - EVIDENCE_NEEDED must be non-empty.
    - FOLLOWUP_QUERY must be present.
      * If EVIDENCE_STATUS == SUFFICIENT: FOLLOWUP_QUERY must be NONE.
      * If EVIDENCE_STATUS == INSUFFICIENT: FOLLOWUP_QUERY must NOT be NONE or empty.
    - PLAN must contain between 1 and 5 consecutively numbered steps starting at 1.
    - ANSWER_TYPE must be non-empty.
    """
    if not raw_text or not str(raw_text).strip():
        fallback = build_adaptive_fallback_plan(raw_text=raw_text or "", error_message="empty_provider_response")
        return AdaptivePlannerParseResult(
            success=False,
            plan_spec=fallback,
            error_message="empty_provider_response",
            error_type="PlannerEmptyResponseError",
        )

    text = str(raw_text).strip()

    # 1. Parse MODE
    mode_match = re.search(r"(?:^|\n)\s*(?:\*{1,2})?MODE(?:\*{1,2})?\s*:\s*([^\n\r]+)", text, re.IGNORECASE)
    if not mode_match:
        fallback = build_adaptive_fallback_plan(raw_text=text, error_message="missing_mode_key")
        return AdaptivePlannerParseResult(
            success=False,
            plan_spec=fallback,
            error_message="missing_mode_key",
            error_type="PlannerMissingKeyError",
        )

    raw_mode = mode_match.group(1).strip().strip("*_` ")
    mode_upper = raw_mode.upper()
    if mode_upper in ("DIRECT", "PYTHON"):
        mode = mode_upper
    else:
        fallback = build_adaptive_fallback_plan(raw_text=text, error_message="unsupported_mode")
        return AdaptivePlannerParseResult(
            success=False,
            plan_spec=fallback,
            error_message="unsupported_mode",
            error_type="PlannerInvalidModeError",
        )

    # 2. Parse OBJECTIVE
    obj_match = re.search(r"(?:^|\n)\s*(?:\*{1,2})?OBJECTIVE(?:\*{1,2})?\s*:\s*([^\n\r]+)", text, re.IGNORECASE)
    if not obj_match or not obj_match.group(1).strip():
        fallback = build_adaptive_fallback_plan(raw_text=text, error_message="missing_objective_key")
        return AdaptivePlannerParseResult(
            success=False,
            plan_spec=fallback,
            error_message="missing_objective_key",
            error_type="PlannerMissingKeyError",
        )
    objective = obj_match.group(1).strip().strip("*_` ")

    # 3. Parse EVIDENCE_STATUS
    ev_status_match = re.search(
        r"(?:^|\n)\s*(?:\*{1,2})?EVIDENCE_STATUS(?:\*{1,2})?\s*:\s*([^\n\r]+)", text, re.IGNORECASE
    )
    if not ev_status_match or not ev_status_match.group(1).strip():
        fallback = build_adaptive_fallback_plan(raw_text=text, error_message="missing_evidence_status_key")
        return AdaptivePlannerParseResult(
            success=False,
            plan_spec=fallback,
            error_message="missing_evidence_status_key",
            error_type="PlannerMissingKeyError",
        )
    raw_ev_status = ev_status_match.group(1).strip().strip("*_` ").upper()
    if raw_ev_status in ("SUFFICIENT", "INSUFFICIENT"):
        evidence_status = raw_ev_status
    else:
        fallback = build_adaptive_fallback_plan(raw_text=text, error_message="invalid_evidence_status")
        return AdaptivePlannerParseResult(
            success=False,
            plan_spec=fallback,
            error_message="invalid_evidence_status",
            error_type="PlannerInvalidEvidenceStatusError",
        )

    # 4. Parse EVIDENCE_NEEDED
    evid_match = re.search(
        r"(?:^|\n)\s*(?:\*{1,2})?EVIDENCE_NEEDED(?:\*{1,2})?\s*:\s*([^\n\r]+)", text, re.IGNORECASE
    )
    if not evid_match or not evid_match.group(1).strip():
        fallback = build_adaptive_fallback_plan(raw_text=text, error_message="missing_evidence_needed_key")
        return AdaptivePlannerParseResult(
            success=False,
            plan_spec=fallback,
            error_message="missing_evidence_needed_key",
            error_type="PlannerMissingKeyError",
        )
    evidence_needed = evid_match.group(1).strip().strip("*_` ")

    # 5. Parse FOLLOWUP_QUERY
    query_key_match = re.search(
        r"(?:^|\n)\s*(?:\*{1,2})?FOLLOWUP_QUERY(?:\*{1,2})?\s*:\s*([^\n\r]*)", text, re.IGNORECASE
    )
    if not query_key_match:
        fallback = build_adaptive_fallback_plan(raw_text=text, error_message="missing_followup_query_key")
        return AdaptivePlannerParseResult(
            success=False,
            plan_spec=fallback,
            error_message="missing_followup_query_key",
            error_type="PlannerMissingKeyError",
        )
    raw_followup_query = query_key_match.group(1).strip().strip("*_` ")

    # Validate FOLLOWUP_QUERY vs EVIDENCE_STATUS contract
    if evidence_status == "SUFFICIENT":
        if raw_followup_query.upper() != "NONE":
            fallback = build_adaptive_fallback_plan(raw_text=text, error_message="sufficient_with_non_none_query")
            return AdaptivePlannerParseResult(
                success=False,
                plan_spec=fallback,
                error_message="sufficient_with_non_none_query",
                error_type="PlannerInvalidFollowupQueryError",
            )
        followup_query = "NONE"
    else:  # INSUFFICIENT
        if not raw_followup_query or raw_followup_query.upper() == "NONE":
            fallback = build_adaptive_fallback_plan(
                raw_text=text, error_message="insufficient_with_none_or_empty_query"
            )
            return AdaptivePlannerParseResult(
                success=False,
                plan_spec=fallback,
                error_message="insufficient_with_none_or_empty_query",
                error_type="PlannerInvalidFollowupQueryError",
            )
        followup_query = raw_followup_query

    # 6. Parse ANSWER_TYPE
    ans_match = re.search(
        r"(?:^|\n)\s*(?:\*{1,2})?ANSWER_TYPE(?:\*{1,2})?\s*:\s*([^\n\r]+)", text, re.IGNORECASE
    )
    if not ans_match or not ans_match.group(1).strip():
        fallback = build_adaptive_fallback_plan(raw_text=text, error_message="missing_answer_type_key")
        return AdaptivePlannerParseResult(
            success=False,
            plan_spec=fallback,
            error_message="missing_answer_type_key",
            error_type="PlannerMissingKeyError",
        )
    answer_type = ans_match.group(1).strip().strip("*_` ")

    # 7. Parse PLAN steps
    plan_section_match = re.search(
        r"(?:^|\n)\s*(?:\*{1,2})?PLAN(?:\*{1,2})?\s*:\s*(.*?)(?=\s*(?:\*{1,2})?ANSWER_TYPE|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not plan_section_match:
        fallback = build_adaptive_fallback_plan(raw_text=text, error_message="empty_or_missing_plan")
        return AdaptivePlannerParseResult(
            success=False,
            plan_spec=fallback,
            error_message="empty_or_missing_plan",
            error_type="PlannerEmptyPlanError",
        )

    plan_body = plan_section_match.group(1).strip()
    if not plan_body:
        fallback = build_adaptive_fallback_plan(raw_text=text, error_message="empty_or_missing_plan")
        return AdaptivePlannerParseResult(
            success=False,
            plan_spec=fallback,
            error_message="empty_or_missing_plan",
            error_type="PlannerEmptyPlanError",
        )

    raw_lines = [line.strip() for line in plan_body.splitlines() if line.strip()]
    if not raw_lines:
        fallback = build_adaptive_fallback_plan(raw_text=text, error_message="empty_or_missing_plan")
        return AdaptivePlannerParseResult(
            success=False,
            plan_spec=fallback,
            error_message="empty_or_missing_plan",
            error_type="PlannerEmptyPlanError",
        )

    step_count = len(raw_lines)
    if step_count > 5:
        fallback = build_adaptive_fallback_plan(raw_text=text, error_message="plan_step_count_exceeded")
        return AdaptivePlannerParseResult(
            success=False,
            plan_spec=fallback,
            error_message="plan_step_count_exceeded",
            error_type="PlannerStepCountError",
        )

    formatted_steps: List[str] = []
    for expected_idx, line in enumerate(raw_lines, start=1):
        cleaned_line = line.strip("*_` ")
        step_match = re.match(r"^(\d+)\.\s*(.+)$", cleaned_line)
        if not step_match:
            fallback = build_adaptive_fallback_plan(raw_text=text, error_message="non_consecutive_plan_steps")
            return AdaptivePlannerParseResult(
                success=False,
                plan_spec=fallback,
                error_message="non_consecutive_plan_steps",
                error_type="PlannerStepNumberingError",
            )
        step_num = int(step_match.group(1))
        step_desc = step_match.group(2).strip()
        if step_num != expected_idx or not step_desc:
            fallback = build_adaptive_fallback_plan(raw_text=text, error_message="non_consecutive_plan_steps")
            return AdaptivePlannerParseResult(
                success=False,
                plan_spec=fallback,
                error_message="non_consecutive_plan_steps",
                error_type="PlannerStepNumberingError",
            )
        formatted_steps.append(f"{step_num}. {step_desc}")

    plan_spec = AdaptivePlanSpec(
        mode=mode,
        objective=objective,
        evidence_status=evidence_status,
        evidence_needed=evidence_needed,
        followup_query=followup_query,
        plan_steps=formatted_steps,
        answer_type=answer_type,
        raw_plan=text,
        is_fallback=False,
        validation_error=None,
    )

    return AdaptivePlannerParseResult(success=True, plan_spec=plan_spec, error_message=None, error_type=None)


def build_adaptive_planner_prompt(
    question: str,
    web_evidence: str = "",
    file_evidence: str = "",
    attachment_filename: str = "",
) -> str:
    """Constructs the prompt for the Structured Planner v2 Gemini generation (Slot 1)."""
    sections = [ADAPTIVE_PLANNER_SYSTEM_PROMPT.strip()]

    if web_evidence and web_evidence.strip():
        sections.append(f"WEB SEARCH EVIDENCE:\n{web_evidence.strip()}")

    if file_evidence and file_evidence.strip():
        sections.append(f"ATTACHMENT EVIDENCE:\n{file_evidence.strip()}")

    if attachment_filename and attachment_filename.strip():
        sections.append(
            f"ATTACHMENT FILE:\nFilename: {attachment_filename.strip()} (accessible in current working directory)"
        )

    sections.append(f"QUESTION:\n{question.strip()}")

    return "\n\n".join(sections)

