"""Structured Planner definitions, Line-Oriented Grammar, and Parser for V10."""

import re
from dataclasses import dataclass, field
from typing import List, Optional

PLANNER_PROMPT_VERSION = "planner-v1"

PLANNER_SYSTEM_PROMPT = """You are a Structured Task Planner for complex questions and reasoning tasks.
Your role is to analyze the user's question, along with any provided search evidence and file context, and create a concrete, structured plan to solve it.

STRICT OPERATIONAL RULES:
1. Do NOT attempt to solve the question or output the final answer.
2. Do NOT execute code, write full scripts, or simulate tool executions.
3. Output ONLY the structured plan block adhering exactly to the grammar below.
4. No introduction, no markdown outside the grammar, no conversational filler, and no private scratchpad reasoning.

GRAMMAR SPECIFICATION:
MODE: <DIRECT | PYTHON>
OBJECTIVE: <single concise sentence defining what must be found or computed>
EVIDENCE_NEEDED: <specific facts, variables, or data elements required from search/file context>
PLAN:
1. <actionable step 1>
2. <actionable step 2>
...
ANSWER_TYPE: <target data format, e.g. integer, float, date, name, comma-separated list, short text>

MODE SELECTION CRITERIA:
- Use DIRECT for factual lookups, text extraction, straightforward reasoning, or where the provided evidence directly states the answer.
- Use PYTHON for complex multi-step math, date calculations, file data parsing, sorting, filtering, aggregations, or precise string manipulation.

PLAN CONSTRAINTS:
- The PLAN section must contain between 1 and 5 numbered steps (1 to 5).
- Each step must be a concrete, operational instruction.
"""


@dataclass
class PlanSpec:
    mode: str  # "DIRECT" or "PYTHON"
    objective: str
    evidence_needed: str
    plan_steps: List[str]
    answer_type: str
    raw_plan: str
    is_fallback: bool = False
    validation_error: Optional[str] = None

    @property
    def steps(self) -> List[str]:
        return self.plan_steps


@dataclass
class PlannerParseResult:
    success: bool
    plan_spec: PlanSpec
    error_message: Optional[str] = None
    error_type: Optional[str] = None

    @property
    def plan(self) -> PlanSpec:
        return self.plan_spec

    @property
    def fallback_used(self) -> bool:
        return not self.success or self.plan_spec.is_fallback


def build_fallback_plan(
    question: str = "",
    raw_text: str = "",
    error_message: str = "parse_failed",
) -> PlanSpec:
    """Constructs the deterministic safe fallback plan when planning or parsing fails."""
    return PlanSpec(
        mode="DIRECT",
        objective="Answer the question directly using available evidence.",
        evidence_needed="Existing web search or file context.",
        plan_steps=["1. Extract the direct answer from the available evidence."],
        answer_type="short text",
        raw_plan=raw_text or "",
        is_fallback=True,
        validation_error=error_message,
    )


def parse_planner_result(raw_text: Optional[str]) -> PlannerParseResult:
    """Parses the planner LLM output according to the line-oriented deterministic grammar.

    Enforces:
    - MODE must be either DIRECT or PYTHON (case-insensitive).
    - OBJECTIVE must be non-empty.
    - EVIDENCE_NEEDED must be non-empty.
    - PLAN must contain between 1 and 5 steps.
    - ANSWER_TYPE must be non-empty.
    """
    if not raw_text or not str(raw_text).strip():
        fallback = build_fallback_plan(raw_text=raw_text or "", error_message="empty_provider_response")
        return PlannerParseResult(success=False, plan_spec=fallback, error_message="empty_provider_response", error_type="PlannerEmptyResponseError")

    text = str(raw_text).strip()

    # 1. Parse MODE
    mode_match = re.search(r"(?:^|\n)\s*(?:\*{1,2})?MODE(?:\*{1,2})?\s*:\s*([^\n\r]+)", text, re.IGNORECASE)
    if not mode_match:
        fallback = build_fallback_plan(raw_text=text, error_message="missing_mode_key")
        return PlannerParseResult(success=False, plan_spec=fallback, error_message="missing_mode_key", error_type="PlannerMissingKeyError")

    raw_mode = mode_match.group(1).strip().strip("*_` ")
    # Check for valid DIRECT or PYTHON
    mode_upper = raw_mode.upper()
    if mode_upper in ("DIRECT", "PYTHON"):
        mode = mode_upper
    else:
        # Check if mode contains unambiguous DIRECT or PYTHON
        matches = re.findall(r"\b(DIRECT|PYTHON)\b", mode_upper)
        unique_matches = set(matches)
        if len(unique_matches) == 1:
            mode = unique_matches.pop()
        else:
            fallback = build_fallback_plan(raw_text=text, error_message="unsupported_mode")
            return PlannerParseResult(success=False, plan_spec=fallback, error_message="unsupported_mode", error_type="PlannerInvalidModeError")

    # 2. Parse OBJECTIVE
    obj_match = re.search(r"(?:^|\n)\s*(?:\*{1,2})?OBJECTIVE(?:\*{1,2})?\s*:\s*([^\n\r]+)", text, re.IGNORECASE)
    if not obj_match or not obj_match.group(1).strip():
        fallback = build_fallback_plan(raw_text=text, error_message="missing_objective_key")
        return PlannerParseResult(success=False, plan_spec=fallback, error_message="missing_objective_key", error_type="PlannerMissingKeyError")
    objective = obj_match.group(1).strip().strip("*_` ")

    # 3. Parse EVIDENCE_NEEDED
    evid_match = re.search(r"(?:^|\n)\s*(?:\*{1,2})?EVIDENCE_NEEDED(?:\*{1,2})?\s*:\s*([^\n\r]+)", text, re.IGNORECASE)
    if not evid_match or not evid_match.group(1).strip():
        fallback = build_fallback_plan(raw_text=text, error_message="missing_evidence_needed_key")
        return PlannerParseResult(success=False, plan_spec=fallback, error_message="missing_evidence_needed_key", error_type="PlannerMissingKeyError")
    evidence_needed = evid_match.group(1).strip().strip("*_` ")

    # 4. Parse ANSWER_TYPE
    ans_match = re.search(r"(?:^|\n)\s*(?:\*{1,2})?ANSWER_TYPE(?:\*{1,2})?\s*:\s*([^\n\r]+)", text, re.IGNORECASE)
    if not ans_match or not ans_match.group(1).strip():
        fallback = build_fallback_plan(raw_text=text, error_message="missing_answer_type_key")
        return PlannerParseResult(success=False, plan_spec=fallback, error_message="missing_answer_type_key", error_type="PlannerMissingKeyError")
    answer_type = ans_match.group(1).strip().strip("*_` ")

    # 5. Parse PLAN steps
    # Extract the text between PLAN: and ANSWER_TYPE:
    plan_section_match = re.search(
        r"(?:^|\n)\s*(?:\*{1,2})?PLAN(?:\*{1,2})?\s*:\s*(.*?)(?=\s*(?:\*{1,2})?ANSWER_TYPE|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not plan_section_match:
        fallback = build_fallback_plan(raw_text=text, error_message="empty_or_missing_plan")
        return PlannerParseResult(success=False, plan_spec=fallback, error_message="empty_or_missing_plan", error_type="PlannerEmptyPlanError")

    plan_body = plan_section_match.group(1).strip()
    if not plan_body:
        fallback = build_fallback_plan(raw_text=text, error_message="empty_or_missing_plan")
        return PlannerParseResult(success=False, plan_spec=fallback, error_message="empty_or_missing_plan", error_type="PlannerEmptyPlanError")

    # Split steps by numbered lines, bullets, or semicolons
    raw_lines = [line.strip() for line in plan_body.splitlines() if line.strip()]
    plan_steps: List[str] = []

    for line in raw_lines:
        cleaned_line = line.strip("*_` ")
        # Check if line looks like a step (e.g. 1. step, 1) step, - step, * step, or text)
        if cleaned_line:
            plan_steps.append(cleaned_line)

    # If steps were not found line-by-line (e.g. single line separated by semicolons or numbers)
    if len(plan_steps) == 1 and (";" in plan_steps[0] or re.search(r"\b\d+[\.\)]\s+", plan_steps[0])):
        if ";" in plan_steps[0]:
            sub_steps = [s.strip() for s in plan_steps[0].split(";") if s.strip()]
            if sub_steps:
                plan_steps = sub_steps
        else:
            split_parts = re.split(r"(?=\b\d+[\.\)]\s+)", plan_steps[0])
            sub_steps = [s.strip() for s in split_parts if s.strip()]
            if sub_steps:
                plan_steps = sub_steps

    step_count = len(plan_steps)
    if step_count == 0:
        fallback = build_fallback_plan(raw_text=text, error_message="empty_or_missing_plan")
        return PlannerParseResult(success=False, plan_spec=fallback, error_message="empty_or_missing_plan", error_type="PlannerEmptyPlanError")

    if step_count > 5:
        fallback = build_fallback_plan(raw_text=text, error_message="plan_step_count_exceeded")
        return PlannerParseResult(success=False, plan_spec=fallback, error_message="plan_step_count_exceeded", error_type="PlannerStepCountError")

    # Format step strings nicely (ensure 1. ..., 2. ... if not numbered)
    formatted_steps: List[str] = []
    for i, step in enumerate(plan_steps, 1):
        if re.match(r"^\d+[\.\)]\s*", step):
            # Normalize to "i. Step"
            step_clean = re.sub(r"^\d+[\.\)]\s*", "", step).strip()
            formatted_steps.append(f"{i}. {step_clean}")
        elif re.match(r"^[\-\*]\s*", step):
            step_clean = re.sub(r"^[\-\*]\s*", "", step).strip()
            formatted_steps.append(f"{i}. {step_clean}")
        else:
            formatted_steps.append(f"{i}. {step}")

    plan_spec = PlanSpec(
        mode=mode,
        objective=objective,
        evidence_needed=evidence_needed,
        plan_steps=formatted_steps,
        answer_type=answer_type,
        raw_plan=text,
        is_fallback=False,
        validation_error=None,
    )

    return PlannerParseResult(success=True, plan_spec=plan_spec, error_message=None, error_type=None)


def build_planner_prompt(
    question: str,
    web_evidence: str = "",
    file_evidence: str = "",
    attachment_filename: str = "",
) -> str:
    """Constructs the prompt for the Structured Planner Gemini generation (Slot 1)."""
    sections = [PLANNER_SYSTEM_PROMPT.strip()]

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
