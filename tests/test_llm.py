import os
import unittest
from unittest.mock import patch, MagicMock
from agent.llm import LLMClient, LLMResponse, extract_part_diagnostics


class TestLLMClient(unittest.TestCase):
    def test_missing_api_key_raises_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                LLMClient(api_key=None)
            self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    def test_temperature_omitted_when_unset(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=True):
            with patch("google.genai.Client"):
                client = LLMClient(temperature=None)
                self.assertIsNone(client.temperature)
                cfg = client._build_config()
                self.assertIsNone(cfg.temperature)

    def test_explicit_temperature_and_thinking_level(self):
        with patch("google.genai.Client") as mock_client_cls:
            client = LLMClient(
                model="gemini-custom",
                api_key="fake-key",
                temperature=0.7,
                max_output_tokens=1024,
                thinking_level="low",
            )
            self.assertEqual(client.model, "gemini-custom")
            self.assertEqual(client.api_key, "fake-key")
            self.assertEqual(client.temperature, 0.7)
            self.assertEqual(client.max_output_tokens, 1024)
            self.assertEqual(client.thinking_level, "low")

            cfg = client._build_config()
            self.assertEqual(cfg.temperature, 0.7)
            self.assertEqual(cfg.max_output_tokens, 1024)
            self.assertIsNotNone(cfg.thinking_config)
            self.assertEqual(cfg.thinking_config.thinking_level, "LOW")

    def test_default_config_values(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=True):
            with patch("google.genai.Client"):
                client = LLMClient()
                self.assertEqual(client.model, "gemini-3.5-flash")
                self.assertIsNone(client.temperature)
                self.assertEqual(client.max_output_tokens, 2048)
                self.assertEqual(client.thinking_level, "medium")

    def test_build_config_disables_function_calling_mode_none(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=True):
            with patch("google.genai.Client"):
                client = LLMClient()
                cfg = client._build_config()

                # Verify automatic function calling is disabled
                self.assertIsNotNone(cfg.automatic_function_calling)
                self.assertTrue(cfg.automatic_function_calling.disable)

                # Verify tool_config and function_calling_config mode is explicitly NONE
                self.assertIsNotNone(cfg.tool_config)
                self.assertIsNotNone(cfg.tool_config.function_calling_config)
                self.assertEqual(cfg.tool_config.function_calling_config.mode, "NONE")

                # Verify no tools or function declarations are provided
                self.assertIsNone(cfg.tools)

    def test_build_config_preserves_other_gemini_config(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=True):
            with patch("google.genai.Client"):
                client = LLMClient(
                    temperature=0.5,
                    max_output_tokens=1024,
                    thinking_level="high",
                )
                cfg = client._build_config()

                self.assertEqual(cfg.temperature, 0.5)
                self.assertEqual(cfg.max_output_tokens, 1024)
                self.assertIsNotNone(cfg.thinking_config)
                self.assertEqual(cfg.thinking_config.thinking_level, "HIGH")
                self.assertTrue(cfg.automatic_function_calling.disable)
                self.assertEqual(cfg.tool_config.function_calling_config.mode, "NONE")

    def test_thinking_token_and_finish_reason_extraction(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.text = "42"
            mock_response.response_id = "resp-123"
            mock_response.model_version = "gemini-3.5-flash-001"

            mock_candidate = MagicMock()
            mock_candidate.finish_reason = "STOP"
            mock_candidate.token_count = 20
            mock_response.candidates = [mock_candidate]

            mock_usage = MagicMock()
            mock_usage.prompt_token_count = 50
            mock_usage.candidates_token_count = 20
            mock_usage.thoughts_token_count = 180
            mock_usage.total_token_count = 250
            mock_response.usage_metadata = mock_usage

            mock_instance.models.generate_content.return_value = mock_response
            mock_client_cls.return_value = mock_instance

            client = LLMClient(api_key="fake-key")
            resp = client.generate("What is 6 * 7?")

            self.assertIsInstance(resp, LLMResponse)
            self.assertEqual(resp.text, "42")
            self.assertEqual(resp.finish_reason, "STOP")
            self.assertEqual(resp.input_tokens, 50)
            self.assertEqual(resp.output_tokens, 20)
            self.assertEqual(resp.thinking_tokens, 180)
            self.assertEqual(resp.total_tokens, 250)
            self.assertEqual(resp.response_id, "resp-123")
            self.assertEqual(resp.model_version, "gemini-3.5-flash-001")

    def test_candidate_token_count_fallback(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.text = "42"

            mock_candidate = MagicMock()
            mock_candidate.finish_reason = "STOP"
            mock_candidate.token_count = 25
            mock_response.candidates = [mock_candidate]

            # usage_metadata has NO candidates_token_count
            mock_usage = MagicMock()
            mock_usage.prompt_token_count = 60
            mock_usage.candidates_token_count = None
            mock_usage.thoughts_token_count = 300
            mock_usage.total_token_count = 385
            mock_response.usage_metadata = mock_usage

            mock_instance.models.generate_content.return_value = mock_response
            mock_client_cls.return_value = mock_instance

            client = LLMClient(api_key="fake-key")
            resp = client.generate("question")

            self.assertEqual(resp.output_tokens, 25)
            self.assertEqual(resp.thinking_tokens, 300)

    def test_missing_both_token_count_sources_keeps_output_tokens_none(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.text = "hello"

            mock_candidate = MagicMock()
            mock_candidate.finish_reason = "STOP"
            mock_candidate.token_count = None
            mock_response.candidates = [mock_candidate]
            mock_response.usage_metadata = None

            mock_instance.models.generate_content.return_value = mock_response
            mock_client_cls.return_value = mock_instance

            client = LLMClient(api_key="fake-key")
            resp = client.generate("hi")

            self.assertEqual(resp.text, "hello")
            self.assertIsNone(resp.output_tokens)
            self.assertIsNone(resp.input_tokens)
            self.assertIsNone(resp.thinking_tokens)

    def test_max_tokens_finish_reason(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.text = "Incomplete senten"

            mock_candidate = MagicMock()
            mock_candidate.finish_reason = "MAX_TOKENS"
            mock_candidate.token_count = 512
            mock_response.candidates = [mock_candidate]
            mock_response.usage_metadata = None

            mock_instance.models.generate_content.return_value = mock_response
            mock_client_cls.return_value = mock_instance

            client = LLMClient(api_key="fake-key")
            resp = client.generate("tell me a story")

            self.assertEqual(resp.finish_reason, "MAX_TOKENS")

    def test_generate_failure_raises_runtime_error(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.models.generate_content.side_effect = Exception("API rate limit")
            mock_client_cls.return_value = mock_instance

            client = LLMClient(api_key="fake-key")
            with self.assertRaises(RuntimeError) as ctx:
                client.generate("test question")
            self.assertIn("LLM generation failed", str(ctx.exception))


class TestLLMPartDiagnostics(unittest.TestCase):
    """Tests for sanitized candidate response part diagnostics."""

    def test_normal_text_only_response(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.text = "Paris"

            mock_part = MagicMock()
            mock_part.thought = None
            mock_part.text = "Paris"
            mock_part.function_call = None

            mock_candidate = MagicMock()
            mock_candidate.finish_reason = "STOP"
            mock_candidate.content.parts = [mock_part]
            mock_response.candidates = [mock_candidate]
            mock_response.usage_metadata = None

            mock_instance.models.generate_content.return_value = mock_response
            mock_client_cls.return_value = mock_instance

            client = LLMClient(api_key="fake-key")
            resp = client.generate("What is the capital of France?")

            self.assertEqual(resp.response_part_types, ["text"])
            self.assertEqual(resp.response_part_count, 1)
            self.assertTrue(resp.has_text_part)
            self.assertFalse(resp.has_function_call_part)
            self.assertEqual(resp.text, "Paris")
            self.assertEqual(resp.finish_reason, "STOP")

    def test_function_call_only_response(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.text = None  # SDK returns None when only non-text parts

            mock_part = MagicMock()
            mock_part.thought = None
            mock_part.text = None
            mock_part.function_call = MagicMock(name="search")

            mock_candidate = MagicMock()
            mock_candidate.finish_reason = "STOP"
            mock_candidate.content.parts = [mock_part]
            mock_response.candidates = [mock_candidate]
            mock_response.usage_metadata = None

            mock_instance.models.generate_content.return_value = mock_response
            mock_client_cls.return_value = mock_instance

            client = LLMClient(api_key="fake-key")
            resp = client.generate("Look up the rules of chess")

            self.assertEqual(resp.response_part_types, ["function_call"])
            self.assertEqual(resp.response_part_count, 1)
            self.assertFalse(resp.has_text_part)
            self.assertTrue(resp.has_function_call_part)
            self.assertEqual(resp.text, "")
            self.assertEqual(resp.raw_text, "")
            self.assertEqual(resp.finish_reason, "STOP")

    def test_thought_plus_final_text_response(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.text = "Paris"  # SDK skips thought parts, returns text

            thought_part = MagicMock()
            thought_part.thought = True
            thought_part.text = "Thinking about French geography..."
            thought_part.function_call = None

            text_part = MagicMock()
            text_part.thought = False
            text_part.text = "Paris"
            text_part.function_call = None

            mock_candidate = MagicMock()
            mock_candidate.finish_reason = "STOP"
            mock_candidate.content.parts = [thought_part, text_part]
            mock_response.candidates = [mock_candidate]
            mock_response.usage_metadata = None

            mock_instance.models.generate_content.return_value = mock_response
            mock_client_cls.return_value = mock_instance

            client = LLMClient(api_key="fake-key")
            resp = client.generate("Capital of France?")

            self.assertEqual(resp.response_part_types, ["thought", "text"])
            self.assertEqual(resp.response_part_count, 2)
            self.assertTrue(resp.has_text_part)
            self.assertFalse(resp.has_function_call_part)
            self.assertEqual(resp.text, "Paris")

    def test_thought_only_response_does_not_count_as_final_text(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.text = None  # SDK returns None if only thought parts

            thought_part = MagicMock()
            thought_part.thought = True
            thought_part.text = "Just thinking without final answer..."
            thought_part.function_call = None

            mock_candidate = MagicMock()
            mock_candidate.finish_reason = "STOP"
            mock_candidate.content.parts = [thought_part]
            mock_response.candidates = [mock_candidate]
            mock_response.usage_metadata = None

            mock_instance.models.generate_content.return_value = mock_response
            mock_client_cls.return_value = mock_instance

            client = LLMClient(api_key="fake-key")
            resp = client.generate("What is 1+1?")

            self.assertEqual(resp.response_part_types, ["thought"])
            self.assertEqual(resp.response_part_count, 1)
            self.assertFalse(resp.has_text_part)
            self.assertFalse(resp.has_function_call_part)
            self.assertEqual(resp.text, "")

    def test_mixed_text_and_function_call_response(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.text = "FINAL ANSWER: 42"

            text_part = MagicMock()
            text_part.thought = None
            text_part.text = "FINAL ANSWER: 42"
            text_part.function_call = None

            fc_part = MagicMock()
            fc_part.thought = None
            fc_part.text = None
            fc_part.function_call = MagicMock(name="calc")

            mock_candidate = MagicMock()
            mock_candidate.finish_reason = "STOP"
            mock_candidate.content.parts = [text_part, fc_part]
            mock_response.candidates = [mock_candidate]
            mock_response.usage_metadata = None

            mock_instance.models.generate_content.return_value = mock_response
            mock_client_cls.return_value = mock_instance

            client = LLMClient(api_key="fake-key")
            resp = client.generate("What is 6*7?")

            self.assertEqual(resp.response_part_types, ["text", "function_call"])
            self.assertEqual(resp.response_part_count, 2)
            self.assertTrue(resp.has_text_part)
            self.assertTrue(resp.has_function_call_part)
            self.assertEqual(resp.text, "FINAL ANSWER: 42")

    def test_empty_and_missing_candidate_parts_handled_safely(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_client_cls.return_value = mock_instance
            client = LLMClient(api_key="fake-key")

            # Case A: candidates is None
            resp_a = MagicMock()
            resp_a.candidates = None
            resp_a.text = ""
            resp_a.usage_metadata = None
            mock_instance.models.generate_content.return_value = resp_a
            out_a = client.generate("test")
            self.assertEqual(out_a.response_part_types, [])
            self.assertEqual(out_a.response_part_count, 0)
            self.assertFalse(out_a.has_text_part)
            self.assertFalse(out_a.has_function_call_part)

            # Case B: candidates is empty list
            resp_b = MagicMock()
            resp_b.candidates = []
            resp_b.text = ""
            resp_b.usage_metadata = None
            mock_instance.models.generate_content.return_value = resp_b
            out_b = client.generate("test")
            self.assertEqual(out_b.response_part_types, [])
            self.assertEqual(out_b.response_part_count, 0)

            # Case C: candidate.content is None
            cand_c = MagicMock()
            cand_c.content = None
            cand_c.finish_reason = "STOP"
            cand_c.token_count = 10
            resp_c = MagicMock()
            resp_c.candidates = [cand_c]
            resp_c.text = ""
            resp_c.usage_metadata = None
            mock_instance.models.generate_content.return_value = resp_c
            out_c = client.generate("test")
            self.assertEqual(out_c.response_part_types, [])
            self.assertEqual(out_c.response_part_count, 0)

            # Case D: candidate.content.parts is empty list
            cand_d = MagicMock()
            cand_d.content.parts = []
            cand_d.finish_reason = "STOP"
            cand_d.token_count = 10
            resp_d = MagicMock()
            resp_d.candidates = [cand_d]
            resp_d.text = ""
            resp_d.usage_metadata = None
            mock_instance.models.generate_content.return_value = resp_d
            out_d = client.generate("test")
            self.assertEqual(out_d.response_part_types, [])
            self.assertEqual(out_d.response_part_count, 0)

    def test_real_sdk_part_types_classification(self):
        from google.genai import types
        p_text = types.Part.from_text(text="hello")
        p_thought = types.Part(text="thinking...", thought=True)
        p_fc = types.Part(function_call=types.FunctionCall(name="lookup", args={"k": "v"}))

        # Real text
        resp_text = MagicMock()
        resp_text.candidates = [MagicMock(content=MagicMock(parts=[p_text]))]
        t, c, ht, hfc = extract_part_diagnostics(resp_text)
        self.assertEqual(t, ["text"])
        self.assertEqual(c, 1)
        self.assertTrue(ht)
        self.assertFalse(hfc)

        # Real thought + text + fc
        resp_multi = MagicMock()
        resp_multi.candidates = [MagicMock(content=MagicMock(parts=[p_thought, p_text, p_fc]))]
        t, c, ht, hfc = extract_part_diagnostics(resp_multi)
        self.assertEqual(t, ["thought", "text", "function_call"])
        self.assertEqual(c, 3)
        self.assertTrue(ht)
        self.assertTrue(hfc)


if __name__ == "__main__":
    unittest.main()
