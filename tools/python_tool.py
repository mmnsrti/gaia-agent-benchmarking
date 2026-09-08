"""PythonTool: Controlled, single-shot local Python execution environment for V3.

Executes generated Python code in an ephemeral temporary directory with:
- Best-effort research execution isolation for empirical capability ablation
- Static AST validation blocking dangerous modules, system calls, dynamic imports, and path traversal
- Explicit read-only task attachment copying into the execution workspace
- Subprocess execution with isolated flag (python -I) without sensitive environment variables
- Deterministic timeout enforcement (default: 15s)
- Bounded stdout/stderr capture and truncation flags (default: 20,000 chars)
- Automatic temporary directory cleanup

Note on Isolation Boundaries & Limitations:
This tool provides best-effort research execution isolation. It is designed to evaluate
single-shot algorithmic/computational assistance under controlled benchmark conditions.
Guarantees provided:
- Subprocess execution in an isolated working directory with copied read-only attachments.
- Subprocess launched with `sys.executable -I` (ignores environment variables like PYTHONPATH,
  disables user site-packages with -s, and activates safe path with -P). Virtualenv site-packages
  remains accessible (no_site=0), but user-specific directories and ambient environment variables are ignored.
- Minimal sanitized environment variables (no API keys, no tokens, no secrets).
- Static AST policy rejecting dangerous standard-library modules, OS escape calls, and literal path traversal.

Limitations:
- Not an OS-level kernel sandbox (no Linux namespaces/cgroups, Docker, or gVisor).
- Static AST analysis inspects syntax trees; non-literal or dynamically assembled string paths
  cannot be guaranteed caught without kernel containment.
- No guaranteed OS-level network barrier; network isolation relies on static AST import restrictions.
"""

import ast
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import List, Optional, Set


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
    "ssl",
    "xmlrpc",
    "socketserver",
    "asyncio",
    "ipaddress",
    # Dynamic code loading & low-level evasion
    "importlib",
    "ctypes",
    "cffi",
    # Process / thread concurrency
    "multiprocessing",
    "threading",
    "concurrent",
}

FORBIDDEN_OS_CALLS: Set[str] = {
    # Process execution
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
    # Directory & permission modifications outside sandbox
    "chdir",
    "chroot",
    "chmod",
    "chown",
    # Destructive operations
    "remove",
    "unlink",
    "rmdir",
    "removedirs",
}

FORBIDDEN_SHUTIL_CALLS: Set[str] = {
    "rmtree",
    "move",
}

FORBIDDEN_ATTRIBUTES: Set[str] = {
    "__subclasses__",
    "__globals__",
    "__code__",
    "__builtins__",
    "__class__",
    "__mro__",
    "__bases__",
    "__base__",
}

FORBIDDEN_BUILTINS: Set[str] = {
    "eval",
    "exec",
    "__import__",
    "compile",
    "globals",
    "locals",
}


class SecurityPolicyError(Exception):
    """Raised when Python code violates static AST security policy."""
    pass


class SecurityValidator(ast.NodeVisitor):
    """Validates Python AST against forbidden imports, calls, path traversals, and dunders."""

    def __init__(self):
        self.errors: List[str] = []
        self.os_aliases: Set[str] = {"os"}
        self.shutil_aliases: Set[str] = {"shutil"}
        self.forbidden_func_aliases: Set[str] = set()

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            base_mod = alias.name.split(".")[0]
            if base_mod in FORBIDDEN_MODULES:
                self.errors.append(f"Import of forbidden module: '{alias.name}'")
            # Track aliased module names
            if alias.name == "os" and alias.asname:
                self.os_aliases.add(alias.asname)
            if alias.name == "shutil" and alias.asname:
                self.shutil_aliases.add(alias.asname)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            base_mod = node.module.split(".")[0]
            if base_mod in FORBIDDEN_MODULES:
                self.errors.append(f"Import from forbidden module: '{node.module}'")

            # Check imports from os
            if base_mod == "os":
                for alias in node.names:
                    if alias.name in FORBIDDEN_OS_CALLS or alias.name == "*":
                        self.errors.append(f"Import of forbidden os function: 'os.{alias.name}'")
                    if alias.asname:
                        self.forbidden_func_aliases.add(alias.asname)
                    else:
                        self.forbidden_func_aliases.add(alias.name)

            # Check imports from shutil
            if base_mod == "shutil":
                for alias in node.names:
                    if alias.name in FORBIDDEN_SHUTIL_CALLS or alias.name == "*":
                        self.errors.append(f"Import of forbidden shutil function: 'shutil.{alias.name}'")

        self.generic_visit(node)

    def _check_string_path(self, path_str: str, context: str):
        """Rejects obvious directory traversal or absolute paths outside the sandbox."""
        if ".." in path_str:
            self.errors.append(f"Directory traversal ('..') forbidden in {context}: '{path_str}'")
        elif path_str.startswith(("/", "\\")) or re.match(r"^[a-zA-Z]:", path_str):
            self.errors.append(f"Absolute path forbidden in {context}: '{path_str}'")

    def visit_Call(self, node: ast.Call):
        # 1. Check direct forbidden function calls (eval, exec, compile, etc.)
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in FORBIDDEN_BUILTINS:
                self.errors.append(f"Direct call to forbidden builtin: '{func_name}'")
            elif func_name in self.forbidden_func_aliases:
                self.errors.append(f"Call to aliased forbidden function: '{func_name}'")
            elif func_name in ("open", "Path") and node.args:
                # Check path argument in open()
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                    self._check_string_path(first_arg.value, "open()")

        # 2. Check attribute calls (os.system, shutil.rmtree, etc.)
        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr

            # Check os.<call>
            if isinstance(node.func.value, ast.Name) and node.func.value.id in self.os_aliases:
                if attr_name in FORBIDDEN_OS_CALLS:
                    self.errors.append(f"Call to forbidden os function: 'os.{attr_name}'")
                elif attr_name == "open" and node.args:
                    first_arg = node.args[0]
                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                        self._check_string_path(first_arg.value, "os.open()")

            # Check shutil.<call>
            elif isinstance(node.func.value, ast.Name) and node.func.value.id in self.shutil_aliases:
                if attr_name in FORBIDDEN_SHUTIL_CALLS:
                    self.errors.append(f"Call to forbidden shutil function: 'shutil.{attr_name}'")

            # Check Path() / pathlib.Path()
            elif attr_name == "Path" and node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                    self._check_string_path(first_arg.value, "Path()")

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
    """Controlled single-shot Python execution tool providing best-effort research execution isolation."""

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
        """Executes the given Python code in an ephemeral directory with best-effort research isolation."""
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
