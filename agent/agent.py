import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional
from prompts.baseline import build_baseline_prompt, PROMPT_VERSION
from prompts.web_search import build_web_search_prompt, WEB_SEARCH_PROMPT_VERSION
from prompts.file_search import build_file_search_prompt, FILE_SEARCH_PROMPT_VERSION
from prompts.python_execution import build_python_execution_prompt, PYTHON_EXECUTION_PROMPT_VERSION
from prompts.router import (
    ROUTER_PROMPT_VERSION,
    ROUTER_DIRECT_WORKER_PROMPT_VERSION,
    ROUTER_PYTHON_WORKER_PROMPT_VERSION,
    build_router_prompt,
    build_direct_worker_prompt,
    build_python_worker_prompt,
)
from prompts.verification import (
    VERIFICATION_PROMPT_VERSION,
    build_verifier_prompt,
    parse_verifier_result,
    VerifierParseResult,
)
from prompts.self_evaluation import (
    SELF_EVALUATION_PROMPT_VERSION,
    build_execution_summary,
    build_self_evaluator_prompt,
    parse_self_evaluation_result,
)
from prompts.targeted_repair import (
    TARGETED_REPAIR_PROMPT_VERSION,
    build_targeted_repair_prompt,
    parse_targeted_repair_result,
)
from prompts.candidate_recovery import (
    CANDIDATE_RECOVERY_PROMPT_VERSION,
    build_candidate_recovery_prompt,
    parse_candidate_recovery_result,
    CandidateRecoveryParseResult,
)
from prompts.planner import (
    PLANNER_PROMPT_VERSION,
    PlanSpec,
    PlannerParseResult,
    build_planner_prompt,
    parse_planner_result,
    build_fallback_plan,
)
from prompts.executor import (
    EXECUTOR_DIRECT_PROMPT_VERSION,
    EXECUTOR_PYTHON_PROMPT_VERSION,
    build_direct_executor_prompt,
    build_python_executor_prompt,
)
from prompts.adaptive_planner import (
    ADAPTIVE_PLANNER_PROMPT_VERSION,
    AdaptivePlanSpec,
    AdaptivePlannerParseResult,
    build_adaptive_planner_prompt,
    parse_adaptive_planner_result,
    build_adaptive_fallback_plan,
    normalize_followup_query,
    canonical_execution_plan_payload,
    hash_canonical_execution_plan,
)
import hashlib
from tools.web_search import TavilySearchTool, WebSearchResult
from tools.file_tool import FileTool, FileResult
from tools.python_tool import PythonTool, PythonResult
from .llm import LLMResponse


@dataclass
class UpstreamContext:
    question: str
    file_path: Optional[str] = None
    web_evidence: str = ""
    file_evidence: str = ""
    attachment_filename: str = ""
    search_res: Optional[WebSearchResult] = None
    search_fallback: bool = False
    file_res: Optional[FileResult] = None
    file_fallback: bool = False
    attachment_parts: Optional[Any] = None



@dataclass
class AgentResult:
    """Encapsulates untouched model output, normalized text, and cleaned final answer."""
    raw_response: str           # Untouched model text directly from provider
    final_answer: str           # Cleaned final answer (whitespace + prefix stripped)
    normalized_response: str = "" # Moderately normalized model text (.strip())
    llm_response: Optional[LLMResponse] = None
    prompt: Optional[str] = None
    prompt_version: str = PROMPT_VERSION
    primary_prompt_version: Optional[str] = None
    fallback_prompt_version: Optional[str] = None
    search_result: Optional[WebSearchResult] = None
    search_fallback: bool = False
    file_result: Optional[FileResult] = None
    file_fallback: bool = False
    # Python execution metadata (V3)
    python_result: Optional[PythonResult] = None
    python_requested: bool = False
    python_executed: bool = False
    python_fallback: bool = False
    python_prompt_version: Optional[str] = None
    python_prompt: Optional[str] = None
    llm_generation_count: int = 1
    # Router & Worker metadata (V4)
    router_requested: bool = False
    router_decision: Optional[str] = None
    router_success: bool = False
    router_fallback: bool = False
    router_error_type: Optional[str] = None
    router_prompt_version: Optional[str] = None
    router_prompt: Optional[str] = None
    router_raw_response: Optional[str] = None
    router_latency_seconds: Optional[float] = None
    router_input_tokens: Optional[int] = None
    router_output_tokens: Optional[int] = None
    router_thinking_tokens: Optional[int] = None
    router_generation_attempts: int = 0
    router_generation_success: bool = False
    worker_mode: Optional[str] = None
    worker_success: bool = False
    worker_error_type: Optional[str] = None
    worker_prompt_version: Optional[str] = None
    worker_prompt: Optional[str] = None
    worker_raw_response: Optional[str] = None
    worker_latency_seconds: Optional[float] = None
    worker_input_tokens: Optional[int] = None
    worker_output_tokens: Optional[int] = None
    worker_thinking_tokens: Optional[int] = None
    worker_generation_attempts: int = 0
    worker_generation_success: bool = False
    llm_generation_attempts: int = 1
    llm_generation_success_count: int = 1
    candidate_answer: Optional[str] = None
    # Verifier metadata (V5)
    pre_verification_answer: Optional[str] = None
    post_verification_answer: Optional[str] = None
    verifier_eligible: bool = False
    verifier_attempted: bool = False
    verifier_generation_attempts: int = 0
    verifier_generation_success: bool = False
    verifier_finish_reason: Optional[str] = None
    verifier_error_type: Optional[str] = None
    verifier_verdict: Optional[str] = None
    verifier_revised: bool = False
    verifier_fallback: bool = False
    verifier_latency_seconds: Optional[float] = None
    verifier_input_tokens: Optional[int] = None
    verifier_output_tokens: Optional[int] = None
    verifier_thinking_tokens: Optional[int] = None
    verifier_total_tokens: Optional[int] = None
    verifier_prompt_version: Optional[str] = None
    verifier_prompt: Optional[str] = None
    verifier_raw_response: Optional[str] = None
    # Self-evaluation metadata (V6). Raw prompt/response are internal only and
    # are intentionally excluded from public evaluation serializers.
    pre_self_evaluation_answer: Optional[str] = None
    post_self_evaluation_answer: Optional[str] = None
    self_eval_eligible: bool = False
    self_eval_attempted: bool = False
    self_eval_success: bool = False
    self_eval_prompt_version: Optional[str] = None
    self_eval_assessment: Optional[str] = None
    self_eval_risk_type: Optional[str] = None
    self_eval_confidence: Optional[float] = None
    self_eval_error_type: Optional[str] = None
    self_eval_finish_reason: Optional[str] = None
    self_eval_generation_attempts: int = 0
    self_eval_generation_success: bool = False
    self_eval_latency_seconds: Optional[float] = None
    self_eval_input_tokens: Optional[int] = None
    self_eval_output_tokens: Optional[int] = None
    self_eval_thinking_tokens: Optional[int] = None
    self_eval_total_tokens: Optional[int] = None
    self_eval_answer_unchanged: bool = True
    self_eval_prompt: Optional[str] = None
    self_eval_raw_response: Optional[str] = None
    # Targeted repair metadata (V7). Raw prompt/response are internal only and
    # are intentionally excluded from public evaluation serializers.
    pre_repair_answer: Optional[str] = None
    post_repair_answer: Optional[str] = None
    repair_eligible: bool = False
    repair_triggered: bool = False
    repair_attempted: bool = False
    repair_success: bool = False
    repair_action: Optional[str] = None
    repair_answer_changed: bool = False
    repair_error_type: Optional[str] = None
    repair_finish_reason: Optional[str] = None
    repair_generation_attempts: int = 0
    repair_generation_success: bool = False
    repair_latency_seconds: Optional[float] = None
    repair_input_tokens: Optional[int] = None
    repair_output_tokens: Optional[int] = None
    repair_thinking_tokens: Optional[int] = None
    repair_total_tokens: Optional[int] = None
    repair_prompt_version: Optional[str] = None
    repair_prompt: Optional[str] = None
    repair_raw_response: Optional[str] = None
    # Candidate recovery metadata (V9). Raw prompt/response are internal only and
    # are intentionally excluded from public evaluation serializers.
    pre_recovery_candidate: Optional[str] = None
    post_recovery_candidate: Optional[str] = None
    candidate_recovery_eligible: bool = False
    candidate_recovery_triggered: bool = False
    candidate_recovery_failure_class: Optional[str] = None
    candidate_recovery_attempted: bool = False
    candidate_recovery_success: bool = False
    candidate_recovery_action: Optional[str] = None
    candidate_recovery_recovered: bool = False
    candidate_recovery_parse_success: bool = False
    candidate_recovery_candidate_changed: bool = False
    candidate_recovery_finish_reason: Optional[str] = None
    candidate_recovery_response_part_types: Optional[list[str]] = None
    candidate_recovery_has_text_part: bool = False
    candidate_recovery_has_function_call_part: bool = False
    candidate_recovery_error_type: Optional[str] = None
    candidate_recovery_error_message: Optional[str] = None
    candidate_recovery_generation_attempts: int = 0
    candidate_recovery_generation_success: bool = False
    candidate_recovery_logical_generation_count: int = 0
    candidate_recovery_latency_seconds: Optional[float] = None
    candidate_recovery_input_tokens: Optional[int] = None
    candidate_recovery_output_tokens: Optional[int] = None
    candidate_recovery_thinking_tokens: Optional[int] = None
    candidate_recovery_total_tokens: Optional[int] = None
    candidate_recovery_prompt_version: Optional[str] = None
    candidate_recovery_prompt: Optional[str] = None
    candidate_recovery_raw_response: Optional[str] = None
    candidate_recovery_non_triggered_preserved: bool = True
    candidate_recovery_searches_added: int = 0
    candidate_recovery_python_runs_added: int = 0

    # V10 Structured Planner telemetry fields
    planner_prompt_version: Optional[str] = None
    planner_attempted: bool = False
    planner_success: bool = False
    planner_parse_success: bool = False
    planner_fallback_used: bool = False
    planner_mode: Optional[str] = None
    planner_objective: Optional[str] = None
    planner_evidence_needed: Optional[str] = None
    plan_step_count: Optional[int] = None
    plan_steps: Optional[list[str]] = None
    plan_answer_type: Optional[str] = None
    planner_error_type: Optional[str] = None
    planner_prompt: Optional[str] = None
    planner_raw_response: Optional[str] = None
    planner_latency_seconds: Optional[float] = None
    planner_input_tokens: Optional[int] = None
    planner_output_tokens: Optional[int] = None
    planner_thinking_tokens: Optional[int] = None
    planner_total_tokens: Optional[int] = None
    planner_generation_attempts: int = 0
    planner_generation_success: bool = False

    # V10 Plan-Guided Executor telemetry fields
    executor_mode: Optional[str] = None
    executor_plan_used: bool = False
    executor_success: bool = False
    executor_error_type: Optional[str] = None
    executor_prompt_version: Optional[str] = None
    executor_prompt: Optional[str] = None
    executor_raw_response: Optional[str] = None
    executor_latency_seconds: Optional[float] = None
    executor_input_tokens: Optional[int] = None
    executor_output_tokens: Optional[int] = None
    executor_thinking_tokens: Optional[int] = None
    executor_total_tokens: Optional[int] = None
    executor_generation_attempts: int = 0
    executor_generation_success: bool = False

    # V11 Planner-Guided Adaptive Evidence Retrieval telemetry fields
    planner_evidence_status: Optional[str] = None
    planner_followup_query: Optional[str] = None
    planner_requested_followup: bool = False
    followup_query_valid: bool = False
    followup_query_duplicate: bool = False
    followup_eligible: bool = False
    second_search_triggered: bool = False
    second_search_attempted: bool = False
    second_search_success: bool = False
    second_search_empty_results: bool = False
    second_search_skipped_duplicate_query: bool = False
    second_search_query: Optional[str] = None
    second_search_provider_query: Optional[str] = None
    second_search_query_truncated: bool = False
    second_search_latency_seconds: Optional[float] = None
    second_search_result_count: Optional[int] = None
    second_search_error_type: Optional[str] = None
    second_search_error_message: Optional[str] = None
    second_search_new_urls_count: Optional[int] = None
    second_search_urls: Optional[list[str]] = None
    primary_search_urls: Optional[list[str]] = None
    second_search_has_new_urls: Optional[bool] = None
    primary_search_call_count: int = 1
    second_search_call_count: int = 0
    total_search_call_count: int = 1
    primary_search_evidence_hash: Optional[str] = None
    followup_search_evidence_hash: Optional[str] = None
    combined_search_evidence_hash: Optional[str] = None
    v11_retrieval_category: Optional[str] = None


    @property
    def python_analysis_prompt(self) -> Optional[str]:
        """Deprecated: V3 uses single-generation prompt (python_prompt)."""
        return None

    @property
    def python_analysis_response(self) -> Optional[str]:
        """Deprecated: V3 has no separate analysis response."""
        return None

    @property
    def python_final_prompt(self) -> Optional[str]:
        """Deprecated: V3 uses single-generation prompt (python_prompt)."""
        return self.python_prompt

    @property
    def python_success(self) -> bool:
        return self.python_result.success if self.python_result else False

    @property
    def python_execution_count(self) -> int:
        return 1 if self.python_executed else 0

    @property
    def python_exit_code(self) -> Optional[int]:
        return self.python_result.exit_code if self.python_result else None


class GAIAAgent:
    """Tool-free baseline GAIA agent (v0).

    Takes a question, formats it using a minimal baseline prompt, passes it to the
    LLMClient, and performs conservative cleaning on the final response.
    """

    def __init__(self, llm_client: Any):
        self.llm = llm_client
        self.primary_prompt_version = PROMPT_VERSION
        self.fallback_prompt_version = None

    def build_prompt(self, question: str) -> str:
        """Wraps the question in the standard v0 baseline prompt."""
        return build_baseline_prompt(question)

    def clean_answer(self, raw_response: str) -> str:
        """Conservatively cleans raw LLM output without altering content or formatting.

        Only strips surrounding whitespace and removes obvious 'FINAL ANSWER:' prefixes.
        """
        if not raw_response:
            return ""

        text = raw_response.strip()

        # Remove leading 'Final Answer:' or 'FINAL ANSWER:' prefixes if present
        pattern = r"^(?:final answer|answer)\s*:\s*"
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

        return text

    def run(self, question: str) -> AgentResult:
        """Runs the question through the v0 pipeline and returns an AgentResult."""
        prompt = self.build_prompt(question)
        llm_resp = self.llm.generate(prompt)

        if isinstance(llm_resp, LLMResponse):
            raw_text = llm_resp.raw_text if llm_resp.raw_text else llm_resp.text
            norm_text = llm_resp.text
        else:
            raw_text = str(llm_resp)
            norm_text = raw_text.strip()

        final_answer = self.clean_answer(raw_text)

        return AgentResult(
            raw_response=raw_text,
            normalized_response=norm_text,
            final_answer=final_answer,
            llm_response=llm_resp if isinstance(llm_resp, LLMResponse) else None,
            prompt=prompt,
            prompt_version=PROMPT_VERSION,
            primary_prompt_version=PROMPT_VERSION,
            fallback_prompt_version=None,
        )

    def __call__(self, question: str) -> str:
        """Allows GAIAAgent instances to be invoked as callables returning the final answer."""
        return self.run(question).final_answer


class GAIAWebAgent(GAIAAgent):
    """V1 GAIA agent with single-shot web retrieval via Tavily.

    Executes exactly one search on the original question using Tavily,
    formats retrieved evidence into a compact prompt, and queries Gemini.
    If search fails, deterministically falls back to the LLM-only baseline prompt.
    """

    def __init__(self, llm_client: Any, search_tool: Optional[Any] = None):
        super().__init__(llm_client=llm_client)
        self.search_tool = search_tool if search_tool is not None else TavilySearchTool()
        self.prompt_version = WEB_SEARCH_PROMPT_VERSION
        self.primary_prompt_version = WEB_SEARCH_PROMPT_VERSION
        self.fallback_prompt_version = PROMPT_VERSION

    def run(self, question: str) -> AgentResult:
        """Runs the single-shot retrieval pipeline on the given question."""
        # 1. Execute exactly one search with the original GAIA question
        search_res = self.search_tool.search(question)

        # 2. Determine prompt and fallback state
        search_fallback = False
        if search_res.success:
            evidence_text = search_res.format_evidence_block()
            prompt = build_web_search_prompt(question, evidence_text)
            prompt_ver = WEB_SEARCH_PROMPT_VERSION
        else:
            # Deterministic fallback to baseline LLM-only prompt
            search_fallback = True
            prompt = build_baseline_prompt(question)
            prompt_ver = PROMPT_VERSION

        # 3. Model generation
        llm_resp = self.llm.generate(prompt)

        if isinstance(llm_resp, LLMResponse):
            raw_text = llm_resp.raw_text if llm_resp.raw_text else llm_resp.text
            norm_text = llm_resp.text
        else:
            raw_text = str(llm_resp)
            norm_text = raw_text.strip()

        final_answer = self.clean_answer(raw_text)

        return AgentResult(
            raw_response=raw_text,
            normalized_response=norm_text,
            final_answer=final_answer,
            llm_response=llm_resp if isinstance(llm_resp, LLMResponse) else None,
            prompt=prompt,
            prompt_version=prompt_ver,
            primary_prompt_version=WEB_SEARCH_PROMPT_VERSION,
            fallback_prompt_version=PROMPT_VERSION,
            search_result=search_res,
            search_fallback=search_fallback,
        )


class GAIAFileAgent(GAIAWebAgent):
    """V2 GAIA agent combining single-shot Tavily web retrieval with local attachment access.

    For every task:
    1. Executes exactly one Tavily search on the original question.
    2. If an attachment is provided, processes it deterministically using FileTool.
    3. If attachment processing succeeds:
       - For text mode: formats file evidence and web evidence into file-search-v1 prompt.
       - For native multimodal: formats prompt with file reference and attaches binary Part.
       - file_fallback = False.
    4. If attachment processing fails (or no attachment):
       - If search succeeded: falls back to V1 web-search-v1 prompt (file_fallback = True if file requested).
       - If search also failed: falls back to V0 baseline-v1 prompt.
    5. Queries Gemini via LLMClient with tools explicitly disabled.
    """

    def __init__(
        self,
        llm_client: Any,
        search_tool: Optional[Any] = None,
        file_tool: Optional[Any] = None,
    ):
        super().__init__(llm_client=llm_client, search_tool=search_tool)
        self.file_tool = file_tool if file_tool is not None else FileTool()
        self.prompt_version = FILE_SEARCH_PROMPT_VERSION
        self.primary_prompt_version = FILE_SEARCH_PROMPT_VERSION
        self.fallback_prompt_version = WEB_SEARCH_PROMPT_VERSION

    def run(self, question: str, file_path: Optional[str] = None) -> AgentResult:
        """Runs the single-shot retrieval + file pipeline on the given question and attachment."""
        # 1. Execute exactly one search with the original GAIA question (same as V1)
        search_res = self.search_tool.search(question)
        web_evidence = search_res.format_evidence_block() if search_res.success else ""
        search_fallback = not search_res.success

        # 2. Process file attachment if provided
        file_res: Optional[FileResult] = None
        file_fallback = False
        attachment_parts = None

        if file_path:
            file_res = self.file_tool.process(file_path)

        # 3. Determine prompt and multimodal parts
        if file_res is not None and file_res.success:
            file_fallback = False
            prompt_ver = FILE_SEARCH_PROMPT_VERSION

            if file_res.content_mode == "native_multimodal" and file_res.native_bytes:
                try:
                    from google.genai import types
                    mime = file_res.mime_type or "application/octet-stream"
                    part = types.Part.from_bytes(data=file_res.native_bytes, mime_type=mime)
                    attachment_parts = [part]
                    file_evidence = f"[Attached file provided as native multimodal input: {file_res.file_name} ({mime})]"
                except Exception as e:
                    file_res.success = False
                    file_res.error_type = type(e).__name__
                    file_res.error_message = f"Failed to create multimodal part: {e}"
                    file_fallback = True

            if not file_fallback:
                file_evidence = file_res.text_content or f"[Attached file: {file_res.file_name}]"
                prompt = build_file_search_prompt(
                    question=question,
                    web_evidence=web_evidence if search_res.success else "[Web search unavailable]",
                    file_evidence=file_evidence,
                )

        if file_res is None or not file_res.success:
            file_fallback = bool(file_path)
            attachment_parts = None

            if search_res.success:
                prompt = build_web_search_prompt(question, web_evidence)
                prompt_ver = WEB_SEARCH_PROMPT_VERSION
            else:
                prompt = build_baseline_prompt(question)
                prompt_ver = PROMPT_VERSION

        # 4. Model generation
        llm_resp = self.llm.generate(prompt, attachment_parts=attachment_parts)

        if isinstance(llm_resp, LLMResponse):
            raw_text = llm_resp.raw_text if llm_resp.raw_text else llm_resp.text
            norm_text = llm_resp.text
        else:
            raw_text = str(llm_resp)
            norm_text = raw_text.strip()

        final_answer = self.clean_answer(raw_text)

        if file_path:
            primary_prompt_ver = FILE_SEARCH_PROMPT_VERSION
            fallback_prompt_ver = WEB_SEARCH_PROMPT_VERSION
        else:
            primary_prompt_ver = WEB_SEARCH_PROMPT_VERSION
            fallback_prompt_ver = PROMPT_VERSION

        return AgentResult(
            raw_response=raw_text,
            normalized_response=norm_text,
            final_answer=final_answer,
            llm_response=llm_resp if isinstance(llm_resp, LLMResponse) else None,
            prompt=prompt,
            prompt_version=prompt_ver,
            primary_prompt_version=primary_prompt_ver,
            fallback_prompt_version=fallback_prompt_ver,
            search_result=search_res,
            search_fallback=search_fallback,
            file_result=file_res,
            file_fallback=file_fallback,
        )

    def __call__(self, question: str, file_path: Optional[str] = None) -> str:
        return self.run(question, file_path=file_path).final_answer



def extract_python_code(text: str) -> Optional[str]:
    """Extracts Python code enclosed within ```python ... ``` or ``` ... ``` blocks."""
    if not text:
        return None
    pattern = r"```(?:python|py)?\s*\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        code = match.group(1).strip()
        return code if code else None
    return None


def extract_python_final_answer(stdout: str) -> Optional[str]:
    """Extracts the final answer marker 'FINAL_ANSWER: <ans>' printed by Python code."""
    if not stdout:
        return None
    pattern = r"(?:^|\n)\s*FINAL_?ANSWER\s*:\s*(.+)$"
    matches = re.findall(pattern, stdout, re.IGNORECASE | re.MULTILINE)
    if matches:
        return matches[-1].strip()
    return None


def extract_direct_answer(raw_text: str) -> str:
    """Extracts direct answer from 'FINAL: <ans>' line or falls back to clean_answer."""
    if not raw_text:
        return ""
    pattern = r"(?:^|\n)\s*FINAL\s*:\s*(.+)$"
    matches = re.findall(pattern, raw_text, re.IGNORECASE | re.MULTILINE)
    if matches:
        return matches[-1].strip()
    # Fallback to standard clean_answer
    text = raw_text.strip()
    prefix_pattern = r"^(?:final answer|answer)\s*:\s*"
    return re.sub(prefix_pattern, "", text, flags=re.IGNORECASE).strip()


class GAIAPythonAgent(GAIAFileAgent):
    """V3 GAIA agent combining single-shot Tavily search, V2 attachment handling,
    and controlled single-shot local Python execution under a single-generation contract.

    Contract:
    1. Executes exactly one Tavily search on original question (inherited from V1/V2).
    2. Processes file attachment using FileTool if provided (inherited from V2).
    3. Builds a single execution-aware prompt (`python-execution-v1`).
    4. Executes exactly ONE primary Gemini generation (`llm_generation_count == 1`).
    5. The model chooses either:
       Option A (Direct Answer): Returns 'FINAL: <answer>'
       Option B (Python Code): Returns ```python ... ``` script printing 'FINAL_ANSWER: <answer>'
    6. If Python code is returned:
       - Executes PythonTool.execute(code, attachment_path) strictly ONCE (`python_execution_count <= 1`).
       - If execution succeeds and stdout contains 'FINAL_ANSWER: <answer>', extracts it deterministically.
       - If execution fails (syntax error, AST violation, non-zero return code, timeout) OR missing marker:
         - Sets python_fallback = True.
         - Uses direct answer if present in model text; otherwise empty string.
         - Does NOT invoke a second Gemini synthesis or retry turn.
    """

    def __init__(
        self,
        llm_client: Any,
        search_tool: Optional[Any] = None,
        file_tool: Optional[Any] = None,
        python_tool: Optional[Any] = None,
    ):
        super().__init__(llm_client=llm_client, search_tool=search_tool, file_tool=file_tool)
        self.python_tool = python_tool if python_tool is not None else PythonTool()
        self.prompt_version = PYTHON_EXECUTION_PROMPT_VERSION
        self.primary_prompt_version = PYTHON_EXECUTION_PROMPT_VERSION
        self.fallback_prompt_version = None

    def run(self, question: str, file_path: Optional[str] = None) -> AgentResult:
        """Runs the V3 single-shot retrieval + file + single-shot Python execution pipeline."""
        # 1. Execute exactly one search with original GAIA question
        search_res = self.search_tool.search(question)
        web_evidence = search_res.format_evidence_block() if search_res.success else ""
        search_fallback = not search_res.success

        # 2. Process file attachment if provided
        file_res: Optional[FileResult] = None
        file_fallback = False
        attachment_parts = None
        file_evidence = ""
        attachment_filename = ""

        if file_path:
            # Derive attachment basename independently of FileTool processing success.
            # In V3, Python can access the task attachment in its workspace even when
            # FileTool does not support text/multimodal extraction (e.g. .zip, .pdb, .jsonld).
            attachment_filename = os.path.basename(file_path)

            file_res = self.file_tool.process(file_path)
            if file_res.success:
                if file_res.content_mode == "native_multimodal" and file_res.native_bytes:
                    try:
                        from google.genai import types
                        mime = file_res.mime_type or "application/octet-stream"
                        part = types.Part.from_bytes(data=file_res.native_bytes, mime_type=mime)
                        attachment_parts = [part]
                        file_evidence = f"[Attached file provided as native multimodal input: {file_res.file_name} ({mime})]"
                    except Exception as e:
                        file_res.success = False
                        file_res.error_type = type(e).__name__
                        file_res.error_message = f"Failed to create multimodal part: {e}"
                        file_fallback = True
                if not file_fallback:
                    file_evidence = file_res.text_content or f"[Attached file: {file_res.file_name}]"
            else:
                file_fallback = True
        else:
            file_fallback = False

        # 3. Build single V3 execution-aware prompt
        prompt = build_python_execution_prompt(
            question=question,
            web_evidence=web_evidence if search_res.success else "[Web search unavailable]",
            file_evidence=file_evidence,
            attachment_filename=attachment_filename,
        )

        # 4. Execute exactly one primary LLM generation (llm_generation_count == 1)
        llm_resp = self.llm.generate(prompt, attachment_parts=attachment_parts)
        if isinstance(llm_resp, LLMResponse):
            raw_text = llm_resp.raw_text if llm_resp.raw_text else llm_resp.text
            norm_text = llm_resp.text
        else:
            raw_text = str(llm_resp)
            norm_text = raw_text.strip()

        # 5. Parse response: Option A (Direct) vs Option B (Python)
        code = extract_python_code(raw_text)
        py_result: Optional[PythonResult] = None
        python_requested = bool(code)
        python_executed = False
        python_fallback = False
        final_answer = ""

        if code:
            # Option B: Python execution requested (strictly at most once)
            python_executed = True
            py_result = self.python_tool.execute(code, attachment_path=file_path)

            if py_result.success:
                extracted_ans = extract_python_final_answer(py_result.stdout)
                if extracted_ans is not None:
                    final_answer = self.clean_answer(extracted_ans)
                    python_fallback = False
                else:
                    # Missing or malformed FINAL_ANSWER: marker
                    python_fallback = True
                    py_result.success = False
                    py_result.error_type = py_result.error_type or "MissingFinalAnswerMarker"
                    py_result.error_message = (
                        py_result.error_message
                        or "Python execution succeeded but stdout did not contain 'FINAL_ANSWER:' marker"
                    )
                    # Check if model had a FINAL: direct answer in its text; otherwise empty
                    final_answer = self.clean_answer(extract_direct_answer(raw_text)) if "FINAL:" in raw_text else ""
            else:
                # Execution failed, timed out, or violated policy -> fallback without second LLM call
                python_fallback = True
                final_answer = self.clean_answer(extract_direct_answer(raw_text)) if "FINAL:" in raw_text else ""
        else:
            # Option A: Direct answer without Python execution
            python_requested = False
            python_executed = False
            python_fallback = False
            final_answer = self.clean_answer(extract_direct_answer(raw_text))

        return AgentResult(
            raw_response=raw_text,
            normalized_response=norm_text,
            final_answer=final_answer,
            llm_response=llm_resp if isinstance(llm_resp, LLMResponse) else None,
            prompt=prompt,
            prompt_version=self.prompt_version,
            primary_prompt_version=self.primary_prompt_version,
            fallback_prompt_version=self.fallback_prompt_version,
            search_result=search_res,
            search_fallback=search_fallback,
            file_result=file_res,
            file_fallback=file_fallback,
            python_result=py_result,
            python_requested=python_requested,
            python_executed=python_executed,
            python_fallback=python_fallback,
            python_prompt_version=self.prompt_version,
            python_prompt=prompt,
            llm_generation_count=1,
        )

    def __call__(self, question: str, file_path: Optional[str] = None) -> str:
        return self.run(question, file_path=file_path).final_answer


def parse_router_decision(raw_text: Optional[str]) -> Optional[str]:
    """Parses router output text for 'ROUTE: DIRECT' or 'ROUTE: PYTHON'.

    Returns 'DIRECT', 'PYTHON', or None if ambiguous, malformed, or missing.
    """
    if not raw_text or not str(raw_text).strip():
        return None
    pattern = r"\bROUTE\s*:\s*(DIRECT|PYTHON)\b"
    matches = re.findall(pattern, str(raw_text), flags=re.IGNORECASE)
    if not matches:
        return None
    normalized = {m.upper() for m in matches}
    if len(normalized) == 1:
        return normalized.pop()
    return None


class GAIARouterAgent(GAIAFileAgent):
    """V4 GAIA agent with explicit two-stage capability-routing architecture.

    Stage 1 (Router): Evaluates question, web evidence, and attachment evidence
    to explicitly select ROUTE: DIRECT or ROUTE: PYTHON.
    Stage 2 (Worker): Executes the selected route using a specialized, single-purpose
    worker prompt (router-direct-worker-v1 or router-python-worker-v1).
    Python execution is only permitted when routed to PYTHON.
    Deterministic fallback to DIRECT if router fails or produces ambiguous output.
    Zero router retries, zero worker retries, zero Python retries, and NO third LLM generation.
    """

    def __init__(
        self,
        llm_client: Any,
        search_tool: Optional[Any] = None,
        file_tool: Optional[Any] = None,
        python_tool: Optional[Any] = None,
    ):
        super().__init__(llm_client=llm_client, search_tool=search_tool, file_tool=file_tool)
        self.python_tool = python_tool if python_tool is not None else PythonTool()
        self.prompt_version = ROUTER_PROMPT_VERSION
        self.primary_prompt_version = ROUTER_PROMPT_VERSION
        self.fallback_prompt_version = None

    def _prepare_upstream_context(self, question: str, file_path: Optional[str] = None) -> UpstreamContext:
        """Retrieves web evidence and processes file attachments into a shared UpstreamContext."""
        # 1. Execute exactly one search with original GAIA question
        search_res = self.search_tool.search(question)
        web_evidence = search_res.format_evidence_block() if search_res.success else ""
        search_fallback = not search_res.success

        # 2. Process file attachment if provided
        file_res: Optional[FileResult] = None
        file_fallback = False
        attachment_parts = None
        file_evidence = ""
        attachment_filename = ""

        if file_path:
            attachment_filename = os.path.basename(file_path)
            file_res = self.file_tool.process(file_path)
            if file_res.success:
                if file_res.content_mode == "native_multimodal" and file_res.native_bytes:
                    try:
                        from google.genai import types
                        mime = file_res.mime_type or "application/octet-stream"
                        part = types.Part.from_bytes(data=file_res.native_bytes, mime_type=mime)
                        attachment_parts = [part]
                        file_evidence = f"[Attached file provided as native multimodal input: {file_res.file_name} ({mime})]"
                    except Exception as e:
                        file_res.success = False
                        file_res.error_type = type(e).__name__
                        file_res.error_message = f"Failed to create multimodal part: {e}"
                        file_fallback = True
                if not file_fallback:
                    file_evidence = file_res.text_content or f"[Attached file: {file_res.file_name}]"
            else:
                file_fallback = True
        else:
            file_fallback = False

        return UpstreamContext(
            question=question,
            file_path=file_path,
            web_evidence=web_evidence,
            file_evidence=file_evidence,
            attachment_filename=attachment_filename,
            search_res=search_res,
            search_fallback=search_fallback,
            file_res=file_res,
            file_fallback=file_fallback,
            attachment_parts=attachment_parts,
        )

    def _execute_upstream_pair_from_context(self, context: UpstreamContext) -> AgentResult:
        """Executes the Capability Router (Slot 1) -> Worker (Slot 2) pair from UpstreamContext."""
        import time

        question = context.question
        file_path = context.file_path
        web_evidence = context.web_evidence
        file_evidence = context.file_evidence
        attachment_filename = context.attachment_filename
        search_res = context.search_res
        search_fallback = context.search_fallback
        file_res = context.file_res
        file_fallback = context.file_fallback
        attachment_parts = context.attachment_parts

        # 3. Stage 1: Router Generation (Generation #1)
        router_prompt = build_router_prompt(
            question=question,
            web_evidence=web_evidence if (search_res and search_res.success) else "[Web search unavailable]",
            file_evidence=file_evidence,
            attachment_filename=attachment_filename,
        )

        router_generation_attempts = 1
        router_generation_success = False
        router_llm_resp = None
        router_raw_response = None
        router_error_type = None
        router_start = time.time()

        try:
            router_llm_resp = self.llm.generate(router_prompt, attachment_parts=attachment_parts)
            router_generation_success = True
            if isinstance(router_llm_resp, LLMResponse):
                router_raw_response = router_llm_resp.raw_text if router_llm_resp.raw_text else router_llm_resp.text
                if router_llm_resp.finish_reason == "MALFORMED_FUNCTION_CALL":
                    router_error_type = "malformed_function_call_finish_reason"
            else:
                router_raw_response = str(router_llm_resp)
        except Exception as e:
            err_str = str(e).lower()
            if "timeout" in err_str or "deadline" in err_str:
                router_error_type = "provider_timeout"
            elif "malformed_function_call" in err_str:
                router_error_type = "malformed_function_call_finish_reason"
            else:
                router_error_type = "provider_api_error"
            router_raw_response = None

        router_latency = round(time.time() - router_start, 2)

        # Parse router decision
        if router_error_type is not None:
            router_decision = "DIRECT"
            router_success = False
            router_fallback = True
        elif router_raw_response is None or not router_raw_response.strip():
            router_decision = "DIRECT"
            router_success = False
            router_fallback = True
            router_error_type = "empty_provider_response"
        else:
            parsed_route = parse_router_decision(router_raw_response)
            if parsed_route is not None:
                router_decision = parsed_route
                router_success = True
                router_fallback = False
                router_error_type = None
            else:
                router_decision = "DIRECT"
                router_success = False
                router_fallback = True
                pattern = r"\bROUTE\s*:\s*(DIRECT|PYTHON)\b"
                matches = re.findall(pattern, router_raw_response, flags=re.IGNORECASE)
                if len(set(m.upper() for m in matches)) > 1:
                    router_error_type = "ambiguous_route_text"
                elif "route" in router_raw_response.lower():
                    router_error_type = "malformed_router_text"
                else:
                    router_error_type = "missing_route_marker"

        router_input_tokens = getattr(router_llm_resp, "input_tokens", None) if router_llm_resp else None
        router_output_tokens = getattr(router_llm_resp, "output_tokens", None) if router_llm_resp else None
        router_thinking_tokens = getattr(router_llm_resp, "thinking_tokens", None) if router_llm_resp else None

        # 4. Stage 2: Route-Specific Worker Generation (Generation #2)
        # INFORMATION FIREWALL: Worker receives ONLY question, web evidence, file evidence, and attachment filename.
        # Router output is never passed to worker prompt.
        worker_mode = router_decision
        if worker_mode == "DIRECT":
            worker_prompt_ver = ROUTER_DIRECT_WORKER_PROMPT_VERSION
            worker_prompt = build_direct_worker_prompt(
                question=question,
                web_evidence=web_evidence if (search_res and search_res.success) else "[Web search unavailable]",
                file_evidence=file_evidence,
                attachment_filename=attachment_filename,
            )
        else:
            worker_prompt_ver = ROUTER_PYTHON_WORKER_PROMPT_VERSION
            worker_prompt = build_python_worker_prompt(
                question=question,
                web_evidence=web_evidence if (search_res and search_res.success) else "[Web search unavailable]",
                file_evidence=file_evidence,
                attachment_filename=attachment_filename,
            )

        worker_generation_attempts = 1
        worker_generation_success = False
        worker_llm_resp = None
        worker_raw_response = None
        worker_error_type = None
        worker_start = time.time()

        try:
            worker_llm_resp = self.llm.generate(worker_prompt, attachment_parts=attachment_parts)
            worker_generation_success = True
            if isinstance(worker_llm_resp, LLMResponse):
                worker_raw_response = worker_llm_resp.raw_text if worker_llm_resp.raw_text else worker_llm_resp.text
                if worker_llm_resp.finish_reason == "MALFORMED_FUNCTION_CALL":
                    worker_error_type = "malformed_function_call_finish_reason"
            else:
                worker_raw_response = str(worker_llm_resp)
        except Exception as e:
            err_str = str(e).lower()
            if "timeout" in err_str or "deadline" in err_str:
                worker_error_type = "provider_timeout"
            elif "malformed_function_call" in err_str:
                worker_error_type = "malformed_function_call_finish_reason"
            else:
                worker_error_type = "provider_api_error"
            worker_raw_response = None

        worker_latency = round(time.time() - worker_start, 2)

        if worker_error_type is None and (worker_raw_response is None or not worker_raw_response.strip()):
            worker_error_type = "empty_worker_response"

        worker_input_tokens = getattr(worker_llm_resp, "input_tokens", None) if worker_llm_resp else None
        worker_output_tokens = getattr(worker_llm_resp, "output_tokens", None) if worker_llm_resp else None
        worker_thinking_tokens = getattr(worker_llm_resp, "thinking_tokens", None) if worker_llm_resp else None

        # 5. Extract Answer / Execute Python
        py_result: Optional[PythonResult] = None
        python_requested = False
        python_executed = False
        python_fallback = False
        final_answer = ""
        worker_success = False

        if worker_mode == "DIRECT":
            python_requested = False
            python_executed = False
            python_fallback = False
            final_answer = self.clean_answer(extract_direct_answer(worker_raw_response or ""))
            worker_success = bool(final_answer and not worker_error_type)
        else:
            # PYTHON worker mode
            code = extract_python_code(worker_raw_response or "")
            python_requested = bool(code)
            if code:
                python_executed = True
                py_result = self.python_tool.execute(code, attachment_path=file_path)

                if py_result.success:
                    extracted_ans = extract_python_final_answer(py_result.stdout)
                    if extracted_ans is not None:
                        final_answer = self.clean_answer(extracted_ans)
                        python_fallback = False
                        worker_success = True
                    else:
                        python_fallback = True
                        py_result.success = False
                        py_result.error_type = py_result.error_type or "MissingFinalAnswerMarker"
                        py_result.error_message = (
                            py_result.error_message
                            or "Python execution succeeded but stdout did not contain 'FINAL_ANSWER:' marker"
                        )
                        final_answer = (
                            self.clean_answer(extract_direct_answer(worker_raw_response))
                            if worker_raw_response and "FINAL:" in worker_raw_response
                            else ""
                        )
                        worker_success = False
                else:
                    python_fallback = True
                    final_answer = (
                        self.clean_answer(extract_direct_answer(worker_raw_response))
                        if worker_raw_response and "FINAL:" in worker_raw_response
                        else ""
                    )
                    worker_success = False
            else:
                python_requested = False
                python_executed = False
                python_fallback = True
                final_answer = (
                    self.clean_answer(extract_direct_answer(worker_raw_response or ""))
                    if worker_raw_response and "FINAL:" in worker_raw_response
                    else ""
                )
                worker_success = False

        llm_generation_attempts = router_generation_attempts + worker_generation_attempts
        llm_generation_success_count = (1 if router_generation_success else 0) + (1 if worker_generation_success else 0)

        raw_resp = worker_raw_response or ""
        norm_resp = raw_resp.strip()

        fallback_pv = ROUTER_DIRECT_WORKER_PROMPT_VERSION if router_fallback else None

        agent_result = AgentResult(
            raw_response=raw_resp,
            normalized_response=norm_resp,
            final_answer=final_answer,
            candidate_answer=final_answer,
            llm_response=worker_llm_resp if isinstance(worker_llm_resp, LLMResponse) else None,
            prompt=worker_prompt,
            prompt_version=ROUTER_PROMPT_VERSION,
            primary_prompt_version=ROUTER_PROMPT_VERSION,
            fallback_prompt_version=fallback_pv,
            search_result=search_res,
            search_fallback=search_fallback,
            file_result=file_res,
            file_fallback=file_fallback,
            python_result=py_result,
            python_requested=python_requested,
            python_executed=python_executed,
            python_fallback=python_fallback,
            python_prompt_version=ROUTER_PYTHON_WORKER_PROMPT_VERSION if worker_mode == "PYTHON" else None,
            python_prompt=worker_prompt if worker_mode == "PYTHON" else None,
            llm_generation_count=llm_generation_attempts,
            router_requested=True,
            router_decision=router_decision,
            router_success=router_success,
            router_fallback=router_fallback,
            router_error_type=router_error_type,
            router_prompt_version=ROUTER_PROMPT_VERSION,
            router_prompt=router_prompt,
            router_raw_response=router_raw_response,
            router_latency_seconds=router_latency,
            router_input_tokens=router_input_tokens,
            router_output_tokens=router_output_tokens,
            router_thinking_tokens=router_thinking_tokens,
            router_generation_attempts=router_generation_attempts,
            router_generation_success=router_generation_success,
            worker_mode=worker_mode,
            worker_success=worker_success,
            worker_error_type=worker_error_type,
            worker_prompt_version=worker_prompt_ver,
            worker_prompt=worker_prompt,
            worker_raw_response=worker_raw_response,
            worker_latency_seconds=worker_latency,
            worker_input_tokens=worker_input_tokens,
            worker_output_tokens=worker_output_tokens,
            worker_thinking_tokens=worker_thinking_tokens,
            worker_generation_attempts=worker_generation_attempts,
            worker_generation_success=worker_generation_success,
            llm_generation_attempts=llm_generation_attempts,
            llm_generation_success_count=llm_generation_success_count,
        )
        return agent_result

    def run(self, question: str, file_path: Optional[str] = None) -> AgentResult:
        """Runs the V4 two-stage capability-routing pipeline."""
        context = self._prepare_upstream_context(question=question, file_path=file_path)
        agent_result = self._execute_upstream_pair_from_context(context)
        return self._post_worker_candidate_hook(
            question=question,
            file_path=file_path,
            result=agent_result,
        )

    def _post_worker_candidate_hook(
        self,
        question: str,
        file_path: Optional[str],
        result: AgentResult,
    ) -> AgentResult:
        """Extension hook executed immediately after worker candidate answer generation.

        Default implementation is an identity no-op to preserve Frozen V4–V7 behavior.
        Overridden by V9 to perform candidate recovery on eligible starved tasks.
        """
        return result

    def __call__(self, question: str, file_path: Optional[str] = None) -> str:
        return self.run(question, file_path=file_path).final_answer


class GAIAVerificationAgent(GAIARouterAgent):
    """V5 One-Shot Post-Answer Verification Agent.

    Inherits the exact frozen V4 pipeline:
    Tavily search -> FileTool -> Router LLM -> Worker LLM -> optional Python execution -> candidate answer.

    Then executes at most one conservative post-answer verification call:
    - Candidate empty: verifier skipped, final answer remains empty.
    - Candidate non-empty: verifier LLM called (with mode="NONE").
    - Verifier returns KEEP: keep candidate answer.
    - Verifier returns REVISE: adopt revised answer.
    - Verifier returns INVALID / error / timeout: fallback to candidate answer non-destructively.
    """

    def __init__(
        self,
        llm_client: Any,
        search_tool: Optional[Any] = None,
        file_tool: Optional[Any] = None,
        python_tool: Optional[Any] = None,
        tavily_tool: Optional[Any] = None,
    ):
        st = search_tool or tavily_tool
        super().__init__(llm_client=llm_client, search_tool=st, file_tool=file_tool, python_tool=python_tool)

    def run(self, question: str, file_path: Optional[str] = None) -> AgentResult:
        # 1. Execute frozen V4 pipeline via super()
        v4_result = super().run(question, file_path=file_path)

        pre_verification_answer = v4_result.final_answer
        verifier_eligible = bool(pre_verification_answer and pre_verification_answer.strip())

        if not verifier_eligible:
            # Skip verifier completely
            v4_result.pre_verification_answer = pre_verification_answer
            v4_result.post_verification_answer = pre_verification_answer
            v4_result.verifier_eligible = False
            v4_result.verifier_attempted = False
            v4_result.verifier_generation_attempts = 0
            v4_result.verifier_generation_success = False
            v4_result.verifier_finish_reason = None
            v4_result.verifier_error_type = None
            v4_result.verifier_verdict = None
            v4_result.verifier_revised = False
            v4_result.verifier_fallback = False
            v4_result.verifier_latency_seconds = None
            v4_result.verifier_input_tokens = None
            v4_result.verifier_output_tokens = None
            v4_result.verifier_thinking_tokens = None
            v4_result.verifier_total_tokens = None
            v4_result.verifier_prompt_version = None
            v4_result.verifier_prompt = None
            v4_result.verifier_raw_response = None
            return v4_result

        # 2. Candidate is non-empty -> Attempt one-shot verification
        # Information Firewall: Verifier receives ONLY question, candidate answer,
        # already-retrieved web evidence, already-processed file evidence, and attachment filename.
        # No raw router/worker reasoning, ground truth, code, or stdout/stderr.

        search_res = v4_result.search_result
        if search_res and getattr(search_res, "success", False):
            if hasattr(search_res, "format_evidence_block"):
                web_evidence = search_res.format_evidence_block()
            elif hasattr(search_res, "formatted_snippets"):
                web_evidence = search_res.formatted_snippets
            else:
                web_evidence = str(search_res)
        else:
            web_evidence = "[Web search unavailable]"

        file_res = v4_result.file_result
        file_evidence = None
        attachment_filename = None
        attachment_parts = None

        if file_res and not v4_result.file_fallback:
            attachment_filename = file_res.file_name
            if (file_res.content_mode in ("native_multimodal", "native") or not file_res.text_content) and file_res.native_bytes:
                try:
                    from google.genai import types
                    mime = file_res.mime_type or "application/octet-stream"
                    part = types.Part.from_bytes(data=file_res.native_bytes, mime_type=mime)
                    attachment_parts = [part]
                    file_evidence = f"[Attached file provided as native multimodal input: {file_res.file_name} ({mime})]"
                except Exception:
                    file_evidence = f"[Attached file: {file_res.file_name}]"
            else:
                file_evidence = file_res.text_content or f"[Attached file: {file_res.file_name}]"

        verifier_prompt = build_verifier_prompt(
            question=question,
            candidate_answer=pre_verification_answer,
            web_evidence=web_evidence,
            file_evidence=file_evidence,
            attachment_filename=attachment_filename,
        )

        verifier_generation_attempts = 1
        verifier_generation_success = False
        verifier_llm_resp = None
        verifier_raw_response = None
        verifier_error_type = None
        verifier_start = time.time()

        try:
            verifier_llm_resp = self.llm.generate(verifier_prompt, attachment_parts=attachment_parts)
            verifier_generation_success = True
            if isinstance(verifier_llm_resp, LLMResponse):
                verifier_raw_response = verifier_llm_resp.raw_text if verifier_llm_resp.raw_text else verifier_llm_resp.text
                if verifier_llm_resp.finish_reason == "MALFORMED_FUNCTION_CALL":
                    verifier_error_type = "malformed_function_call_finish_reason"
            else:
                verifier_raw_response = str(verifier_llm_resp)
        except Exception as e:
            err_str = str(e).lower()
            if "timeout" in err_str or "deadline" in err_str:
                verifier_error_type = "provider_timeout"
            elif "malformed_function_call" in err_str:
                verifier_error_type = "malformed_function_call_finish_reason"
            else:
                verifier_error_type = "provider_api_error"
            verifier_raw_response = None

        verifier_latency = round(time.time() - verifier_start, 2)

        verifier_finish_reason = getattr(verifier_llm_resp, "finish_reason", None) if verifier_llm_resp else None
        verifier_input_tokens = getattr(verifier_llm_resp, "input_tokens", None) if verifier_llm_resp else None
        verifier_output_tokens = getattr(verifier_llm_resp, "output_tokens", None) if verifier_llm_resp else None
        verifier_thinking_tokens = getattr(verifier_llm_resp, "thinking_tokens", None) if verifier_llm_resp else None
        verifier_total_tokens = getattr(verifier_llm_resp, "total_tokens", None) if verifier_llm_resp else None
        if verifier_total_tokens is None and verifier_input_tokens is not None and verifier_output_tokens is not None:
            verifier_total_tokens = verifier_input_tokens + verifier_output_tokens

        # 3. Parse verifier response and apply non-destructive policy
        post_verification_answer = pre_verification_answer
        verifier_verdict = None
        verifier_revised = False
        verifier_fallback = False

        if verifier_error_type is not None:
            verifier_fallback = True
        else:
            parse_result = parse_verifier_result(verifier_raw_response)
            if parse_result.is_valid:
                if parse_result.verdict == "KEEP":
                    verifier_verdict = "KEEP"
                    verifier_revised = False
                    verifier_fallback = False
                    post_verification_answer = pre_verification_answer
                elif parse_result.verdict == "REVISE":
                    cleaned = self.clean_answer(parse_result.revised_answer or "")
                    if cleaned:
                        verifier_verdict = "REVISE"
                        verifier_revised = True
                        verifier_fallback = False
                        post_verification_answer = cleaned
                    else:
                        verifier_verdict = None
                        verifier_revised = False
                        verifier_fallback = True
                        verifier_error_type = "revise_empty_final"
                        post_verification_answer = pre_verification_answer
            else:
                verifier_verdict = None
                verifier_revised = False
                verifier_fallback = True
                verifier_error_type = parse_result.error_type
                post_verification_answer = pre_verification_answer

        # Total generations accounting
        total_llm_attempts = v4_result.llm_generation_attempts + verifier_generation_attempts
        total_llm_success = v4_result.llm_generation_success_count + (1 if verifier_generation_success else 0)

        # Update and return result
        v4_result.pre_verification_answer = pre_verification_answer
        v4_result.post_verification_answer = post_verification_answer
        v4_result.final_answer = post_verification_answer
        v4_result.prompt_version = VERIFICATION_PROMPT_VERSION
        v4_result.verifier_eligible = True
        v4_result.verifier_attempted = True
        v4_result.verifier_generation_attempts = verifier_generation_attempts
        v4_result.verifier_generation_success = verifier_generation_success
        v4_result.verifier_finish_reason = verifier_finish_reason
        v4_result.verifier_error_type = verifier_error_type
        v4_result.verifier_verdict = verifier_verdict
        v4_result.verifier_revised = verifier_revised
        v4_result.verifier_fallback = verifier_fallback
        v4_result.verifier_latency_seconds = verifier_latency
        v4_result.verifier_input_tokens = verifier_input_tokens
        v4_result.verifier_output_tokens = verifier_output_tokens
        v4_result.verifier_thinking_tokens = verifier_thinking_tokens
        v4_result.verifier_total_tokens = verifier_total_tokens
        v4_result.verifier_prompt_version = VERIFICATION_PROMPT_VERSION
        v4_result.verifier_prompt = verifier_prompt
        v4_result.verifier_raw_response = verifier_raw_response
        v4_result.llm_generation_attempts = total_llm_attempts
        v4_result.llm_generation_count = total_llm_attempts
        v4_result.llm_generation_success_count = total_llm_success

        return v4_result

    def __call__(self, question: str, file_path: Optional[str] = None) -> str:
        return self.run(question, file_path=file_path).final_answer


class GAIASelfEvaluationAgent(GAIAVerificationAgent):
    """V6 read-only post-answer self-evaluation agent.

    V5's verifier may KEEP or REVISE a candidate answer. V6 is deliberately a
    different mechanism: after V5 has finalized its answer, this class may only
    classify reliability as PASS or SUSPECT. It never changes that answer.
    """

    def _build_execution_summary(self, result: AgentResult, file_path: Optional[str]) -> str:
        """Creates deterministic V6 context without V5 verdict information."""
        search_res = result.search_result
        file_res = result.file_result
        py_result = result.python_result
        worker_response = result.llm_response

        if result.worker_error_type:
            execution_error = result.worker_error_type
        elif result.router_error_type:
            execution_error = result.router_error_type
        elif py_result and getattr(py_result, "error_type", None):
            execution_error = py_result.error_type
        else:
            execution_error = None

        finish_reason = getattr(worker_response, "finish_reason", None) if worker_response else None
        completion_success = bool(
            finish_reason == "STOP"
            and result.raw_response is not None
            and result.raw_response.strip() != ""
        )
        return build_execution_summary(
            route=result.worker_mode or result.router_decision,
            search_attempted=search_res is not None,
            search_success=bool(search_res and getattr(search_res, "success", False)),
            search_fallback=bool(result.search_fallback),
            attachment_required=bool(file_path),
            file_attempted=file_res is not None,
            file_success=bool(file_res and getattr(file_res, "success", False)),
            python_routed=result.worker_mode == "PYTHON",
            python_attempted=bool(result.python_executed),
            python_success=bool(py_result and getattr(py_result, "success", False)),
            execution_error_type=execution_error,
            completion_success=completion_success,
            finish_reason=finish_reason,
        )

    @staticmethod
    def _existing_web_evidence(result: AgentResult) -> str:
        search_res = result.search_result
        if not search_res or not getattr(search_res, "success", False):
            return "[Web search unavailable]"
        if hasattr(search_res, "format_evidence_block"):
            return search_res.format_evidence_block()
        if hasattr(search_res, "formatted_snippets"):
            return str(search_res.formatted_snippets)
        return str(search_res)

    @staticmethod
    def _existing_file_context(result: AgentResult) -> tuple[str, str]:
        """Returns already-extracted text context only; V6 never rereads a file."""
        file_res = result.file_result
        if not file_res or result.file_fallback:
            return "", ""
        filename = str(getattr(file_res, "file_name", "") or "")
        text_content = str(getattr(file_res, "text_content", "") or "")
        if text_content.strip():
            return text_content, filename
        if filename:
            return "[Attachment was available to the frozen V5 pipeline but has no extracted text context.]", filename
        return "", ""

    def run(self, question: str, file_path: Optional[str] = None) -> AgentResult:
        """Runs frozen V5, then performs at most one observational text-only call."""
        v5_result = super().run(question, file_path=file_path)
        pre_self_evaluation_answer = v5_result.final_answer
        eligible = bool(pre_self_evaluation_answer and pre_self_evaluation_answer.strip())

        # The exact V5 answer remains authoritative in every branch below.
        v5_result.pre_self_evaluation_answer = pre_self_evaluation_answer
        v5_result.post_self_evaluation_answer = pre_self_evaluation_answer
        v5_result.self_eval_eligible = eligible
        v5_result.self_eval_prompt_version = SELF_EVALUATION_PROMPT_VERSION if eligible else None
        v5_result.self_eval_answer_unchanged = True

        if not eligible:
            v5_result.self_eval_attempted = False
            v5_result.self_eval_success = False
            v5_result.self_eval_generation_attempts = 0
            v5_result.self_eval_generation_success = False
            v5_result.self_eval_assessment = None
            v5_result.self_eval_risk_type = None
            v5_result.self_eval_confidence = None
            v5_result.self_eval_error_type = None
            v5_result.self_eval_finish_reason = None
            v5_result.self_eval_latency_seconds = None
            v5_result.self_eval_input_tokens = None
            v5_result.self_eval_output_tokens = None
            v5_result.self_eval_thinking_tokens = None
            v5_result.self_eval_total_tokens = None
            v5_result.self_eval_prompt = None
            v5_result.self_eval_raw_response = None
            return v5_result

        web_evidence = self._existing_web_evidence(v5_result)
        file_evidence, attachment_filename = self._existing_file_context(v5_result)
        execution_summary = self._build_execution_summary(v5_result, file_path)
        self_eval_prompt = build_self_evaluator_prompt(
            question=question,
            final_answer=pre_self_evaluation_answer,
            execution_summary=execution_summary,
            web_evidence=web_evidence,
            file_evidence=file_evidence,
            attachment_filename=attachment_filename,
        )

        self_eval_generation_attempts = 1
        self_eval_generation_success = False
        self_eval_llm_resp = None
        self_eval_raw_response = None
        self_eval_error_type = None
        start_time = time.time()
        try:
            # max_retries=0 is intentional: V6 permits exactly one provider attempt.
            self_eval_llm_resp = self.llm.generate(
                self_eval_prompt,
                attachment_parts=None,
                max_retries=0,
            )
            self_eval_generation_success = True
            if isinstance(self_eval_llm_resp, LLMResponse):
                self_eval_raw_response = (
                    self_eval_llm_resp.raw_text
                    if self_eval_llm_resp.raw_text
                    else self_eval_llm_resp.text
                )
                if self_eval_llm_resp.finish_reason == "MALFORMED_FUNCTION_CALL":
                    self_eval_error_type = "malformed_function_call_finish_reason"
                elif self_eval_llm_resp.finish_reason != "STOP":
                    self_eval_error_type = "unexpected_finish_reason"
            else:
                self_eval_raw_response = str(self_eval_llm_resp)
                self_eval_error_type = "unexpected_provider_response_type"
        except Exception as exc:
            error_text = str(exc).lower()
            if "timeout" in error_text or "deadline" in error_text:
                self_eval_error_type = "provider_timeout"
            elif "malformed_function_call" in error_text:
                self_eval_error_type = "malformed_function_call_finish_reason"
            else:
                self_eval_error_type = "provider_api_error"

        self_eval_latency = round(time.time() - start_time, 2)
        self_eval_finish_reason = getattr(self_eval_llm_resp, "finish_reason", None) if self_eval_llm_resp else None
        self_eval_input_tokens = getattr(self_eval_llm_resp, "input_tokens", None) if self_eval_llm_resp else None
        self_eval_output_tokens = getattr(self_eval_llm_resp, "output_tokens", None) if self_eval_llm_resp else None
        self_eval_thinking_tokens = getattr(self_eval_llm_resp, "thinking_tokens", None) if self_eval_llm_resp else None
        self_eval_total_tokens = getattr(self_eval_llm_resp, "total_tokens", None) if self_eval_llm_resp else None
        if (
            self_eval_total_tokens is None
            and self_eval_input_tokens is not None
            and self_eval_output_tokens is not None
        ):
            self_eval_total_tokens = self_eval_input_tokens + self_eval_output_tokens

        parsed = None
        if self_eval_error_type is None:
            parsed = parse_self_evaluation_result(self_eval_raw_response)
            if not parsed.is_valid:
                self_eval_error_type = parsed.error_type

        v5_result.self_eval_attempted = True
        v5_result.self_eval_success = bool(parsed and parsed.is_valid)
        v5_result.self_eval_generation_attempts = self_eval_generation_attempts
        v5_result.self_eval_generation_success = self_eval_generation_success
        v5_result.self_eval_assessment = parsed.assessment if parsed and parsed.is_valid else None
        v5_result.self_eval_risk_type = parsed.risk_type if parsed and parsed.is_valid else None
        v5_result.self_eval_confidence = parsed.confidence if parsed and parsed.is_valid else None
        v5_result.self_eval_error_type = self_eval_error_type
        v5_result.self_eval_finish_reason = self_eval_finish_reason
        v5_result.self_eval_latency_seconds = self_eval_latency
        v5_result.self_eval_input_tokens = self_eval_input_tokens
        v5_result.self_eval_output_tokens = self_eval_output_tokens
        v5_result.self_eval_thinking_tokens = self_eval_thinking_tokens
        v5_result.self_eval_total_tokens = self_eval_total_tokens
        v5_result.self_eval_prompt = self_eval_prompt
        v5_result.self_eval_raw_response = self_eval_raw_response

        # V6 diagnostic data has no write path to final_answer.
        v5_result.post_self_evaluation_answer = pre_self_evaluation_answer
        v5_result.self_eval_answer_unchanged = v5_result.final_answer == pre_self_evaluation_answer
        v5_result.llm_generation_attempts += self_eval_generation_attempts
        v5_result.llm_generation_count = v5_result.llm_generation_attempts
        v5_result.llm_generation_success_count += 1 if self_eval_generation_success else 0
        max_v6_gens = 5 if getattr(self, "_is_v9", False) else 4
        max_v6_gens = 5 if (getattr(self, "_is_v9", False) or getattr(self, "_is_v10", False)) else 4
        assert v5_result.llm_generation_attempts <= max_v6_gens, f"Exceeds generation cap ({max_v6_gens})"
        assert v5_result.self_eval_answer_unchanged, "V6 self-evaluation mutated the final answer"
        return v5_result

    def __call__(self, question: str, file_path: Optional[str] = None) -> str:
        return self.run(question, file_path=file_path).final_answer


class GAIATargetedRepairAgent(GAIASelfEvaluationAgent):
    """V7 SUSPECT-triggered targeted repair agent.

    Inherits frozen V6 behavior completely. After V6 has performed its read-only
    reliability assessment, this agent triggers exactly one bounded text-only
    targeted repair generation if and only if V6 produced a valid SUSPECT
    assessment on a non-empty answer.
    """

    def run(self, question: str, file_path: Optional[str] = None) -> AgentResult:
        """Runs frozen V6, then performs at most one text-only repair generation if SUSPECT."""
        v6_result = super().run(question, file_path=file_path)
        pre_repair_answer = v6_result.final_answer

        eligible = (
            bool(pre_repair_answer and pre_repair_answer.strip())
            and v6_result.self_eval_success is True
            and v6_result.self_eval_assessment == "SUSPECT"
        )

        v6_result.pre_repair_answer = pre_repair_answer
        v6_result.post_repair_answer = pre_repair_answer
        v6_result.repair_eligible = eligible
        v6_result.repair_triggered = eligible
        v6_result.repair_prompt_version = TARGETED_REPAIR_PROMPT_VERSION if eligible else None
        v6_result.repair_answer_changed = False

        if not eligible:
            v6_result.repair_attempted = False
            v6_result.repair_success = False
            v6_result.repair_action = None
            v6_result.repair_error_type = None
            v6_result.repair_finish_reason = None
            v6_result.repair_generation_attempts = 0
            v6_result.repair_generation_success = False
            v6_result.repair_latency_seconds = None
            v6_result.repair_input_tokens = None
            v6_result.repair_output_tokens = None
            v6_result.repair_thinking_tokens = None
            v6_result.repair_total_tokens = None
            v6_result.repair_prompt = None
            v6_result.repair_raw_response = None
            max_v7_gens = 6 if getattr(self, "_is_v9", False) else 5
            max_v7_gens = 6 if (getattr(self, "_is_v9", False) or getattr(self, "_is_v10", False) or getattr(self, "_is_v11", False)) else 5
            assert v6_result.llm_generation_attempts <= max_v7_gens, f"Exceeds generation cap ({max_v7_gens})"
            return v6_result

        web_evidence = self._existing_web_evidence(v6_result)
        file_evidence, attachment_filename = self._existing_file_context(v6_result)
        execution_summary = self._build_execution_summary(v6_result, file_path)

        repair_prompt = build_targeted_repair_prompt(
            question=question,
            current_answer=pre_repair_answer,
            risk_type=v6_result.self_eval_risk_type,
            confidence=v6_result.self_eval_confidence,
            execution_summary=execution_summary,
            web_evidence=web_evidence,
            file_evidence=file_evidence,
            attachment_filename=attachment_filename,
        )

        repair_generation_attempts = 1
        repair_generation_success = False
        repair_llm_resp = None
        repair_raw_response = None
        repair_error_type = None
        start_time = time.time()

        try:
            # max_retries=0 is intentional: V7 permits exactly one provider attempt.
            repair_llm_resp = self.llm.generate(
                repair_prompt,
                attachment_parts=None,
                max_retries=0,
            )
            repair_generation_success = True
            if isinstance(repair_llm_resp, LLMResponse):
                repair_raw_response = (
                    repair_llm_resp.raw_text
                    if repair_llm_resp.raw_text
                    else repair_llm_resp.text
                )
                if repair_llm_resp.finish_reason == "MALFORMED_FUNCTION_CALL":
                    repair_error_type = "malformed_function_call_finish_reason"
                elif repair_llm_resp.finish_reason != "STOP":
                    repair_error_type = "unexpected_finish_reason"
            else:
                repair_raw_response = str(repair_llm_resp)
                repair_error_type = "unexpected_provider_response_type"
        except Exception as exc:
            error_text = str(exc).lower()
            if "timeout" in error_text or "timed out" in error_text or "deadline" in error_text:
                repair_error_type = "provider_timeout"
            elif "malformed_function_call" in error_text:
                repair_error_type = "malformed_function_call_finish_reason"
            else:
                repair_error_type = "provider_api_error"

        repair_latency = round(time.time() - start_time, 2)
        repair_finish_reason = getattr(repair_llm_resp, "finish_reason", None) if repair_llm_resp else None
        repair_input_tokens = getattr(repair_llm_resp, "input_tokens", None) if repair_llm_resp else None
        repair_output_tokens = getattr(repair_llm_resp, "output_tokens", None) if repair_llm_resp else None
        repair_thinking_tokens = getattr(repair_llm_resp, "thinking_tokens", None) if repair_llm_resp else None
        repair_total_tokens = getattr(repair_llm_resp, "total_tokens", None) if repair_llm_resp else None
        if (
            repair_total_tokens is None
            and repair_input_tokens is not None
            and repair_output_tokens is not None
        ):
            repair_total_tokens = repair_input_tokens + repair_output_tokens

        parsed = None
        if repair_error_type is None:
            parsed = parse_targeted_repair_result(
                repair_raw_response,
                original_answer=pre_repair_answer,
            )
            if not parsed.is_valid:
                repair_error_type = parsed.error_type

        # Action resolution and answer assignment
        final_answer = pre_repair_answer
        repair_action = None
        repair_success = False
        repair_answer_changed = False

        if parsed and parsed.is_valid and repair_error_type is None:
            repair_success = True
            repair_action = parsed.action
            if parsed.action == "KEEP":
                final_answer = pre_repair_answer
                repair_answer_changed = False
            elif parsed.action == "REPLACE":
                final_answer = parsed.final_answer
                repair_answer_changed = (final_answer != pre_repair_answer)
        else:
            # Failure policy: preserve pre_repair_answer
            final_answer = pre_repair_answer
            repair_success = False
            repair_action = None
            repair_answer_changed = False

        v6_result.final_answer = final_answer
        v6_result.post_repair_answer = final_answer
        v6_result.repair_attempted = True
        v6_result.repair_success = repair_success
        v6_result.repair_action = repair_action
        v6_result.repair_answer_changed = repair_answer_changed
        v6_result.repair_error_type = repair_error_type
        v6_result.repair_finish_reason = repair_finish_reason
        v6_result.repair_generation_attempts = repair_generation_attempts
        v6_result.repair_generation_success = repair_generation_success
        v6_result.repair_latency_seconds = repair_latency
        v6_result.repair_input_tokens = repair_input_tokens
        v6_result.repair_output_tokens = repair_output_tokens
        v6_result.repair_thinking_tokens = repair_thinking_tokens
        v6_result.repair_total_tokens = repair_total_tokens
        v6_result.repair_prompt = repair_prompt
        v6_result.repair_raw_response = repair_raw_response

        v6_result.llm_generation_attempts += repair_generation_attempts
        v6_result.llm_generation_count = v6_result.llm_generation_attempts
        v6_result.llm_generation_success_count += 1 if repair_generation_success else 0

        max_v7_gens = (
            6
            if (getattr(self, "_is_v9", False) or getattr(self, "_is_v10", False))
            if (getattr(self, "_is_v9", False) or getattr(self, "_is_v10", False) or getattr(self, "_is_v11", False))
            else 5
        )
        assert v6_result.llm_generation_attempts <= max_v7_gens, f"Exceeds generation cap ({max_v7_gens})"
        return v6_result

    def __call__(self, question: str, file_path: Optional[str] = None) -> str:
        return self.run(question, file_path=file_path).final_answer


# ==============================================================================
# V9 — Upstream Candidate Recovery Architecture & Taxonomy Helpers
# ==============================================================================

ELIGIBLE_RECOVERY_FAILURE_CLASSES = {
    "PYTHON_OUTPUT_MISSING_MARKER",
    "PYTHON_EXECUTION_FAILURE",
    "PYTHON_CODE_EXTRACTION_FAILURE",
    "MALFORMED_FUNCTION_CALL",
    "FUNCTION_CALL_ONLY",
    "THOUGHT_ONLY",
    "DIRECT_EXTRACTION_FAILURE",
    "EMPTY_RESPONSE",
}


def classify_candidate_recovery_failure(result: AgentResult, worker_mode: Optional[str] = None) -> Optional[str]:
    """Deterministically classifies upstream candidate failure in strict precedence order.

    Returns:
        One of the mutually exclusive failure classes, or None if candidate already exists.
    """
    # If a candidate answer exists, there is no candidate starvation
    if result.final_answer and str(result.final_answer).strip():
        return None

    effective_worker_mode = worker_mode or result.worker_mode

    # 1. PROVIDER_ERROR (Highest priority; strictly ineligible)
    if (
        result.worker_error_type in {"provider_timeout", "provider_api_error"}
        or result.router_error_type in {"provider_timeout", "provider_api_error"}
        or getattr(result, "error_type", None) in {"provider_timeout", "provider_api_error"}
    ):
        return "PROVIDER_ERROR"

    # 2. PYTHON_OUTPUT_MISSING_MARKER
    if (
        effective_worker_mode == "PYTHON"
        and result.python_executed is True
        and result.python_result is not None
        and getattr(result.python_result, "error_type", None) == "MissingFinalAnswerMarker"
    ):
        return "PYTHON_OUTPUT_MISSING_MARKER"

    # 3. PYTHON_EXECUTION_FAILURE
    if (
        effective_worker_mode == "PYTHON"
        and result.python_executed is True
        and result.python_result is not None
        and getattr(result.python_result, "success", False) is False
        and getattr(result.python_result, "error_type", None) != "MissingFinalAnswerMarker"
    ):
        return "PYTHON_EXECUTION_FAILURE"

    # 4. PYTHON_CODE_EXTRACTION_FAILURE
    if (
        effective_worker_mode == "PYTHON"
        and (result.python_requested is False or getattr(result, "error_type", None) == "python_code_extraction_failure")
    ):
        return "PYTHON_CODE_EXTRACTION_FAILURE"

    # 5. MALFORMED_FUNCTION_CALL
    worker_resp = result.llm_response
    worker_finish = getattr(worker_resp, "finish_reason", None) if worker_resp else None
    if (
        result.worker_error_type == "malformed_function_call_finish_reason"
        or worker_finish == "MALFORMED_FUNCTION_CALL"
    ):
        return "MALFORMED_FUNCTION_CALL"

    # 6. FUNCTION_CALL_ONLY
    has_func = getattr(worker_resp, "has_function_call_part", False) if worker_resp else False
    has_text = getattr(worker_resp, "has_text_part", False) if worker_resp else False
    if (
        has_func is True
        and has_text is False
        and result.worker_error_type != "malformed_function_call_finish_reason"
    ):
        return "FUNCTION_CALL_ONLY"

    # 7. THOUGHT_ONLY
    part_types = getattr(worker_resp, "response_part_types", []) if worker_resp else []
    thinking_tok = getattr(worker_resp, "thinking_tokens", 0) or 0
    output_tok = getattr(worker_resp, "output_tokens", 0) or 0
    if (
        ("thought" in part_types or (thinking_tok > 0 and output_tok == 0))
        and has_text is False
        and has_func is False
    ):
        return "THOUGHT_ONLY"

    # 8. DIRECT_EXTRACTION_FAILURE
    if (
        effective_worker_mode == "DIRECT"
        and result.worker_raw_response is not None
        and str(result.worker_raw_response).strip() != ""
    ):
        return "DIRECT_EXTRACTION_FAILURE"

    # 9. EMPTY_RESPONSE (Last-resort semantic empty class)
    raw_empty = (not result.worker_raw_response or not str(result.worker_raw_response).strip())
    if (
        result.worker_error_type in (None, "empty_worker_response")
        and raw_empty
    ):
        return "EMPTY_RESPONSE"

    # 10. UNKNOWN_NO_CANDIDATE
    return "UNKNOWN_NO_CANDIDATE"


def is_candidate_recovery_eligible(
    failure_class_or_candidate: Optional[str],
    failure_class: Optional[str] = None,
) -> bool:
    """Determines whether an upstream failure is eligible for V9 candidate recovery.

    Supports both signatures:
    - is_candidate_recovery_eligible(pre_recovery_candidate, failure_class)
    - is_candidate_recovery_eligible(failure_class)
    """
    if failure_class is None:
        return failure_class_or_candidate in ELIGIBLE_RECOVERY_FAILURE_CLASSES
    if failure_class_or_candidate and str(failure_class_or_candidate).strip():
        return False
    return failure_class in ELIGIBLE_RECOVERY_FAILURE_CLASSES


class GAIAUpstreamCandidateRecoveryAgent(GAIATargetedRepairAgent):
    """V9 Upstream Candidate Recovery Agent.

    Inherits the exact Frozen V7 pipeline:
    Tavily search -> FileTool -> Router LLM -> Worker LLM -> post-worker recovery hook
    -> V5 Verifier -> V6 Self-Evaluator -> V7 Targeted Repair -> Final Answer.

    Only intervenes if the upstream worker failed to produce a candidate answer
    due to an eligible semantic/execution failure.
    If the worker already produced a candidate answer, recovery is strictly bypassed
    and the candidate is preserved 100% verbatim at the recovery boundary.
    """

    _is_v9: bool = True

    def _build_sanitized_execution_snippet(self, result: AgentResult) -> Optional[str]:
        py_res = result.python_result
        if not py_res:
            return None
        parts = []
        if py_res.error_message:
            parts.append(f"Error: {str(py_res.error_message).strip()}")
        if py_res.stderr:
            parts.append(f"Stderr: {str(py_res.stderr).strip()[:200]}")
        if py_res.stdout:
            tail_stdout = str(py_res.stdout).strip()[-200:]
            parts.append(f"Stdout: {tail_stdout}")
        if not parts:
            return None
        combined = " | ".join(parts)
        # Redact long tokens or credentials
        combined = re.sub(r"[A-Za-z0-9_-]{25,}", "[REDACTED]", combined)
        return combined[:500]

    @staticmethod
    def _existing_file_context_text_only(result: AgentResult) -> tuple[str, str]:
        """Returns already-extracted text context only; V9 never rereads a file and is text-only."""
        file_res = result.file_result
        if not file_res or result.file_fallback:
            return "", ""
        filename = str(getattr(file_res, "file_name", "") or "")
        text_content = str(getattr(file_res, "text_content", "") or "")
        if text_content.strip():
            return text_content, filename
        if filename:
            mime = getattr(file_res, "mime_type", "unknown")
            return f"[Attachment '{filename}' ({mime}) was processed upstream but has no extracted text context.]", filename
        return "", ""

    def _post_worker_candidate_hook(
        self,
        question: str,
        file_path: Optional[str],
        result: AgentResult,
    ) -> AgentResult:
        pre_recovery_candidate = result.final_answer or ""

        # Case 1: Worker already produced a non-empty candidate answer -> strictly bypass
        if pre_recovery_candidate and pre_recovery_candidate.strip():
            result.pre_recovery_candidate = pre_recovery_candidate
            result.post_recovery_candidate = pre_recovery_candidate
            result.candidate_recovery_eligible = False
            result.candidate_recovery_triggered = False
            result.candidate_recovery_attempted = False
            result.candidate_recovery_success = False
            result.candidate_recovery_action = "SKIP"
            result.candidate_recovery_recovered = False
            result.candidate_recovery_parse_success = False
            result.candidate_recovery_candidate_changed = False
            result.candidate_recovery_logical_generation_count = 0
            result.candidate_recovery_generation_attempts = 0
            result.candidate_recovery_generation_success = False
            result.candidate_recovery_non_triggered_preserved = True
            result.candidate_recovery_searches_added = 0
            result.candidate_recovery_python_runs_added = 0
            assert result.post_recovery_candidate == result.pre_recovery_candidate, "Non-triggered preservation violation"
            return result

        # Case 2: Candidate is empty -> classify failure
        result.pre_recovery_candidate = ""
        result.post_recovery_candidate = ""

        failure_class = classify_candidate_recovery_failure(result)
        result.candidate_recovery_failure_class = failure_class
        eligible = is_candidate_recovery_eligible(pre_recovery_candidate, failure_class)
        result.candidate_recovery_eligible = eligible
        result.candidate_recovery_triggered = eligible

        if not eligible:
            result.candidate_recovery_attempted = False
            result.candidate_recovery_success = False
            result.candidate_recovery_action = "SKIP"
            result.candidate_recovery_recovered = False
            result.candidate_recovery_parse_success = False
            result.candidate_recovery_candidate_changed = False
            result.candidate_recovery_logical_generation_count = 0
            result.candidate_recovery_generation_attempts = 0
            result.candidate_recovery_generation_success = False
            result.candidate_recovery_non_triggered_preserved = True
            result.candidate_recovery_searches_added = 0
            result.candidate_recovery_python_runs_added = 0
            assert result.post_recovery_candidate == result.pre_recovery_candidate, "Non-triggered preservation violation"
            return result

        # Case 3: Eligible candidate recovery opportunity
        result.candidate_recovery_attempted = True
        result.candidate_recovery_logical_generation_count = 1
        result.candidate_recovery_generation_attempts = 1
        result.candidate_recovery_prompt_version = CANDIDATE_RECOVERY_PROMPT_VERSION
        result.candidate_recovery_non_triggered_preserved = True
        result.candidate_recovery_searches_added = 0
        result.candidate_recovery_python_runs_added = 0

        web_evidence = self._existing_web_evidence(result)
        file_evidence, attachment_filename = self._existing_file_context_text_only(result)
        execution_snippet = self._build_sanitized_execution_snippet(result)

        recovery_prompt = build_candidate_recovery_prompt(
            question=question,
            web_evidence=web_evidence,
            file_evidence=file_evidence,
            attachment_filename=attachment_filename,
            router_decision=result.router_decision or result.worker_mode,
            failure_class=failure_class,
            execution_snippet=execution_snippet,
        )
        result.candidate_recovery_prompt = recovery_prompt

        recovery_start = time.time()
        recovery_llm_resp = None
        recovery_raw_response = None
        recovery_error_type = None
        recovery_generation_success = False

        try:
            # max_retries=0: V9 permits exactly one logical provider attempt
            recovery_llm_resp = self.llm.generate(
                recovery_prompt,
                attachment_parts=None,
                max_retries=0,
            )
            recovery_generation_success = True
            if isinstance(recovery_llm_resp, LLMResponse):
                recovery_raw_response = (
                    recovery_llm_resp.raw_text
                    if recovery_llm_resp.raw_text
                    else recovery_llm_resp.text
                )
                if recovery_llm_resp.finish_reason == "MALFORMED_FUNCTION_CALL":
                    recovery_error_type = "malformed_function_call"
                elif recovery_llm_resp.finish_reason != "STOP":
                    recovery_error_type = "unexpected_finish_reason"
            else:
                recovery_raw_response = str(recovery_llm_resp)
                recovery_error_type = "unexpected_provider_response_type"
        except Exception as exc:
            err_text = str(exc).lower()
            if "timeout" in err_text or "timed out" in err_text or "deadline" in err_text:
                recovery_error_type = "provider_timeout"
            elif "malformed_function_call" in err_text:
                recovery_error_type = "malformed_function_call"
            else:
                recovery_error_type = "provider_api_error"
            result.candidate_recovery_error_message = str(exc)

        recovery_latency = round(time.time() - recovery_start, 2)
        result.candidate_recovery_latency_seconds = recovery_latency
        result.candidate_recovery_raw_response = recovery_raw_response

        finish_reason = getattr(recovery_llm_resp, "finish_reason", None) if recovery_llm_resp else None
        part_types = getattr(recovery_llm_resp, "response_part_types", []) if recovery_llm_resp else []
        has_text = getattr(recovery_llm_resp, "has_text_part", False) if recovery_llm_resp else False
        has_func = getattr(recovery_llm_resp, "has_function_call_part", False) if recovery_llm_resp else False

        result.candidate_recovery_finish_reason = finish_reason
        result.candidate_recovery_response_part_types = part_types
        result.candidate_recovery_has_text_part = has_text
        result.candidate_recovery_has_function_call_part = has_func

        in_tok = getattr(recovery_llm_resp, "input_tokens", None) if recovery_llm_resp else None
        out_tok = getattr(recovery_llm_resp, "output_tokens", None) if recovery_llm_resp else None
        th_tok = getattr(recovery_llm_resp, "thinking_tokens", None) if recovery_llm_resp else None
        tot_tok = getattr(recovery_llm_resp, "total_tokens", None) if recovery_llm_resp else None
        if tot_tok is None and in_tok is not None and out_tok is not None:
            tot_tok = in_tok + out_tok

        result.candidate_recovery_input_tokens = in_tok
        result.candidate_recovery_output_tokens = out_tok
        result.candidate_recovery_thinking_tokens = th_tok
        result.candidate_recovery_total_tokens = tot_tok

        # Parse recovery result
        parsed: Optional[CandidateRecoveryParseResult] = None
        if recovery_error_type is None:
            parsed = parse_candidate_recovery_result(recovery_raw_response)
            if not parsed.is_valid:
                recovery_error_type = parsed.error_type

        result.candidate_recovery_generation_success = recovery_generation_success
        result.candidate_recovery_error_type = recovery_error_type

        if parsed and parsed.is_valid and recovery_error_type is None:
            cleaned_candidate = self.clean_answer(parsed.candidate_answer or "")
            if cleaned_candidate:
                result.post_recovery_candidate = cleaned_candidate
                result.final_answer = cleaned_candidate
                result.candidate_recovery_success = True
                result.candidate_recovery_action = "RECOVER"
                result.candidate_recovery_recovered = True
                result.candidate_recovery_parse_success = True
                result.candidate_recovery_candidate_changed = True
            else:
                result.post_recovery_candidate = ""
                result.final_answer = ""
                result.candidate_recovery_success = False
                result.candidate_recovery_action = "SKIP"
                result.candidate_recovery_recovered = False
                result.candidate_recovery_parse_success = False
                result.candidate_recovery_candidate_changed = False
                result.candidate_recovery_error_type = "empty_final_value"
        else:
            result.post_recovery_candidate = ""
            result.final_answer = ""
            result.candidate_recovery_success = False
            result.candidate_recovery_action = "SKIP"
            result.candidate_recovery_recovered = False
            result.candidate_recovery_parse_success = False
            result.candidate_recovery_candidate_changed = False

        # Accounting: logical LLM generation attempts
        result.llm_generation_attempts += 1
        result.llm_generation_count = result.llm_generation_attempts
        if recovery_generation_success:
            result.llm_generation_success_count += 1

        return result

    def run(self, question: str, file_path: Optional[str] = None) -> AgentResult:
        result = super().run(question, file_path=file_path)
        if result.candidate_recovery_triggered is False:
            assert result.llm_generation_attempts <= 5, "Non-triggered V9 exceeds five-generation cap"
            assert result.post_recovery_candidate == result.pre_recovery_candidate, "Non-triggered recovery boundary preservation violation"
        else:
            assert result.llm_generation_attempts <= 6, "Triggered V9 exceeds six-generation cap"
        return result


class GAIAPlannerExecutorAgent(GAIAUpstreamCandidateRecoveryAgent):
    """V10 Structured Planner -> Plan-Guided Executor Agent.

    Replaces the coarse capability router (Router -> Worker) upstream pair
    with a Structured Planner (Slot 1) and Plan-Guided Executor (Slot 2).
    Preserves all downstream stages (V9 candidate recovery, V5 verifier,
    V6 self-evaluator, V7 targeted repair).
    """

    _is_v10: bool = True
    _is_v9: bool = False

    def __init__(
        self,
        llm_client: Any,
        search_tool: Optional[Any] = None,
        file_tool: Optional[Any] = None,
        python_tool: Optional[Any] = None,
        tavily_tool: Optional[Any] = None,
    ):
        super().__init__(
            llm_client=llm_client,
            search_tool=search_tool,
            file_tool=file_tool,
            python_tool=python_tool,
            tavily_tool=tavily_tool,
        )
        self.prompt_version = PLANNER_PROMPT_VERSION
        self.primary_prompt_version = PLANNER_PROMPT_VERSION
        self.fallback_prompt_version = None

    def _execute_upstream_pair_from_context(self, context: UpstreamContext) -> AgentResult:
        """Executes the V10 Structured Planner (Slot 1) -> Plan-Guided Executor (Slot 2) pair."""
        import time

        question = context.question
        file_path = context.file_path
        web_evidence = context.web_evidence
        file_evidence = context.file_evidence
        attachment_filename = context.attachment_filename
        search_res = context.search_res
        search_fallback = context.search_fallback
        file_res = context.file_res
        file_fallback = context.file_fallback
        attachment_parts = context.attachment_parts

        # 1. Slot 1: Structured Planner Generation (Generation #1)
        planner_prompt = build_planner_prompt(
            question=question,
            web_evidence=web_evidence if (search_res and search_res.success) else "[Web search unavailable]",
            file_evidence=file_evidence,
            attachment_filename=attachment_filename,
        )

        planner_generation_attempts = 1
        planner_generation_success = False
        planner_llm_resp = None
        planner_raw_response = None
        planner_error_type = None
        planner_start = time.time()

        try:
            planner_llm_resp = self.llm.generate(planner_prompt, attachment_parts=attachment_parts)
            planner_generation_success = True
            if isinstance(planner_llm_resp, LLMResponse):
                planner_raw_response = planner_llm_resp.raw_text if planner_llm_resp.raw_text else planner_llm_resp.text
                if planner_llm_resp.finish_reason == "MALFORMED_FUNCTION_CALL":
                    planner_error_type = "malformed_function_call_finish_reason"
                elif planner_llm_resp.finish_reason not in (None, "", "STOP"):
                    planner_error_type = "unexpected_finish_reason"
            else:
                planner_raw_response = str(planner_llm_resp)
        except Exception as e:
            err_str = str(e).lower()
            if "timeout" in err_str or "deadline" in err_str:
                planner_error_type = "provider_timeout"
            elif "malformed_function_call" in err_str:
                planner_error_type = "malformed_function_call_finish_reason"
            else:
                planner_error_type = "provider_api_error"
            planner_raw_response = None

        planner_latency = round(time.time() - planner_start, 2)
        planner_input_tokens = getattr(planner_llm_resp, "input_tokens", None) if planner_llm_resp else None
        planner_output_tokens = getattr(planner_llm_resp, "output_tokens", None) if planner_llm_resp else None
        planner_thinking_tokens = getattr(planner_llm_resp, "thinking_tokens", None) if planner_llm_resp else None
        planner_total_tokens = getattr(planner_llm_resp, "total_tokens", None) if planner_llm_resp else None
        if planner_total_tokens is None and (planner_input_tokens is not None or planner_output_tokens is not None):
            planner_total_tokens = (planner_input_tokens or 0) + (planner_output_tokens or 0) + (planner_thinking_tokens or 0)

        # Parse planner output
        if planner_error_type is not None:
            parse_res = PlannerParseResult(
                success=False,
                plan_spec=build_fallback_plan(question=question, raw_text="", error_message=planner_error_type),
                error_message=planner_error_type,
            )
        elif planner_raw_response is None or not planner_raw_response.strip():
            planner_error_type = "empty_provider_response"
            parse_res = PlannerParseResult(
                success=False,
                plan_spec=build_fallback_plan(question=question, raw_text="", error_message=planner_error_type),
                error_message=planner_error_type,
            )
        else:
            parse_res = parse_planner_result(planner_raw_response)
            if not parse_res.success:
                planner_error_type = parse_res.error_message

        plan_spec = parse_res.plan_spec
        planner_success = parse_res.success and (planner_error_type is None)
        planner_parse_success = parse_res.success
        planner_fallback_used = plan_spec.is_fallback

        # 2. Slot 2: Plan-Guided Executor Generation (Generation #2)
        executor_mode = plan_spec.mode
        if executor_mode == "DIRECT":
            executor_prompt_ver = EXECUTOR_DIRECT_PROMPT_VERSION
            executor_prompt = build_direct_executor_prompt(
                question=question,
                plan_spec=plan_spec,
                web_evidence=web_evidence if (search_res and search_res.success) else "[Web search unavailable]",
                file_evidence=file_evidence,
                attachment_filename=attachment_filename,
            )
        else:
            executor_prompt_ver = EXECUTOR_PYTHON_PROMPT_VERSION
            executor_prompt = build_python_executor_prompt(
                question=question,
                plan_spec=plan_spec,
                web_evidence=web_evidence if (search_res and search_res.success) else "[Web search unavailable]",
                file_evidence=file_evidence,
                attachment_filename=attachment_filename,
            )

        executor_generation_attempts = 1
        executor_generation_success = False
        executor_llm_resp = None
        executor_raw_response = None
        executor_error_type = None
        executor_start = time.time()

        try:
            executor_llm_resp = self.llm.generate(executor_prompt, attachment_parts=attachment_parts)
            executor_generation_success = True
            if isinstance(executor_llm_resp, LLMResponse):
                executor_raw_response = executor_llm_resp.raw_text if executor_llm_resp.raw_text else executor_llm_resp.text
                if executor_llm_resp.finish_reason == "MALFORMED_FUNCTION_CALL":
                    executor_error_type = "malformed_function_call_finish_reason"
            else:
                executor_raw_response = str(executor_llm_resp)
        except Exception as e:
            err_str = str(e).lower()
            if "timeout" in err_str or "deadline" in err_str:
                executor_error_type = "provider_timeout"
            elif "malformed_function_call" in err_str:
                executor_error_type = "malformed_function_call_finish_reason"
            else:
                executor_error_type = "provider_api_error"
            executor_raw_response = None

        executor_latency = round(time.time() - executor_start, 2)

        if executor_error_type is None and (executor_raw_response is None or not executor_raw_response.strip()):
            executor_error_type = "empty_worker_response"

        executor_input_tokens = getattr(executor_llm_resp, "input_tokens", None) if executor_llm_resp else None
        executor_output_tokens = getattr(executor_llm_resp, "output_tokens", None) if executor_llm_resp else None
        executor_thinking_tokens = getattr(executor_llm_resp, "thinking_tokens", None) if executor_llm_resp else None
        executor_total_tokens = getattr(executor_llm_resp, "total_tokens", None) if executor_llm_resp else None
        if executor_total_tokens is None and (executor_input_tokens is not None or executor_output_tokens is not None):
            executor_total_tokens = (executor_input_tokens or 0) + (executor_output_tokens or 0) + (executor_thinking_tokens or 0)

        # 3. Extract Answer / Execute Python
        py_result: Optional[PythonResult] = None
        python_requested = False
        python_executed = False
        python_fallback = False
        final_answer = ""
        executor_success = False

        if executor_mode == "DIRECT":
            python_requested = False
            python_executed = False
            python_fallback = False
            final_answer = self.clean_answer(extract_direct_answer(executor_raw_response or ""))
            executor_success = bool(final_answer and not executor_error_type)
        else:
            code = extract_python_code(executor_raw_response or "")
            python_requested = bool(code)
            if code:
                python_executed = True
                py_result = self.python_tool.execute(code, attachment_path=file_path)
                if py_result.success:
                    extracted_ans = extract_python_final_answer(py_result.stdout)
                    if extracted_ans is not None:
                        final_answer = self.clean_answer(extracted_ans)
                        python_fallback = False
                        executor_success = True
                    else:
                        python_fallback = True
                        py_result.success = False
                        py_result.error_type = py_result.error_type or "MissingFinalAnswerMarker"
                        py_result.error_message = (
                            py_result.error_message
                            or "Python execution succeeded but stdout did not contain 'FINAL_ANSWER:' marker"
                        )
                        final_answer = (
                            self.clean_answer(extract_direct_answer(executor_raw_response))
                            if executor_raw_response and "FINAL:" in executor_raw_response
                            else ""
                        )
                        executor_success = False
                else:
                    python_fallback = True
                    final_answer = (
                        self.clean_answer(extract_direct_answer(executor_raw_response))
                        if executor_raw_response and "FINAL:" in executor_raw_response
                        else ""
                    )
                    executor_success = False
            else:
                python_requested = False
                python_executed = False
                python_fallback = True
                final_answer = (
                    self.clean_answer(extract_direct_answer(executor_raw_response or ""))
                    if executor_raw_response and "FINAL:" in executor_raw_response
                    else ""
                )
                executor_success = False

        llm_generation_attempts = planner_generation_attempts + executor_generation_attempts
        llm_generation_success_count = (1 if planner_generation_success else 0) + (1 if executor_generation_success else 0)

        raw_resp = executor_raw_response or ""
        norm_resp = raw_resp.strip()

        fallback_pv = EXECUTOR_DIRECT_PROMPT_VERSION if planner_fallback_used else None

        agent_result = AgentResult(
            raw_response=raw_resp,
            normalized_response=norm_resp,
            final_answer=final_answer,
            candidate_answer=final_answer,
            llm_response=executor_llm_resp if isinstance(executor_llm_resp, LLMResponse) else None,
            prompt=executor_prompt,
            prompt_version=PLANNER_PROMPT_VERSION,
            primary_prompt_version=PLANNER_PROMPT_VERSION,
            fallback_prompt_version=fallback_pv,
            search_result=search_res,
            search_fallback=search_fallback,
            file_result=file_res,
            file_fallback=file_fallback,
            python_result=py_result,
            python_requested=python_requested,
            python_executed=python_executed,
            python_fallback=python_fallback,
            python_prompt_version=EXECUTOR_PYTHON_PROMPT_VERSION if executor_mode == "PYTHON" else None,
            python_prompt=executor_prompt if executor_mode == "PYTHON" else None,
            llm_generation_count=llm_generation_attempts,

            # Planner telemetry
            planner_prompt_version=PLANNER_PROMPT_VERSION,
            planner_attempted=True,
            planner_success=planner_success,
            planner_parse_success=planner_parse_success,
            planner_fallback_used=planner_fallback_used,
            planner_mode=plan_spec.mode,
            planner_objective=plan_spec.objective,
            planner_evidence_needed=plan_spec.evidence_needed,
            plan_step_count=len(plan_spec.plan_steps),
            plan_steps=plan_spec.plan_steps,
            plan_answer_type=plan_spec.answer_type,
            planner_error_type=planner_error_type,
            planner_prompt=planner_prompt,
            planner_raw_response=planner_raw_response,
            planner_latency_seconds=planner_latency,
            planner_input_tokens=planner_input_tokens,
            planner_output_tokens=planner_output_tokens,
            planner_thinking_tokens=planner_thinking_tokens,
            planner_total_tokens=planner_total_tokens,
            planner_generation_attempts=planner_generation_attempts,
            planner_generation_success=planner_generation_success,

            # Executor telemetry
            executor_mode=executor_mode,
            executor_plan_used=True,
            executor_success=executor_success,
            executor_error_type=executor_error_type,
            executor_prompt_version=executor_prompt_ver,
            executor_prompt=executor_prompt,
            executor_raw_response=executor_raw_response,
            executor_latency_seconds=executor_latency,
            executor_input_tokens=executor_input_tokens,
            executor_output_tokens=executor_output_tokens,
            executor_thinking_tokens=executor_thinking_tokens,
            executor_total_tokens=executor_total_tokens,
            executor_generation_attempts=executor_generation_attempts,
            executor_generation_success=executor_generation_success,

            # Worker compatibility aliases (for Frozen V9 candidate recovery classifier)
            worker_mode=executor_mode,
            worker_success=executor_success,
            worker_error_type=executor_error_type,
            worker_prompt_version=executor_prompt_ver,
            worker_prompt=executor_prompt,
            worker_raw_response=executor_raw_response,
            worker_latency_seconds=executor_latency,
            worker_input_tokens=executor_input_tokens,
            worker_output_tokens=executor_output_tokens,
            worker_thinking_tokens=executor_thinking_tokens,
            worker_generation_attempts=executor_generation_attempts,
            worker_generation_success=executor_generation_success,

            # Router compatibility aliases
            router_requested=False,
            router_decision=plan_spec.mode,
            router_success=planner_success,
            router_fallback=planner_fallback_used,
            router_error_type=planner_error_type,
            router_prompt_version=PLANNER_PROMPT_VERSION,
            router_prompt=planner_prompt,
            router_raw_response=planner_raw_response,
            router_latency_seconds=planner_latency,
            router_input_tokens=planner_input_tokens,
            router_output_tokens=planner_output_tokens,
            router_thinking_tokens=planner_thinking_tokens,
            router_generation_attempts=planner_generation_attempts,
            router_generation_success=planner_generation_success,

            llm_generation_attempts=llm_generation_attempts,
            llm_generation_success_count=llm_generation_success_count,
        )
        return agent_result

    def run(self, question: str, file_path: Optional[str] = None) -> AgentResult:
        result = super().run(question, file_path=file_path)
        if result.candidate_recovery_triggered is False:
            assert result.llm_generation_attempts <= 5, "Non-triggered V10 exceeds five-generation cap"
            assert result.post_recovery_candidate == result.pre_recovery_candidate, "Non-triggered recovery boundary preservation violation"
        else:
            assert result.llm_generation_attempts <= 6, "Triggered V10 exceeds six-generation cap"
        return result


def _compute_sha256(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class V11ExecutorResult:
    """Pre-recovery candidate boundary execution result from Plan-Guided Executor (Slot 2)."""
    candidate_answer: str
    python_requested: bool
    python_executed: bool
    python_fallback: bool
    executor_success: bool
    raw_response: Optional[str]
    error_type: Optional[str]
    latency_seconds: Optional[float]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    thinking_tokens: Optional[int]
    total_tokens: Optional[int]
    py_result: Optional[PythonResult]
    prompt_version: str
    prompt: str
    llm_response: Optional[LLMResponse] = None


def _execute_v11_executor_from_plan(
    agent: Any,
    question: str,
    plan_spec: Any,
    combined_web_evidence: str,
    file_evidence: str,
    attachment_filename: str,
    attachment_parts: Any,
    file_path: Optional[str] = None,
) -> V11ExecutorResult:
    """Executes Plan-Guided Executor (Slot 2) under shared plan and combined evidence.

    Shared between canonical V11 and within-task paired retrieval branches (Branch A/B).
    Enforces identical prompt construction, LLM generation, finish-reason handling,
    and Python execution.
    """
    import time

    executor_mode = plan_spec.mode
    if executor_mode == "DIRECT":
        executor_prompt_ver = EXECUTOR_DIRECT_PROMPT_VERSION
        executor_prompt = build_direct_executor_prompt(
            question=question,
            plan_spec=plan_spec,
            web_evidence=combined_web_evidence,
            file_evidence=file_evidence,
            attachment_filename=attachment_filename,
        )
    else:
        executor_prompt_ver = EXECUTOR_PYTHON_PROMPT_VERSION
        executor_prompt = build_python_executor_prompt(
            question=question,
            plan_spec=plan_spec,
            web_evidence=combined_web_evidence,
            file_evidence=file_evidence,
            attachment_filename=attachment_filename,
        )

    executor_generation_attempts = 1
    executor_generation_success = False
    executor_llm_resp = None
    executor_raw_response = None
    executor_error_type = None
    executor_start = time.time()

    try:
        executor_llm_resp = agent.llm.generate(executor_prompt, attachment_parts=attachment_parts)
        executor_generation_success = True
        if isinstance(executor_llm_resp, LLMResponse):
            executor_raw_response = executor_llm_resp.raw_text if executor_llm_resp.raw_text else executor_llm_resp.text
            if executor_llm_resp.finish_reason == "MALFORMED_FUNCTION_CALL":
                executor_error_type = "malformed_function_call_finish_reason"
            elif executor_llm_resp.finish_reason not in (None, "", "STOP"):
                executor_error_type = "unexpected_finish_reason"
        else:
            executor_raw_response = str(executor_llm_resp)
    except Exception as e:
        err_str = str(e).lower()
        if "timeout" in err_str or "deadline" in err_str:
            executor_error_type = "provider_timeout"
        elif "malformed_function_call" in err_str:
            executor_error_type = "malformed_function_call_finish_reason"
        else:
            executor_error_type = "provider_api_error"
        executor_raw_response = None

    executor_latency = round(time.time() - executor_start, 2)

    if executor_error_type is None and (executor_raw_response is None or not executor_raw_response.strip()):
        executor_error_type = "empty_worker_response"

    executor_input_tokens = getattr(executor_llm_resp, "input_tokens", None) if executor_llm_resp else None
    executor_output_tokens = getattr(executor_llm_resp, "output_tokens", None) if executor_llm_resp else None
    executor_thinking_tokens = getattr(executor_llm_resp, "thinking_tokens", None) if executor_llm_resp else None
    executor_total_tokens = getattr(executor_llm_resp, "total_tokens", None) if executor_llm_resp else None
    if executor_total_tokens is None and (executor_input_tokens is not None or executor_output_tokens is not None):
        executor_total_tokens = (executor_input_tokens or 0) + (executor_output_tokens or 0) + (executor_thinking_tokens or 0)

    # Extract Answer / Execute Python
    py_result: Optional[PythonResult] = None
    python_requested = False
    python_executed = False
    python_fallback = False
    final_answer = ""
    executor_success = False

    if executor_mode == "DIRECT":
        python_requested = False
        python_executed = False
        python_fallback = False
        final_answer = agent.clean_answer(extract_direct_answer(executor_raw_response or ""))
        executor_success = bool(final_answer and not executor_error_type)
    else:
        if executor_error_type is not None:
            python_requested = False
            python_executed = False
            python_fallback = True
            final_answer = (
                agent.clean_answer(extract_direct_answer(executor_raw_response or ""))
                if executor_raw_response and "FINAL:" in executor_raw_response
                else ""
            )
            executor_success = False
        else:
            code = extract_python_code(executor_raw_response or "")
            python_requested = bool(code)
            if code:
                python_executed = True
                py_result = agent.python_tool.execute(code, attachment_path=file_path)
                if py_result.success:
                    extracted_ans = extract_python_final_answer(py_result.stdout)
                    if extracted_ans is not None:
                        final_answer = agent.clean_answer(extracted_ans)
                        python_fallback = False
                        executor_success = True
                    else:
                        python_fallback = True
                        py_result.success = False
                        py_result.error_type = py_result.error_type or "MissingFinalAnswerMarker"
                        py_result.error_message = (
                            py_result.error_message
                            or "Python execution succeeded but stdout did not contain 'FINAL_ANSWER:' marker"
                        )
                        final_answer = (
                            agent.clean_answer(extract_direct_answer(executor_raw_response))
                            if executor_raw_response and "FINAL:" in executor_raw_response
                            else ""
                        )
                        executor_success = False
                else:
                    python_fallback = True
                    final_answer = (
                        agent.clean_answer(extract_direct_answer(executor_raw_response))
                        if executor_raw_response and "FINAL:" in executor_raw_response
                        else ""
                    )
                    executor_success = False
            else:
                python_requested = False
                python_executed = False
                python_fallback = True
                final_answer = (
                    agent.clean_answer(extract_direct_answer(executor_raw_response or ""))
                    if executor_raw_response and "FINAL:" in executor_raw_response
                    else ""
                )
                executor_success = False

    return V11ExecutorResult(
        candidate_answer=final_answer,
        python_requested=python_requested,
        python_executed=python_executed,
        python_fallback=python_fallback,
        executor_success=executor_success,
        raw_response=executor_raw_response,
        error_type=executor_error_type,
        latency_seconds=executor_latency,
        input_tokens=executor_input_tokens,
        output_tokens=executor_output_tokens,
        thinking_tokens=executor_thinking_tokens,
        total_tokens=executor_total_tokens,
        py_result=py_result,
        prompt_version=executor_prompt_ver,
        prompt=executor_prompt,
        llm_response=executor_llm_resp if isinstance(executor_llm_resp, LLMResponse) else None,
    )


def _plan_v11_from_context(
    agent: Any,
    question: str,
    web_evidence_primary: str,
    file_evidence: str,
    attachment_filename: str,
    attachment_parts: Any,
) -> tuple[AdaptivePlannerParseResult, dict]:
    """Generates and parses the Structured Planner v2 output (Slot 1)."""
    import time

    planner_prompt = build_adaptive_planner_prompt(
        question=question,
        web_evidence=web_evidence_primary,
        file_evidence=file_evidence,
        attachment_filename=attachment_filename,
    )

    planner_generation_attempts = 1
    planner_generation_success = False
    planner_llm_resp = None
    planner_raw_response = None
    planner_error_type = None
    planner_start = time.time()

    try:
        planner_llm_resp = agent.llm.generate(planner_prompt, attachment_parts=attachment_parts)
        planner_generation_success = True
        if isinstance(planner_llm_resp, LLMResponse):
            planner_raw_response = planner_llm_resp.raw_text if planner_llm_resp.raw_text else planner_llm_resp.text
            if planner_llm_resp.finish_reason == "MALFORMED_FUNCTION_CALL":
                planner_error_type = "malformed_function_call_finish_reason"
            elif planner_llm_resp.finish_reason not in (None, "", "STOP"):
                planner_error_type = "unexpected_finish_reason"
        else:
            planner_raw_response = str(planner_llm_resp)
    except Exception as e:
        err_str = str(e).lower()
        if "timeout" in err_str or "deadline" in err_str:
            planner_error_type = "provider_timeout"
        elif "malformed_function_call" in err_str:
            planner_error_type = "malformed_function_call_finish_reason"
        else:
            planner_error_type = "provider_api_error"
        planner_raw_response = None

    planner_latency = round(time.time() - planner_start, 2)
    planner_input_tokens = getattr(planner_llm_resp, "input_tokens", None) if planner_llm_resp else None
    planner_output_tokens = getattr(planner_llm_resp, "output_tokens", None) if planner_llm_resp else None
    planner_thinking_tokens = getattr(planner_llm_resp, "thinking_tokens", None) if planner_llm_resp else None
    planner_total_tokens = getattr(planner_llm_resp, "total_tokens", None) if planner_llm_resp else None
    if planner_total_tokens is None and (planner_input_tokens is not None or planner_output_tokens is not None):
        planner_total_tokens = (planner_input_tokens or 0) + (planner_output_tokens or 0) + (planner_thinking_tokens or 0)

    # Parse planner output
    if planner_error_type is not None:
        parse_res = AdaptivePlannerParseResult(
            success=False,
            plan_spec=build_adaptive_fallback_plan(question=question, raw_text="", error_message=planner_error_type),
            error_message=planner_error_type,
            error_type=planner_error_type,
        )
    elif planner_raw_response is None or not planner_raw_response.strip():
        planner_error_type = "empty_provider_response"
        parse_res = AdaptivePlannerParseResult(
            success=False,
            plan_spec=build_adaptive_fallback_plan(question=question, raw_text="", error_message=planner_error_type),
            error_message=planner_error_type,
            error_type="PlannerEmptyResponseError",
        )
    else:
        parse_res = parse_adaptive_planner_result(planner_raw_response)
        if not parse_res.success:
            planner_error_type = parse_res.error_message

    telemetry = {
        "planner_prompt": planner_prompt,
        "planner_generation_attempts": planner_generation_attempts,
        "planner_generation_success": planner_generation_success,
        "planner_raw_response": planner_raw_response,
        "planner_error_type": planner_error_type,
        "planner_latency": planner_latency,
        "planner_input_tokens": planner_input_tokens,
        "planner_output_tokens": planner_output_tokens,
        "planner_thinking_tokens": planner_thinking_tokens,
        "planner_total_tokens": planner_total_tokens,
    }

    return parse_res, telemetry


def _evaluate_v11_followup_control(
    plan_spec: AdaptivePlanSpec,
    parse_success: bool,
    search1_query_candidate: str,
) -> dict:
    """Evaluates follow-up query validity, duplicate detection, and cohort eligibility.

    Uses exact normalized string comparison without case folding.
    """
    planner_requested_followup = bool(parse_success and plan_spec.evidence_status == "INSUFFICIENT")
    norm_followup_query, followup_truncated = normalize_followup_query(plan_spec.followup_query)
    followup_query_valid = bool(
        planner_requested_followup and norm_followup_query and norm_followup_query.upper() != "NONE"
    )

    norm_search1_query, _ = normalize_followup_query(search1_query_candidate)
    followup_query_duplicate = bool(
        planner_requested_followup
        and followup_query_valid
        and (norm_followup_query == norm_search1_query)
    )

    followup_eligible = bool(planner_requested_followup and followup_query_valid and not followup_query_duplicate)

    return {
        "planner_evidence_status": plan_spec.evidence_status,
        "raw_followup_query": plan_spec.followup_query,
        "norm_followup_query": norm_followup_query,
        "followup_truncated": followup_truncated,
        "norm_search1_query": norm_search1_query,
        "planner_requested_followup": planner_requested_followup,
        "followup_query_valid": followup_query_valid,
        "followup_query_duplicate": followup_query_duplicate,
        "followup_eligible": followup_eligible,
    }


def _execute_v11_followup_search(
    search_tool: Any,
    norm_followup_query: str,
    primary_urls: list[str],
) -> dict:
    """Executes Search 2 once with strict mutual exclusion between success and empty results."""
    import time

    s2_start = time.time()
    second_search_success = False
    second_search_empty_results = False
    second_search_latency_seconds = None
    second_search_result_count = 0
    second_search_error_type = None
    second_search_error_message = None
    second_search_urls: list[str] = []
    second_search_new_urls_count = 0
    second_search_has_new_urls = False
    followup_evidence_text = None
    followup_search_hash = None

    try:
        second_search_res = search_tool.search(norm_followup_query)
        second_search_latency_seconds = round(
            getattr(second_search_res, "latency_seconds", None) or (time.time() - s2_start), 2
        )
        provider_ok = bool(second_search_res and second_search_res.success)
        second_search_result_count = (
            len(second_search_res.results) if (second_search_res and second_search_res.results) else 0
        )
        second_search_success = bool(provider_ok and second_search_result_count > 0)
        second_search_empty_results = bool(provider_ok and second_search_result_count == 0)
        assert not (second_search_success and second_search_empty_results), (
            "Mutual exclusion violation: second_search_success and second_search_empty_results cannot both be True"
        )
        second_search_error_type = second_search_res.error_type if second_search_res else None
        second_search_error_message = second_search_res.error_message if second_search_res else None

        if second_search_res and second_search_res.results:
            second_urls = []
            for item in second_search_res.results:
                u = getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else None)
                if u:
                    second_urls.append(u)
            second_search_urls = second_urls
            primary_url_set = set(primary_urls)
            new_urls = [u for u in second_urls if u not in primary_url_set]
            second_search_new_urls_count = len(new_urls)
            second_search_has_new_urls = len(new_urls) > 0

        if second_search_success:
            followup_evidence_text = second_search_res.format_evidence_block()
            followup_search_hash = _compute_sha256(followup_evidence_text)
            v11_retrieval_category = "FOLLOWUP_ELIGIBLE_SEARCH2_SUCCESS"
        elif second_search_empty_results:
            v11_retrieval_category = "FOLLOWUP_ELIGIBLE_SEARCH2_EMPTY_RESULTS"
        else:
            v11_retrieval_category = "FOLLOWUP_ELIGIBLE_SEARCH2_PROVIDER_FAILURE"
    except Exception as e:
        second_search_latency_seconds = round(time.time() - s2_start, 2)
        second_search_success = False
        second_search_empty_results = False
        second_search_error_type = type(e).__name__
        second_search_error_message = str(e)
        second_search_result_count = 0
        second_search_urls = []
        second_search_new_urls_count = 0
        second_search_has_new_urls = False
        v11_retrieval_category = "FOLLOWUP_ELIGIBLE_SEARCH2_PROVIDER_FAILURE"

    return {
        "second_search_success": second_search_success,
        "second_search_empty_results": second_search_empty_results,
        "second_search_latency_seconds": second_search_latency_seconds,
        "second_search_result_count": second_search_result_count,
        "second_search_error_type": second_search_error_type,
        "second_search_error_message": second_search_error_message,
        "second_search_urls": second_search_urls,
        "second_search_new_urls_count": second_search_new_urls_count,
        "second_search_has_new_urls": second_search_has_new_urls,
        "followup_evidence_text": followup_evidence_text,
        "followup_search_hash": followup_search_hash,
        "v11_retrieval_category": v11_retrieval_category,
    }


def _build_v11_executor_evidence(
    web_evidence_primary: str,
    second_search_success: bool,
    followup_evidence_text: Optional[str],
) -> tuple[str, str]:
    """Builds combined web evidence string and its SHA-256 hash."""
    if second_search_success and followup_evidence_text and followup_evidence_text.strip():
        combined_web_evidence = (
            f"=== PRIMARY WEB SEARCH EVIDENCE ===\n{web_evidence_primary}\n\n"
            f"=== FOLLOW-UP WEB SEARCH EVIDENCE ===\n{followup_evidence_text.strip()}"
        )
    else:
        combined_web_evidence = f"=== PRIMARY WEB SEARCH EVIDENCE ===\n{web_evidence_primary}"
    combined_search_evidence_hash = _compute_sha256(combined_web_evidence)
    return combined_web_evidence, combined_search_evidence_hash


class GAIAAdaptiveEvidenceAgent(GAIAPlannerExecutorAgent):
    """V11 Agent: Planner-Guided Adaptive Evidence Retrieval.

    Inherits from GAIAPlannerExecutorAgent (Frozen V10).
    Upgrades Slot 1 to Structured Planner v2 (planner-v2-adaptive-evidence).
    Enforces bounded, at most ONE follow-up Tavily search when the planner
    determines evidence is INSUFFICIENT with a valid non-duplicate query.
    Preserves upstream slot count = 2 (Search 2 is a non-LLM retrieval call).
    Preserves all downstream stages (V9 Candidate Recovery, V5 Verifier,
    V6 Self-Evaluator, V7 Targeted Repair) verbatim.
    """

    _is_v11: bool = True
    _is_v10: bool = True
    _is_v9: bool = False

    def __init__(
        self,
        llm_client: Any,
        search_tool: Optional[Any] = None,
        file_tool: Optional[Any] = None,
        python_tool: Optional[Any] = None,
        tavily_tool: Optional[Any] = None,
    ):
        super().__init__(
            llm_client=llm_client,
            search_tool=search_tool,
            file_tool=file_tool,
            python_tool=python_tool,
            tavily_tool=tavily_tool,
        )
        self.prompt_version = ADAPTIVE_PLANNER_PROMPT_VERSION
        self.primary_prompt_version = ADAPTIVE_PLANNER_PROMPT_VERSION
        self.fallback_prompt_version = None

    def _execute_upstream_pair_from_context(self, context: UpstreamContext) -> AgentResult:
        """Executes the V11 Planner v2 -> [Adaptive Search 2] -> Plan-Guided Executor upstream flow."""
        import time

        question = context.question
        file_path = context.file_path
        web_evidence = context.web_evidence
        file_evidence = context.file_evidence
        attachment_filename = context.attachment_filename
        search_res = context.search_res
        search_fallback = context.search_fallback
        file_res = context.file_res
        file_fallback = context.file_fallback
        attachment_parts = context.attachment_parts

        # Primary search evidence string and hash
        web_evidence_primary = web_evidence if (search_res and search_res.success) else "[Web search unavailable]"
        primary_search_hash = _compute_sha256(web_evidence_primary)

        # Primary search URLs
        primary_urls: list[str] = []
        if search_res and getattr(search_res, "results", None):
            for item in search_res.results:
                url = getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else None)
                if url:
                    primary_urls.append(url)

        # 1. Slot 1: Structured Planner v2 Generation (Generation #1)
        planner_prompt = build_adaptive_planner_prompt(
        parse_res, p_telem = _plan_v11_from_context(
            agent=self,
            question=question,
            web_evidence=web_evidence_primary,
            web_evidence_primary=web_evidence_primary,
            file_evidence=file_evidence,
            attachment_filename=attachment_filename,
            attachment_parts=attachment_parts,
        )

        planner_generation_attempts = 1
        planner_generation_success = False
        planner_llm_resp = None
        planner_raw_response = None
        planner_error_type = None
        planner_start = time.time()

        try:
            planner_llm_resp = self.llm.generate(planner_prompt, attachment_parts=attachment_parts)
            planner_generation_success = True
            if isinstance(planner_llm_resp, LLMResponse):
                planner_raw_response = planner_llm_resp.raw_text if planner_llm_resp.raw_text else planner_llm_resp.text
                if planner_llm_resp.finish_reason == "MALFORMED_FUNCTION_CALL":
                    planner_error_type = "malformed_function_call_finish_reason"
                elif planner_llm_resp.finish_reason not in (None, "", "STOP"):
                    planner_error_type = "unexpected_finish_reason"
            else:
                planner_raw_response = str(planner_llm_resp)
        except Exception as e:
            err_str = str(e).lower()
            if "timeout" in err_str or "deadline" in err_str:
                planner_error_type = "provider_timeout"
            elif "malformed_function_call" in err_str:
                planner_error_type = "malformed_function_call_finish_reason"
            else:
                planner_error_type = "provider_api_error"
            planner_raw_response = None

        planner_latency = round(time.time() - planner_start, 2)
        planner_input_tokens = getattr(planner_llm_resp, "input_tokens", None) if planner_llm_resp else None
        planner_output_tokens = getattr(planner_llm_resp, "output_tokens", None) if planner_llm_resp else None
        planner_thinking_tokens = getattr(planner_llm_resp, "thinking_tokens", None) if planner_llm_resp else None
        planner_total_tokens = getattr(planner_llm_resp, "total_tokens", None) if planner_llm_resp else None
        if planner_total_tokens is None and (planner_input_tokens is not None or planner_output_tokens is not None):
            planner_total_tokens = (planner_input_tokens or 0) + (planner_output_tokens or 0) + (planner_thinking_tokens or 0)

        # Parse planner output
        if planner_error_type is not None:
            parse_res = AdaptivePlannerParseResult(
                success=False,
                plan_spec=build_adaptive_fallback_plan(question=question, raw_text="", error_message=planner_error_type),
                error_message=planner_error_type,
                error_type=planner_error_type,
            )
        elif planner_raw_response is None or not planner_raw_response.strip():
            planner_error_type = "empty_provider_response"
            parse_res = AdaptivePlannerParseResult(
                success=False,
                plan_spec=build_adaptive_fallback_plan(question=question, raw_text="", error_message=planner_error_type),
                error_message=planner_error_type,
                error_type="PlannerEmptyResponseError",
            )
        else:
            parse_res = parse_adaptive_planner_result(planner_raw_response)
            if not parse_res.success:
                planner_error_type = parse_res.error_message

        plan_spec = parse_res.plan_spec
        planner_prompt = p_telem["planner_prompt"]
        planner_error_type = p_telem["planner_error_type"]
        planner_success = parse_res.success and (planner_error_type is None)
        planner_parse_success = parse_res.success
        planner_fallback_used = plan_spec.is_fallback
        planner_raw_response = p_telem["planner_raw_response"]
        planner_latency = p_telem["planner_latency"]
        planner_input_tokens = p_telem["planner_input_tokens"]
        planner_output_tokens = p_telem["planner_output_tokens"]
        planner_thinking_tokens = p_telem["planner_thinking_tokens"]
        planner_total_tokens = p_telem["planner_total_tokens"]
        planner_generation_attempts = p_telem["planner_generation_attempts"]
        planner_generation_success = p_telem["planner_generation_success"]

        planner_evidence_status = plan_spec.evidence_status
        raw_followup_query = plan_spec.followup_query

        # Evaluate cohort criteria
        planner_requested_followup = bool(planner_parse_success and planner_evidence_status == "INSUFFICIENT")
        norm_followup_query, followup_truncated = normalize_followup_query(raw_followup_query)
        followup_query_valid = bool(
            planner_requested_followup and norm_followup_query and norm_followup_query.upper() != "NONE"
        )

        search1_query_candidate = search_res.query if (search_res and search_res.query) else question
        norm_search1_query, _ = normalize_followup_query(search1_query_candidate)
        followup_query_duplicate = bool(
            planner_requested_followup
            and followup_query_valid
            and (norm_followup_query.lower() == norm_search1_query.lower())
        ctrl = _evaluate_v11_followup_control(
            plan_spec=plan_spec,
            parse_success=planner_parse_success,
            search1_query_candidate=search1_query_candidate,
        )

        followup_eligible = bool(planner_requested_followup and followup_query_valid and not followup_query_duplicate)
        planner_requested_followup = ctrl["planner_requested_followup"]
        norm_followup_query = ctrl["norm_followup_query"]
        followup_truncated = ctrl["followup_truncated"]
        followup_query_valid = ctrl["followup_query_valid"]
        followup_query_duplicate = ctrl["followup_query_duplicate"]
        followup_eligible = ctrl["followup_eligible"]
        planner_evidence_status = ctrl["planner_evidence_status"]
        raw_followup_query = ctrl["raw_followup_query"]

        # Search 2 Telemetry Defaults
        second_search_triggered = False
        second_search_attempted = False
        second_search_success = False
        second_search_empty_results = False
        second_search_skipped_duplicate_query = False
        second_search_query = None
        second_search_provider_query = None
        second_search_query_truncated = False
        second_search_latency_seconds = None
        second_search_result_count = None
        second_search_error_type = None
        second_search_error_message = None
        second_search_new_urls_count = None
        second_search_urls = None
        second_search_has_new_urls = None
        second_search_call_count = 0
        followup_search_hash = None
        followup_evidence_text = None

        if planner_requested_followup and followup_query_duplicate:
            second_search_triggered = True
            second_search_skipped_duplicate_query = True
            second_search_attempted = False
            second_search_query = raw_followup_query
            second_search_provider_query = norm_followup_query
            v11_retrieval_category = "INSUFFICIENT_DUPLICATE_QUERY"
        elif followup_eligible:
            second_search_triggered = True
            second_search_attempted = True
            second_search_query = raw_followup_query
            second_search_provider_query = norm_followup_query
            second_search_query_truncated = followup_truncated
            second_search_call_count = 1

            s2_start = time.time()
            try:
                second_search_res = self.search_tool.search(norm_followup_query)
                second_search_latency_seconds = round(
                    getattr(second_search_res, "latency_seconds", None) or (time.time() - s2_start), 2
                )
                second_search_success = bool(second_search_res and second_search_res.success)
                second_search_result_count = (
                    len(second_search_res.results) if (second_search_res and second_search_res.results) else 0
                )
                second_search_empty_results = bool(second_search_success and second_search_result_count == 0)
                second_search_error_type = second_search_res.error_type if second_search_res else None
                second_search_error_message = second_search_res.error_message if second_search_res else None

                if second_search_res and second_search_res.results:
                    second_urls = []
                    for item in second_search_res.results:
                        u = getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else None)
                        if u:
                            second_urls.append(u)
                    second_search_urls = second_urls
                    primary_url_set = set(primary_urls)
                    new_urls = [u for u in second_urls if u not in primary_url_set]
                    second_search_new_urls_count = len(new_urls)
                    second_search_has_new_urls = len(new_urls) > 0
                else:
                    second_search_urls = []
                    second_search_new_urls_count = 0
                    second_search_has_new_urls = False

                if second_search_success and second_search_result_count > 0:
                    followup_evidence_text = second_search_res.format_evidence_block()
                    followup_search_hash = _compute_sha256(followup_evidence_text)
                    v11_retrieval_category = "FOLLOWUP_ELIGIBLE_SEARCH2_SUCCESS"
                elif second_search_success and second_search_result_count == 0:
                    v11_retrieval_category = "FOLLOWUP_ELIGIBLE_SEARCH2_EMPTY_RESULTS"
                else:
                    v11_retrieval_category = "FOLLOWUP_ELIGIBLE_SEARCH2_PROVIDER_FAILURE"
            except Exception as e:
                second_search_latency_seconds = round(time.time() - s2_start, 2)
                second_search_success = False
                second_search_error_type = type(e).__name__
                second_search_error_message = str(e)
                second_search_result_count = 0
                second_search_empty_results = False
                second_search_urls = []
                second_search_new_urls_count = 0
                second_search_has_new_urls = False
                v11_retrieval_category = "FOLLOWUP_ELIGIBLE_SEARCH2_PROVIDER_FAILURE"
            s2_info = _execute_v11_followup_search(
                search_tool=self.search_tool,
                norm_followup_query=norm_followup_query,
                primary_urls=primary_urls,
            )
            second_search_success = s2_info["second_search_success"]
            second_search_empty_results = s2_info["second_search_empty_results"]
            second_search_latency_seconds = s2_info["second_search_latency_seconds"]
            second_search_result_count = s2_info["second_search_result_count"]
            second_search_error_type = s2_info["second_search_error_type"]
            second_search_error_message = s2_info["second_search_error_message"]
            second_search_urls = s2_info["second_search_urls"]
            second_search_new_urls_count = s2_info["second_search_new_urls_count"]
            second_search_has_new_urls = s2_info["second_search_has_new_urls"]
            followup_evidence_text = s2_info["followup_evidence_text"]
            followup_search_hash = s2_info["followup_search_hash"]
            v11_retrieval_category = s2_info["v11_retrieval_category"]
        else:
            if planner_fallback_used:
                v11_retrieval_category = "PLANNER_FALLBACK"
            else:
                v11_retrieval_category = "SUFFICIENT_NON_TRIGGERED"

        primary_search_call_count = 1
        total_search_call_count = primary_search_call_count + second_search_call_count

        # Format combined evidence for executor
        if second_search_success and followup_evidence_text and followup_evidence_text.strip():
            combined_web_evidence = (
                f"=== PRIMARY WEB SEARCH EVIDENCE ===\n{web_evidence_primary}\n\n"
                f"=== FOLLOW-UP WEB SEARCH EVIDENCE ===\n{followup_evidence_text.strip()}"
            )
        else:
            combined_web_evidence = f"=== PRIMARY WEB SEARCH EVIDENCE ===\n{web_evidence_primary}"
        combined_search_evidence_hash = _compute_sha256(combined_web_evidence)
        combined_web_evidence, combined_search_evidence_hash = _build_v11_executor_evidence(
            web_evidence_primary=web_evidence_primary,
            second_search_success=second_search_success,
            followup_evidence_text=followup_evidence_text,
        )

        # 2. Slot 2: Plan-Guided Executor Generation (Generation #2)
        executor_mode = plan_spec.mode
        if executor_mode == "DIRECT":
            executor_prompt_ver = EXECUTOR_DIRECT_PROMPT_VERSION
            executor_prompt = build_direct_executor_prompt(
                question=question,
                plan_spec=plan_spec,
                web_evidence=combined_web_evidence,
                file_evidence=file_evidence,
                attachment_filename=attachment_filename,
            )
        else:
            executor_prompt_ver = EXECUTOR_PYTHON_PROMPT_VERSION
            executor_prompt = build_python_executor_prompt(
                question=question,
                plan_spec=plan_spec,
                web_evidence=combined_web_evidence,
                file_evidence=file_evidence,
                attachment_filename=attachment_filename,
            )
        exec_res = _execute_v11_executor_from_plan(
            agent=self,
            question=question,
            plan_spec=plan_spec,
            combined_web_evidence=combined_web_evidence,
            file_evidence=file_evidence,
            attachment_filename=attachment_filename,
            attachment_parts=attachment_parts,
            file_path=file_path,
        )

        executor_generation_attempts = 1
        executor_generation_success = False
        executor_llm_resp = None
        executor_raw_response = None
        executor_error_type = None
        executor_start = time.time()
        llm_generation_attempts = planner_generation_attempts + 1
        llm_generation_success_count = (1 if planner_generation_success else 0) + (1 if exec_res.raw_response is not None else 0)

        try:
            executor_llm_resp = self.llm.generate(executor_prompt, attachment_parts=attachment_parts)
            executor_generation_success = True
            if isinstance(executor_llm_resp, LLMResponse):
                executor_raw_response = executor_llm_resp.raw_text if executor_llm_resp.raw_text else executor_llm_resp.text
                if executor_llm_resp.finish_reason == "MALFORMED_FUNCTION_CALL":
                    executor_error_type = "malformed_function_call_finish_reason"
            else:
                executor_raw_response = str(executor_llm_resp)
        except Exception as e:
            err_str = str(e).lower()
            if "timeout" in err_str or "deadline" in err_str:
                executor_error_type = "provider_timeout"
            elif "malformed_function_call" in err_str:
                executor_error_type = "malformed_function_call_finish_reason"
            else:
                executor_error_type = "provider_api_error"
            executor_raw_response = None

        executor_latency = round(time.time() - executor_start, 2)

        if executor_error_type is None and (executor_raw_response is None or not executor_raw_response.strip()):
            executor_error_type = "empty_worker_response"

        executor_input_tokens = getattr(executor_llm_resp, "input_tokens", None) if executor_llm_resp else None
        executor_output_tokens = getattr(executor_llm_resp, "output_tokens", None) if executor_llm_resp else None
        executor_thinking_tokens = getattr(executor_llm_resp, "thinking_tokens", None) if executor_llm_resp else None
        executor_total_tokens = getattr(executor_llm_resp, "total_tokens", None) if executor_llm_resp else None
        if executor_total_tokens is None and (executor_input_tokens is not None or executor_output_tokens is not None):
            executor_total_tokens = (executor_input_tokens or 0) + (executor_output_tokens or 0) + (executor_thinking_tokens or 0)

        # 3. Extract Answer / Execute Python
        py_result: Optional[PythonResult] = None
        python_requested = False
        python_executed = False
        python_fallback = False
        final_answer = ""
        executor_success = False

        if executor_mode == "DIRECT":
            python_requested = False
            python_executed = False
            python_fallback = False
            final_answer = self.clean_answer(extract_direct_answer(executor_raw_response or ""))
            executor_success = bool(final_answer and not executor_error_type)
        else:
            code = extract_python_code(executor_raw_response or "")
            python_requested = bool(code)
            if code:
                python_executed = True
                py_result = self.python_tool.execute(code, attachment_path=file_path)
                if py_result.success:
                    extracted_ans = extract_python_final_answer(py_result.stdout)
                    if extracted_ans is not None:
                        final_answer = self.clean_answer(extracted_ans)
                        python_fallback = False
                        executor_success = True
                    else:
                        python_fallback = True
                        py_result.success = False
                        py_result.error_type = py_result.error_type or "MissingFinalAnswerMarker"
                        py_result.error_message = (
                            py_result.error_message
                            or "Python execution succeeded but stdout did not contain 'FINAL_ANSWER:' marker"
                        )
                        final_answer = (
                            self.clean_answer(extract_direct_answer(executor_raw_response))
                            if executor_raw_response and "FINAL:" in executor_raw_response
                            else ""
                        )
                        executor_success = False
                else:
                    python_fallback = True
                    final_answer = (
                        self.clean_answer(extract_direct_answer(executor_raw_response))
                        if executor_raw_response and "FINAL:" in executor_raw_response
                        else ""
                    )
                    executor_success = False
            else:
                python_requested = False
                python_executed = False
                python_fallback = True
                final_answer = (
                    self.clean_answer(extract_direct_answer(executor_raw_response or ""))
                    if executor_raw_response and "FINAL:" in executor_raw_response
                    else ""
                )
                executor_success = False

        llm_generation_attempts = planner_generation_attempts + executor_generation_attempts
        llm_generation_success_count = (1 if planner_generation_success else 0) + (1 if executor_generation_success else 0)

        raw_resp = executor_raw_response or ""
        raw_resp = exec_res.raw_response or ""
        norm_resp = raw_resp.strip()

        fallback_pv = EXECUTOR_DIRECT_PROMPT_VERSION if planner_fallback_used else None

        agent_result = AgentResult(
            raw_response=raw_resp,
            normalized_response=norm_resp,
            final_answer=final_answer,
            candidate_answer=final_answer,
            llm_response=executor_llm_resp if isinstance(executor_llm_resp, LLMResponse) else None,
            prompt=executor_prompt,
            final_answer=exec_res.candidate_answer,
            candidate_answer=exec_res.candidate_answer,
            llm_response=exec_res.llm_response,
            prompt=exec_res.prompt,
            prompt_version=ADAPTIVE_PLANNER_PROMPT_VERSION,
            primary_prompt_version=ADAPTIVE_PLANNER_PROMPT_VERSION,
            fallback_prompt_version=fallback_pv,
            search_result=search_res,
            search_fallback=search_fallback,
            file_result=file_res,
            file_fallback=file_fallback,
            python_result=py_result,
            python_requested=python_requested,
            python_executed=python_executed,
            python_fallback=python_fallback,
            python_prompt_version=EXECUTOR_PYTHON_PROMPT_VERSION if executor_mode == "PYTHON" else None,
            python_prompt=executor_prompt if executor_mode == "PYTHON" else None,
            python_result=exec_res.py_result,
            python_requested=exec_res.python_requested,
            python_executed=exec_res.python_executed,
            python_fallback=exec_res.python_fallback,
            python_prompt_version=EXECUTOR_PYTHON_PROMPT_VERSION if plan_spec.mode == "PYTHON" else None,
            python_prompt=exec_res.prompt if plan_spec.mode == "PYTHON" else None,
            llm_generation_count=llm_generation_attempts,

            # Planner telemetry
            planner_prompt_version=ADAPTIVE_PLANNER_PROMPT_VERSION,
            planner_attempted=True,
            planner_success=planner_success,
            planner_parse_success=planner_parse_success,
            planner_fallback_used=planner_fallback_used,
            planner_mode=plan_spec.mode,
            planner_objective=plan_spec.objective,
            planner_evidence_needed=plan_spec.evidence_needed,
            plan_step_count=len(plan_spec.plan_steps),
            plan_steps=plan_spec.plan_steps,
            plan_answer_type=plan_spec.answer_type,
            planner_error_type=planner_error_type,
            planner_prompt=planner_prompt,
            planner_raw_response=planner_raw_response,
            planner_latency_seconds=planner_latency,
            planner_input_tokens=planner_input_tokens,
            planner_output_tokens=planner_output_tokens,
            planner_thinking_tokens=planner_thinking_tokens,
            planner_total_tokens=planner_total_tokens,
            planner_generation_attempts=planner_generation_attempts,
            planner_generation_success=planner_generation_success,

            # V11 Adaptive Retrieval Telemetry
            planner_evidence_status=planner_evidence_status,
            planner_followup_query=raw_followup_query,
            planner_requested_followup=planner_requested_followup,
            followup_query_valid=followup_query_valid,
            followup_query_duplicate=followup_query_duplicate,
            followup_eligible=followup_eligible,
            second_search_triggered=second_search_triggered,
            second_search_attempted=second_search_attempted,
            second_search_success=second_search_success,
            second_search_empty_results=second_search_empty_results,
            second_search_skipped_duplicate_query=second_search_skipped_duplicate_query,
            second_search_query=second_search_query,
            second_search_provider_query=second_search_provider_query,
            second_search_query_truncated=second_search_query_truncated,
            second_search_latency_seconds=second_search_latency_seconds,
            second_search_result_count=second_search_result_count,
            second_search_error_type=second_search_error_type,
            second_search_error_message=second_search_error_message,
            second_search_new_urls_count=second_search_new_urls_count,
            second_search_urls=second_search_urls,
            primary_search_urls=primary_urls,
            second_search_has_new_urls=second_search_has_new_urls,
            primary_search_call_count=primary_search_call_count,
            second_search_call_count=second_search_call_count,
            total_search_call_count=total_search_call_count,
            primary_search_evidence_hash=primary_search_hash,
            followup_search_evidence_hash=followup_search_hash,
            combined_search_evidence_hash=combined_search_evidence_hash,
            v11_retrieval_category=v11_retrieval_category,

            # Executor telemetry
            executor_mode=executor_mode,
            executor_mode=plan_spec.mode,
            executor_plan_used=True,
            executor_success=executor_success,
            executor_error_type=executor_error_type,
            executor_prompt_version=executor_prompt_ver,
            executor_prompt=executor_prompt,
            executor_raw_response=executor_raw_response,
            executor_latency_seconds=executor_latency,
            executor_input_tokens=executor_input_tokens,
            executor_output_tokens=executor_output_tokens,
            executor_thinking_tokens=executor_thinking_tokens,
            executor_total_tokens=executor_total_tokens,
            executor_generation_attempts=executor_generation_attempts,
            executor_generation_success=executor_generation_success,
            executor_success=exec_res.executor_success,
            executor_error_type=exec_res.error_type,
            executor_prompt_version=exec_res.prompt_version,
            executor_prompt=exec_res.prompt,
            executor_raw_response=exec_res.raw_response,
            executor_latency_seconds=exec_res.latency_seconds,
            executor_input_tokens=exec_res.input_tokens,
            executor_output_tokens=exec_res.output_tokens,
            executor_thinking_tokens=exec_res.thinking_tokens,
            executor_total_tokens=exec_res.total_tokens,
            executor_generation_attempts=1,
            executor_generation_success=bool(exec_res.raw_response is not None),

            # Worker compatibility aliases (for Frozen V9 candidate recovery classifier)
            worker_mode=executor_mode,
            worker_success=executor_success,
            worker_error_type=executor_error_type,
            worker_prompt_version=executor_prompt_ver,
            worker_prompt=executor_prompt,
            worker_raw_response=executor_raw_response,
            worker_latency_seconds=executor_latency,
            worker_input_tokens=executor_input_tokens,
            worker_output_tokens=executor_output_tokens,
            worker_thinking_tokens=executor_thinking_tokens,
            worker_generation_attempts=executor_generation_attempts,
            worker_generation_success=executor_generation_success,
            worker_mode=plan_spec.mode,
            worker_success=exec_res.executor_success,
            worker_error_type=exec_res.error_type,
            worker_prompt_version=exec_res.prompt_version,
            worker_prompt=exec_res.prompt,
            worker_raw_response=exec_res.raw_response,
            worker_latency_seconds=exec_res.latency_seconds,
            worker_input_tokens=exec_res.input_tokens,
            worker_output_tokens=exec_res.output_tokens,
            worker_thinking_tokens=exec_res.thinking_tokens,
            worker_generation_attempts=1,
            worker_generation_success=bool(exec_res.raw_response is not None),

            # Router compatibility aliases
            router_requested=False,
            router_decision=plan_spec.mode,
            router_success=planner_success,
            router_fallback=planner_fallback_used,
            router_error_type=planner_error_type,
            router_prompt_version=ADAPTIVE_PLANNER_PROMPT_VERSION,
            router_prompt=planner_prompt,
            router_raw_response=planner_raw_response,
            router_latency_seconds=planner_latency,
            router_input_tokens=planner_input_tokens,
            router_output_tokens=planner_output_tokens,
            router_thinking_tokens=planner_thinking_tokens,
            router_generation_attempts=planner_generation_attempts,
            router_generation_success=planner_generation_success,

            llm_generation_attempts=llm_generation_attempts,
            llm_generation_success_count=llm_generation_success_count,
        )
        return agent_result

    def run(self, question: str, file_path: Optional[str] = None) -> AgentResult:
        result = super().run(question, file_path=file_path)

        # Budget invariants assertions
        assert result.total_search_call_count <= 2, "V11 exceeds maximum 2 web searches"
        assert result.second_search_call_count <= 1, "V11 exceeds maximum 1 second search"

        if result.planner_fallback_used:
            assert not result.second_search_triggered, "Planner fallback must never trigger Search 2"
            assert not result.second_search_attempted, "Planner fallback must never attempt Search 2"
            assert result.second_search_call_count == 0, "Planner fallback search call count must be 0"

        if result.candidate_recovery_triggered is False:
            assert result.llm_generation_attempts <= 5, "Non-triggered V11 exceeds five-generation cap"
            assert result.post_recovery_candidate == result.pre_recovery_candidate, "Non-triggered recovery boundary preservation violation"
        else:
            assert result.llm_generation_attempts <= 6, "Triggered V11 exceeds six-generation cap"
        return result
