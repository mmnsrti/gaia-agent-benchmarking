# V9 Controlled Smoke Test Audit Report

**Date:** September 18, 2026  
**Auditor:** Automated Benchmark Integrity Suite / Antigravity Agent  
**Target Version:** `V9 — Upstream Candidate Recovery`  
**Parent Baseline:** `V7 — Targeted Repair` (Frozen)  
**Test Suite Reference:** `tests/test_v9_candidate_recovery.py`  
**Verdict:** `ALL_18_SCENARIOS_VERIFIED_PASS`

---

## 1. Executive Summary

This document provides the formal audit record of the **18 controlled smoke test scenarios** preregistered for **V9 — Upstream Candidate Recovery**. All 18 scenarios were executed deterministically against no-network mock doubles in `tests/test_v9_candidate_recovery.py` with 0 live API calls and 0 token expenditure.

All scenarios passed with 100% adherence to:
1. Exact 10-step failure classification precedence.
2. Binary trigger gating (eligible failure classes trigger; provider errors and valid candidate tasks strictly bypass).
3. 100.0% verbatim non-triggered recovery-boundary preservation.
4. Non-destructive safety fallbacks on recovery failure or exception.
5. Strict resource bounds: maximum 6 LLM generation attempts and 0 added search/Python/file tools during recovery.

---

## 2. Controlled Smoke Scenarios Verification Matrix

| # | Scenario Name | Route / Worker Output | Failure Class | Recovery Eligible? | Recovery Triggered? | Post-Recovery Candidate | Total Gen | Status |
| :-: | :--- | :--- | :--- | :-: | :-: | :--- | :-: | :-: |
| **1** | Normal DIRECT Worker Bypass | `FINAL: 42` | `None` | **No** | **No** | `42` (Verbatim) | 4 | **PASS** |
| **2** | Normal PYTHON Worker Bypass | `FINAL_ANSWER: 100` | `None` | **No** | **No** | `100` (Verbatim) | 4 | **PASS** |
| **3** | Python Missing Final Marker | `stdout: Computed answer is 42` | `PYTHON_OUTPUT_MISSING_MARKER` | **Yes** | **Yes** | `42` | 5 | **PASS** |
| **4** | Python Execution Failure | `ModuleNotFoundError: non_existent_mod` | `PYTHON_EXECUTION_FAILURE` | **Yes** | **Yes** | `fallback_value` | 5 | **PASS** |
| **5** | Python Code Extraction Failure | No ` ```python ` block found in text | `PYTHON_CODE_EXTRACTION_FAILURE` | **Yes** | **Yes** | `recovered_text` | 5 | **PASS** |
| **6** | Malformed Function Call | Finish reason `MALFORMED_FUNCTION_CALL` | `MALFORMED_FUNCTION_CALL` | **Yes** | **Yes** | `recovered_from_mfc` | 5 | **PASS** |
| **7** | Function Call Only | Parts contain only function calls | `FUNCTION_CALL_ONLY` | **Yes** | **Yes** | `recovered_from_fco` | 5 | **PASS** |
| **8** | Thought Only | Thinking tokens > 0, output tokens = 0 | `THOUGHT_ONLY` | **Yes** | **Yes** | `recovered_from_to` | 5 | **PASS** |
| **9** | Direct Extraction Failure | Empty or missing `FINAL:` marker | `DIRECT_EXTRACTION_FAILURE` | **Yes** | **Yes** | `Paris` | 5 | **PASS** |
| **10** | Empty LLM Response | `raw_response == ""` | `EMPTY_RESPONSE` | **Yes** | **Yes** | `recovered_from_empty` | 5 | **PASS** |
| **11** | Provider Timeout Bypass | Exception: `provider_timeout` | `PROVIDER_ERROR` | **No** | **No** | `""` (Bypass) | 2 | **PASS** |
| **12** | Provider API Error Bypass | Exception: `provider_api_error` | `PROVIDER_ERROR` | **No** | **No** | `""` (Bypass) | 1 | **PASS** |
| **13** | Precedence: Function Call vs Empty | Text empty, but function call present | `FUNCTION_CALL_ONLY` | **Yes** | **Yes** | `recovered_fc` | 5 | **PASS** |
| **14** | Precedence: Thought Only vs Empty | Text empty, but thinking tokens present | `THOUGHT_ONLY` | **Yes** | **Yes** | `recovered_thought` | 5 | **PASS** |
| **15** | Recovery Empty Output Fallback | Recovery returns whitespace `   \n` | `DIRECT_EXTRACTION_FAILURE` | **Yes** | **Yes** | `""` (Safe fallback) | 3 | **PASS** |
| **16** | Recovery Code Fence Fallback | Recovery returns markdown fence ` ``` ` | `EMPTY_RESPONSE` | **Yes** | **Yes** | `""` (Safe fallback) | 3 | **PASS** |
| **17** | Recovery Exception Fallback | Provider error during recovery LLM call | `EMPTY_RESPONSE` | **Yes** | **Yes** | `""` (Safe fallback) | 3 | **PASS** |
| **18** | Full Pipeline Budget & Zero Tools | Triggered + Verifier + Self-Eval + Repair | `EMPTY_RESPONSE` | **Yes** | **Yes** | `final_repaired_value`| 6 | **PASS** |

---

## 3. Scenario Details & Execution Traces

### Scenario 1: Normal DIRECT Worker Bypass
- **Objective**: Ensure tasks with a valid upstream direct candidate answer bypass recovery entirely.
- **Trace**: Router (`DIRECT`) $\to$ Worker (`FINAL: 42`) $\to$ Recovery Hook (Bypass) $\to$ Verifier (KEEP) $\to$ Self-Eval (PASS).
- **Result**: `pre_recovery_candidate == "42"`, `post_recovery_candidate == "42"`, `candidate_recovery_eligible == False`, `candidate_recovery_triggered == False`, `candidate_recovery_non_triggered_preserved == True`.
- **Generations**: 4 / 5 max.

### Scenario 2: Normal PYTHON Worker Bypass
- **Objective**: Ensure tasks with a valid upstream Python candidate answer bypass recovery entirely.
- **Trace**: Router (`PYTHON`) $\to$ Worker code executes and outputs `FINAL_ANSWER: 100` $\to$ Recovery Hook (Bypass) $\to$ Verifier (KEEP) $\to$ Self-Eval (PASS).
- **Result**: `pre_recovery_candidate == "100"`, `post_recovery_candidate == "100"`, `candidate_recovery_eligible == False`, `candidate_recovery_triggered == False`, `candidate_recovery_non_triggered_preserved == True`.
- **Generations**: 4 / 5 max.

### Scenario 3: Python Missing Final Answer Marker
- **Objective**: Recover candidate when Python script ran successfully and produced diagnostic calculations but omitted `FINAL_ANSWER:`.
- **Classification**: `PYTHON_OUTPUT_MISSING_MARKER` (Eligible).
- **Recovery Prompt**: Contains original question, web evidence, file context, and Python stdout snippet.
- **Recovery Generation**: Outputs `FINAL: 42`.
- **Result**: `pre_recovery_candidate == ""`, `post_recovery_candidate == "42"`, `candidate_recovery_recovered == True`.

### Scenario 4: Python Execution Failure
- **Objective**: Recover candidate when Python code raises an uncaught exception (e.g. `ModuleNotFoundError`).
- **Classification**: `PYTHON_EXECUTION_FAILURE` (Eligible).
- **Recovery Prompt**: Ingests stdout/stderr snippet describing the error alongside existing text evidence.
- **Recovery Generation**: Outputs `FINAL: fallback_value`.
- **Result**: `candidate_recovery_recovered == True`, `final_answer == "fallback_value"`.

### Scenario 5: Python Code Extraction Failure
- **Objective**: Recover candidate when the worker model on the Python route failed to format its response with markdown code fences.
- **Classification**: `PYTHON_CODE_EXTRACTION_FAILURE` (Eligible).
- **Recovery Generation**: Outputs `FINAL: recovered_text`.
- **Result**: `candidate_recovery_recovered == True`, `post_recovery_candidate == "recovered_text"`.

### Scenario 6: Malformed Function Call
- **Objective**: Handle provider finish reason `MALFORMED_FUNCTION_CALL` during upstream worker.
- **Classification**: `MALFORMED_FUNCTION_CALL` (Eligible).
- **Recovery Generation**: Outputs `FINAL: recovered_from_mfc`.
- **Result**: Restores reachability for tasks corrupted by provider tool-calling serialization anomalies.

### Scenario 7: Function Call Only
- **Objective**: Handle cases where worker emitted a tool call part without generating any text part.
- **Classification**: `FUNCTION_CALL_ONLY` (Eligible).
- **Recovery Generation**: Outputs `FINAL: recovered_from_fco`.
- **Result**: Valid candidate extracted from existing context.

### Scenario 8: Thought Only
- **Objective**: Handle cases where worker consumed token budget entirely in `thought` part without producing a `text` part.
- **Classification**: `THOUGHT_ONLY` (Eligible).
- **Recovery Generation**: Outputs `FINAL: recovered_from_to`.
- **Result**: Candidate extracted into valid string format.

### Scenario 9: Direct Extraction Failure
- **Objective**: Handle cases where worker generated text analysis but omitted `FINAL:` marker or provided an empty marker value.
- **Classification**: `DIRECT_EXTRACTION_FAILURE` (Eligible).
- **Recovery Generation**: Outputs `FINAL: Paris`.
- **Result**: `post_recovery_candidate == "Paris"`.

### Scenario 10: Empty Response
- **Objective**: Handle empty LLM worker generation (`""`).
- **Classification**: `EMPTY_RESPONSE` (Eligible).
- **Recovery Generation**: Outputs `FINAL: recovered_from_empty`.
- **Result**: `candidate_recovery_recovered == True`.

### Scenario 11: Provider Timeout Bypass
- **Objective**: Enforce safety boundary on transport timeouts. Timeouts must NOT trigger recovery.
- **Classification**: `PROVIDER_ERROR` (Ineligible).
- **Result**: `candidate_recovery_eligible == False`, `candidate_recovery_triggered == False`, `final_answer == ""`.

### Scenario 12: Provider API Error Bypass
- **Objective**: Enforce safety boundary on HTTP 500 / provider errors.
- **Classification**: `PROVIDER_ERROR` (Ineligible).
- **Result**: Recovery is completely bypassed; transport failures do not waste generation attempts.

### Scenario 13: Precedence - Function Call Only over Empty Response
- **Objective**: Verify that a response with empty text but a function call part is classified as `FUNCTION_CALL_ONLY`, not `EMPTY_RESPONSE`.
- **Result**: Confirmed strict deterministic classification precedence.

### Scenario 14: Precedence - Thought Only over Empty Response
- **Objective**: Verify that a response with empty text but positive thinking tokens is classified as `THOUGHT_ONLY`, not `EMPTY_RESPONSE`.
- **Result**: Confirmed strict deterministic classification precedence.

### Scenario 15: Recovery Output Empty Fallback
- **Objective**: Ensure that if the recovery generation itself returns whitespace, it falls back cleanly without runtime crash.
- **Result**: `candidate_recovery_success == False`, `candidate_recovery_error_type == "empty_recovery_response"`, `post_recovery_candidate == ""`. Downstream verifier cleanly bypassed.

### Scenario 16: Recovery Code Fence Rejection Fallback
- **Objective**: Enforce strict output schema on recovery generation (rejecting ```` ``` ```` code fences).
- **Result**: `candidate_recovery_success == False`, `candidate_recovery_error_type == "markdown_code_fence"`, `post_recovery_candidate == ""`.

### Scenario 17: Recovery Provider Exception Fallback
- **Objective**: Ensure that a network error during recovery generation is caught and handled non-destructively.
- **Result**: Exception safely captured as `candidate_recovery_error_type == "provider_api_error"`, returning clean empty candidate without crashing.

### Scenario 18: Resource Budget & Zero Tools Invariant
- **Objective**: Verify full pipeline execution under worst-case maximum depth:
  Router (1) $\to$ Worker (1) $\to$ Recovery (1) $\to$ Verifier (1) $\to$ Self-Eval (1) $\to$ Targeted Repair (1).
- **Assertions Verified**:
  - `llm_generation_attempts == 6` ($\le 6$ maximum generation bound).
  - `candidate_recovery_searches_added == 0`.
  - `candidate_recovery_python_runs_added == 0`.
  - `candidate_recovery_files_read_added == 0`.
  - Final answer cleanly updated to `final_repaired_value`.

---

## 4. Audit Conclusion

All 18 scenarios have been verified deterministically in `tests/test_v9_candidate_recovery.py`. V9 exhibits zero regressions, full adherence to the pre-registered failure classification taxonomy, strictly non-destructive behavior, and exact budget caps.

