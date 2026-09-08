import os
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from agent import GAIAAgent, GAIAWebAgent, GAIAFileAgent, GAIAPythonAgent, LLMClient
from prompts.baseline import PROMPT_VERSION
from evaluation.experiment_logger import get_git_metadata


def resolve_attachment_path(
    file_path: Optional[str] = None,
    file_name: Optional[str] = None,
    repo_root: Optional[str] = None,
) -> Optional[str]:
    """Deterministically resolves local GAIA task attachment path with explicit precedence.

    Precedence:
    1. If file_path is absolute and exists, use it.
    2. If file_path exists relative to the current/repository context, use it.
    3. Try: <repo_root>/data/gaia/<file_path>
    4. Try: <repo_root>/data/gaia/2023/validation/<clean_file_name>
    5. Try: <repo_root>/data/gaia/<clean_file_name>
    6. If none exist on disk, leave as None to trigger existing safe file fallback (FileNotFoundError).
    """
    if repo_root is None:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    clean_fp = file_path.strip() if file_path and file_path.strip() else None
    clean_fn = file_name.strip() if file_name and file_name.strip() else None
    if not clean_fn and clean_fp:
        clean_fn = os.path.basename(clean_fp)

    # 1. If file_path is absolute and exists, use it.
    if clean_fp and os.path.isabs(clean_fp) and os.path.isfile(clean_fp):
        return os.path.abspath(clean_fp)

    # 2. If file_path exists relative to the current/repository context, use it.
    if clean_fp:
        if not os.path.isabs(clean_fp) and os.path.isfile(clean_fp):
            return os.path.abspath(clean_fp)
        rel_fp = clean_fp.lstrip("/\\") if not (len(clean_fp) > 1 and clean_fp[1] == ":") else clean_fp
        repo_rel = os.path.join(repo_root, rel_fp)
        if os.path.isfile(repo_rel):
            return os.path.abspath(repo_rel)

    # 3. Try: <repo_root>/data/gaia/<file_path>
    if clean_fp:
        rel_fp = clean_fp.lstrip("/\\") if not (len(clean_fp) > 1 and clean_fp[1] == ":") else clean_fp
        gaia_fp = os.path.join(repo_root, "data", "gaia", rel_fp)
        if os.path.isfile(gaia_fp):
            return os.path.abspath(gaia_fp)

    # 4. Try: <repo_root>/data/gaia/2023/validation/<clean_file_name>
    if clean_fn:
        val_path = os.path.join(repo_root, "data", "gaia", "2023", "validation", clean_fn)
        if os.path.isfile(val_path):
            return os.path.abspath(val_path)

    # 5. Try: <repo_root>/data/gaia/<clean_file_name>
    if clean_fn:
        root_data_path = os.path.join(repo_root, "data", "gaia", clean_fn)
        if os.path.isfile(root_data_path):
            return os.path.abspath(root_data_path)

    # 6. If none exist on disk, leave as None to trigger existing safe file fallback (FileNotFoundError).
    return None


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
        if project_version == "v3":
            agent = GAIAPythonAgent(llm_client=llm)
        elif project_version == "v2":
            agent = GAIAFileAgent(llm_client=llm)
        elif project_version == "v1":
            agent = GAIAWebAgent(llm_client=llm)
        else:
            agent = GAIAAgent(llm_client=llm)

    if isinstance(agent, GAIAPythonAgent) and project_version in ("v0", "v1", "v2"):
        project_version = "v3"
    elif isinstance(agent, GAIAFileAgent) and project_version in ("v0", "v1"):
        project_version = "v2"
    elif isinstance(agent, GAIAWebAgent) and project_version == "v0":
        project_version = "v1"

    clean_file_name = file_name.strip() if file_name and file_name.strip() else None
    clean_file_path = file_path.strip() if file_path and file_path.strip() else None
    if not clean_file_name and clean_file_path:
        clean_file_name = os.path.basename(clean_file_path)
    has_attachment = bool(clean_file_name)

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    resolved_file_path = resolve_attachment_path(
        file_path=clean_file_path,
        file_name=clean_file_name,
        repo_root=repo_root,
    )

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
    response_part_types = []
    response_part_count = 0
    has_text_part = False
    has_function_call_part = False

    result = None
    request_success = False
    completion_success = False
    error_type = None
    error_message = None

    start_time = time.time()
    try:
        if isinstance(agent, (GAIAFileAgent, GAIAPythonAgent)):
            target_path = resolved_file_path or clean_file_path or clean_file_name
            result = agent.run(question, file_path=target_path)
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
            response_part_types = getattr(llm_resp, "response_part_types", []) or []
            response_part_count = getattr(llm_resp, "response_part_count", 0)
            has_text_part = getattr(llm_resp, "has_text_part", False)
            has_function_call_part = getattr(llm_resp, "has_function_call_part", False)

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
    file_enabled = (project_version == "v2") or isinstance(agent, GAIAFileAgent)
    if result is None:
        if file_enabled:
            prompt_ver = "file-search-v1" if has_attachment else "web-search-v1"
        elif isinstance(agent, GAIAWebAgent) or project_version == "v1":
            prompt_ver = "web-search-v1"
        else:
            prompt_ver = "baseline-v1"

    primary_prompt_ver = getattr(result, "primary_prompt_version", None) if result else None
    fallback_prompt_ver = getattr(result, "fallback_prompt_version", None) if result else None

    if primary_prompt_ver is None:
        if file_enabled:
            primary_prompt_ver = "file-search-v1" if has_attachment else "web-search-v1"
        elif isinstance(agent, GAIAWebAgent) or project_version == "v1":
            primary_prompt_ver = "web-search-v1"
        else:
            primary_prompt_ver = prompt_ver or "baseline-v1"

    if fallback_prompt_ver is None:
        if file_enabled:
            fallback_prompt_ver = "web-search-v1" if has_attachment else "baseline-v1"
        elif isinstance(agent, GAIAWebAgent) or project_version == "v1":
            fallback_prompt_ver = "baseline-v1"
        else:
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

    # Python execution metadata (V3)
    py_result = getattr(result, "python_result", None) if result else None
    python_requested = getattr(result, "python_requested", False) if result else False
    python_executed = getattr(result, "python_executed", False) if result else False
    python_fallback = getattr(result, "python_fallback", False) if result else False
    python_execution_count = 1 if python_executed else 0
    assert python_execution_count in (0, 1), f"Execution count {python_execution_count} not in {0, 1}"
    llm_generation_count = getattr(result, "llm_generation_count", 1) if result else 1
    assert llm_generation_count == 1, f"LLM generation count {llm_generation_count} != 1"
    python_prompt_version = getattr(result, "python_prompt_version", None) if result else None

    if py_result is not None:
        python_success = py_result.success
        python_timeout = py_result.timed_out
        python_exit_code = py_result.exit_code
        python_error_type = py_result.error_type
        python_latency_seconds = py_result.latency_seconds
        python_stdout_length = py_result.stdout_length
        python_stderr_length = py_result.stderr_length
        python_output_truncated = py_result.output_truncated
    else:
        python_success = False
        python_timeout = False
        python_exit_code = None
        python_error_type = None
        python_latency_seconds = None
        python_stdout_length = 0
        python_stderr_length = 0
        python_output_truncated = False

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

        # LLM candidate part diagnostics
        "response_part_types": response_part_types,
        "response_part_count": response_part_count,
        "has_text_part": has_text_part,
        "has_function_call_part": has_function_call_part,

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

        # Python execution metadata (V3)
        "python_prompt_version": python_prompt_version,
        "python_requested": python_requested,
        "python_executed": python_executed,
        "python_success": python_success,
        "python_execution_count": python_execution_count,
        "python_timeout": python_timeout,
        "python_exit_code": python_exit_code,
        "python_error_type": python_error_type,
        "python_latency_seconds": python_latency_seconds,
        "python_stdout_length": python_stdout_length,
        "python_stderr_length": python_stderr_length,
        "python_output_truncated": python_output_truncated,
        "python_fallback": python_fallback,
        "llm_generation_count": llm_generation_count,
    }

