"""Active evidence verification prompt definitions and strict parser for V8."""

import re
from dataclasses import dataclass
from typing import Optional


ACTIVE_EVIDENCE_VERIFICATION_PROMPT_VERSION = "active-evidence-verification-v1"

ACTIVE_EVIDENCE_VERIFICATION_SYSTEM_PROMPT = """You are a bounded evidence adjudicator for a GAIA benchmark assistant.

The current answer was previously marked SUSPECT with an EVIDENCE risk.

You have now been given one additional retrieval result.

Use the question, existing context, and newly retrieved evidence to decide whether the current answer should be preserved or replaced.

The SUSPECT label does not prove the current answer is wrong.
The new search result does not automatically prove the answer is wrong or right.

KEEP the current answer unless the available evidence supports a clearly better exact answer.

Do not search. Do not execute Python. Do not call tools. Do not retry. Do not produce reasoning or explanation.

OUTPUT FORMAT:
If the current answer should be preserved:
VERIFICATION_ACTION: KEEP

If a clearly better answer is supported by the evidence:
VERIFICATION_ACTION: REPLACE
FINAL: <corrected answer>

STRICT RULES:
- Output ONLY the lines specified in the contract.
- No markdown, code fences, explanations, or hidden reasoning.
- VERIFICATION_ACTION is case-insensitive during parsing and must be KEEP or REPLACE.
- KEEP must be exactly one line and must NOT include a FINAL line.
- REPLACE must be exactly two lines and must include a non-empty single-line FINAL answer.
- If REPLACE is chosen, the FINAL answer must not be identical to the current answer.
- Native function calling is disabled."""

VERIFICATION_ACTIONS = {"KEEP", "REPLACE"}


@dataclass(frozen=True)
class ActiveEvidenceVerificationParseResult:
    """Structured result of strict V8 active evidence verification schema parsing.

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


def build_active_evidence_query(
    question: str,
    current_answer: str,
) -> str:
    """Deterministic, pure Python query formulation for V8 active verification search.

    Contract:
    <Question>

    Candidate answer to independently verify:
    <Current V7 final answer>

    Truncation beyond 1500 chars is delegated to TavilySearchTool.
    """
    cleaned_q = question.strip() if question else ""
    cleaned_ans = current_answer.strip() if current_answer else ""
    return f"{cleaned_q}\n\nCandidate answer to independently verify:\n{cleaned_ans}"


def build_active_evidence_verification_prompt(
    question: str,
    current_answer: str,
    new_evidence: str,
    web_evidence: str = "",
    file_evidence: str = "",
    attachment_filename: str = "",
    risk_type: Optional[str] = "EVIDENCE",
    confidence: Optional[float] = None,
    execution_summary: str = "",
    self_eval_assessment: Optional[str] = "SUSPECT",
    self_eval_risk_type: Optional[str] = None,
    self_eval_confidence: Optional[float] = None,
) -> str:
    """Builds the text-only V8 active evidence adjudication prompt.

    FIREWALL GUARANTEE:
    Receives ONLY:
    - Original question
    - Current Frozen V7 final answer
    - Existing original web search evidence
    - Existing extracted file context and filename
    - Newly retrieved active verification evidence
    - Upstream V6 diagnostic signal (SUSPECT, risk type, confidence)
    - Compact deterministic execution summary

    Never receives ground truth, reference answers, scorer results, raw worker
    reasoning, generated Python source code, Python stdout/stderr, or raw
    verifier/evaluator/repair responses.
    """
    if risk_type is None and self_eval_risk_type is not None:
        risk_type = self_eval_risk_type
    if confidence is None and self_eval_confidence is not None:
        confidence = self_eval_confidence

    sections = [ACTIVE_EVIDENCE_VERIFICATION_SYSTEM_PROMPT.strip()]

    if web_evidence and web_evidence.strip():
        sections.append(f"ORIGINAL WEB SEARCH EVIDENCE:\n{web_evidence.strip()}")
    if file_evidence and file_evidence.strip():
        sections.append(f"ATTACHMENT CONTEXT:\n{file_evidence.strip()}")
    if attachment_filename and attachment_filename.strip():
        sections.append(f"ATTACHMENT FILE:\nFilename: {attachment_filename.strip()}")

    cleaned_new = new_evidence.strip() if new_evidence else "No new evidence retrieved."
    sections.append(f"NEWLY RETRIEVED ACTIVE VERIFICATION EVIDENCE:\n{cleaned_new}")

    sections.append(f"QUESTION:\n{question.strip()}")
    sections.append(f"CURRENT ANSWER (MARKED SUSPECT):\n{current_answer.strip()}")

    assessment_str = (self_eval_assessment or "SUSPECT").strip().upper()
    resolved_risk = (risk_type or "EVIDENCE").strip().upper()
    diagnostic_lines = [
        "UPSTREAM DIAGNOSTIC SIGNAL:",
        f"ASSESSMENT: {assessment_str}",
        f"RISK_TYPE: {resolved_risk}",
    ]
    if confidence is not None:
        diagnostic_lines.append(f"CONFIDENCE: {confidence:.2f}")
    sections.append("\n".join(diagnostic_lines))

    if execution_summary and execution_summary.strip():
        sections.append(f"EXECUTION SUMMARY:\n{execution_summary.strip()}")

    return "\n\n".join(sections)


def _invalid(error_type: str) -> ActiveEvidenceVerificationParseResult:
    return ActiveEvidenceVerificationParseResult(status="INVALID", error_type=error_type)


def parse_active_evidence_verification_result(
    raw_text: Optional[str],
    current_answer: Optional[str] = None,
) -> ActiveEvidenceVerificationParseResult:
    """Strictly parses active evidence verification schema output.

    Accepts:
    1. Exactly one line for KEEP:
       VERIFICATION_ACTION: KEEP
    2. Exactly two lines for REPLACE:
       VERIFICATION_ACTION: REPLACE
       FINAL: <non-empty answer>

    Action matching is case-insensitive. All extra content, code fences,
    duplicate fields, and malformed syntax are rejected as INVALID.
    """
    if raw_text is None or not str(raw_text).strip():
        return _invalid("empty_verification_response")

    text = str(raw_text).strip()
    if "```" in text:
        return _invalid("markdown_code_fence")

    lines = text.splitlines()
    if len(lines) not in (1, 2):
        return _invalid("unexpected_verification_content")

    field_pattern = re.compile(r"^\s*([A-Za-z_]+)\s*:\s*(.*?)\s*$")
    parsed_fields = {}

    for line in lines:
        match = field_pattern.fullmatch(line)
        if not match:
            return _invalid("malformed_verification_text")
        field = match.group(1).upper()
        value = match.group(2)
        if field not in {"VERIFICATION_ACTION", "FINAL"}:
            return _invalid("unexpected_verification_field")
        if field in parsed_fields:
            return _invalid("duplicate_verification_field")
        parsed_fields[field] = value

    if "VERIFICATION_ACTION" not in parsed_fields:
        return _invalid("missing_verification_field")

    action_raw = parsed_fields["VERIFICATION_ACTION"].strip().upper()
    if action_raw not in VERIFICATION_ACTIONS:
        return _invalid("unknown_verification_action")

    if action_raw == "KEEP":
        if len(lines) != 1 or "FINAL" in parsed_fields:
            return _invalid("keep_with_final")
        return ActiveEvidenceVerificationParseResult(status="VALID_KEEP", action="KEEP")

    # action_raw == "REPLACE"
    if len(lines) != 2 or "FINAL" not in parsed_fields:
        return _invalid("replace_missing_final")

    final_val = parsed_fields["FINAL"].strip()
    if not final_val:
        return _invalid("replace_empty_final")

    if "\n" in final_val or "\r" in final_val:
        return _invalid("multiline_replacement")

    if current_answer is not None and final_val == current_answer.strip():
        return _invalid("replace_same_answer")

    return ActiveEvidenceVerificationParseResult(
        status="VALID_REPLACE",
        action="REPLACE",
        final_answer=final_val,
    )

