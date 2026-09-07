import re
from dataclasses import dataclass
from typing import Any, Optional
from prompts.baseline import build_baseline_prompt, PROMPT_VERSION
from prompts.web_search import build_web_search_prompt, WEB_SEARCH_PROMPT_VERSION
from tools.web_search import TavilySearchTool, WebSearchResult
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
