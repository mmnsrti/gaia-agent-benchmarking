import argparse
import os
import sys

# Add repository root to python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from evaluation.gaia_client import GAIAClient
from evaluation.experiment_logger import ExperimentLogger
from evaluation.runner import execute_task


def run_one(index: int = 0, task_id: str = None, log: bool = True, version: str = "v1") -> dict:
    """Fetches and runs the agent baseline on a single GAIA question without submitting."""
    client = GAIAClient()
    questions = client.get_questions()

    if not questions:
        print("Error: No questions received from evaluation API.")
        return {}

    target = None
    if task_id:
        for q in questions:
            if q.get("task_id") == task_id:
                target = q
                break
        if not target:
            print(f"Error: task_id '{task_id}' not found in fetched questions.")
            return {}
    else:
        if index < 0 or index >= len(questions):
            print(f"Error: index {index} is out of bounds (total questions: {len(questions)}).")
            return {}
        target = questions[index]

    q_task_id = target.get("task_id", "")
    question = target.get("question", "")
    file_name = target.get("file_name") or None
    raw_level = target.get("Level") or target.get("level") or 1
    try:
        level = int(raw_level)
    except (ValueError, TypeError):
        level = 1

    has_attachment = bool(file_name and str(file_name).strip())

    print("=" * 80)
    print(f"Task ID: {q_task_id}")
    print(f"Level: {level}")
    print(f"Question: {question}")
    print(f"Attachment: {'yes' if has_attachment else 'no'}")
    if has_attachment:
        print(f"File Name: {file_name}")
        if version in ("v0", "v1"):
            print(f"Note: {version} baseline intentionally does NOT process file attachments.")
        elif version == "v2":
            print("Note: v2 processes local file attachments.")
        elif version == "v3":
            print("Note: v3 processes local file attachments and supports controlled Python execution.")
        elif version == "v4":
            print("Note: v4 evaluates question and attachments using explicit capability routing (DIRECT vs PYTHON).")
    print("-" * 80)

    record = execute_task(
        task_id=q_task_id,
        question=question,
        level=level,
        file_name=file_name,
        project_version=version,
    )

    print(f"Run ID: {record['run_id']}")
    print(f"Project Version: {record['project_version']}")
    print(f"Model: {record['model']}")
    print(f"Temperature: {record['temperature']}")
    print(f"Max Output Tokens: {record['max_output_tokens']}")
    print(f"Thinking Level: {record['thinking_level']}")
    print(f"Prompt Version: {record['prompt_version']}")
    if record.get("primary_prompt_version"):
        print(f"Primary Prompt Version: {record['primary_prompt_version']}")
    if record.get("fallback_prompt_version"):
        print(f"Fallback Prompt Version: {record['fallback_prompt_version']}")
    if record.get("router_requested"):
        print(f"Router Decision: {record.get('router_decision')}")
        print(f"Router Success: {record.get('router_success')}")
        print(f"Router Fallback: {record.get('router_fallback')}")
        if record.get("router_error_type"):
            print(f"Router Error: {record.get('router_error_type')}")
        print(f"Router Latency: {record.get('router_latency_seconds')}s")
        print(f"Worker Mode: {record.get('worker_mode')}")
        print(f"Worker Success: {record.get('worker_success')}")
        if record.get("worker_error_type"):
            print(f"Worker Error: {record.get('worker_error_type')}")
        print(f"Worker Latency: {record.get('worker_latency_seconds')}s")
        print(f"LLM Generation Attempts: {record.get('llm_generation_attempts')}")
    if record.get("search_enabled"):
        print(f"Search Provider: {record['search_provider']}")
        print(f"Search Success: {record['search_success']}")
        print(f"Search Result Count: {record['search_result_count']}")
        print(f"Search Fallback: {record['search_fallback']}")
        if record.get("search_query_truncated"):
            print(f"Search Query Truncated: True (orig={record.get('original_query_length')}, provider={record.get('provider_query_length')})")
        if record.get("search_error_message"):
            print(f"Search Error: [{record['search_error_type']}] {record['search_error_message']}")
    if record.get("file_enabled") and record.get("attachment_required"):
        print(f"File Present: {record.get('file_present')}")
        print(f"File Processing Success: {record.get('file_processing_success')}")
        print(f"File Processor: {record.get('file_processor')}")
        print(f"File Content Mode: {record.get('file_content_mode')}")
        print(f"File Fallback: {record.get('file_fallback')}")
        if record.get("file_content_truncated"):
            print(f"File Content Truncated: True (orig={record.get('original_file_content_length')}, provided={record.get('provided_file_content_length')})")
        if record.get("file_error_message"):
            print(f"File Error: [{record['file_error_type']}] {record['file_error_message']}")
    if record.get("python_requested") or record.get("python_executed"):
        print(f"Python Requested: {record.get('python_requested')}")
        print(f"Python Executed: {record.get('python_executed')}")
        print(f"Python Execution Count: {record.get('python_execution_count')}")
        print(f"Python Success: {record.get('python_success')}")
        print(f"Python Fallback: {record.get('python_fallback')}")
        if record.get("python_exit_code") is not None:
            print(f"Python Exit Code: {record.get('python_exit_code')}")
        if record.get("python_error_type"):
            print(f"Python Error Type: {record.get('python_error_type')}")
    print(f"Request Success: {record['request_success']}")
    print(f"Completion Success: {record['completion_success']}")
    print(f"Finish Reason: {record['finish_reason']}")
    if record["request_success"]:
        print(f"Raw Response: {record['raw_response']}")
        print(f"Final Answer: {record['final_answer']}")
        print(f"Tokens: input={record['input_tokens']}, thinking={record['thinking_tokens']}, output={record['output_tokens']}, total={record['total_tokens']}")
    else:
        print(f"Error: [{record['error_type']}] {record['error_message']}")
    print(f"Latency: {record['latency_seconds']} seconds")
    print("=" * 80)

    if log:
        logger = ExperimentLogger(version=version)
        log_path = logger.append(record)
        print(f"Experiment logged to: {log_path}")

    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run GAIA baseline on one question with completion-aware tracking.")
    parser.add_argument("-i", "--index", type=int, default=0, help="Question index to run (0 to 19, default: 0)")
    parser.add_argument("-t", "--task-id", type=str, default=None, help="Specific task ID to run")
    # Legacy CLI choices compatibility: choices=["v0", "v1", "v2", "v3"]
    parser.add_argument("--version", type=str, required=True, choices=["v0", "v1", "v2", "v3", "v4"], help="Agent version (v0: baseline, v1: web search, v2: file attachments, v3: controlled single-shot Python execution, v4: explicit capability routing; required)")
    parser.add_argument("--no-log", action="store_true", help="Do not write record to experiments/runs.jsonl")
    args = parser.parse_args()

    run_one(index=args.index, task_id=args.task_id, log=not args.no_log, version=args.version)

