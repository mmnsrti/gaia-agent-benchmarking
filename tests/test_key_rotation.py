import os
import unittest
from unittest.mock import patch, MagicMock
from agent.llm import (
    LLMClient,
    _discover_gemini_api_keys,
    _GLOBAL_EXHAUSTED_KEYS,
)
import agent.llm as llm_module


class TestKeyRotation(unittest.TestCase):
    def setUp(self):
        # Reset global rotation state between tests
        llm_module._GLOBAL_EXHAUSTED_KEYS.clear()
        llm_module._GLOBAL_ACTIVE_KEY_INDEX = 0

    def test_discover_explicit_single_and_comma_separated(self):
        keys = _discover_gemini_api_keys(explicit_key="test-key-1234567890")
        self.assertEqual(keys, ["test-key-1234567890"])

        keys_multi = _discover_gemini_api_keys(explicit_key="key-alpha-12345678,key-beta-12345678")
        self.assertEqual(keys_multi, ["key-alpha-12345678", "key-beta-12345678"])

    def test_discover_from_gemini_api_keys_env(self):
        with patch.dict(os.environ, {"GEMINI_API_KEYS": "env-key-11111111,env-key-22222222"}, clear=True):
            keys = _discover_gemini_api_keys()
            self.assertEqual(keys, ["env-key-11111111", "env-key-22222222"])

    def test_discover_from_numbered_env_vars(self):
        env = {
            "GEMINI_API_KEY": "base-key-11111111",
            "GEMINI_API_KEY_1": "num-key-22222222",
            "GEMINI_API_KEY_2": "num-key-33333333",
        }
        with patch.dict(os.environ, env, clear=True):
            keys = _discover_gemini_api_keys()
            self.assertIn("base-key-11111111", keys)
            self.assertIn("num-key-22222222", keys)
            self.assertIn("num-key-33333333", keys)

    def test_single_key_preserves_existing_behavior(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "single-key-12345678"}, clear=True):
            with patch("google.genai.Client") as mock_client:
                client = LLMClient(scan_env_file=False)
                self.assertEqual(client.api_key, "single-key-12345678")
                self.assertEqual(client.api_keys, ["single-key-12345678"])
                self.assertEqual(client.current_key_idx, 0)
                mock_client.assert_called_with(api_key="single-key-12345678")

    def test_rotation_on_429_resource_exhausted(self):
        keys = "key-first-12345678,key-second-12345678"
        with patch("google.genai.Client") as mock_client_cls:
            mock_gen_first = MagicMock()
            mock_gen_first.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED Quota exceeded")

            mock_gen_second = MagicMock()
            fake_resp = MagicMock()
            fake_resp.text = "Success after rotation"
            fake_resp.candidates = [MagicMock(finish_reason="STOP", token_count=10)]
            fake_resp.usage_metadata = None
            fake_resp.response_id = "test-id"
            fake_resp.model_version = "gemini-3.5-flash"
            mock_gen_second.models.generate_content.return_value = fake_resp

            # First client created with key-first, second with key-second
            mock_client_cls.side_effect = [mock_gen_first, mock_gen_second]

            client = LLMClient(api_key=keys)
            self.assertEqual(client.api_key, "key-first-12345678")

            resp = client.generate("Hello world")

            self.assertEqual(resp.text, "Success after rotation")
            self.assertEqual(client.api_key, "key-second-12345678")
            self.assertIn("key-first-12345678", llm_module._GLOBAL_EXHAUSTED_KEYS)

    def test_rotation_on_401_unauthenticated(self):
        keys = "key-authfail-12345678,key-authok-12345678"
        with patch("google.genai.Client") as mock_client_cls:
            mock_gen_first = MagicMock()
            mock_gen_first.models.generate_content.side_effect = Exception("401 UNAUTHENTICATED: Service account disabled")

            mock_gen_second = MagicMock()
            fake_resp = MagicMock()
            fake_resp.text = "Recovered from 401"
            fake_resp.candidates = [MagicMock(finish_reason="STOP", token_count=10)]
            fake_resp.usage_metadata = None
            fake_resp.response_id = "test-id-2"
            fake_resp.model_version = "gemini-3.5-flash"
            mock_gen_second.models.generate_content.return_value = fake_resp

            mock_client_cls.side_effect = [mock_gen_first, mock_gen_second]

            client = LLMClient(api_key=keys)
            resp = client.generate("Hello")

            self.assertEqual(resp.text, "Recovered from 401")
            self.assertEqual(client.api_key, "key-authok-12345678")

    def test_all_keys_exhausted_raises_runtime_error(self):
        keys = "key-dead1-12345678,key-dead2-12345678"
        with patch("google.genai.Client") as mock_client_cls:
            mock_gen = MagicMock()
            mock_gen.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED Daily limit reached")
            mock_client_cls.return_value = mock_gen

            client = LLMClient(api_key=keys)
            with self.assertRaises(RuntimeError) as ctx:
                client.generate("Test prompt")

            self.assertIn("LLM generation failed", str(ctx.exception))
            self.assertIn("429", str(ctx.exception))
            # Both keys are now in exhausted set
            self.assertIn("key-dead1-12345678", llm_module._GLOBAL_EXHAUSTED_KEYS)
            self.assertIn("key-dead2-12345678", llm_module._GLOBAL_EXHAUSTED_KEYS)

    def test_exhausted_key_skipped_by_new_instance(self):
        llm_module._GLOBAL_EXHAUSTED_KEYS.add("key-alreadydead-12345678")
        keys = "key-alreadydead-12345678,key-alive-12345678"

        with patch("google.genai.Client") as mock_client_cls:
            client = LLMClient(api_key=keys)
            # Should have skipped the exhausted key and picked key-alive
            self.assertEqual(client.api_key, "key-alive-12345678")
            self.assertEqual(client.current_key_idx, 1)


if __name__ == "__main__":
    unittest.main()

