import argparse
import os
import sys
import time
import uuid
from datetime import datetime, timezone

# Add repository root to python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent import GAIAAgent, LLMClient
from prompts.baseline import PROMPT_VERSION
from evaluation.gaia_client import GAIAClient
from evaluation.experiment_logger import ExperimentLogger, get_git_metadata


def run_one(index: int = 0, task_id: str = None, log: bool = True) -> dict:
    """Fetches and runs the v0 baseline on a single GAIA question without submitting."""
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
    if file_name and not file_name.strip():
        file_name = None
    has_attachment = bool(file_name)

    print("=" * 80)
    print(f"Task ID: {q_task_id}")
    print(f"Question: {question}")
    print(f"Attachment: {'yes' if has_attachment else 'no'}")
    if has_attachment:
        print(f"File Name: {file_name}")
        print("Note: v0 baseline intentionally does NOT process file attachments.")
    print("-" * 80)

    run_id = str(uuid.uuid4())
    git_meta = get_git_metadata()

    llm = LLMClient()
    agent = GAIAAgent(llm_client=llm)

    start_time = time.time()
    raw_response = None
    final_answer = None
    finish_reason = None
    input_tokens = None
    output_tokens = None
    thinking_tokens = None
    total_tokens = None
    response_id = None
    model_version = None

    request_success = False
    completion_success = False
    error_type = None
    error_message = None

    prompt = agent.build_prompt(question)

    try:
        result = agent.run(question)
        request_success = True
        raw_response = result.raw_response
        final_answer = result.final_answer

        if result.llm_response:
            llm_resp = result.llm_response
            finish_reason = llm_resp.finish_reason
            input_tokens = llm_resp.input_tokens
            output_tokens = llm_resp.output_tokens
            thinking_tokens = llm_resp.thinking_tokens
            total_tokens = llm_resp.total_tokens
            response_id = llm_resp.response_id
            model_version = llm_resp.model_version

            # Completion is only successful if model finished normally (STOP) and produced a non-empty response
            if finish_reason == "STOP" and raw_response is not None and raw_response.strip() != "":
                completion_success = True
            else:
                completion_success = False
        else:
            completion_success = False

    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)
        request_success = False
        completion_success = False
        print(f"Inference error ({error_type}): {error_message}")

    latency = round(time.time() - start_time, 2)

    print(f"Run ID: {run_id}")
    print(f"Project Version: v0")
    print(f"Model: {llm.model}")
    print(f"Temperature: {llm.temperature}")
    print(f"Max Output Tokens: {llm.max_output_tokens}")
    print(f"Thinking Level: {llm.thinking_level}")
    print(f"Prompt Version: {PROMPT_VERSION}")
    print(f"Request Success: {request_success}")
    print(f"Completion Success: {completion_success}")
    print(f"Finish Reason: {finish_reason}")
    if request_success:
        print(f"Raw Response: {raw_response}")
        print(f"Final Answer: {final_answer}")
        print(f"Tokens: input={input_tokens}, thinking={thinking_tokens}, output={output_tokens}, total={total_tokens}")
    else:
        print(f"Error: [{error_type}] {error_message}")
    print(f"Latency: {latency} seconds")
    print("=" * 80)

    record = {
        "schema_version": 2,
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),

        "project_version": "v0",
        "git_commit": git_meta.get("git_commit"),
        "git_branch": git_meta.get("git_branch"),
        "git_dirty": git_meta.get("git_dirty"),

        "task_id": q_task_id,
        "question": question,
        "attachment_required": has_attachment,
        "file_name": file_name,

        "model": llm.model,
        "temperature": llm.temperature,
        "max_output_tokens": llm.max_output_tokens,
        "thinking_level": llm.thinking_level,

        "prompt_version": PROMPT_VERSION,
        "prompt": prompt,

        "raw_response": raw_response,
        "final_answer": final_answer,

        "finish_reason": finish_reason,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "thinking_tokens": thinking_tokens,
        "total_tokens": total_tokens,
        "response_id": response_id,
        "model_version": model_version,

        "latency_seconds": latency,

        "request_success": request_success,
        "completion_success": completion_success,
        "error_type": error_type,
        "error_message": error_message,
    }

    if log:
        logger = ExperimentLogger(version="v0")
        log_path = logger.append(record)
        print(f"Experiment logged to: {log_path}")

    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run v0 tool-free GAIA baseline on one question with completion-aware tracking.")
    parser.add_argument("-i", "--index", type=int, default=0, help="Question index to run (0 to 19, default: 0)")
    parser.add_argument("-t", "--task-id", type=str, default=None, help="Specific task ID to run")
    parser.add_argument("--no-log", action="store_true", help="Do not write record to experiments/v0/runs.jsonl")
    args = parser.parse_args()

    run_one(index=args.index, task_id=args.task_id, log=not args.no_log)
