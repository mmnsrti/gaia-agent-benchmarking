PROMPT_VERSION = "baseline-v1"

BASELINE_SYSTEM_PROMPT = """Answer the following question accurately.

Return only the final answer.
Do not include explanations unless explicitly requested.
Follow the requested output format exactly.
"""


def build_baseline_prompt(question: str) -> str:
    """Constructs the baseline prompt for a given question without extra tools."""
    return f"""{BASELINE_SYSTEM_PROMPT.strip()}

Question:
{question.strip()}"""
