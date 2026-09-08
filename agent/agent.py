import re
from dataclasses import dataclass
from typing import Any, Optional
from prompts.baseline import build_baseline_prompt, PROMPT_VERSION
from prompts.web_search import build_web_search_prompt, WEB_SEARCH_PROMPT_VERSION
from prompts.file_search import build_file_search_prompt, FILE_SEARCH_PROMPT_VERSION
from prompts.python_execution import build_python_execution_prompt, PYTHON_EXECUTION_PROMPT_VERSION
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
    python_prompt: Optional[str] = None
    python_analysis_prompt: Optional[str] = None
    python_analysis_response: Optional[str] = None
    python_final_prompt: Optional[str] = None
    llm_generation_count: int = 1


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
                    attachment_filename = os.path.basename(file_path)
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
            python_prompt=prompt,
            python_analysis_prompt=prompt,
            python_analysis_response=None,
            python_final_prompt=prompt,
            llm_generation_count=1,
        )

    def __call__(self, question: str, file_path: Optional[str] = None) -> str:
        return self.run(question, file_path=file_path).final_answer
