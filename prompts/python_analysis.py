"""Python analysis/code-generation prompt definition for V3 single-shot Python execution."""

PYTHON_ANALYSIS_PROMPT_VERSION = "python-analysis-v1"

PYTHON_ANALYSIS_SYSTEM_PROMPT = """You are analyzing a GAIA benchmark task to determine if writing and executing a short Python script is needed to calculate or verify the answer.

Consider:
- Mathematical calculations, multi-step arithmetic, unit conversions
- Data aggregation, tabular data filtering (CSV, XLSX, etc.)
- String manipulation, parsing, or counting
- Simulation, combinatorial search, or algorithmic problem solving

If Python computation is helpful:
Write a single, self-contained Python script enclosed in a ```python ... ``` block.
The script should perform the necessary calculation and print the final result using print().
If a task file attachment is present, it is located in the current working directory.
Do not use network access, subprocesses, or external shell commands.

If NO Python execution is needed (e.g., pure factual question directly answered in the evidence, visual question, or simple direct lookup):
Respond with:
NO_CODE"""


def build_python_analysis_prompt(
    question: str,
    web_evidence: str = "",
    file_evidence: str = "",
) -> str:
    """Constructs the V3 prompt requesting Python code generation or NO_CODE."""
    sections = [PYTHON_ANALYSIS_SYSTEM_PROMPT.strip()]

    if web_evidence and web_evidence.strip():
        sections.append(f"WEB SEARCH EVIDENCE:\n{web_evidence.strip()}")

    if file_evidence and file_evidence.strip():
        sections.append(f"ATTACHMENT EVIDENCE:\n{file_evidence.strip()}")

    sections.append(f"QUESTION:\n{question.strip()}")

    return "\n\n".join(sections)
