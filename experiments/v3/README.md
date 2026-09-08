# V3 — Controlled Single-Shot Python Execution Baseline

Status: In Development (Capability Scaffolding Phase)

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
- Planning / routing agents
- Multiple web searches or query rewriting
- Verification / reflection agents
- Autonomous Gemini function calling (tools disabled, `mode="NONE"`)
- Automatic execution of attached `.py` files

## Prospective Hypothesis

> Python execution is expected to provide the largest benefit on tasks requiring deterministic calculation, aggregation, filtering, or structured-data manipulation, while providing less benefit on tasks dominated by pure retrieval or visual recognition.

*(Note: This is a prospective hypothesis to be evaluated empirically against contemporaneous matched V2 controls, not a proven claim.)*

## Execution Flow & Invariants

```text
Question
    |
    +-- exactly one Tavily search
    |
    +-- optional V2 FileTool processing
    |
    v
V2 evidence context
    |
    v
Python analysis stage (`python-analysis-v1`)
    |
    +-- NO_CODE generated
    |       |
    |       v
    |   Direct V2 evidence prompt (`file-search-v1` / `web-search-v1`)
    |       |
    |       v
    |   Final Answer
    |
    +-- Python code generated
            |
            v
        PythonTool.execute() [strictly once, max_executions=1]
            |
            +-- Success:
            |       `python-result-v1` prompt -> Gemini -> Final Answer
            |
            +-- Failure / Timeout / Policy rejection:
                    python_fallback = True
                    Fallback to V2 evidence prompt without retrying
                    -> Final Answer
```

## Security & Isolation Boundaries

- Out-of-process execution in an ephemeral temporary directory (`tempfile.mkdtemp`)
- Pre-execution static AST validation (blocking forbidden imports: `subprocess`, `socket`, `requests`, `urllib`, `ctypes`, `os.system`, etc.)
- Task attachment copied into temporary directory as read-only
- Subprocess invoked in isolated mode (`python -I`) with sanitized environment
- Bounded stdout and stderr capture (default 20,000 characters)
- Deterministic timeout (default 15.0 seconds)
- Ephemeral workspace cleanup on completion
