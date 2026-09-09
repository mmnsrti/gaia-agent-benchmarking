"""Unit tests for V3 PythonTool isolation, single-generation execution contract, and GAIAPythonAgent."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from tools.python_tool import PythonTool, PythonResult, SecurityPolicyError
from tools.file_tool import FileTool
from agent.agent import (
    GAIAAgent,
    GAIAWebAgent,
    GAIAFileAgent,
    GAIAPythonAgent,
    extract_python_code,
    extract_python_final_answer,
    extract_direct_answer,
)
from agent.llm import LLMClient, LLMResponse
from prompts.baseline import PROMPT_VERSION
from prompts.web_search import WEB_SEARCH_PROMPT_VERSION
from prompts.file_search import FILE_SEARCH_PROMPT_VERSION
from prompts.python_execution import PYTHON_EXECUTION_PROMPT_VERSION


class TestPythonTool(unittest.TestCase):
    def setUp(self):
        self.tool = PythonTool(timeout_seconds=5.0, max_output_length=1000)

    # 1. Every V3 task uses exactly one Gemini generation
    def test_01_single_generation_invariant(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            raw_text="FINAL: 42", text="FINAL: 42"
        )

        agent = GAIAPythonAgent(
            llm_client=mock_llm,
            search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=False))),
            python_tool=self.tool,
        )

        res = agent.run("What is 40 + 2?")
        self.assertEqual(mock_llm.generate.call_count, 1)
        self.assertEqual(res.llm_generation_count, 1)

    # 2. Direct-answer path returns FINAL: ... without executing Python
    def test_02_direct_answer_path(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            raw_text="FINAL: 1969", text="FINAL: 1969"
        )

        mock_py = MagicMock(spec=PythonTool)
        agent = GAIAPythonAgent(
            llm_client=mock_llm,
            search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=False))),
            python_tool=mock_py,
        )

        res = agent.run("When was Apollo 11?")
        self.assertEqual(res.final_answer, "1969")
        self.assertFalse(res.python_requested)
        self.assertFalse(res.python_executed)
        self.assertEqual(mock_py.execute.call_count, 0)
        self.assertEqual(mock_llm.generate.call_count, 1)

    # 3. Python path executes at most once
    def test_03_python_path_executes_at_most_once(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            raw_text="```python\nprint('FINAL_ANSWER: 1500')\n```",
            text="```python\nprint('FINAL_ANSWER: 1500')\n```",
        )

        mock_py = MagicMock(spec=PythonTool)
        mock_py.execute.return_value = PythonResult(
            success=True, executed=True, exit_code=0, stdout="FINAL_ANSWER: 1500\n", latency_seconds=0.1
        )

        agent = GAIAPythonAgent(
            llm_client=mock_llm,
            search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=False))),
            python_tool=mock_py,
        )

        res = agent.run("Calculate 30 * 50")
        self.assertEqual(mock_py.execute.call_count, 1)
        self.assertEqual(res.final_answer, "1500")
        self.assertTrue(res.python_requested)
        self.assertTrue(res.python_executed)
        self.assertEqual(mock_llm.generate.call_count, 1)

    # 4. Python stdout FINAL_ANSWER: is deterministically extracted
    def test_04_python_stdout_marker_deterministically_extracted(self):
        stdout_noisy = "Starting calculation...\nStep 1: 50\nStep 2: 100\nFINAL_ANSWER: 42.5\nExiting."
        extracted = extract_python_final_answer(stdout_noisy)
        self.assertEqual(extracted, "42.5")

        stdout_clean = "FINAL_ANSWER: Paris"
        self.assertEqual(extract_python_final_answer(stdout_clean), "Paris")

    # 5. Malformed/no final marker becomes structured failure
    def test_05_malformed_or_no_final_marker_becomes_structured_failure(self):
        mock_llm = MagicMock()
        # Model emits code that prints but omits FINAL_ANSWER: marker
        mock_llm.generate.return_value = LLMResponse(
            raw_text="```python\nprint(42)\n```",
            text="```python\nprint(42)\n```",
        )

        agent = GAIAPythonAgent(
            llm_client=mock_llm,
            search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=False))),
            python_tool=self.tool,
        )

        res = agent.run("Calculate answer")
        self.assertTrue(res.python_requested)
        self.assertTrue(res.python_executed)
        self.assertFalse(res.python_result.success)
        self.assertTrue(res.python_fallback)
        self.assertEqual(res.python_result.error_type, "MissingFinalAnswerMarker")
        self.assertIn("FINAL_ANSWER:", res.python_result.error_message)
        # Exactly one LLM call occurred
        self.assertEqual(mock_llm.generate.call_count, 1)

    # 6. No second synthesis LLM call occurs
    def test_06_no_second_synthesis_llm_call_occurs(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            raw_text="```python\nprint('FINAL_ANSWER: success')\n```",
            text="```python\nprint('FINAL_ANSWER: success')\n```",
        )

        agent = GAIAPythonAgent(
            llm_client=mock_llm,
            search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=False))),
            python_tool=self.tool,
        )

        res = agent.run("Compute")
        self.assertEqual(mock_llm.generate.call_count, 1)
        self.assertEqual(res.final_answer, "success")

    # 7. No-Python tasks do not receive an extra planning call
    def test_07_no_python_tasks_do_not_receive_planning_call(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            raw_text="FINAL: Mount Everest", text="FINAL: Mount Everest"
        )

        agent = GAIAPythonAgent(
            llm_client=mock_llm,
            search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=False))),
            python_tool=self.tool,
        )

        res = agent.run("What is the highest mountain?")
        self.assertEqual(mock_llm.generate.call_count, 1)
        self.assertEqual(res.final_answer, "Mount Everest")
        self.assertFalse(res.python_executed)

    # 8. Python failures do not trigger a second LLM call
    def test_08_python_failures_do_not_trigger_second_llm_call(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            raw_text="```python\n1 / 0\n```",
            text="```python\n1 / 0\n```",
        )

        agent = GAIAPythonAgent(
            llm_client=mock_llm,
            search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=False))),
            python_tool=self.tool,
        )

        res = agent.run("What is 1/0?")
        self.assertEqual(mock_llm.generate.call_count, 1)
        self.assertTrue(res.python_requested)
        self.assertTrue(res.python_executed)
        self.assertTrue(res.python_fallback)
        self.assertFalse(res.python_result.success)

    # 9. Python execution count remains <= 1
    def test_09_python_execution_count_remains_less_or_equal_to_one(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            raw_text="```python\nprint('FINAL_ANSWER: 99')\n```",
            text="```python\nprint('FINAL_ANSWER: 99')\n```",
        )

        mock_py = MagicMock(spec=PythonTool)
        mock_py.execute.return_value = PythonResult(
            success=True, executed=True, exit_code=0, stdout="FINAL_ANSWER: 99\n"
        )

        agent = GAIAPythonAgent(
            llm_client=mock_llm,
            search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=False))),
            python_tool=mock_py,
        )

        res = agent.run("Compute")
        self.assertLessEqual(mock_py.execute.call_count, 1)

    # 10. V0/V1/V2 behavior remains unchanged
    def test_10_v0_v1_v2_behavior_remains_unchanged(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(raw_text="Final Answer: 42", text="42")

        v0_agent = GAIAAgent(llm_client=mock_llm)
        v0_res = v0_agent.run("What is 2+2?")
        self.assertEqual(v0_res.prompt_version, PROMPT_VERSION)
        self.assertFalse(v0_res.python_executed)
        self.assertEqual(v0_res.llm_generation_count, 1)

        v1_agent = GAIAWebAgent(
            llm_client=mock_llm,
            search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=True, format_evidence_block=MagicMock(return_value="evidence"))))
        )
        v1_res = v1_agent.run("What is 2+2?")
        self.assertEqual(v1_res.prompt_version, WEB_SEARCH_PROMPT_VERSION)
        self.assertFalse(v1_res.python_executed)
        self.assertEqual(v1_res.llm_generation_count, 1)

        v2_agent = GAIAFileAgent(
            llm_client=mock_llm,
            search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=True, format_evidence_block=MagicMock(return_value="evidence"))))
        )
        v2_res = v2_agent.run("What is 2+2?")
        self.assertEqual(v2_res.prompt_version, WEB_SEARCH_PROMPT_VERSION)
        self.assertFalse(v2_res.python_executed)
        self.assertEqual(v2_res.llm_generation_count, 1)

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

    # 12. Public artifacts do not expose generated code
    def test_12_public_artifacts_do_not_expose_generated_code(self):
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

    # 13. Sandbox documentation contains no unsupported security guarantees
    def test_13_sandbox_documentation_contains_no_unsupported_guarantees(self):
        readme_file = "experiments/v3/README.md"
        with open(readme_file, "r", encoding="utf-8") as f:
            readme_text = f.read()

        # Must describe isolation as best-effort research execution isolation
        self.assertIn("best-effort research execution isolation", readme_text)
        # Must explicitly acknowledge limitations (not a kernel sandbox)
        self.assertIn("Not a Kernel Container", readme_text)
        self.assertIn("Static Inspection Limits", readme_text)

    # 14. -I documentation matches actual behavior
    def test_14_python_isolated_mode_flag_matches_actual_behavior(self):
        res = subprocess.run(
            [sys.executable, "-I", "-c", "import sys; print(sys.flags.isolated); print(sys.flags.no_user_site)"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        lines = res.stdout.strip().splitlines()
        self.assertEqual(lines[0], "1")  # sys.flags.isolated == 1
        self.assertEqual(lines[1], "1")  # sys.flags.no_user_site == 1

    # 15. Obvious dynamic import/process/network/path-traversal bypasses are rejected by static AST policy
    def test_15_ast_blocks_obvious_bypasses(self):
        forbidden_snippets = [
            # Dynamic imports & importlib
            "import importlib\nimportlib.import_module('os')",
            "from importlib import util",
            "__import__('os').system('ls')",
            "eval('__import__(' + chr(34) + 'os' + chr(34) + ').system(' + chr(34) + 'ls' + chr(34) + ')')",
            "exec('import os')",
            "compile('1+1', '', 'eval')",
            # Path traversal in open() and pathlib.Path()
            "open('../parent_file.txt', 'r')",
            "open('/etc/passwd', 'r')",
            r"open('C:\\Windows\\System32\\cmd.exe')",
            "from pathlib import Path\nPath('../secret.txt')",
            "from pathlib import Path\nPath('/etc/shadow')",
            # OS / process / alias bypasses
            "from os import system as s\ns('dir')",
            "from os import popen",
            "import os as my_os\nmy_os.system('dir')",
            "import subprocess\nsubprocess.run(['dir'])",
            # Network modules
            "import socket\ns = socket.socket()",
            "import urllib.request\nurllib.request.urlopen('http://example.com')",
            "import requests\nrequests.get('http://example.com')",
            "import ssl\nssl.create_default_context()",
            "import asyncio\nasyncio.get_event_loop()",
        ]

        for snippet in forbidden_snippets:
            res = self.tool.execute(snippet)
            self.assertFalse(res.success, f"Snippet should have failed static validation: {snippet}")
            self.assertFalse(res.executed, f"Snippet should not have been executed: {snippet}")
            self.assertEqual(res.error_type, "SecurityPolicyError")

    # 16. Stdout and stderr captured and bounded
    def test_16_stdout_and_stderr_captured_and_bounded(self):
        # Normal execution
        res = self.tool.execute("print('stdout_test')\nimport sys\nsys.stderr.write('stderr_test\\n')")
        self.assertTrue(res.success)
        self.assertIn("stdout_test", res.stdout)
        self.assertIn("stderr_test", res.stderr)

        # Truncation
        bounded_tool = PythonTool(max_output_length=100)
        res_trunc = bounded_tool.execute("print('A' * 500)")
        self.assertTrue(res_trunc.success)
        self.assertTrue(res_trunc.output_truncated)
        self.assertIn("[stdout truncated]", res_trunc.stdout)

    # 17. Timeout is enforced
    def test_17_timeout_is_enforced(self):
        quick_tool = PythonTool(timeout_seconds=0.2)
        res = quick_tool.execute("import time\ntime.sleep(1.0)")
        self.assertFalse(res.success)
        self.assertTrue(res.timed_out)
        self.assertEqual(res.error_type, "TimeoutError")

    # 18. Temporary workspace is cleaned up
    def test_18_temporary_workspace_cleaned_up(self):
        created_dirs = []
        orig_mkdtemp = tempfile.mkdtemp

        def tracking_mkdtemp(*args, **kwargs):
            d = orig_mkdtemp(*args, **kwargs)
            created_dirs.append(d)
            return d

        with patch("tempfile.mkdtemp", side_effect=tracking_mkdtemp):
            res = self.tool.execute("print('FINAL_ANSWER: done')")
            self.assertTrue(res.success)

        self.assertEqual(len(created_dirs), 1)
        temp_dir = created_dirs[0]
        self.assertFalse(os.path.exists(temp_dir), f"Workspace {temp_dir} not cleaned up!")

    # 19. Gemini function calling remains disabled
    def test_19_gemini_function_calling_remains_disabled(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key_for_unit_tests"}):
            client = LLMClient()
            config = client._build_config()
            self.assertEqual(config.tool_config.function_calling_config.mode.value, "NONE")
            self.assertTrue(config.automatic_function_calling.disable)

    # 20. Runner metadata includes llm_generation_count == 1 and python metadata
    def test_20_runner_metadata_and_asserts(self):
        from evaluation.runner import execute_task
        mock_llm = MagicMock()
        mock_llm.model = "gemini-3.5-flash-lite"
        mock_llm.temperature = None
        mock_llm.max_output_tokens = 2048
        mock_llm.thinking_level = "medium"
        mock_llm.generate.return_value = LLMResponse(
            raw_text="FINAL: 42", text="FINAL: 42"
        )

        task_record = {
            "task_id": "v3-test-task",
            "Question": "What is 40 + 2?",
            "Level": 1,
            "file_name": "",
        }

        task_res = execute_task(
            task_id=task_record["task_id"],
            question=task_record["Question"],
            level=task_record["Level"],
            file_name=task_record["file_name"],
            project_version="v3",
            llm=mock_llm,
        )

        self.assertEqual(task_res["project_version"], "v3")
        self.assertEqual(task_res["llm_generation_count"], 1)
        self.assertEqual(task_res["python_execution_count"], 0)
        self.assertFalse(task_res["python_executed"])
        self.assertFalse(task_res["python_fallback"])
        self.assertEqual(task_res["final_answer"], "42")
        self.assertEqual(task_res["python_prompt_version"], "python-execution-v1")
        self.assertEqual(mock_llm.generate.call_count, 1)


    # 21. Supported attachment + successful FileTool processing
    def test_21_supported_attachment_file_tool_success(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8") as tf:
            tf.write("colA,colB\n10,20\n")
            csv_path = tf.name

        try:
            mock_llm = MagicMock()
            mock_llm.generate.return_value = LLMResponse(
                raw_text="FINAL: 30", text="FINAL: 30"
            )

            agent = GAIAPythonAgent(
                llm_client=mock_llm,
                search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=False))),
                python_tool=self.tool,
            )

            res = agent.run("What is the sum?", file_path=csv_path)
            self.assertTrue(res.file_result.success)
            self.assertFalse(res.file_fallback)
            # Both attachment evidence and attachment filename are in the single prompt
            self.assertIn("ATTACHMENT EVIDENCE:", res.prompt)
            self.assertIn("ATTACHMENT FILE:", res.prompt)
            self.assertIn(os.path.basename(csv_path), res.prompt)
            self.assertEqual(res.final_answer, "30")
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

    # 22. Unsupported attachment + failed FileTool processing
    def test_22_unsupported_attachment_file_tool_fails(self):
        with tempfile.NamedTemporaryFile(suffix=".zip", mode="wb", delete=False) as tf:
            tf.write(b"PK\x05\x06" + b"\x00" * 18)
            zip_path = tf.name

        try:
            ft = FileTool()
            f_res = ft.process(zip_path)
            # FileTool support rules remain strictly unchanged (unsupported)
            self.assertFalse(f_res.success)
            self.assertEqual(f_res.error_type, "UnsupportedFileTypeError")
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)

    # 23. Unsupported attachment still exposes basename to V3 Python prompt and runtime
    def test_23_unsupported_attachment_exposes_basename_to_python_prompt_and_runtime(self):
        with tempfile.NamedTemporaryFile(suffix=".zip", mode="wb", delete=False) as tf:
            tf.write(b"dummy zip data")
            zip_path = tf.name

        try:
            mock_llm = MagicMock()
            # Model uses Python code to inspect the zip file
            zip_base = os.path.basename(zip_path)
            mock_llm.generate.return_value = LLMResponse(
                raw_text=f"```python\nimport os\nexists = os.path.exists('{zip_base}')\nprint(f'FINAL_ANSWER: {{exists}}')\n```",
                text="code",
            )

            agent = GAIAPythonAgent(
                llm_client=mock_llm,
                search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=False))),
                python_tool=self.tool,
            )

            res = agent.run("Does the archive exist?", file_path=zip_path)
            # FileTool failed (unsupported)
            self.assertFalse(res.file_result.success)
            self.assertTrue(res.file_fallback)
            # But the prompt STILL informed the model of the attachment filename
            self.assertIn("ATTACHMENT FILE:", res.prompt)
            self.assertIn(zip_base, res.prompt)
            # And Python runtime received the file in its workspace and successfully accessed it!
            self.assertTrue(res.python_executed)
            self.assertTrue(res.python_result.success)
            self.assertEqual(res.final_answer, "True")
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)

    # 24. Single-generation provenance metadata
    def test_24_single_generation_provenance_metadata(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            raw_text="FINAL: 42", text="FINAL: 42"
        )

        agent = GAIAPythonAgent(
            llm_client=mock_llm,
            search_tool=MagicMock(search=MagicMock(return_value=MagicMock(success=False))),
            python_tool=self.tool,
        )

        res = agent.run("What is 40 + 2?")
        self.assertEqual(res.python_prompt_version, PYTHON_EXECUTION_PROMPT_VERSION)
        self.assertEqual(res.python_prompt, res.prompt)
        self.assertEqual(res.llm_generation_count, 1)
        # Deprecated fields do not contain active multi-stage prompts
        self.assertIsNone(res.python_analysis_prompt)
        self.assertIsNone(res.python_analysis_response)
        self.assertEqual(res.python_final_prompt, res.prompt)


if __name__ == "__main__":
    unittest.main()
