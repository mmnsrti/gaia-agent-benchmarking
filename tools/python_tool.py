"""PythonTool: Controlled, single-shot local Python execution environment for V3.

Executes generated Python code in an isolated temporary directory with:
- Static AST validation blocking dangerous modules and system calls
- Explicit read-only task attachment copying into the execution workspace
- Subprocess execution in isolated mode (python -I) without sensitive environment variables
- Deterministic timeout enforcement
- Bounded stdout/stderr capture and truncation flags
- Automatic temporary directory cleanup

Note: This tool provides conservative isolation for research ablation runs.
It is not a multi-tenant, kernel-level secure operating system container.
"""

import ast
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Optional, Set, Tuple


FORBIDDEN_MODULES: Set[str] = {
    # Shell / Subprocess execution
    "subprocess",
    "pty",
    "commands",
    # Network access
    "socket",
    "urllib",
    "http",
    "requests",
    "aiohttp",
    "httpx",
    "ftplib",
    "poplib",
    "imaplib",
    "smtplib",
    "telnetlib",
    "webbrowser",
    # Low-level memory / system evasion
    "ctypes",
    "cffi",
    # Process / thread spawning
    "multiprocessing",
    "threading",
}

FORBIDDEN_OS_CALLS: Set[str] = {
    "system",
    "popen",
    "kill",
    "fork",
    "spawnl",
    "spawnle",
    "spawnlp",
    "spawnlpe",
    "spawnv",
    "spawnve",
    "spawnvp",
    "spawnvpe",
    "execl",
    "execle",
    "execlp",
    "execlpe",
    "execv",
    "execve",
    "execvp",
    "execvpe",
}

FORBIDDEN_ATTRIBUTES: Set[str] = {
    "__subclasses__",
    "__globals__",
    "__code__",
    "__builtins__",
}


class SecurityPolicyError(Exception):
    """Raised when Python code violates static AST security policy."""
    pass


class SecurityValidator(ast.NodeVisitor):
    """Validates Python AST against forbidden imports, calls, and dunders."""

    def __init__(self):
        self.errors = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            base_mod = alias.name.split(".")[0]
            if base_mod in FORBIDDEN_MODULES:
                self.errors.append(f"Import of forbidden module: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            base_mod = node.module.split(".")[0]
            if base_mod in FORBIDDEN_MODULES:
                self.errors.append(f"Import from forbidden module: '{node.module}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Detect os.system(), os.popen(), etc.
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == "os" and node.func.attr in FORBIDDEN_OS_CALLS:
                self.errors.append(f"Call to forbidden os function: 'os.{node.func.attr}'")
        # Detect direct eval, exec, __import__
        elif isinstance(node.func, ast.Name):
            if node.func.id in ("eval", "exec", "__import__"):
                self.errors.append(f"Direct call to forbidden builtin: '{node.func.id}'")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in FORBIDDEN_ATTRIBUTES:
            self.errors.append(f"Access to forbidden internal attribute: '{node.attr}'")
        self.generic_visit(node)


@dataclass
class PythonResult:
    """Encapsulates execution result, output streams, latency, and failure metadata."""
    success: bool
    executed: bool
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    timed_out: bool = False
    latency_seconds: float = 0.0
    code_length: int = 0
    stdout_length: int = 0
    stderr_length: int = 0
    output_truncated: bool = False
    code: str = ""


class PythonTool:
    """Controlled single-shot Python execution tool."""

    DEFAULT_TIMEOUT_SECONDS: float = 15.0
    DEFAULT_MAX_OUTPUT_LENGTH: int = 20000

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_output_length: int = DEFAULT_MAX_OUTPUT_LENGTH,
        python_executable: Optional[str] = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.max_output_length = max_output_length
        self.python_executable = python_executable or sys.executable

    def validate_code(self, code: str) -> Optional[str]:
        """Validates syntax and static AST security rules. Returns error string if invalid."""
        if not code or not code.strip():
            return "Empty code provided"

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"SyntaxError: {e}"

        validator = SecurityValidator()
        validator.visit(tree)
        if validator.errors:
            return "; ".join(validator.errors)

        return None

    def execute(
        self,
        code: str,
        attachment_path: Optional[str] = None,
    ) -> PythonResult:
        """Executes the given Python code in an ephemeral directory."""
        code_str = code if code is not None else ""
        code_len = len(code_str)

        # 1. Static AST validation
        validation_error = self.validate_code(code_str)
        if validation_error is not None:
            err_type = "SyntaxError" if validation_error.startswith("SyntaxError") else "SecurityPolicyError"
            return PythonResult(
                success=False,
                executed=False,
                exit_code=None,
                stdout="",
                stderr=validation_error,
                error_type=err_type,
                error_message=validation_error,
                timed_out=False,
                latency_seconds=0.0,
                code_length=code_len,
                stdout_length=0,
                stderr_length=len(validation_error),
                output_truncated=False,
                code=code_str,
            )

        # 2. Setup isolated temporary directory
        temp_dir = tempfile.mkdtemp(prefix="gaia_v3_py_")
        start_time = time.time()
        output_truncated = False

        try:
            # Copy task attachment as read-only if provided and exists
            if attachment_path and os.path.isfile(attachment_path):
                dest_file = os.path.join(temp_dir, os.path.basename(attachment_path))
                shutil.copy2(attachment_path, dest_file)
                try:
                    # Mark read-only
                    os.chmod(dest_file, stat.S_IREAD)
                except Exception:
                    pass

            script_path = os.path.join(temp_dir, "solution.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code_str)

            # Build minimal sanitized environment (no API keys, no secrets)
            clean_env = {}
            for k in ("SYSTEMROOT", "PATH", "TMP", "TEMP", "WINDIR", "LOCALAPPDATA", "APPDATA", "TMPDIR", "LANG"):
                if k in os.environ:
                    clean_env[k] = os.environ[k]
            clean_env["PYTHONIOENCODING"] = "utf-8"
            clean_env["PYTHONUNBUFFERED"] = "1"

            # Execute via subprocess in isolated mode (-I)
            cmd = [self.python_executable, "-I", "solution.py"]
            timed_out = False
            exit_code: Optional[int] = None
            stdout_str = ""
            stderr_str = ""
            error_type = None
            error_msg = None

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=temp_dir,
                    env=clean_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=self.timeout_seconds,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                exit_code = proc.returncode
                stdout_str = proc.stdout or ""
                stderr_str = proc.stderr or ""

                if exit_code != 0:
                    error_type = "NonZeroExitCode"
                    error_msg = f"Python process exited with return code {exit_code}"
            except subprocess.TimeoutExpired as te:
                timed_out = True
                exit_code = None
                stdout_str = te.stdout or "" if isinstance(te.stdout, str) else ""
                stderr_str = te.stderr or "" if isinstance(te.stderr, str) else ""
                error_type = "TimeoutError"
                error_msg = f"Execution timed out after {self.timeout_seconds} seconds"
            except Exception as e:
                exit_code = None
                error_type = type(e).__name__
                error_msg = str(e)

            latency = round(time.time() - start_time, 4)
            stdout_len = len(stdout_str)
            stderr_len = len(stderr_str)

            # Bounded output handling
            if stdout_len > self.max_output_length:
                stdout_str = stdout_str[:self.max_output_length] + "\n... [stdout truncated]"
                output_truncated = True

            if stderr_len > self.max_output_length:
                stderr_str = stderr_str[:self.max_output_length] + "\n... [stderr truncated]"
                output_truncated = True

            is_success = (exit_code == 0) and not timed_out and (error_type is None)

            return PythonResult(
                success=is_success,
                executed=True,
                exit_code=exit_code,
                stdout=stdout_str,
                stderr=stderr_str,
                error_type=error_type,
                error_message=error_msg,
                timed_out=timed_out,
                latency_seconds=latency,
                code_length=code_len,
                stdout_length=stdout_len,
                stderr_length=stderr_len,
                output_truncated=output_truncated,
                code=code_str,
            )

        finally:
            # Workspace cleanup (reset read-only bits before rmtree on Windows)
            def _remove_readonly(func, path, _):
                try:
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception:
                    pass

            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, onerror=_remove_readonly)
