"""Candidate recovery prompt definitions and strict parser for V9."""

import re
from dataclasses import dataclass
from typing import Optional


CANDIDATE_RECOVERY_PROMPT_VERSION = "candidate-recovery-v1"

CANDIDATE_RECOVERY_SYSTEM_PROMPT = """You are a bounded candidate answer recovery specialist for a GAIA benchmark assistant.

The upstream pipeline failed to extract or produce a valid final answer for this question due to an upstream generation or execution failure.

Your task is to synthesize the single, definitive exact candidate answer using ONLY the supplied question, existing search evidence, existing attachment context, and sanitized execution details.

Do not search. Do not request evidence. Do not execute Python. Do not use tools. Do not call another agent. Do not retry. Do not produce reasoning, commentary, or explanation.

OUTPUT FORMAT:
State the final answer on a single line prefixed by FINAL:
FINAL: <candidate answer>

STRICT RULES:
- Output exactly one line.
- Do NOT include markdown formatting, markdown code fences (```), or multiple lines.
- Do NOT provide explanation, caveats, or preamble.
- The answer must be the exact factual answer to the question.
- Native function calling is disabled."""


@dataclass(frozen=True)
class CandidateRecoveryParseResult:
    """Structured result of strict V9 candidate recovery schema parsing.

    ``status`` is one of ``VALID`` or ``INVALID``.
    The parser never normalizes a malformed response into a valid candidate.
    """

    status: str
    candidate_answer: Optional[str] = None
    error_type: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.status == "VALID"

    @property
    def candidate(self) -> Optional[str]:
        return self.candidate_answer


def build_candidate_recovery_prompt(
    question: str,
    web_evidence: str = "",
    file_evidence: str = "",
    attachment_filename: str = "",
    router_decision: Optional[str] = None,
    failure_class: Optional[str] = None,
    execution_snippet: Optional[str] = None,
) -> str:
    """Builds the text-only V9 candidate recovery prompt.

    FIREWALL GUARANTEE:
    Receives ONLY:
    - Original question
    - Existing web evidence (already gathered upstream)
    - Existing file context and filename (already gathered upstream)
    - Upstream router decision
    - Deterministic failure class
    - Optional sanitized execution snippet (bounded to 500 chars)

    Never receives ground truth, reference answers, scorer results, raw worker
    reasoning / chain-of-thought, or active tool interfaces.
    """
    sections = [CANDIDATE_RECOVERY_SYSTEM_PROMPT.strip()]

    if web_evidence and web_evidence.strip():
        sections.append(f"WEB SEARCH EVIDENCE:\n{web_evidence.strip()}")
    if file_evidence and file_evidence.strip():
        sections.append(f"ATTACHMENT CONTEXT:\n{file_evidence.strip()}")
    if attachment_filename and attachment_filename.strip():
        sections.append(f"ATTACHMENT FILE:\nFilename: {attachment_filename.strip()}")

    sections.append(f"QUESTION:\n{question.strip()}")

    if router_decision and router_decision.strip():
        sections.append(f"UPSTREAM ROUTER DECISION:\n{router_decision.strip()}")
    if failure_class and failure_class.strip():
        sections.append(f"UPSTREAM FAILURE CLASSIFICATION:\n{failure_class.strip()}")
    if execution_snippet and execution_snippet.strip():
        bounded_snippet = execution_snippet.strip()[:500]
        sections.append(f"UPSTREAM EXECUTION OUTPUT (SANITIZED):\n{bounded_snippet}")

    return "\n\n".join(sections)


def _invalid(error_type: str) -> CandidateRecoveryParseResult:
    return CandidateRecoveryParseResult(status="INVALID", error_type=error_type)


def parse_candidate_recovery_result(raw_text: Optional[str]) -> CandidateRecoveryParseResult:
    """Strictly parses candidate recovery schema output.

    Accepts:
    Exactly one line prefixed by FINAL:
    FINAL: <non-empty candidate answer>

    All extra lines, markdown code fences, missing markers, or empty values
    are rejected as INVALID.
    """
    if raw_text is None or not str(raw_text).strip():
        return _invalid("empty_recovery_response")

    text = str(raw_text).strip()
    if "```" in text:
        return _invalid("markdown_code_fence")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        if not any(line.upper().startswith("FINAL:") for line in lines):
        if not any(re.match(r"^\s*FINAL\s*:", l, re.IGNORECASE) for l in lines):
            return _invalid("missing_final_marker")
        return _invalid("multiline_candidate")

    line = lines[0]
    if not line.upper().startswith("FINAL:"):
    field_pattern = re.compile(r"^\s*([A-Za-z_]+)\s*:\s*(.*?)\s*$")
    match = field_pattern.fullmatch(line)
    if not match or match.group(1).upper() != "FINAL":
        return _invalid("missing_final_marker")

    val = line[6:].strip()
    val = match.group(2).strip()
    if not val:
        return _invalid("empty_final_value")

    if "\n" in val or "\r" in val:
        return _invalid("multiline_candidate")

    return CandidateRecoveryParseResult(
        status="VALID",
        candidate_answer=val,
    )
