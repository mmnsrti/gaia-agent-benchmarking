"""Targeted repair prompt definitions and strict parser for V7."""

import re
from dataclasses import dataclass
from typing import Optional


TARGETED_REPAIR_PROMPT_VERSION = "targeted-repair-v1"

TARGETED_REPAIR_SYSTEM_PROMPT = """You are a bounded targeted repairer for a GAIA benchmark assistant.

The current final answer was marked SUSPECT by an upstream reliability evaluator.

Reconsider the answer using ONLY the supplied question, existing evidence, existing attachment context, structured diagnostic signal, and execution summary.

Do not search. Do not request evidence. Do not execute Python. Do not use tools. Do not call another agent. Do not retry. Do not produce reasoning or explanation.

The SUSPECT signal does not prove the answer is wrong.

If the existing answer remains the best-supported exact answer, KEEP it.

Only REPLACE it when the supplied evidence supports a clearly better answer.

OUTPUT FORMAT:
If the existing answer should be preserved:
REPAIR_ACTION: KEEP

If a clearly better answer is supported by the evidence:
REPAIR_ACTION: REPLACE
FINAL: <corrected answer>

STRICT RULES:
- Output ONLY the lines specified in the contract.
- No markdown, code fences, explanations, or hidden reasoning.
- REPAIR_ACTION is case-insensitive during parsing and must be KEEP or REPLACE.
- KEEP must be exactly one line and must NOT include a FINAL line.
- REPLACE must be exactly two lines and must include a non-empty single-line FINAL answer.
- If REPLACE is chosen, the FINAL answer must not be identical to the current answer.
- Native function calling is disabled."""

REPAIR_ACTIONS = {"KEEP", "REPLACE"}


@dataclass(frozen=True)
class TargetedRepairParseResult:
    """Structured result of strict V7 targeted repair schema parsing.

    ``status`` is one of ``VALID_KEEP``, ``VALID_REPLACE``, or ``INVALID``.
    The parser never normalizes a malformed response into a valid action.
    """

    status: str
    action: Optional[str] = None
    final_answer: Optional[str] = None
    error_type: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.status in {"VALID_KEEP", "VALID_REPLACE"}


def build_targeted_repair_prompt(
    question: str,
    current_answer: str,
    risk_type: Optional[str] = None,
    confidence: Optional[float] = None,
    execution_summary: str = "",
    web_evidence: str = "",
    file_evidence: str = "",
    attachment_filename: str = "",
    self_eval_assessment: Optional[str] = None,
    self_eval_risk_type: Optional[str] = None,
    self_eval_confidence: Optional[float] = None,
) -> str:
    """Builds the text-only V7 targeted repair prompt.

    FIREWALL GUARANTEE:
    Receives ONLY:
    - Original question
    - Existing web evidence
    - Existing file context and filename
    - Current pre-repair answer
    - Upstream V6 diagnostic signal (SUSPECT, risk type, confidence)
    - Compact deterministic execution summary

    Never receives ground truth, reference answers, scorer results, raw worker
    reasoning, generated Python code, or Python stdout/stderr.
    """
    if risk_type is None and self_eval_risk_type is not None:
        risk_type = self_eval_risk_type
    if confidence is None and self_eval_confidence is not None:
        confidence = self_eval_confidence

    sections = [TARGETED_REPAIR_SYSTEM_PROMPT.strip()]

    if web_evidence and web_evidence.strip():
        sections.append(f"WEB SEARCH EVIDENCE:\n{web_evidence.strip()}")
    if file_evidence and file_evidence.strip():
        sections.append(f"ATTACHMENT CONTEXT:\n{file_evidence.strip()}")
    if attachment_filename and attachment_filename.strip():
        sections.append(f"ATTACHMENT FILE:\nFilename: {attachment_filename.strip()}")

    sections.append(f"QUESTION:\n{question.strip()}")
    sections.append(f"CURRENT ANSWER (MARKED SUSPECT):\n{current_answer.strip()}")

    assessment_str = (self_eval_assessment or "SUSPECT").strip().upper()
    diagnostic_lines = ["UPSTREAM DIAGNOSTIC SIGNAL:", f"ASSESSMENT: {assessment_str}"]
    if risk_type and risk_type.strip():
        diagnostic_lines.append(f"RISK_TYPE: {risk_type.strip().upper()}")
    if confidence is not None:
        diagnostic_lines.append(f"CONFIDENCE: {confidence:.2f}")
    sections.append("\n".join(diagnostic_lines))

    if execution_summary and execution_summary.strip():
        sections.append(f"EXECUTION SUMMARY:\n{execution_summary.strip()}")

    return "\n\n".join(sections)


def _invalid(error_type: str) -> TargetedRepairParseResult:
    return TargetedRepairParseResult(status="INVALID", error_type=error_type)


def parse_targeted_repair_result(
    raw_text: Optional[str],
    original_answer: Optional[str] = None,
    current_answer: Optional[str] = None,
) -> TargetedRepairParseResult:
    """Strictly parses targeted repair schema output.

    Accepts:
    1. Exactly one line for KEEP:
       REPAIR_ACTION: KEEP
    2. Exactly two lines for REPLACE:
       REPAIR_ACTION: REPLACE
       FINAL: <non-empty answer>

    Action matching is case-insensitive. All extra content, code fences,
    duplicate fields, and malformed syntax are rejected as INVALID.
    """
    if original_answer is None and current_answer is not None:
        original_answer = current_answer

    if raw_text is None or not str(raw_text).strip():
        return _invalid("empty_repair_response")

    text = str(raw_text).strip()
    if "```" in text:
        return _invalid("markdown_code_fence")

    lines = text.splitlines()
    if len(lines) not in (1, 2):
        return _invalid("unexpected_repair_content")

    field_pattern = re.compile(r"^\s*([A-Za-z_]+)\s*:\s*(.*?)\s*$")
    parsed_fields = {}
    field_order = []

    for line in lines:
        match = field_pattern.fullmatch(line)
        if not match:
            return _invalid("malformed_repair_text")
        field = match.group(1).upper()
        value = match.group(2)
        if field not in {"REPAIR_ACTION", "FINAL"}:
            return _invalid("unexpected_repair_field")
        if field in parsed_fields:
            return _invalid("duplicate_repair_field")
        parsed_fields[field] = value
        field_order.append(field)

    if "REPAIR_ACTION" not in parsed_fields:
        return _invalid("missing_repair_field")

    action_raw = parsed_fields["REPAIR_ACTION"].strip().upper()
    if action_raw not in REPAIR_ACTIONS:
        return _invalid("unknown_repair_action")

    if action_raw == "KEEP":
        if len(lines) != 1 or "FINAL" in parsed_fields:
            return _invalid("keep_with_final")
        return TargetedRepairParseResult(status="VALID_KEEP", action="KEEP")

    # action_raw == "REPLACE"
    if len(lines) != 2 or "FINAL" not in parsed_fields:
        return _invalid("replace_missing_final")

    final_val = parsed_fields["FINAL"].strip()
    if not final_val:
        return _invalid("replace_empty_final")

    if "\n" in final_val or "\r" in final_val:
        return _invalid("multiline_replacement")

    if original_answer is not None and final_val == original_answer.strip():
        return _invalid("replace_same_answer")

    return TargetedRepairParseResult(
        status="VALID_REPLACE",
        action="REPLACE",
        final_answer=final_val,
    )
