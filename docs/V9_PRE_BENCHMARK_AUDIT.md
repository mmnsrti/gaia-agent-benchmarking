# V9 Pre-Benchmark Audit Report

**Date:** September 18, 2026  
**Auditor:** Automated Benchmark Integrity Suite / Antigravity Agent  
**Target Version:** `V9 — Upstream Candidate Recovery`  
**Parent Baseline:** `V7 — Targeted Repair` (Frozen `v7-targeted-repair`)  
**Branch:** `v9-upstream-candidate-recovery`  
**Parent Preregistration Commit:** `b4891cd29d30a877e06a08dfbf2a551902de7523`  
**Verdict:** `READY_FOR_CANONICAL_BENCHMARK`

---

## 1. Executive Summary

This pre-benchmark audit validates the architectural design, runtime implementation, information firewall, failure safety, telemetry serialization, reachability and downstream safeguard metrics, and test coverage for **V9 (Upstream Candidate Recovery)** prior to canonical benchmarking on the GAIA dataset.

V9 introduces exactly **one bounded capability increment** directly on top of the frozen V7 baseline:
$$\text{V9} = \text{Frozen V7} + \text{Bounded One-Shot Upstream Candidate Recovery for Eligible No-Candidate Tasks}$$

The audit confirms that all core invariants, non-destructive safety mechanisms, information firewalls, deterministic failure classification rules, and test suites are intact and verified across all 373 unit tests with **0 live API calls** and **0 token expenditure**.

---

## 2. Audit Checklist & Verification Matrix

| Audit Dimension | Requirement | Status | Evidence / Invariant |
| :--- | :--- | :---: | :--- |
| **Parent Baseline Integrity** | Frozen V7 code, prompts, and frozen artifacts unmodified | **PASS** | `experiments/v7/FROZEN.md`, configs, summaries intact |
| **Capability Scope** | Single isolated capability increment | **PASS** | Only `_post_worker_candidate_hook` recovery added |
| **Hook Architecture** | Identity no-op for V4–V7; active only in V9 | **PASS** | `_post_worker_candidate_hook` returns original result in `GAIARouterAgent` |
| **Trigger Eligibility** | Triggered only on eligible no-candidate upstream failures | **PASS** | Bypass on non-empty candidate, `PROVIDER_ERROR`, `UNKNOWN_NO_CANDIDATE` |
| **Tool Isolation** | 0 search, 0 python, 0 file re-reads in recovery | **PASS** | `tools_mode = "NONE"`, verified in unit tests (`added_tools == 0`) |
| **Generation Caps** | Strict $\le 5$ (non-triggered) and $\le 6$ (triggered) limit | **PASS** | Enforced by runtime assertions in `GAIAUpstreamCandidateRecoveryAgent` |
| **Failure Safety** | Strictly non-destructive on any error | **PASS** | Falls back cleanly to `pre_recovery_candidate` (`""`) |
| **Information Firewall** | Zero access to ground truth or scorer at runtime | **PASS** | `build_candidate_recovery_prompt` audited; ground truth excluded |
| **Preservation Invariant**| 100.0% verbatim preservation on non-triggered tasks | **PASS** | Verified across all test cases (`preservation_rate == 1.0`) |
| **Telemetry & Privacy** | Public JSONL records contain telemetry without private prompts | **PASS** | Schema version 7; prompts and raw responses excluded from public records |
| **Controlled Smoke** | All 18 smoke scenarios verified deterministically | **PASS** | `docs/V9_CONTROLLED_SMOKE_AUDIT.md` (18/18 PASS) |
| **Full Unit Test Suite** | Dedicated V9 suite + entire repository suite pass | **PASS** | **373 / 373 tests pass** in 72.2s (36 dedicated V9 tests) |

---

## 3. Detailed Technical Verification

### 3.1 Parent Baseline (Frozen V7) Integrity & Subclass Design
- The scientific parent baseline `V7` (`v7-targeted-repair`) is fully preserved.
- `GAIAUpstreamCandidateRecoveryAgent` inherits from `GAIATargetedRepairAgent` (which inherits through `GAIASelfEvaluationAgent` $\to$ `GAIAVerificationAgent` $\to$ `GAIARouterAgent`).
- In the base `GAIARouterAgent`, `_post_worker_candidate_hook(result, ...)` is implemented as a strict identity no-op returning `result` without alteration.
- `GAIAUpstreamCandidateRecoveryAgent` overrides **only** `_post_worker_candidate_hook` and `run()`, injecting candidate recovery at the worker boundary before the candidate answer flows downstream into V5 verification, V6 self-evaluation, and V7 targeted repair.
- Subclass resolution in `evaluation/runner.py` places `GAIAUpstreamCandidateRecoveryAgent` first, preventing subclass shadowing.

### 3.2 Deterministic 10-Class Failure Precedence & Eligibility
Upstream worker failures are classified using a pure, deterministic 10-step decision hierarchy:
1. `PROVIDER_ERROR` (Ineligible): Timeouts, API 500s, quota exhaustion, network disconnects.
2. `PYTHON_OUTPUT_MISSING_MARKER` (Eligible): Python executed successfully with stdout but missing `FINAL_ANSWER:` marker.
3. `PYTHON_EXECUTION_FAILURE` (Eligible): Python script crashed with non-zero exit code or uncaught exception.
4. `PYTHON_CODE_EXTRACTION_FAILURE` (Eligible): Worker on Python route produced no valid markdown code block.
5. `MALFORMED_FUNCTION_CALL` (Eligible): Model finished with `MALFORMED_FUNCTION_CALL` finish reason.
6. `FUNCTION_CALL_ONLY` (Eligible): Response contains function call parts with no text parts.
7. `THOUGHT_ONLY` (Eligible): Response contains thinking tokens but zero output tokens and no text.
8. `DIRECT_EXTRACTION_FAILURE` (Eligible): Worker on Direct route produced text but missing or empty `FINAL:` marker.
9. `EMPTY_RESPONSE` (Eligible): Worker produced an empty string `""`.
10. `UNKNOWN_NO_CANDIDATE` (Ineligible): Any unclassified failure state without a candidate.

Only the 8 designated failure classes are eligible (`is_candidate_recovery_eligible(fc) == True`).

### 3.3 Prompt Construction & Information Firewall
The candidate recovery prompt (`prompts/candidate_recovery.py`, version `candidate-recovery-v1`):
- Assembles: original question, web search evidence snippet, file context summary, and sanitized upstream execution snippet (truncated stdout/stderr without private traces).
- Strictly excludes: ground truth, test labels, official scorer functions, and internal router reasoning traces.
- Enforces a single-line output contract:
  ```text
  FINAL: <candidate answer>
  ```
- Parser (`parse_candidate_recovery_result`) strictly rejects markdown code fences, multiline answers, and missing markers.

### 3.4 Strict Resource Budget & Invariant Enforcement
Runtime assertions in `GAIAUpstreamCandidateRecoveryAgent.run()` guarantee:
- Non-triggered tasks: `llm_generation_attempts <= 5`
- Triggered recovery tasks: `llm_generation_attempts <= 6`
- Zero tool calls during recovery:
  - `candidate_recovery_searches_added == 0`
  - `candidate_recovery_python_runs_added == 0`
  - `candidate_recovery_files_read_added == 0`

### 3.5 Schema Version 7 & Public Serialization
- Output records use `schema_version = 7`.
- Comprehensive telemetry fields are recorded:
  - `candidate_recovery_prompt_version`
  - `pre_recovery_candidate`, `post_recovery_candidate`
  - `candidate_recovery_eligible`, `candidate_recovery_triggered`, `candidate_recovery_attempted`
  - `candidate_recovery_success`, `candidate_recovery_recovered`
  - `candidate_recovery_failure_class`, `candidate_recovery_error_type`, `candidate_recovery_finish_reason`
  - `candidate_recovery_generation_attempts`
  - `candidate_recovery_tokens_*`, `candidate_recovery_latency_seconds`
  - `candidate_recovery_non_triggered_preserved`
- Strict exclusion of raw recovery prompts and raw responses from public prediction files.

---

## 4. Test Suite Verification Summary

The complete test suite was executed via `python -m unittest discover tests`:
```text
Ran 373 tests in 72.203s

OK
```

Breakdown of relevant suites:
- `tests/test_v9_candidate_recovery.py`: 36 / 36 tests PASS
  - Output parsing & validation taxonomy: 2 tests
  - Failure classification & precedence: 10 tests
  - Controlled smoke scenarios: 18 tests
  - Pipeline integration & execute_task: 3 tests
  - Telemetry and candidate recovery metrics: 3 tests
- `tests/test_v7_targeted_repair.py`: 23 / 23 tests PASS
- `tests/test_v6_self_evaluation.py`: 23 / 23 tests PASS
- `tests/test_v5_verification.py`: 14 / 14 tests PASS
- `tests/test_router_agent.py`: 17 / 17 tests PASS
- `tests/test_web_search.py`: 24 / 24 tests PASS
- `tests/test_python_tool.py`: 23 / 23 tests PASS
- `tests/test_v3_runner_and_evaluation.py`: 24 / 24 tests PASS

**Zero regressions detected across all 373 tests.**

---

## 5. Formal Audit Verdict

```text
================================================================================
FINAL AUDIT VERDICT: READY_FOR_CANONICAL_BENCHMARK
================================================================================
```

All preregistered architectural, theoretical, safety, and metric specifications defined in `experiments/v9/DESIGN.md` and `experiments/v9/PRE_BENCHMARK.md` have been fully implemented, validated by controlled smoke tests, and verified across the entire test suite. The system is ready for canonical benchmarking on the GAIA benchmark.
