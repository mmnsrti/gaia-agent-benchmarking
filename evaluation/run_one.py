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
        print(f"Note: {version} baseline intentionally does NOT process file attachments.")
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
    if record.get("search_enabled"):
        print(f"Search Provider: {record['search_provider']}")
        print(f"Search Success: {record['search_success']}")
        print(f"Search Result Count: {record['search_result_count']}")
        print(f"Search Fallback: {record['search_fallback']}")
        if record.get("search_query_truncated"):
            print(f"Search Query Truncated: True (orig={record.get('original_query_length')}, provider={record.get('provider_query_length')})")
        if record.get("search_error_message"):
            print(f"Search Error: [{record['search_error_type']}] {record['search_error_message']}")
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
    parser.add_argument("--version", type=str, required=True, choices=["v0", "v1"], help="Agent version (v0: baseline, v1: web search; required)")
    parser.add_argument("--no-log", action="store_true", help="Do not write record to experiments/runs.jsonl")
    args = parser.parse_args()

    run_one(index=args.index, task_id=args.task_id, log=not args.no_log, version=args.version)

