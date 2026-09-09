# V3 — Controlled Single-Shot Python Execution Baseline

Status: FROZEN

See [FROZEN.md](FROZEN.md) for the complete canonical freeze manifest, benchmark results, transition analysis, regression mechanism audit, and research summary.

Branch: `v3-python-execution`

Base Tag: `v2-file-attachments-final` (commit `96f5b229c7c0ae8e58b83855c97ca7564ee495ef`)

## Capability Definition

V3 adds controlled, single-shot local Python code execution to the frozen V2 baseline:
```text
V3 = frozen V2 + controlled single-shot local Python execution
```

V3 does NOT add:
- Autonomous tool loops
- Multi-step Python retries or debugging loops
- Planning / routing agents or multiple reasoning turns
- Multiple web searches or query rewriting
- Verification / reflection agents
- Autonomous Gemini function calling (tools disabled, `mode="NONE"`)
- Automatic execution of attached `.py` files

## Prospective Hypothesis

> Python execution is expected to provide the largest benefit on tasks requiring deterministic calculation, aggregation, filtering, or structured-data manipulation, while providing less benefit on tasks dominated by pure retrieval or visual recognition.

*(Note: This is a prospective hypothesis to be evaluated empirically against contemporaneous matched V2 controls, not a proven claim.)*

## Single-Generation Execution Flow & Invariants

To avoid confounding the ablation with extra LLM reasoning turns, V3 enforces a strict single-generation contract (`llm_generation_count == 1` per task).

```text
Question
    |
    +-- exactly one Tavily search (inherited from V1/V2)
    |
    +-- optional V2 FileTool processing (inherited from V2)
    |
    v
Single V3 execution-aware prompt (`python-execution-v1`)
    |
    v
Single Gemini generation (`llm_generation_count == 1`)
    |
    +-- Option A: "FINAL: <answer>"
    |       -> Deterministically extract answer (python_executed = False)
    |
    +-- Option B: ```python ... ``` script
            |
            v
        PythonTool.execute() [strictly once, python_execution_count <= 1]
            |
            +-- Success (stdout contains 'FINAL_ANSWER: <ans>'):
            |       Extract <ans> deterministically from stdout
            |
            +-- Failure / Missing Marker / Policy Rejection / Timeout:
                    python_fallback = True
                    Extract direct answer if present in model text; otherwise empty string
                    No second Gemini call, no retry, no self-correction
```

### Invariants Preserved
- `llm_generation_count == 1` for every task
- `python_execution_count in (0, 1)` for every task
- No second LLM synthesis turn after Python execution
- No retry or self-correction turn on execution failure

## Isolation Boundaries & Limitations

Execution isolation in V3 is characterized as **best-effort research execution isolation**:
- **Ephemeral Workspace:** Executed inside a dedicated temporary directory (`tempfile.mkdtemp`), cleaned up immediately upon completion.
- **Read-Only Attachments:** Copied task attachments are placed in the ephemeral directory with read-only permissions (`stat.S_IREAD`).
- **Subprocess Flag (`-I`):** Launched via `[sys.executable, "-I", "solution.py"]`. The `-I` flag operates in isolated mode:
  - `-E`: Ignores ambient environment variables such as `PYTHONPATH` and `PYTHONHOME`.
  - `-s`: Disables user site-packages (`~/.local` or `%APPDATA%\Python`).
  - `-P`: Safe path mode (does not prepend current directory to `sys.path` by default).
  - *Note:* Virtual environment `site-packages` remains accessible (`no_site=0`), but ambient user paths are excluded.
- **Environment Sanitization:** Subprocess receives a minimal whitelist of system variables (`SYSTEMROOT`, `PATH`, `TMP`, etc.), omitting all API keys and secrets.
- **Static AST Policy:** Static syntax inspection blocks dangerous modules (`subprocess`, `socket`, `urllib`, `requests`, `aiohttp`, `importlib`, `ctypes`, `multiprocessing`), dangerous functions (`os.system`, `eval`, `exec`, `compile`), and path traversal (`..` or absolute paths in `open`/`pathlib.Path`).
- **Resource Bounds:** Execution timeout at 15.0s; stdout and stderr capped at 20,000 characters.

### Explicit Limitations
- **Not a Kernel Container:** Does not employ OS-level containerization (Docker, gVisor, or Linux namespaces/cgroups).
- **Static Inspection Limits:** Static AST analysis inspects literal syntax nodes; non-literal or dynamically assembled string paths cannot be guaranteed caught without kernel sandboxing.
- **No Kernel Network Firewall:** Network isolation relies on static AST import restrictions, not OS-level firewall rules.

## Freeze Rule

V3 is frozen as the immutable research baseline for controlled single-shot local Python execution:

```text
V3 = V2 + controlled single-shot local Python execution
```

Future work must not alter V3 results, agent runtime behavior, prompts, model settings, tool configurations, or benchmark evaluations. Any subsequent planner/router work belongs to V4.
