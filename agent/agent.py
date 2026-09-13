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
from tools.web_search import TavilySearchTool, WebSearchResult
from tools.file_tool import FileTool, FileResult
from tools.python_tool import PythonTool, PythonResult
from .llm import LLMResponse



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

    def run(self, question: str, file_path: Optional[str] = None) -> AgentResult:
        """Runs the V4 two-stage capability-routing pipeline."""
        import time

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

        # 3. Stage 1: Router Generation (Generation #1)
        router_prompt = build_router_prompt(
            question=question,
            web_evidence=web_evidence if search_res.success else "[Web search unavailable]",
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
                web_evidence=web_evidence if search_res.success else "[Web search unavailable]",
                file_evidence=file_evidence,
                attachment_filename=attachment_filename,
            )
        else:
            worker_prompt_ver = ROUTER_PYTHON_WORKER_PROMPT_VERSION
            worker_prompt = build_python_worker_prompt(
                question=question,
                web_evidence=web_evidence if search_res.success else "[Web search unavailable]",
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

        return AgentResult(
            raw_response=raw_resp,
            normalized_response=norm_resp,
            final_answer=final_answer,
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
        assert v5_result.llm_generation_attempts <= 4, "V6 exceeds the four-generation cap"
        assert v5_result.self_eval_answer_unchanged, "V6 self-evaluation mutated the final answer"
        return v5_result

    def __call__(self, question: str, file_path: Optional[str] = None) -> str:
        return self.run(question, file_path=file_path).final_answer

