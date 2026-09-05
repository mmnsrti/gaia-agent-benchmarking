import os
import unittest
from unittest.mock import patch, MagicMock
from agent.llm import LLMClient, LLMResponse


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


if __name__ == "__main__":
    unittest.main()
