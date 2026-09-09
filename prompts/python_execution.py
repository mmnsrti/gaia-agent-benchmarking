"""Python execution prompt definition for V3 single-shot execution-aware generation."""

PYTHON_EXECUTION_PROMPT_VERSION = "python-execution-v1"

PYTHON_EXECUTION_SYSTEM_PROMPT = """You are solving a GAIA benchmark task.

You have access to a local Python execution environment to perform calculations, data analysis, or simulations if needed.

You must choose exactly ONE of the following two response formats:

FORMAT 1: Direct Answer (use when Python computation is NOT needed)
Return your answer on a single line starting with:
FINAL: <answer>

FORMAT 2: Python Code (use when Python computation IS needed)
Provide a single, self-contained Python script enclosed in a ```python ... ``` code block.
The script MUST print the final answer to stdout in this exact format:
print(f"FINAL_ANSWER: {result}")

RULES:
- Choose either Format 1 or Format 2. Do not mix them.
- If using Format 1, output only "FINAL: <answer>". Do not include explanations, reasoning steps, or citations.
- If using Format 2, output ONLY the ```python ... ``` code block. Do not include explanatory text outside the code block.
- Follow the requested answer formatting exactly (e.g. units, rounding, comma-separated lists).
- If an attachment is provided, it is placed directly in your current working directory.
- The Python environment runs with restricted access: network calls, subprocesses, and system command execution are forbidden."""


def build_python_execution_prompt(
    question: str,
    web_evidence: str = "",
    file_evidence: str = "",
    attachment_filename: str = "",
) -> str:
    """Constructs the single V3 execution-aware prompt for Gemini."""
    sections = [PYTHON_EXECUTION_SYSTEM_PROMPT.strip()]

    if web_evidence and web_evidence.strip():
        sections.append(f"WEB SEARCH EVIDENCE:\n{web_evidence.strip()}")

    if file_evidence and file_evidence.strip():
        sections.append(f"ATTACHMENT EVIDENCE:\n{file_evidence.strip()}")

    if attachment_filename and attachment_filename.strip():
        sections.append(f"ATTACHMENT FILE:\nFilename: {attachment_filename.strip()} (accessible in current working directory)")

    sections.append(f"QUESTION:\n{question.strip()}")

    return "\n\n".join(sections)
