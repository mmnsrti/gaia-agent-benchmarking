"""Post-answer verification prompt definitions and deterministic parser for V5."""

import re
from dataclasses import dataclass
from typing import Optional

VERIFICATION_PROMPT_VERSION = "answer-verifier-v1"

ANSWER_VERIFIER_SYSTEM_PROMPT = """You are a conservative post-answer verifier for a GAIA benchmark assistant.

Your task is to inspect a candidate answer to a question against the provided evidence and determine whether to KEEP the answer or REVISE it.

DECISION CRITERIA:
1. KEEP:
   - The candidate answer appears supported by the evidence or reasonable deduction.
   - The candidate answer follows all requested formatting instructions (units, precision, format).
   - Evidence is incomplete, ambiguous, or inconclusive (do NOT guess or speculate; default to KEEP).
2. REVISE:
   - There is a specific, clearly identifiable error in the candidate answer (e.g., calculation mistake, incorrect entity, wrong units, formatting non-compliance).
   - The provided evidence directly and unambiguously supports a specific corrected answer.

OUTPUT FORMAT:
If the candidate answer is accepted:
VERDICT: KEEP

If the candidate answer must be revised:
VERDICT: REVISE
FINAL: <corrected answer>

STRICT RULES:
- Output ONLY the lines specified in the contract.
- Do NOT include explanations, reasoning, or chain-of-thought commentary.
- Do NOT output Python code or markdown code blocks.
- Do NOT request or attempt to invoke tools or web search.
- Do NOT perform speculative recovery if evidence is insufficient; always default to KEEP.
- Native function calling is disabled."""


@dataclass
class VerifierParseResult:
    """Structured result of deterministic verifier output parsing."""
    verdict: str  # "KEEP", "REVISE", or "INVALID"
    revised_answer: Optional[str] = None
    error_type: Optional[str] = None
    is_valid: bool = False


def build_verifier_prompt(
    question: str,
    candidate_answer: str,
    web_evidence: str = "",
    file_evidence: str = "",
    attachment_filename: str = "",
) -> str:
    """Constructs the prompt for the post-answer verifier Gemini generation (Generation #3).

    INFORMATION FIREWALL:
    The verifier receives ONLY:
    - Original question
    - Candidate answer
    - Already-retrieved web evidence
    - Already-processed file evidence
    - Attachment filename (if present)

    The verifier must NOT receive:
    - Benchmark ground truth
    - Scorer results
    - Raw router response or hidden reasoning
    - Raw worker response or hidden reasoning
    - Generated Python code
    - Python stdout / stderr
    """
    sections = [ANSWER_VERIFIER_SYSTEM_PROMPT.strip()]

    if web_evidence and web_evidence.strip():
        sections.append(f"WEB SEARCH EVIDENCE:\n{web_evidence.strip()}")

    if file_evidence and file_evidence.strip():
        sections.append(f"ATTACHMENT EVIDENCE:\n{file_evidence.strip()}")

    if attachment_filename and attachment_filename.strip():
        sections.append(
            f"ATTACHMENT FILE:\nFilename: {attachment_filename.strip()}"
        )

    sections.append(f"QUESTION:\n{question.strip()}")
    sections.append(f"CANDIDATE ANSWER:\n{candidate_answer.strip()}")

    return "\n\n".join(sections)


def parse_verifier_result(raw_text: Optional[str]) -> VerifierParseResult:
    """Deterministically parses the verifier raw response.

    Returns a structured VerifierParseResult:
    - KEEP: Unambiguous 'VERDICT: KEEP' without conflicting REVISE or invalid markers.
    - REVISE: Unambiguous 'VERDICT: REVISE' and exactly one valid non-empty 'FINAL: <answer>'.
    - INVALID: Missing, ambiguous, or malformed verdict, or REVISE missing non-empty FINAL.
    """
    if raw_text is None or not str(raw_text).strip():
        return VerifierParseResult(
            verdict="INVALID",
            error_type="empty_verifier_response",
            is_valid=False,
        )

    text = str(raw_text).strip()

    # Find all VERDICT lines
    verdict_pattern = r"^\s*VERDICT\s*:\s*([A-Za-z]+)\b"
    matches = re.findall(verdict_pattern, text, flags=re.MULTILINE | re.IGNORECASE)

    if not matches:
        # Check inline VERDICT
        inline_matches = re.findall(r"\bVERDICT\s*:\s*([A-Za-z]+)\b", text, flags=re.IGNORECASE)
        if inline_matches:
            matches = inline_matches

    if not matches:
        if "verdict" in text.lower():
            if "keep" in text.lower() and "revise" in text.lower():
                return VerifierParseResult(
                    verdict="INVALID",
                    error_type="ambiguous_verdict",
                    is_valid=False,
                )
            return VerifierParseResult(
                verdict="INVALID",
                error_type="malformed_verifier_text",
                is_valid=False,
            )
        return VerifierParseResult(
            verdict="INVALID",
            error_type="missing_verdict",
            is_valid=False,
        )

    norm_verdicts = [m.upper() for m in matches]
    unique_verdicts = set(norm_verdicts)

    # Check for ambiguous or conflicting verdicts
    if ("KEEP" in unique_verdicts and "REVISE" in unique_verdicts) or len(unique_verdicts) > 1:
        return VerifierParseResult(
            verdict="INVALID",
            error_type="ambiguous_verdict",
            is_valid=False,
        )

    chosen_verdict = norm_verdicts[0]

    # Also check if text mentions conflicting keywords in a verdict-like manner
    has_keep_kw = bool(re.search(r"\bVERDICT\s*:\s*KEEP\b", text, flags=re.IGNORECASE))
    has_revise_kw = bool(re.search(r"\bVERDICT\s*:\s*REVISE\b", text, flags=re.IGNORECASE))
    if has_keep_kw and has_revise_kw:
        return VerifierParseResult(
            verdict="INVALID",
            error_type="ambiguous_verdict",
            is_valid=False,
        )

    if chosen_verdict == "KEEP":
        return VerifierParseResult(
            verdict="KEEP",
            revised_answer=None,
            error_type=None,
            is_valid=True,
        )

    if chosen_verdict == "REVISE":
        # Split on FINAL marker (multiline line-start preferred, inline fallback)
        parts = re.split(r"(?:^|\n)\s*FINAL\s*:\s*", text, flags=re.IGNORECASE)
        if len(parts) == 1:
            parts = re.split(r"\bFINAL\s*:\s*", text, flags=re.IGNORECASE)

        if len(parts) == 1:
            return VerifierParseResult(
                verdict="INVALID",
                error_type="revise_missing_final",
                is_valid=False,
            )

        raw_candidates = parts[1:]
        cleaned_candidates = [c.strip() for c in raw_candidates if c.strip()]

        if not cleaned_candidates:
            return VerifierParseResult(
                verdict="INVALID",
                error_type="revise_empty_final",
                is_valid=False,
            )

        if len(set(cleaned_candidates)) > 1:
            return VerifierParseResult(
                verdict="INVALID",
                error_type="ambiguous_verdict",
                is_valid=False,
            )

        return VerifierParseResult(
            verdict="REVISE",
            revised_answer=cleaned_candidates[0],
            error_type=None,
            is_valid=True,
        )

    # Verdict was something other than KEEP or REVISE (e.g. MAYBE, UNKNOWN)
    return VerifierParseResult(
        verdict="INVALID",
        error_type="malformed_verifier_text",
        is_valid=False,
    )

