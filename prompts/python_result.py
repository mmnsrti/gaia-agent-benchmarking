"""Python result synthesis prompt definition for V3 final-answer synthesis."""

PYTHON_RESULT_PROMPT_VERSION = "python-result-v1"

PYTHON_RESULT_SYSTEM_PROMPT = """You are solving a GAIA benchmark task.

Use the provided web-search evidence, attachment evidence, and the output from the executed Python script to produce the final answer.

Do not invent information that is not supported.

Return only the final answer.
Do not include explanations, reasoning steps, citations, or URLs unless explicitly requested by the question.
Follow the requested output format exactly."""


def build_python_result_prompt(
    question: str,
    web_evidence: str = "",
    file_evidence: str = "",
    executed_code: str = "",
    execution_stdout: str = "",
    execution_stderr: str = "",
) -> str:
    """Constructs the V3 prompt synthesizing the final answer from evidence and Python output."""
    sections = [PYTHON_RESULT_SYSTEM_PROMPT.strip()]

    if web_evidence and web_evidence.strip():
        sections.append(f"WEB SEARCH EVIDENCE:\n{web_evidence.strip()}")

    if file_evidence and file_evidence.strip():
        sections.append(f"ATTACHMENT EVIDENCE:\n{file_evidence.strip()}")

    if executed_code and executed_code.strip():
        sections.append(f"EXECUTED PYTHON SCRIPT:\n```python\n{executed_code.strip()}\n```")

    py_out = execution_stdout.strip() if execution_stdout else ""
    if py_out:
        sections.append(f"PYTHON STDOUT:\n{py_out}")

    py_err = execution_stderr.strip() if execution_stderr else ""
    if py_err:
        sections.append(f"PYTHON STDERR:\n{py_err}")

    sections.append(f"QUESTION:\n{question.strip()}")

    return "\n\n".join(sections)
