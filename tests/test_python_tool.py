"""Unit tests for V3 PythonTool isolation, execution semantics, and GAIAPythonAgent."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from tools.python_tool import PythonTool, PythonResult, SecurityPolicyError
from tools.file_tool import FileTool
from agent.agent import GAIAAgent, GAIAWebAgent, GAIAFileAgent, GAIAPythonAgent, extract_python_code
from agent.llm import LLMClient, LLMResponse
from prompts.baseline import PROMPT_VERSION
from prompts.web_search import WEB_SEARCH_PROMPT_VERSION
from prompts.file_search import FILE_SEARCH_PROMPT_VERSION
from prompts.python_result import PYTHON_RESULT_PROMPT_VERSION
from prompts.python_analysis import PYTHON_ANALYSIS_PROMPT_VERSION


class TestPythonTool(unittest.TestCase):
    def setUp(self):
        self.tool = PythonTool(timeout_seconds=5.0, max_output_length=1000)

    # 1. Python code executes successfully
    def test_01_python_code_executes_successfully(self):
        code = "print(21 * 2)"
        res = self.tool.execute(code)
        self.assertTrue(res.success)
        self.assertTrue(res.executed)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.stdout.strip(), "42")
        self.assertFalse(res.timed_out)
        self.assertIsNone(res.error_type)

    # 2. stdout is captured
    def test_02_stdout_is_captured(self):
        code = "print('line1')\nprint('line2')"
        res = self.tool.execute(code)
        self.assertTrue(res.success)
        self.assertIn("line1", res.stdout)
        self.assertIn("line2", res.stdout)
        self.assertEqual(res.stdout_length, len(res.stdout))

    # 3. stderr is captured
    def test_03_stderr_is_captured(self):
        code = "import sys\nsys.stderr.write('diagnostic warning\\n')"
        res = self.tool.execute(code)
        self.assertTrue(res.success)
        self.assertIn("diagnostic warning", res.stderr)
        self.assertGreater(res.stderr_length, 0)

    # 4. Non-zero exit codes become structured failures
    def test_04_non_zero_exit_codes_become_structured_failures(self):
        code = "import sys\nsys.exit(7)"
        res = self.tool.execute(code)
        self.assertFalse(res.success)
        self.assertTrue(res.executed)
        self.assertEqual(res.exit_code, 7)
        self.assertEqual(res.error_type, "NonZeroExitCode")
        self.assertIn("return code 7", res.error_message)

    # 5. Timeout is enforced
    def test_05_timeout_is_enforced(self):
        quick_tool = PythonTool(timeout_seconds=0.3)
        code = "import time\ntime.sleep(2.0)"
        res = quick_tool.execute(code)
        self.assertFalse(res.success)
        self.assertTrue(res.executed)
        self.assertTrue(res.timed_out)
        self.assertEqual(res.error_type, "TimeoutError")
        self.assertIn("timed out", res.error_message.lower())

    # 6. stdout size is bounded
    def test_06_stdout_size_is_bounded(self):
        bounded_tool = PythonTool(max_output_length=200)
        code = "print('X' * 2000)"
        res = bounded_tool.execute(code)
        self.assertTrue(res.success)
        self.assertTrue(res.output_truncated)
        self.assertLess(len(res.stdout), 300)
        self.assertIn("[stdout truncated]", res.stdout)
        self.assertGreaterEqual(res.stdout_length, 2000)  # 2000 X + newline

    # 7. stderr size is bounded
    def test_07_stderr_size_is_bounded(self):
        bounded_tool = PythonTool(max_output_length=200)
        code = "import sys\nsys.stderr.write('E' * 2000)"
        res = bounded_tool.execute(code)
        self.assertTrue(res.success)
        self.assertTrue(res.output_truncated)
        self.assertLess(len(res.stderr), 300)
        self.assertIn("[stderr truncated]", res.stderr)

    # 8. Execution count cannot exceed one
    def test_08_execution_count_cannot_exceed_one(self):
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = [
            # Stage 1: model proposes Python code
            LLMResponse(raw_text="```python\nprint(10 + 5)\n```", text="```python\nprint(10 + 5)\n```"),
            # Stage 2: model synthesizes final answer
            LLMResponse(raw_text="Final Answer: 15", text="15"),
        ]

        mock_py_tool = MagicMock(spec=PythonTool)
        mock_py_tool.execute.return_value = PythonResult(
            success=True, executed=True, exit_code=0, stdout="15\n", latency_seconds=0.1
        )

        agent = GAIAPythonAgent(
            llm_client=mock_llm,
            search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=False))),
            python_tool=mock_py_tool,
        )

        res = agent.run("What is 10 + 5?")
        self.assertEqual(mock_py_tool.execute.call_count, 1)
        self.assertEqual(res.final_answer, "15")
        self.assertTrue(res.python_executed)
        self.assertEqual(res.prompt_version, PYTHON_RESULT_PROMPT_VERSION)

    # 9. Network-oriented behavior is blocked/rejected
    def test_09_network_oriented_behavior_is_blocked(self):
        network_codes = [
            "import socket\ns = socket.socket()",
            "import urllib.request\nurllib.request.urlopen('http://example.com')",
            "import requests\nrequests.get('http://example.com')",
            "from http import client\nconn = client.HTTPConnection('example.com')",
        ]
        for code in network_codes:
            res = self.tool.execute(code)
            self.assertFalse(res.success)
            self.assertFalse(res.executed)
            self.assertEqual(res.error_type, "SecurityPolicyError")
            self.assertIn("forbidden", res.error_message.lower())

    # 10. Subprocess/shell execution is blocked
    def test_10_subprocess_and_shell_execution_is_blocked(self):
        forbidden_codes = [
            "import subprocess\nsubprocess.run(['echo', 'hi'])",
            "import os\nos.system('echo hi')",
            "import os\nos.popen('dir')",
            "import pty\npty.spawn('/bin/sh')",
        ]
        for code in forbidden_codes:
            res = self.tool.execute(code)
            self.assertFalse(res.success)
            self.assertFalse(res.executed)
            self.assertEqual(res.error_type, "SecurityPolicyError")
            self.assertIn("forbidden", res.error_message.lower())

    # 11. Attached .py files are not automatically executed
    def test_11_attached_py_files_are_not_automatically_executed(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as tf:
            tf.write("import os\nopen('side_effect.txt', 'w').write('executed')")
            temp_py = tf.name

        try:
            ft = FileTool()
            f_res = ft.process(temp_py)
            self.assertTrue(f_res.success)
            self.assertEqual(f_res.processor, "python_source")
            self.assertIn("side_effect", f_res.text_content)
            # Side effect file must NOT exist
            side_effect = os.path.join(os.path.dirname(temp_py), "side_effect.txt")
            self.assertFalse(os.path.exists(side_effect))
        finally:
            if os.path.exists(temp_py):
                os.remove(temp_py)

    # 12. Temporary workspace is cleaned up
    def test_12_temporary_workspace_is_cleaned_up(self):
        created_dirs = []
        original_mkdtemp = tempfile.mkdtemp

        def tracking_mkdtemp(*args, **kwargs):
            d = original_mkdtemp(*args, **kwargs)
            created_dirs.append(d)
            return d

        with patch("tempfile.mkdtemp", side_effect=tracking_mkdtemp):
            res = self.tool.execute("print('workspace test')")
            self.assertTrue(res.success)

        self.assertEqual(len(created_dirs), 1)
        temp_workspace = created_dirs[0]
        self.assertFalse(os.path.exists(temp_workspace), f"Temp dir {temp_workspace} was not cleaned up!")

    # 13. Attachment paths available to Python are restricted to explicitly provided task files
    def test_13_attachment_paths_restricted_to_explicitly_provided_task_files(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as tf:
            tf.write("secret data 12345")
            att_path = tf.name

        try:
            # Script lists files in current working directory
            code = "import os\nfiles = sorted(os.listdir('.'))\nprint(files)"
            res = self.tool.execute(code, attachment_path=att_path)
            self.assertTrue(res.success)
            att_name = os.path.basename(att_path)
            self.assertIn(att_name, res.stdout)
            self.assertIn("solution.py", res.stdout)
            # Ensure no parent repository files leaked in
            self.assertNotIn("runner.py", res.stdout)
            self.assertNotIn(".env", res.stdout)
        finally:
            if os.path.exists(att_path):
                os.remove(att_path)

    # 14. Python failure falls back without retry
    def test_14_python_failure_falls_back_without_retry(self):
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = [
            # Stage 1: proposes buggy code
            LLMResponse(raw_text="```python\n1 / 0\n```", text="```python\n1 / 0\n```"),
            # Fallback Stage 2: produces answer from existing evidence
            LLMResponse(raw_text="Final Answer: fallback answer", text="fallback answer"),
        ]

        mock_search = MagicMock()
        mock_search.search.return_value = MagicMock(success=True, format_evidence_block=MagicMock(return_value="[Search Snippets]"))

        agent = GAIAPythonAgent(
            llm_client=mock_llm,
            search_tool=mock_search,
            python_tool=self.tool,
        )

        res = agent.run("What is 1 divided by 0?")
        self.assertTrue(res.python_requested)
        self.assertTrue(res.python_executed)
        self.assertTrue(res.python_fallback)
        self.assertFalse(res.python_result.success)
        self.assertEqual(res.final_answer, "fallback answer")
        # Exactly two LLM calls (Stage 1 analysis, Stage 2 fallback) - NO python retry!
        self.assertEqual(mock_llm.generate.call_count, 2)

    # 15. V0/V1/V2 behavior remains unchanged
    def test_15_v0_v1_v2_behavior_remains_unchanged(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(raw_text="Final Answer: 42", text="42")

        v0_agent = GAIAAgent(llm_client=mock_llm)
        v0_res = v0_agent.run("What is 2+2?")
        self.assertEqual(v0_res.prompt_version, PROMPT_VERSION)
        self.assertFalse(v0_res.python_executed)

        v1_agent = GAIAWebAgent(llm_client=mock_llm, search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=True, format_evidence_block=MagicMock(return_value="evidence")))))
        v1_res = v1_agent.run("What is 2+2?")
        self.assertEqual(v1_res.prompt_version, WEB_SEARCH_PROMPT_VERSION)
        self.assertFalse(v1_res.python_executed)

        v2_agent = GAIAFileAgent(llm_client=mock_llm, search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=True, format_evidence_block=MagicMock(return_value="evidence")))))
        v2_res = v2_agent.run("What is 2+2?")
        self.assertEqual(v2_res.prompt_version, WEB_SEARCH_PROMPT_VERSION)
        self.assertFalse(v2_res.python_executed)

    # 16. Gemini function calling remains disabled
    def test_16_gemini_function_calling_remains_disabled(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key_for_unit_tests"}):
            client = LLMClient()
            config = client._build_config()
            # Function calling mode must be NONE
            self.assertEqual(config.tool_config.function_calling_config.mode.value, "NONE")
            self.assertTrue(config.automatic_function_calling.disable)

    # 17. Public summaries do not expose generated Python code or attachment contents
    def test_17_public_summaries_do_not_expose_code_or_attachments(self):
        import json
        config_file = "experiments/v3/config.json"
        self.assertTrue(os.path.exists(config_file))
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        prohibited_keys = {"raw_response", "question", "ground_truth", "code", "file_bytes"}
        def check_no_prohibited(d):
            if isinstance(d, dict):
                for k, v in d.items():
                    self.assertNotIn(k.lower(), prohibited_keys)
                    check_no_prohibited(v)
            elif isinstance(d, list):
                for x in d:
                    check_no_prohibited(x)

        check_no_prohibited(data)


if __name__ == "__main__":
    unittest.main()
