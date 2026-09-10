"""Router and worker prompt definitions for V4 explicit capability routing."""

ROUTER_PROMPT_VERSION = "capability-router-v1"
ROUTER_DIRECT_WORKER_PROMPT_VERSION = "router-direct-worker-v1"
ROUTER_PYTHON_WORKER_PROMPT_VERSION = "router-python-worker-v1"

CAPABILITY_ROUTER_SYSTEM_PROMPT = """You are a capability router for a GAIA benchmark solver.

Your role is to determine whether answering the user's question requires executing Python code (for numerical calculation, data manipulation, simulation, or structured parsing) or can be answered directly using web/file evidence and direct reasoning without running code.

You have access to two execution routes:
1. ROUTE: DIRECT - Use when the question can be answered directly from the provided evidence, common knowledge, or descriptive text without running Python code.
2. ROUTE: PYTHON - Use when answering the question requires running Python code (e.g. mathematical calculation, processing data files, sorting/filtering tables, simulating processes, or parsing formats).

OUTPUT FORMAT:
You MUST respond with EXACTLY ONE line containing either:
ROUTE: DIRECT
or
ROUTE: PYTHON

RULES:
- Do NOT provide reasoning, explanations, or step-by-step thinking.
- Do NOT provide candidate answers or preliminary calculations.
- Do NOT output Python code, pseudo-code, or library suggestions.
- Output ONLY the route line."""

ROUTER_DIRECT_WORKER_SYSTEM_PROMPT = """You are solving a GAIA benchmark task using direct question-answering and evidence synthesis.

You do NOT have access to a code execution environment.

You must provide a direct, concise final answer derived from the question and provided evidence.

OUTPUT FORMAT:
Return your answer on a single line starting with:
FINAL: <answer>

RULES:
- Do NOT output Python code or ```python ... ``` code blocks.
- Do NOT suggest or ask the user to run code.
- Follow the requested answer formatting exactly (e.g. units, rounding, comma-separated lists).
- If the question asks for a number, output just the number without words unless units are specifically requested.
- Keep your output minimal and end with "FINAL: <answer>"."""

ROUTER_PYTHON_WORKER_SYSTEM_PROMPT = """You are solving a GAIA benchmark task using Python code execution.

Generate a single, self-contained Python script to compute the exact answer deterministically.

Execution environment details:
- The Python script runs locally in an isolated working directory with a strict 15-second timeout.
- Network access, subprocess creation, and dangerous system calls are strictly blocked.
- If an attachment is provided, it is located in your current working directory.
- Execution is strictly SINGLE-SHOT: there is NO retry, NO interactive debugger, and NO multi-turn code repair.

OUTPUT FORMAT:
Output ONLY a single ```python ... ``` code block.
The script MUST print the final answer to standard output on its own line in this exact format:
print(f"FINAL_ANSWER: {result}")

RULES:
- Output ONLY the ```python ... ``` code block. Do NOT include explanatory text outside the code block.
- The script must be completely self-contained and run without external user input.
- Make sure to print the exact answer using the "FINAL_ANSWER: <answer>" format.
- Ensure all calculations, rounding, and formatting requested by the question are handled in your Python script before printing."""


def build_router_prompt(
    question: str,
    web_evidence: str = "",
    file_evidence: str = "",
    attachment_filename: str = "",
) -> str:
    """Constructs the prompt for the router Gemini generation (Generation #1)."""
    sections = [CAPABILITY_ROUTER_SYSTEM_PROMPT.strip()]

    if web_evidence and web_evidence.strip():
        sections.append(f"WEB SEARCH EVIDENCE:\n{web_evidence.strip()}")

    if file_evidence and file_evidence.strip():
        sections.append(f"ATTACHMENT EVIDENCE:\n{file_evidence.strip()}")

    if attachment_filename and attachment_filename.strip():
        sections.append(
            f"ATTACHMENT FILE:\nFilename: {attachment_filename.strip()} (accessible in current working directory)"
        )

    sections.append(f"QUESTION:\n{question.strip()}")

    return "\n\n".join(sections)


def build_direct_worker_prompt(
    question: str,
    web_evidence: str = "",
    file_evidence: str = "",
    attachment_filename: str = "",
) -> str:
    """Constructs the prompt for the DIRECT worker Gemini generation (Generation #2)."""
    sections = [ROUTER_DIRECT_WORKER_SYSTEM_PROMPT.strip()]

    if web_evidence and web_evidence.strip():
        sections.append(f"WEB SEARCH EVIDENCE:\n{web_evidence.strip()}")

    if file_evidence and file_evidence.strip():
        sections.append(f"ATTACHMENT EVIDENCE:\n{file_evidence.strip()}")

    if attachment_filename and attachment_filename.strip():
        sections.append(
            f"ATTACHMENT FILE:\nFilename: {attachment_filename.strip()} (accessible in current working directory)"
        )

    sections.append(f"QUESTION:\n{question.strip()}")

    return "\n\n".join(sections)


def build_python_worker_prompt(
    question: str,
    web_evidence: str = "",
    file_evidence: str = "",
    attachment_filename: str = "",
) -> str:
    """Constructs the prompt for the PYTHON worker Gemini generation (Generation #2)."""
    sections = [ROUTER_PYTHON_WORKER_SYSTEM_PROMPT.strip()]

    if web_evidence and web_evidence.strip():
        sections.append(f"WEB SEARCH EVIDENCE:\n{web_evidence.strip()}")

    if file_evidence and file_evidence.strip():
        sections.append(f"ATTACHMENT EVIDENCE:\n{file_evidence.strip()}")

    if attachment_filename and attachment_filename.strip():
        sections.append(
            f"ATTACHMENT FILE:\nFilename: {attachment_filename.strip()} (accessible in current working directory)"
        )

    sections.append(f"QUESTION:\n{question.strip()}")

    return "\n\n".join(sections)

