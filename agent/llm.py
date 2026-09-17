import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional, Any, List, Tuple
from dotenv import load_dotenv, find_dotenv
from google import genai
from google.genai import types

# Automatically load environment variables from .env if present
load_dotenv(find_dotenv() or ".env")

logger = logging.getLogger(__name__)


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


def discover_gemini_api_keys(api_key: Optional[str] = None, env_path: Optional[str] = None) -> List[str]:
    """Discovers all available Gemini API keys from explicit args, os.environ, and the .env file.

    Supports:
    - Explicit api_key argument (single key or comma/semicolon-separated)
    - GEMINI_API_KEY, GEMINI_API_KEYS, GEMINI_API_KEY_1, GEMINI_API_KEY_2, etc. in os.environ
    - Multiple duplicate GEMINI_API_KEY=... lines in the .env file
    """
    keys: List[str] = []

    # 1. Explicit api_key argument takes precedence
    if api_key:
        for sub in re.split(r"[,;]", api_key):
            sub = sub.strip().strip("\"'")
            if sub and sub not in keys:
                keys.append(sub)
        return keys

    # 2. Check os.environ for GEMINI_API_KEY, GEMINI_API_KEYS, GEMINI_API_KEY_*
    env_keys: List[str] = []
    primary = os.getenv("GEMINI_API_KEY")
    if primary:
        for sub in re.split(r"[,;]", primary):
            sub = sub.strip().strip("\"'")
            if sub and sub not in env_keys:
                env_keys.append(sub)

    for k in sorted(os.environ.keys()):
        if k.startswith("GEMINI_API_KEY") and k != "GEMINI_API_KEY":
            val = os.environ[k]
            for sub in re.split(r"[,;]", val):
                sub = sub.strip().strip("\"'")
                if sub and sub not in env_keys:
                    env_keys.append(sub)

    for k in env_keys:
        if k not in keys:
            keys.append(k)

    # 3. If Gemini keys exist in environment or explicit env_path is provided, parse .env file to discover all duplicate lines
    if env_keys or env_path:
        target_env = env_path or find_dotenv() or ".env"
        if os.path.exists(target_env):
            try:
                with open(target_env, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        m = re.match(r"^(GEMINI_API_KEY\w*)\s*=\s*(.*)$", line)
                        if m:
                            val = m.group(2).strip().strip("\"'")
                            for sub in re.split(r"[,;]", val):
                                sub = sub.strip()
                                if sub and sub not in keys and not sub.startswith("your_"):
                                    keys.append(sub)
            except Exception:
                pass

    return keys


class LLMClient:
    """Interacts with Google Gemini models with tools explicitly disabled for baseline reproducibility."""

    _shared_key_index: int = 0

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        thinking_level: Optional[str] = None,
        env_path: Optional[str] = None,
    ):
        self._explicit_key = api_key is not None
        self.api_keys = discover_gemini_api_keys(api_key, env_path=env_path)
        if not self.api_keys:
            raise ValueError("GEMINI_API_KEY is not set in environment or provided explicitly.")

        if self._explicit_key:
            self._current_key_index = 0
        else:
            self._current_key_index = (
                LLMClient._shared_key_index % len(self.api_keys)
                if self.api_keys
                else 0
            )

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

        self._client = None
        self._client_key = None
        if self.api_key:
            try:
                self._client = genai.Client(api_key=self.api_key)
                self._client_key = self.api_key
            except Exception:
                self._client = None
                self._client_key = None

    @property
    def api_key(self) -> Optional[str]:
        """Returns the currently active Gemini API key."""
        if self.api_keys and 0 <= self._current_key_index < len(self.api_keys):
            return self.api_keys[self._current_key_index]
        return None

    @api_key.setter
    def api_key(self, value: Optional[str]) -> None:
        """Sets or prepends the active Gemini API key."""
        if value:
            if value not in self.api_keys:
                self.api_keys.insert(0, value)
            self._current_key_index = self.api_keys.index(value)
        else:
            self.api_keys = []
            self._current_key_index = 0
        self._client = None
        self._client_key = None

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
        """Generates a text completion with tools disabled and a bounded provider retry count."""
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

        num_keys = len(self.api_keys) if self.api_keys else 1
        last_error: Optional[Exception] = None

        for key_attempt in range(num_keys):
            current_key = self.api_key
            if not current_key:
                break
            masked_key = (current_key[:8] + "..." + current_key[-4:]) if len(current_key) > 12 else "***"

            if self._client is None or getattr(self, "_client_key", None) != current_key:
                self._client = genai.Client(api_key=current_key)
                self._client_key = current_key

            key_failed = False
            for attempt in range(total_provider_attempts):
                try:
                    response = self._client.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config,
                    )
                    key_failed = False
                    break
                except Exception as e:
                    last_error = e
                    err_str = str(e)
                    is_daily_cap = "GenerateRequestsPerDay" in err_str
                    is_auth_error = any(code in err_str for code in ["401", "403", "API_KEY_INVALID", "PERMISSION_DENIED", "UNAUTHENTICATED"])
                    is_rate_or_quota = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                    is_transient = "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str or is_rate_or_quota

                    # If daily cap or permanent auth error, do not retry same key
                    if is_daily_cap or is_auth_error:
                        key_failed = True
                        break

                    # Transient retry with same key
                    if is_transient and attempt < total_provider_attempts - 1:
                        sleep_time = 2.0 * (attempt + 1)
                        time.sleep(sleep_time)
                        continue

                    # If all transient attempts for this key failed
                    key_failed = True
                    break

            if not key_failed and response is not None:
                if not self._explicit_key:
                    LLMClient._shared_key_index = self._current_key_index
                break
            else:
                if key_attempt < num_keys - 1:
                    next_index = (self._current_key_index + 1) % num_keys
                    logger.warning(
                        f"[LLMClient] Generation failed with key {masked_key} ({type(last_error).__name__}: {last_error}). "
                        f"Rotating to key {next_index + 1}/{num_keys}..."
                    )
                    self._current_key_index = next_index
                    if not self._explicit_key:
                        LLMClient._shared_key_index = next_index
                    continue
                else:
                    if num_keys > 1:
                        raise RuntimeError(
                            f"LLM generation failed on model '{self.model}' across all {num_keys} API keys: {last_error}"
                        ) from last_error
                    else:
                        raise RuntimeError(f"LLM generation failed on model '{self.model}': {last_error}") from last_error

        if response is None:
            raise RuntimeError(f"LLM generation failed on model '{self.model}': {last_error}")

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
