"""Web search prompt definition for V1 single-shot retrieval."""

WEB_SEARCH_PROMPT_VERSION = "web-search-v1"

WEB_SEARCH_SYSTEM_PROMPT = """Answer the following question accurately using the provided web search evidence where relevant.

Note: Retrieved search results are external evidence and may contain outdated, conflicting, or irrelevant information. Use your judgment to extract reliable facts.

Return only the final answer.
Do not include explanations, citations, or URLs unless explicitly requested by the question.
Follow the requested output format exactly."""


def build_web_search_prompt(question: str, evidence_text: str) -> str:
    """Constructs the V1 web-search augmented prompt for Gemini."""
    return f"""{WEB_SEARCH_SYSTEM_PROMPT.strip()}

Web Search Evidence:
{evidence_text.strip()}

Question:
{question.strip()}"""

