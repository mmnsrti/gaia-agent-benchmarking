import re
from dataclasses import dataclass
from typing import Any, Optional
from prompts.baseline import build_baseline_prompt, PROMPT_VERSION
from prompts.web_search import build_web_search_prompt, WEB_SEARCH_PROMPT_VERSION
from prompts.file_search import build_file_search_prompt, FILE_SEARCH_PROMPT_VERSION
from prompts.python_analysis import build_python_analysis_prompt, PYTHON_ANALYSIS_PROMPT_VERSION
from prompts.python_result import build_python_result_prompt, PYTHON_RESULT_PROMPT_VERSION
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
    python_analysis_prompt: Optional[str] = None
    python_analysis_response: Optional[str] = None
    python_final_prompt: Optional[str] = None


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
    """Extracts Python code from model response markdown blocks."""
    if not text:
        return None
    # 1. ```python ... ``` or ```py ... ```
    m = re.search(r"```(?:python|py)\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        code = m.group(1).strip()
        if code:
            return code
    # 2. Generic ``` ... ``` if not NO_CODE
    m2 = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if m2:
        code = m2.group(1).strip()
        if code and not code.upper().startswith("NO_CODE"):
            return code
    return None


class GAIAPythonAgent(GAIAFileAgent):
    """V3 GAIA agent combining single-shot Tavily search, V2 attachment handling,
    and controlled single-shot local Python execution.

    Flow:
    1. Executes exactly one Tavily search on original question (inherited from V1/V2).
    2. Processes file attachment using FileTool if provided (inherited from V2).
    3. Stage 1: Calls Gemini with python-analysis-v1 prompt asking whether Python is needed.
    4. If code is generated:
       - Executes PythonTool.execute(code, attachment_path) strictly ONCE (execution_count <= 1).
       - If execution succeeds:
         - Calls Gemini with python-result-v1 prompt containing the code and stdout.
       - If execution fails / times out / rejected:
         - Sets python_fallback = True.
         - Falls back to V2 evidence prompt without retrying Python.
    5. If NO_CODE generated:
       - Uses V2 evidence prompt directly.
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
        self.prompt_version = PYTHON_RESULT_PROMPT_VERSION
        self.primary_prompt_version = PYTHON_RESULT_PROMPT_VERSION
        self.fallback_prompt_version = FILE_SEARCH_PROMPT_VERSION

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

        if file_path:
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

        # 3. Stage 1: Python analysis / code generation
        analysis_prompt = build_python_analysis_prompt(
            question=question,
            web_evidence=web_evidence if search_res.success else "[Web search unavailable]",
            file_evidence=file_evidence,
        )

        analysis_resp = self.llm.generate(analysis_prompt, attachment_parts=attachment_parts)
        if isinstance(analysis_resp, LLMResponse):
            analysis_raw = analysis_resp.raw_text if analysis_resp.raw_text else analysis_resp.text
        else:
            analysis_raw = str(analysis_resp)

        code = extract_python_code(analysis_raw)
        py_result: Optional[PythonResult] = None
        python_requested = bool(code)
        python_executed = False
        python_fallback = False

        # 4. Stage 2: Execute code if requested (strictly ONCE)
        final_prompt = None
        final_resp = None
        prompt_ver = None
        primary_ver = None
        fallback_ver = None

        if code:
            python_executed = True
            py_result = self.python_tool.execute(code, attachment_path=file_path)

            if py_result.success:
                final_prompt = build_python_result_prompt(
                    question=question,
                    web_evidence=web_evidence if search_res.success else "[Web search unavailable]",
                    file_evidence=file_evidence,
                    executed_code=code,
                    execution_stdout=py_result.stdout,
                    execution_stderr=py_result.stderr,
                )
                prompt_ver = PYTHON_RESULT_PROMPT_VERSION
                primary_ver = PYTHON_RESULT_PROMPT_VERSION
                fallback_ver = FILE_SEARCH_PROMPT_VERSION if file_path else WEB_SEARCH_PROMPT_VERSION
                final_resp = self.llm.generate(final_prompt, attachment_parts=attachment_parts)
            else:
                # Python execution failed, timed out, or violated policy -> fallback without retry
                python_fallback = True
                primary_ver = PYTHON_RESULT_PROMPT_VERSION
                fallback_ver = FILE_SEARCH_PROMPT_VERSION if file_path else WEB_SEARCH_PROMPT_VERSION

                if file_res and file_res.success and not file_fallback:
                    final_prompt = build_file_search_prompt(
                        question=question,
                        web_evidence=web_evidence if search_res.success else "[Web search unavailable]",
                        file_evidence=file_evidence,
                    )
                    prompt_ver = FILE_SEARCH_PROMPT_VERSION
                elif search_res.success:
                    final_prompt = build_web_search_prompt(question, web_evidence)
                    prompt_ver = WEB_SEARCH_PROMPT_VERSION
                else:
                    final_prompt = build_baseline_prompt(question)
                    prompt_ver = PROMPT_VERSION

                final_resp = self.llm.generate(final_prompt, attachment_parts=attachment_parts)
        else:
            # NO_CODE: direct V2 evidence synthesis
            python_executed = False
            python_fallback = False

            if file_res and file_res.success and not file_fallback:
                final_prompt = build_file_search_prompt(
                    question=question,
                    web_evidence=web_evidence if search_res.success else "[Web search unavailable]",
                    file_evidence=file_evidence,
                )
                prompt_ver = FILE_SEARCH_PROMPT_VERSION
                primary_ver = FILE_SEARCH_PROMPT_VERSION
                fallback_ver = WEB_SEARCH_PROMPT_VERSION
            elif search_res.success:
                final_prompt = build_web_search_prompt(question, web_evidence)
                prompt_ver = WEB_SEARCH_PROMPT_VERSION
                primary_ver = WEB_SEARCH_PROMPT_VERSION
                fallback_ver = PROMPT_VERSION
            else:
                final_prompt = build_baseline_prompt(question)
                prompt_ver = PROMPT_VERSION
                primary_ver = WEB_SEARCH_PROMPT_VERSION
                fallback_ver = PROMPT_VERSION

            final_resp = self.llm.generate(final_prompt, attachment_parts=attachment_parts)

        # 5. Extract and clean final answer
        if isinstance(final_resp, LLMResponse):
            raw_text = final_resp.raw_text if final_resp.raw_text else final_resp.text
            norm_text = final_resp.text
        else:
            raw_text = str(final_resp)
            norm_text = raw_text.strip()

        final_answer = self.clean_answer(raw_text)

        return AgentResult(
            raw_response=raw_text,
            normalized_response=norm_text,
            final_answer=final_answer,
            llm_response=final_resp if isinstance(final_resp, LLMResponse) else None,
            prompt=final_prompt,
            prompt_version=prompt_ver,
            primary_prompt_version=primary_ver,
            fallback_prompt_version=fallback_ver,
            search_result=search_res,
            search_fallback=search_fallback,
            file_result=file_res,
            file_fallback=file_fallback,
            python_result=py_result,
            python_requested=python_requested,
            python_executed=python_executed,
            python_fallback=python_fallback,
            python_analysis_prompt=analysis_prompt,
            python_analysis_response=analysis_raw,
            python_final_prompt=final_prompt,
        )

    def __call__(self, question: str, file_path: Optional[str] = None) -> str:
        return self.run(question, file_path=file_path).final_answer
