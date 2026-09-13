"""Read-only post-answer self-evaluation prompt and strict parser for V6."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Optional


SELF_EVALUATION_PROMPT_VERSION = "self-evaluator-v1"

SELF_EVALUATOR_SYSTEM_PROMPT = """You are a bounded reliability assessor for a GAIA benchmark assistant.

Assess only whether the supplied final answer is sufficiently trustworthy using the supplied question, already-available evidence, file context, and compact execution summary. This is a read-only diagnostic task: never rewrite, repair, replace, normalize, append to, or suppress the final answer.

Use only the supplied material. Do not request evidence, search, use tools, run code, execute Python, call another agent, or retry anything. Consider evidence support, reasoning plausibility, calculations, exact-answer formatting requirements, and execution telemetry. A terse answer alone is not a reason to mark it suspect. Plausible-looking answers with insufficient or conflicting evidence may be suspect.

Output exactly these three lines and nothing else:
ASSESSMENT: PASS or SUSPECT
RISK_TYPE: NONE, EVIDENCE, REASONING, CALCULATION, FORMAT, EXECUTION, or UNKNOWN
CONFIDENCE: a decimal number from 0.00 to 1.00

For PASS, RISK_TYPE must be NONE. For SUSPECT, RISK_TYPE must be one of EVIDENCE, REASONING, CALCULATION, FORMAT, EXECUTION, or UNKNOWN. CONFIDENCE is confidence that this assessment is correct.

Do not output an explanation, prose, markdown, a code fence, an alternate answer, or hidden reasoning. Native function calling is disabled."""


ASSESSMENTS = {"PASS", "SUSPECT"}
RISK_TYPES = {"NONE", "EVIDENCE", "REASONING", "CALCULATION", "FORMAT", "EXECUTION", "UNKNOWN"}
SUSPECT_RISK_TYPES = RISK_TYPES - {"NONE"}


@dataclass(frozen=True)
class SelfEvaluationParseResult:
    """Result of strict V6 diagnostic-schema parsing.

    ``status`` is one of ``VALID_PASS``, ``VALID_SUSPECT``, or ``INVALID``.
    The parser never infers a label from malformed model output.
    """

    status: str
    assessment: Optional[str] = None
    risk_type: Optional[str] = None
    confidence: Optional[float] = None
    error_type: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.status in {"VALID_PASS", "VALID_SUSPECT"}


def build_execution_summary(
    *,
    route: Optional[str],
    search_attempted: bool,
    search_success: bool,
    search_fallback: bool,
    attachment_required: bool,
    file_attempted: bool,
    file_success: bool,
    python_routed: bool,
    python_attempted: bool,
    python_success: bool,
    execution_error_type: Optional[str],
    completion_success: bool,
    finish_reason: Optional[str],
) -> str:
    """Returns a compact, deterministic, public-safe V6 execution summary.

    It deliberately omits raw model output, V5 verifier decisions, benchmark labels,
    generated code, and Python stdout/stderr.
    """
    if search_attempted:
        search_status = "success" if search_success else "failed"
        if search_fallback:
            search_status += "; fallback used"
    else:
        search_status = "not attempted"

    if not attachment_required:
        attachment_status = "not required"
    elif not file_attempted:
        attachment_status = "required; not attempted"
    else:
        attachment_status = "success" if file_success else "failed"

    if not python_routed:
        python_status = "not routed"
    elif not python_attempted:
        python_status = "routed; not attempted"
    else:
        python_status = "attempted; success" if python_success else "attempted; failed"

    error_status = execution_error_type.strip() if execution_error_type and execution_error_type.strip() else "none"
    route_status = route.strip().upper() if route and route.strip() else "UNKNOWN"
    finish_status = finish_reason.strip().upper() if finish_reason and finish_reason.strip() else "UNKNOWN"

    return "\n".join(
        [
            f"Route: {route_status}",
            f"Search: {search_status}",
            f"Attachment: {attachment_status}",
            f"Python: {python_status}",
            f"Execution error category: {error_status}",
            f"Completion: {'true' if completion_success else 'false'}",
            f"Finish reason: {finish_status}",
        ]
    )


def build_self_evaluator_prompt(
    *,
    question: str,
    final_answer: str,
    execution_summary: str,
    web_evidence: str = "",
    file_evidence: str = "",
    attachment_filename: str = "",
) -> str:
    """Builds the text-only V6 evaluator input.

    This firewall accepts only completed V5 material. It intentionally has no
    parameter for scoring data, V5 decisions, hidden reasoning, raw worker output,
    generated code, or Python stdout/stderr.
    """
    sections = [SELF_EVALUATOR_SYSTEM_PROMPT.strip()]

    if web_evidence and web_evidence.strip():
        sections.append(f"WEB SEARCH EVIDENCE:\n{web_evidence.strip()}")
    if file_evidence and file_evidence.strip():
        sections.append(f"ATTACHMENT CONTEXT:\n{file_evidence.strip()}")
    if attachment_filename and attachment_filename.strip():
        sections.append(f"ATTACHMENT FILE:\nFilename: {attachment_filename.strip()}")

    sections.append(f"QUESTION:\n{question.strip()}")
    sections.append(f"FINAL ANSWER (READ ONLY):\n{final_answer}")
    sections.append(f"EXECUTION SUMMARY:\n{execution_summary.strip()}")
    return "\n\n".join(sections)


def _invalid(error_type: str) -> SelfEvaluationParseResult:
    return SelfEvaluationParseResult(status="INVALID", error_type=error_type)


def parse_self_evaluation_result(raw_text: Optional[str]) -> SelfEvaluationParseResult:
    """Strictly parses exactly three V6 evaluator schema lines.

    Values are case-insensitive to match the existing V5 parser convention; field
    count, field names, combinations, decimal syntax, and all surrounding content
    remain strict. No malformed response is normalized into PASS or SUSPECT.
    """
    if raw_text is None or not str(raw_text).strip():
        return _invalid("empty_self_evaluator_response")

    text = str(raw_text).strip()
    if "```" in text:
        return _invalid("markdown_code_fence")

    lines = text.splitlines()
    if len(lines) != 3:
        return _invalid("unexpected_self_evaluator_content")

    field_pattern = re.compile(r"^\s*([A-Za-z_]+)\s*:\s*(.*?)\s*$")
    parsed = {}
    expected_fields = {"ASSESSMENT", "RISK_TYPE", "CONFIDENCE"}
    for line in lines:
        match = field_pattern.fullmatch(line)
        if not match:
            return _invalid("malformed_self_evaluator_text")
        field = match.group(1).upper()
        value = match.group(2)
        if field not in expected_fields:
            return _invalid("unexpected_self_evaluator_field")
        if field in parsed:
            return _invalid("duplicate_self_evaluator_field")
        if not value:
            return _invalid("missing_self_evaluator_value")
        parsed[field] = value

    if set(parsed) != expected_fields:
        return _invalid("missing_self_evaluator_field")

    assessment = parsed["ASSESSMENT"].upper()
    risk_type = parsed["RISK_TYPE"].upper()
    confidence_text = parsed["CONFIDENCE"]

    if assessment not in ASSESSMENTS:
        return _invalid("unknown_self_evaluator_assessment")
    if risk_type not in RISK_TYPES:
        return _invalid("unknown_self_evaluator_risk_type")

    # Decimal-only lexical contract: no signs, exponent notation, NaN, or infinity.
    if not re.fullmatch(r"(?:0(?:\.\d+)?|1(?:\.0+)?)", confidence_text):
        return _invalid("malformed_self_evaluator_confidence")
    try:
        confidence_decimal = Decimal(confidence_text)
    except (InvalidOperation, ValueError):
        return _invalid("malformed_self_evaluator_confidence")
    if not Decimal("0") <= confidence_decimal <= Decimal("1"):
        return _invalid("self_evaluator_confidence_out_of_range")

    if assessment == "PASS" and risk_type != "NONE":
        return _invalid("inconsistent_self_evaluation_schema")
    if assessment == "SUSPECT" and risk_type not in SUSPECT_RISK_TYPES:
        return _invalid("inconsistent_self_evaluation_schema")

    return SelfEvaluationParseResult(
        status="VALID_PASS" if assessment == "PASS" else "VALID_SUSPECT",
        assessment=assessment,
        risk_type=risk_type,
        confidence=float(confidence_decimal),
    )
