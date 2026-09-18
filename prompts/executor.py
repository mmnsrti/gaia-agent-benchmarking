"""Plan-Guided Executor prompt definitions for V10."""

from typing import Any, List, Optional
from prompts.planner import PlanSpec

EXECUTOR_DIRECT_PROMPT_VERSION = "executor-direct-v1"
EXECUTOR_PYTHON_PROMPT_VERSION = "executor-python-v1"

EXECUTOR_DIRECT_SYSTEM_PROMPT = """You are a Plan-Guided Executor solving a GAIA benchmark task using direct question-answering and evidence synthesis.

You do NOT have access to a code execution environment.

You must follow the provided STRUCTURED PLAN to synthesize the evidence and determine the final answer.

OUTPUT FORMAT:
Return your answer on a single line starting with:
FINAL: <answer>

RULES:
- Do NOT output Python code or ```python ... ``` code blocks.
- Do NOT suggest or ask the user to run code.
- Follow the plan and requested answer formatting exactly (e.g. units, rounding, comma-separated lists).
- If the question asks for a number, output just the number without words unless units are specifically requested.
- Keep your output minimal and end with "FINAL: <answer>"."""

EXECUTOR_PYTHON_SYSTEM_PROMPT = """You are a Plan-Guided Executor solving a GAIA benchmark task using Python code execution.

Generate a single, self-contained Python script implementing the provided STRUCTURED PLAN to compute the exact answer deterministically.

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
- Implement the sequential steps outlined in the STRUCTURED PLAN.
- Output ONLY the ```python ... ``` code block. Do NOT include explanatory text outside the code block.
- The script must be completely self-contained and run without external user input.
- Make sure to print the exact answer using the "FINAL_ANSWER: <answer>" format.
- Ensure all calculations, rounding, and formatting specified in the plan are handled in your Python script before printing."""


def format_plan_block(plan_spec: Any) -> str:
    """Formats a PlanSpec or dict into the structured plan block for the executor."""
    if hasattr(plan_spec, "mode"):
        mode = plan_spec.mode
        objective = plan_spec.objective
        evidence_needed = plan_spec.evidence_needed
        plan_steps = plan_spec.plan_steps
        answer_type = plan_spec.answer_type
    elif isinstance(plan_spec, dict):
        mode = plan_spec.get("mode", "DIRECT")
        objective = plan_spec.get("objective", "")
        evidence_needed = plan_spec.get("evidence_needed", "")
        plan_steps = plan_spec.get("plan_steps", plan_spec.get("plan", []))
        answer_type = plan_spec.get("answer_type", "short text")
    else:
        return str(plan_spec)

    lines = [
        f"MODE: {mode}",
        f"OBJECTIVE: {objective}",
        f"EVIDENCE_NEEDED: {evidence_needed}",
        "PLAN:",
    ]
    for step in plan_steps:
        lines.append(f"{step}")
    lines.append(f"ANSWER_TYPE: {answer_type}")
    return "\n".join(lines)


def build_direct_executor_prompt(
    question: str,
    plan_spec: Any,
    web_evidence: str = "",
    file_evidence: str = "",
    attachment_filename: str = "",
) -> str:
    """Constructs the prompt for the DIRECT Plan-Guided Executor (Slot 2)."""
    sections = [EXECUTOR_DIRECT_SYSTEM_PROMPT.strip()]

    if web_evidence and web_evidence.strip():
        sections.append(f"WEB SEARCH EVIDENCE:\n{web_evidence.strip()}")

    if file_evidence and file_evidence.strip():
        sections.append(f"ATTACHMENT EVIDENCE:\n{file_evidence.strip()}")

    if attachment_filename and attachment_filename.strip():
        sections.append(
            f"ATTACHMENT FILE:\nFilename: {attachment_filename.strip()} (accessible in current working directory)"
        )

    sections.append(f"STRUCTURED PLAN:\n{format_plan_block(plan_spec).strip()}")
    sections.append(f"QUESTION:\n{question.strip()}")

    return "\n\n".join(sections)


def build_python_executor_prompt(
    question: str,
    plan_spec: Any,
    web_evidence: str = "",
    file_evidence: str = "",
    attachment_filename: str = "",
) -> str:
    """Constructs the prompt for the PYTHON Plan-Guided Executor (Slot 2)."""
    sections = [EXECUTOR_PYTHON_SYSTEM_PROMPT.strip()]

    if web_evidence and web_evidence.strip():
        sections.append(f"WEB SEARCH EVIDENCE:\n{web_evidence.strip()}")

    if file_evidence and file_evidence.strip():
        sections.append(f"ATTACHMENT EVIDENCE:\n{file_evidence.strip()}")

    if attachment_filename and attachment_filename.strip():
        sections.append(
            f"ATTACHMENT FILE:\nFilename: {attachment_filename.strip()} (accessible in current working directory)"
        )

    sections.append(f"STRUCTURED PLAN:\n{format_plan_block(plan_spec).strip()}")
    sections.append(f"QUESTION:\n{question.strip()}")

    return "\n\n".join(sections)

