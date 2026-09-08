"""File-and-web search prompt definition for V2 single-shot retrieval + attachment handling."""

FILE_SEARCH_PROMPT_VERSION = "file-search-v1"

FILE_SEARCH_SYSTEM_PROMPT = """You are solving a GAIA benchmark task.

Use the provided web-search evidence and, when available, the attached-file evidence.

Web evidence may be incomplete or irrelevant.
Attachment evidence may contain the information required to solve the task.

Do not invent information that is not supported.

Return only the final answer.
Do not include explanations, reasoning steps, citations, or URLs unless explicitly requested by the question.
Follow the requested output format exactly."""


def build_file_search_prompt(question: str, web_evidence: str, file_evidence: str) -> str:
    """Constructs the V2 file-and-web augmented prompt for Gemini."""
    return f"""{FILE_SEARCH_SYSTEM_PROMPT.strip()}

WEB SEARCH EVIDENCE:
{web_evidence.strip()}

ATTACHMENT EVIDENCE:
{file_evidence.strip()}

QUESTION:
{question.strip()}"""

