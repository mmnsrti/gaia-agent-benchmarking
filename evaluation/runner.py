import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from agent import GAIAAgent, GAIAWebAgent, LLMClient
from prompts.baseline import PROMPT_VERSION
from evaluation.experiment_logger import get_git_metadata


def execute_task(
    task_id: str,
    question: str,
    level: int = 1,
    file_name: Optional[str] = None,
    agent: Optional[GAIAAgent] = None,
    llm: Optional[LLMClient] = None,
    project_version: str = "v0",
    schema_version: int = 2,
) -> Dict[str, Any]:
    """Executes a single GAIA task using the agent and captures complete evaluation metadata.

    Shared by run_one.py, run_level.py, and automated evaluation pipelines.
    Never submits results to Hugging Face scoring endpoints.
    """
    if llm is None:
        llm = LLMClient()
    if agent is None:
        if project_version == "v1":
            agent = GAIAWebAgent(llm_client=llm)
        else:
            agent = GAIAAgent(llm_client=llm)

    if isinstance(agent, GAIAWebAgent) and project_version == "v0":
        project_version = "v1"

    clean_file_name = file_name.strip() if file_name and file_name.strip() else None
    has_attachment = bool(clean_file_name)

    run_id = str(uuid.uuid4())
    git_meta = get_git_metadata()

    prompt = None
    prompt_ver = getattr(agent, "prompt_version", PROMPT_VERSION)

    raw_response = None
    normalized_response = None
    final_answer = None
    finish_reason = None
    input_tokens = None
    output_tokens = None
    thinking_tokens = None
    total_tokens = None
    response_id = None
    model_version = None

    result = None
    request_success = False
    completion_success = False
    error_type = None
    error_message = None

    start_time = time.time()
    try:
        result = agent.run(question)
        request_success = True
        raw_response = result.raw_response
        normalized_response = getattr(result, "normalized_response", raw_response.strip() if raw_response else "")
        final_answer = result.final_answer
        prompt = result.prompt
        prompt_ver = result.prompt_version

        if result.llm_response:
            llm_resp = result.llm_response
            finish_reason = llm_resp.finish_reason
            input_tokens = llm_resp.input_tokens
            output_tokens = llm_resp.output_tokens
            thinking_tokens = llm_resp.thinking_tokens
            total_tokens = llm_resp.total_tokens
            response_id = llm_resp.response_id
            model_version = llm_resp.model_version

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
        if prompt is None and hasattr(agent, "build_prompt"):
            try:
                prompt = agent.build_prompt(question)
            except Exception:
                prompt = None

    latency = round(time.time() - start_time, 2)

    # Web search metadata extraction
    search_result = getattr(result, "search_result", None) if result else None
    search_fallback = getattr(result, "search_fallback", False) if result else False

    if search_result is not None:
        search_enabled = True
        search_provider = search_result.provider
        search_query = search_result.query
        search_call_count = search_result.call_count
        search_success = search_result.success
        search_latency_seconds = search_result.latency_seconds
        search_result_count = len(search_result.results)
        search_error_type = search_result.error_type
        search_error_message = search_result.error_message
        search_results_data = [item.to_dict() for item in search_result.results]
    elif isinstance(agent, GAIAWebAgent):
        search_enabled = True
        search_provider = "tavily"
        search_query = question
        search_call_count = 1
        search_success = False
        search_latency_seconds = None
        search_result_count = 0
        search_error_type = error_type
        search_error_message = error_message
        search_results_data = []
    else:
        search_enabled = False
        search_provider = None
        search_query = None
        search_call_count = 0
        search_success = False
        search_latency_seconds = None
        search_result_count = 0
        search_error_type = None
        search_error_message = None
        search_results_data = []

    return {
        "schema_version": schema_version,
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),

        "project_version": project_version,
        "git_commit": git_meta.get("git_commit"),
        "git_branch": git_meta.get("git_branch"),
        "git_dirty": git_meta.get("git_dirty"),

        "task_id": task_id,
        "level": level,
        "question": question,
        "attachment_required": has_attachment,
        "file_name": clean_file_name,

        "model": llm.model,
        "temperature": llm.temperature,
        "max_output_tokens": llm.max_output_tokens,
        "thinking_level": llm.thinking_level,

        "prompt_version": prompt_ver,
        "prompt": prompt,

        "raw_response": raw_response,
        "normalized_response": normalized_response,
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

        # Search metadata (V1)
        "search_enabled": search_enabled,
        "search_provider": search_provider,
        "search_query": search_query,
        "search_call_count": search_call_count,
        "search_success": search_success,
        "search_latency_seconds": search_latency_seconds,
        "search_result_count": search_result_count,
        "search_error_type": search_error_type,
        "search_error_message": search_error_message,
        "search_fallback": search_fallback,
        "search_results": search_results_data,
    }

