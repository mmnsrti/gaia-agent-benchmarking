import os
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from agent import GAIAAgent, GAIAWebAgent, GAIAFileAgent, LLMClient
from prompts.baseline import PROMPT_VERSION
from evaluation.experiment_logger import get_git_metadata


def execute_task(
    task_id: str,
    question: str,
    level: int = 1,
    file_name: Optional[str] = None,
    file_path: Optional[str] = None,
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
        if project_version == "v2":
            agent = GAIAFileAgent(llm_client=llm)
        elif project_version == "v1":
            agent = GAIAWebAgent(llm_client=llm)
        else:
            agent = GAIAAgent(llm_client=llm)

    if isinstance(agent, GAIAFileAgent) and project_version in ("v0", "v1"):
        project_version = "v2"
    elif isinstance(agent, GAIAWebAgent) and project_version == "v0":
        project_version = "v1"

    clean_file_name = file_name.strip() if file_name and file_name.strip() else None
    has_attachment = bool(clean_file_name)

    resolved_file_path = file_path
    if clean_file_name and not resolved_file_path:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        candidates = [
            os.path.join(repo_root, "data", "gaia", "2023", "validation", clean_file_name),
            os.path.join(repo_root, "data", "gaia", clean_file_name),
            clean_file_name,
        ]
        for c in candidates:
            if os.path.isfile(c):
                resolved_file_path = c
                break

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
        if isinstance(agent, GAIAFileAgent):
            result = agent.run(question, file_path=resolved_file_path)
        else:
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

    # Prompt provenance extraction
    primary_prompt_ver = getattr(result, "primary_prompt_version", None) if result else None
    fallback_prompt_ver = getattr(result, "fallback_prompt_version", None) if result else None
    if primary_prompt_ver is None:
        if isinstance(agent, GAIAFileAgent) or project_version == "v2":
            primary_prompt_ver = "file-search-v1" if has_attachment else "web-search-v1"
            fallback_prompt_ver = "web-search-v1" if has_attachment else "baseline-v1"
        elif isinstance(agent, GAIAWebAgent) or project_version == "v1":
            primary_prompt_ver = "web-search-v1"
            fallback_prompt_ver = "baseline-v1"
        else:
            primary_prompt_ver = prompt_ver or "baseline-v1"
            fallback_prompt_ver = None

    # Web search metadata extraction
    search_result = getattr(result, "search_result", None) if result else None
    search_fallback = getattr(result, "search_fallback", False) if result else False

    if search_result is not None:
        search_enabled = True
        search_provider = search_result.provider
        search_query = search_result.query
        search_query_truncated = search_result.search_query_truncated
        original_query_length = search_result.original_query_length
        provider_query_length = search_result.provider_query_length
        search_call_count = search_result.call_count
        search_success = search_result.success
        search_latency_seconds = search_result.latency_seconds
        search_result_count = len(search_result.results)
        search_error_type = search_result.error_type
        search_error_message = search_result.error_message
        search_results_data = [item.to_dict() for item in search_result.results]
    elif isinstance(agent, GAIAWebAgent):
        clean_q = question.strip() if question else ""
        search_enabled = True
        search_provider = "tavily"
        search_query = question
        search_query_truncated = len(clean_q) > 1500
        original_query_length = len(clean_q)
        provider_query_length = min(len(clean_q), 1500)
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
        search_query_truncated = False
        original_query_length = 0
        provider_query_length = 0
        search_call_count = 0
        search_success = False
        search_latency_seconds = None
        search_result_count = 0
        search_error_type = None
        search_error_message = None
        search_results_data = []

    # File attachment metadata extraction (V2)
    file_result = getattr(result, "file_result", None) if result else None
    file_fallback = getattr(result, "file_fallback", False) if result else False

    file_enabled = (project_version == "v2") or isinstance(agent, GAIAFileAgent)
    file_present = has_attachment and bool(resolved_file_path and os.path.exists(resolved_file_path))
    file_ext = os.path.splitext(clean_file_name)[1].lower() if clean_file_name else None

    if file_result is not None:
        file_processing_attempted = True
        file_processing_success = file_result.success
        file_processing_latency_seconds = file_result.latency_seconds
        file_processor = file_result.processor
        file_content_mode = file_result.content_mode
        file_content_truncated = file_result.content_truncated
        original_file_content_length = file_result.original_content_length
        provided_file_content_length = file_result.provided_content_length
        file_error_type = file_result.error_type
        file_error_message = file_result.error_message
    elif file_enabled and has_attachment:
        file_processing_attempted = True
        file_processing_success = False
        file_processing_latency_seconds = 0.0
        file_processor = None
        file_content_mode = None
        file_content_truncated = False
        original_file_content_length = 0
        provided_file_content_length = 0
        file_error_type = "FileNotFoundError" if not file_present else error_type
        file_error_message = f"File '{clean_file_name}' could not be located on disk" if not file_present else error_message
        file_fallback = True
    else:
        file_processing_attempted = False
        file_processing_success = False
        file_processing_latency_seconds = None
        file_processor = None
        file_content_mode = None
        file_content_truncated = False
        original_file_content_length = 0
        provided_file_content_length = 0
        file_error_type = None
        file_error_message = None
        file_fallback = False

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
        "primary_prompt_version": primary_prompt_ver,
        "fallback_prompt_version": fallback_prompt_ver,
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
        "search_query_truncated": search_query_truncated,
        "original_query_length": original_query_length,
        "provider_query_length": provider_query_length,
        "search_call_count": search_call_count,
        "search_success": search_success,
        "search_latency_seconds": search_latency_seconds,
        "search_result_count": search_result_count,
        "search_error_type": search_error_type,
        "search_error_message": search_error_message,
        "search_fallback": search_fallback,
        "search_results": search_results_data,

        # File attachment metadata (V2)
        "file_enabled": file_enabled,
        "file_present": file_present,
        "file_extension": file_ext,
        "file_processing_attempted": file_processing_attempted,
        "file_processing_success": file_processing_success,
        "file_processing_latency_seconds": file_processing_latency_seconds,
        "file_processor": file_processor,
        "file_content_mode": file_content_mode,
        "file_content_truncated": file_content_truncated,
        "original_file_content_length": original_file_content_length,
        "provided_file_content_length": provided_file_content_length,
        "file_error_type": file_error_type,
        "file_error_message": file_error_message,
        "file_fallback": file_fallback,
    }

