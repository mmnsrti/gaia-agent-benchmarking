import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional, Any, List, Tuple, Set
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


@dataclass
class LLMResponse:
    """Structured response from LLM inference containing generated text, token metadata, and finish status."""
    text: str  # Stripped/normalized model text
    raw_text: str = ""  # Completely untouched model text directly from provider
    finish_reason: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    thinking_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    response_id: Optional[str] = None
    model_version: Optional[str] = None
    response_part_types: List[str] = field(default_factory=list)
    response_part_count: int = 0
    has_text_part: bool = False
    has_function_call_part: bool = False


def extract_part_diagnostics(response: Any) -> Tuple[List[str], int, bool, bool]:
    """Safely extracts sanitized candidate part types and flags from a Gemini response.

    Returns:
        (response_part_types, response_part_count, has_text_part, has_function_call_part)
    """
    response_part_types: List[str] = []
    has_text_part = False
    has_function_call_part = False
    parts: List[Any] = []

    candidates = getattr(response, "candidates", None)
    if candidates and isinstance(candidates, (list, tuple)) and len(candidates) > 0:
        candidate = candidates[0]
        content = getattr(candidate, "content", None)
        if content is not None:
            raw_parts = getattr(content, "parts", None)
            if isinstance(raw_parts, (list, tuple)):
                parts = list(raw_parts)

    for part in parts:
        thought_val = getattr(part, "thought", None)
        is_thought = thought_val is True or (isinstance(thought_val, bool) and thought_val)
        if is_thought:
            response_part_types.append("thought")
        elif getattr(part, "text", None) is not None:
            response_part_types.append("text")
            has_text_part = True
        elif getattr(part, "function_call", None) is not None:
            response_part_types.append("function_call")
            has_function_call_part = True
        else:
            response_part_types.append("other")

    response_part_count = len(parts)
    return response_part_types, response_part_count, has_text_part, has_function_call_part


_GLOBAL_EXHAUSTED_KEYS: Set[str] = set()
_GLOBAL_ACTIVE_KEY_INDEX: int = 0


def _discover_gemini_api_keys(
    explicit_key: Optional[str] = None,
    scan_env_file: bool = True,
) -> List[str]:
    """Discovers available Gemini API keys from arguments, env vars, and .env file.

    Order of precedence:
    1. Explicit key argument (if provided, comma-separated tokens are parsed).
    2. GEMINI_API_KEYS environment variable (comma-separated tokens).
    3. GEMINI_API_KEY, GEMINI_API_KEY_1, GEMINI_API_KEY_2, etc. in os.environ.
    4. Direct parsing of .env file for active or commented GEMINI_API_KEY lines.
    """
    discovered: List[str] = []

    def _add_key(k: Optional[str]):
        if not k:
            return
        cleaned = k.strip().strip("'\"")
        if cleaned and cleaned not in discovered:
            discovered.append(cleaned)

    if explicit_key:
        for part in explicit_key.split(","):
            _add_key(part)
        return discovered

    env_keys_var = os.getenv("GEMINI_API_KEYS")
    if env_keys_var:
        for part in env_keys_var.split(","):
            _add_key(part)
        return discovered

    # Check GEMINI_API_KEY and indexed variants in os.environ
    for env_k, env_v in os.environ.items():
        if env_k == "GEMINI_API_KEY" or re.match(r"^GEMINI_API_KEY_\d+$", env_k):
            for part in env_v.split(","):
                _add_key(part)

    # Check .env file directly if it exists, but only if scan_env_file is True and discovered keys match .env
    if scan_env_file and discovered:
        env_file_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_file_path):
            try:
                with open(env_file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if any(k in content for k in discovered):
                    for line in content.splitlines():
                        line = line.strip()
                        m = re.match(r"^(?:#\s*)?(GEMINI_API_KEY(?:_\d+)?|GEMINI_API_KEYS)\s*=\s*([^\s#]+)", line)
                        if m:
                            val = m.group(2)
                            for part in val.split(","):
                                _add_key(part)
            except Exception:
                pass

    return discovered


class LLMClient:
    """Interacts with Google Gemini models with tools explicitly disabled and automatic API key rotation on quota exhaustion."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        thinking_level: Optional[str] = None,
        scan_env_file: bool = True,
    ):
        global _GLOBAL_ACTIVE_KEY_INDEX
        self.api_keys = _discover_gemini_api_keys(explicit_key=api_key, scan_env_file=scan_env_file)
        if not self.api_keys:
            raise ValueError("GEMINI_API_KEY is not set in environment or provided explicitly.")

        if _GLOBAL_ACTIVE_KEY_INDEX >= len(self.api_keys):
            _GLOBAL_ACTIVE_KEY_INDEX = 0

        self.current_key_idx = _GLOBAL_ACTIVE_KEY_INDEX
        if self.api_keys[self.current_key_idx] in _GLOBAL_EXHAUSTED_KEYS:
            for idx, k in enumerate(self.api_keys):
                if k not in _GLOBAL_EXHAUSTED_KEYS:
                    self.current_key_idx = idx
                    _GLOBAL_ACTIVE_KEY_INDEX = idx
                    break

        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

        # Temperature: Only set if explicitly provided in args or GEMINI_TEMPERATURE env var.
        # Otherwise None to preserve model default behavior.
        env_temp = os.getenv("GEMINI_TEMPERATURE")
        if temperature is not None:
            self.temperature = float(temperature)
        elif env_temp is not None and env_temp.strip() != "":
            self.temperature = float(env_temp)
        else:
            self.temperature = None

        # Max output tokens: default 2048 to prevent reasoning/thinking truncation
        env_max_tokens = os.getenv("GEMINI_MAX_OUTPUT_TOKENS")
        if max_output_tokens is not None:
            self.max_output_tokens = int(max_output_tokens)
        elif env_max_tokens is not None and env_max_tokens.strip() != "":
            self.max_output_tokens = int(env_max_tokens)
        else:
            self.max_output_tokens = 2048

        # Thinking level: default 'medium'
        env_thinking_level = os.getenv("GEMINI_THINKING_LEVEL")
        if thinking_level is not None:
            self.thinking_level = thinking_level
        elif env_thinking_level is not None and env_thinking_level.strip() != "":
            self.thinking_level = env_thinking_level
        else:
            self.thinking_level = "medium"

        self._init_client()

    def _init_client(self):
        self.api_key = self.api_keys[self.current_key_idx]
        self._client = genai.Client(api_key=self.api_key)

    def has_unexhausted_keys(self) -> bool:
        """Returns True if there are API keys in the pool not yet marked exhausted."""
        return any(k not in _GLOBAL_EXHAUSTED_KEYS for k in self.api_keys)

    def rotate_key(self) -> bool:
        """Rotates to the next available Gemini API key in the pool upon quota/auth failure."""
        global _GLOBAL_ACTIVE_KEY_INDEX
        current_k = self.api_keys[self.current_key_idx]
        _GLOBAL_EXHAUSTED_KEYS.add(current_k)

        for offset in range(1, len(self.api_keys) + 1):
            cand_idx = (self.current_key_idx + offset) % len(self.api_keys)
            if self.api_keys[cand_idx] not in _GLOBAL_EXHAUSTED_KEYS:
                old_idx = self.current_key_idx
                self.current_key_idx = cand_idx
                _GLOBAL_ACTIVE_KEY_INDEX = cand_idx
                self._init_client()
                remaining = sum(1 for k in self.api_keys if k not in _GLOBAL_EXHAUSTED_KEYS)
                print(
                    f"[API KEY ROTATION] Gemini API key index {old_idx + 1}/{len(self.api_keys)} exhausted. "
                    f"Rotated to key index {self.current_key_idx + 1} ({remaining} active key(s) remaining)."
                )
                return True

        return False

    def _build_config(self) -> types.GenerateContentConfig:
        """Builds GenerateContentConfig omitting temperature when None."""
        config_kwargs: dict[str, Any] = {
            "max_output_tokens": self.max_output_tokens,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
            "tool_config": types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="NONE"
                )
            ),
        }

        if self.temperature is not None:
            config_kwargs["temperature"] = self.temperature

        if self.thinking_level:
            level_str = self.thinking_level.upper()
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=level_str)

        return types.GenerateContentConfig(**config_kwargs)

    def generate(
        self,
        prompt: str,
        attachment_parts: Optional[List[Any]] = None,
        max_retries: int = 3,
    ) -> LLMResponse:
        """Generates a text completion with tools disabled, key rotation on quota exhaustion, and bounded retry count."""
        if not prompt and not attachment_parts:
            return LLMResponse(
                text="",
                finish_reason="STOP",
                input_tokens=None,
                output_tokens=None,
                thinking_tokens=None,
                total_tokens=None,
                response_part_types=[],
                response_part_count=0,
                has_text_part=False,
                has_function_call_part=False,
            )

        config = self._build_config()
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        total_provider_attempts = max_retries + 1
        response = None

        if attachment_parts:
            contents = [prompt] + list(attachment_parts)
        else:
            contents = prompt

        while True:
            key_rotated = False
            for attempt in range(total_provider_attempts):
                try:
                    response = self._client.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config,
                    )
                    break
                except Exception as e:
                    err_str = str(e)
                    is_quota_exhausted = (
                        "429" in err_str
                        or "RESOURCE_EXHAUSTED" in err_str
                        or "Quota exceeded" in err_str
                        or "GenerateRequestsPerDay" in err_str
                    )
                    is_auth_error = "401" in err_str or "UNAUTHENTICATED" in err_str

                    if (is_quota_exhausted or is_auth_error) and self.has_unexhausted_keys():
                        if self.rotate_key():
                            key_rotated = True
                            break

                    is_transient = "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                    is_daily_cap = "GenerateRequestsPerDay" in err_str
                    if is_transient and not is_daily_cap and attempt < total_provider_attempts - 1:
                        sleep_time = 2.0 * (attempt + 1)
                        time.sleep(sleep_time)
                        continue
                    raise RuntimeError(f"LLM generation failed on model '{self.model}': {e}") from e

            if key_rotated:
                continue
            break

        # Extract sanitized candidate part diagnostics directly from candidate content parts
        part_types, part_count, has_text, has_fc = extract_part_diagnostics(response)

        raw_text = response.text or ""
        text = raw_text.strip()

        finish_reason = None
        if response.candidates:
            raw_reason = getattr(response.candidates[0], "finish_reason", None)
            if raw_reason is not None:
                finish_reason = raw_reason.value if hasattr(raw_reason, "value") else str(raw_reason)

        input_tokens = None
        output_tokens = None
        thinking_tokens = None
        total_tokens = None

        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            input_tokens = getattr(usage, "prompt_token_count", None)
            output_tokens = getattr(usage, "candidates_token_count", None)
            thinking_tokens = getattr(usage, "thoughts_token_count", None)
            total_tokens = getattr(usage, "total_token_count", None)

        # Fallback for output_tokens if usage_metadata.candidates_token_count is unavailable
        if output_tokens is None and response.candidates:
            candidate_token_count = getattr(response.candidates[0], "token_count", None)
            if candidate_token_count is not None:
                output_tokens = candidate_token_count

        response_id = getattr(response, "response_id", None)
        model_version = getattr(response, "model_version", None)

        return LLMResponse(
            text=text,
            raw_text=raw_text,
            finish_reason=finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            total_tokens=total_tokens,
            response_id=response_id,
            model_version=model_version,
            response_part_types=part_types,
            response_part_count=part_count,
            has_text_part=has_text,
            has_function_call_part=has_fc,
        )
