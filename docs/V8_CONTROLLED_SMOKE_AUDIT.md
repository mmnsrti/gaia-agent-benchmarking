# V8 Controlled Smoke Audit

**Date:** September 14, 2026  
**Starting Commit:** `37e0efddb9ae4999b1654bac4105d13ada5c573b`  
**Branch:** `v8-active-evidence-verification`  
**Phase:** Pre-Benchmark Controlled Smoke Validation  
**Verdict:** `READY_FOR_CANONICAL_BENCHMARK`

---

## 1. Executive Summary

This audit evaluates the **V8 Controlled Smoke Validation** for **V8 (Bounded Active Evidence Verification)** on the `v8-active-evidence-verification` branch.

V8 introduces a single bounded external verification capability on top of the frozen V7 baseline:
```text
V8 = Frozen V7
   + at most one bounded active web evidence retrieval
   + at most one bounded evidence-based adjudication
```

Following the completion of the pre-benchmark audit and consistency pass, the controlled smoke suite executed eight deterministic scenarios spanning the six core behavioral cases (Cases A through F). All operational mechanics, eligibility gates, usable-evidence thresholds, adjudication outcomes, failure-preservation semantics, resource budgets, telemetry serializations, and post-hoc attribution classifications were validated without error.

**Controlled Smoke Verdict:** `READY_FOR_CANONICAL_BENCHMARK`

---

## 2. Smoke Methodology & Isolation

The smoke validation was conducted using deterministic, no-network test doubles for LLM generation (`SmokeLLM`) and search execution (`SmokeSearchTool`), instrumented with call counters and error injectors.

Key principles enforced during execution:
1. **Deterministic Branch Coverage**: Controlled fixtures were used to exercise exact branches (such as search timeouts, zero search results, malformed adjudication syntax, and provider exceptions) without burning live provider API credits or relying on uncontrollable search engine returns.
2. **Zero Runtime Ground-Truth Access**: The runtime agent, tools, and prompts operated with zero access to reference answers, ground truth, or scoring functions.
3. **End-to-End Runner Execution**: Each case was executed via `execute_task` in `evaluation/runner.py`, validating full serialization to `schema_version = 7`.
4. **Tool Isolation**: Direct-route V8 execution was strictly verified to make zero Python calls (`v8_python_calls = 0`) and zero file rereads (`v8_file_rereads = 0`).
5. **Privacy Firewall**: Prompt strings and raw LLM outputs were excluded from public-safe telemetry artifacts.

---

## 3. Scenario Matrix & Execution Results

Eight controlled cases were executed across the mandated behavioral categories:

| Case ID | Scenario | Eligible | Triggered | Search Usable | Adj Attempted | Action | Answer Changed | Observed Searches | Observed Gen Attempts | Post-Hoc Transition | Result |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `case_a_pass_bypass` | Case A — PASS bypass | No | No | No | No | None | No | 1 (0 active) | 4 (0 active) | `NOT_TRIGGERED` | **PASS** |
| `case_b_reasoning_bypass` | Case B — non-EVIDENCE SUSPECT bypass | No | No | No | No | None | No | 1 (0 active) | 5 (0 active) | `NOT_TRIGGERED` | **PASS** |
| `case_c_eligible_evidence_keep` | Case C — EVIDENCE + valid KEEP | Yes | Yes | Yes | Yes | KEEP | No | 2 (1 active) | 6 (1 active) | `STABLE_CORRECT` | **PASS** |
| `case_d_eligible_evidence_replace` | Case D — EVIDENCE + valid REPLACE | Yes | Yes | Yes | Yes | REPLACE | Yes | 2 (1 active) | 6 (1 active) | `IMPROVEMENT` | **PASS** |
| `case_e1_search_exception_preservation` | Case E1 — Search failure (timeout) | Yes | Yes | No | No | None | No | 2 (1 active) | 5 (0 active) | `STABLE_CORRECT` | **PASS** |
| `case_e2_search_zero_results_preservation` | Case E2 — Search zero results | Yes | Yes | No | No | None | No | 2 (1 active) | 5 (0 active) | `STABLE_CORRECT` | **PASS** |
| `case_f1_parser_failure_preservation` | Case F1 — Adjudication parser failure | Yes | Yes | Yes | Yes | None | No | 2 (1 active) | 6 (1 active) | `STABLE_CORRECT` | **PASS** |
| `case_f2_provider_timeout_preservation` | Case F2 — Adjudication provider timeout | Yes | Yes | Yes | Yes | None | No | 2 (1 active) | 6 (1 active) | `STABLE_CORRECT` | **PASS** |

**Execution Summary:**
- Total Cases: 8
- Passed: 8 (100.0%)
- Failed: 0 (0.0%)

---

## 4. Runtime Invariant Verifications

### 4.1. Eligibility & Triggering Gate
- **PASS Bypass (Case A)**: Confirmed that an assessment of `PASS` results in `active_verification_eligible = False` and `active_verification_triggered = False`. Zero active searches and zero adjudications were attempted.
- **Non-EVIDENCE SUSPECT Bypass (Case B)**: Confirmed that an assessment of `SUSPECT` with risk type `REASONING` completely bypasses active verification. V8 remains strictly EVIDENCE-gated.
- **EVIDENCE SUSPECT Trigger (Cases C, D, E1, E2, F1, F2)**: Confirmed that `SUSPECT` + `EVIDENCE` with a non-empty candidate answer correctly transitions to `active_verification_eligible = True` and `active_verification_triggered = True`.

### 4.2. Query Contract
For all eligible cases, the search query submitted to the search tool was verified to match the exact output of `build_active_evidence_query`:
```text
<original question>

Candidate answer to independently verify:
<Frozen V7 final answer>
```
No query rewriting, keyword extraction, entity planning, or stop-word removal occurred. The 1,500-character provider limit applies strictly to the provider query via `cleaned_query[:1500]`.

### 4.3. Usable-Evidence Gating
- **Cases E1 & E2**: When search encountered an exception or returned zero results (`result_count == 0`), `active_verification_search_usable` was `False`.
- In both cases, adjudication was bypassed (`active_verification_adjudication_attempted = False`), generation attempts remained 0 (`active_verification_generation_attempts = 0`), and the candidate answer was preserved verbatim.

### 4.4. Failure Preservation Semantics
- Across all 4 failure scenarios (search exception, zero search results, parser violation, and provider timeout), `post_active_verification_answer` matched `pre_active_verification_answer` verbatim.
- `active_verification_answer_changed` was `False` in every failure case.
- `active_verification_action` was recorded as `None` across all failure cases.
- **Verification of Critical Rule**: Automatic failures were **never** counted as `KEEP`.

### 4.5. Action Resolution
- **Valid KEEP (Case C)**: Emitting `VERIFICATION_ACTION: KEEP` resulted in `action = "KEEP"`, `answer_changed = False`, and unchanged final answer.
- **Valid REPLACE (Case D)**: Emitting `VERIFICATION_ACTION: REPLACE\nFINAL: 79` resulted in `action = "REPLACE"`, `answer_changed = True`, and `final_answer = "79"`.

---

## 5. Budget Assertions

Strict resource caps were verified across all 8 cases:

| Metric | Observed Max | Allowed Max | Status |
| :--- | :---: | :---: | :---: |
| V8 Additional Searches | 1 | 1 | **PASS** |
| V8 Adjudication Generations | 1 | 1 | **PASS** |
| Total Searches per Task | 2 | 2 | **PASS** |
| Total LLM Generations per Task | 6 | 6 | **PASS** |
| V8 Python Executions | 0 | 0 | **PASS** |
| V8 File Rereads | 0 | 0 | **PASS** |

Search and adjudication retries remained configured to zero (`max_retries = 0`).

---

## 6. Telemetry & Privacy Contract

1. **Schema Version**: Serialized records confirmed `schema_version = 7`.
2. **Field Presence**: All 19 required V8 telemetry fields were confirmed present in serialized outputs:
   - `pre_active_verification_answer`
   - `post_active_verification_answer`
   - `active_verification_eligible`
   - `active_verification_triggered`
   - `active_verification_query`
   - `active_verification_search_attempted`
   - `active_verification_search_success`
   - `active_verification_search_usable`
   - `active_verification_search_error_type`
   - `active_verification_search_result_count`
   - `active_verification_adjudication_attempted`
   - `active_verification_adjudication_success`
   - `active_verification_action`
   - `active_verification_error_type`
   - `active_verification_finish_reason`
   - `active_verification_generation_attempts`
   - `active_verification_generation_success`
   - `active_verification_answer_changed`
   - `active_verification_total_stage_latency_seconds`
3. **Privacy Compliance**: Prompts (`active_verification_prompt`) and unparsed model outputs (`active_verification_raw_response`) were confirmed omitted from public-safe artifacts (`smoke_cases.jsonl`).

---

## 7. Post-Hoc Correctness Attribution

Scoring occurred purely post-hoc via the official GAIA `question_scorer`. The within-run attribution machinery successfully categorized each case:
- `case_a_pass_bypass`: `NOT_TRIGGERED`
- `case_b_reasoning_bypass`: `NOT_TRIGGERED`
- `case_c_eligible_evidence_keep`: `STABLE_CORRECT` (correct $\rightarrow$ correct)
- `case_d_eligible_evidence_replace`: `IMPROVEMENT` (incorrect $\rightarrow$ correct)
- `case_e1_search_exception_preservation`: `STABLE_CORRECT` (preserved correct answer)
- `case_e2_search_zero_results_preservation`: `STABLE_CORRECT` (preserved correct answer)
- `case_f1_parser_failure_preservation`: `STABLE_CORRECT` (preserved correct answer)
- `case_f2_provider_timeout_preservation`: `STABLE_CORRECT` (preserved correct answer)

No causal claims are made based on this smoke validation; it validates the attribution apparatus only.

---

## 8. Test Suite Verification

```powershell
python -m unittest tests/test_v8_active_evidence_verification.py
```
Output:
```text
Ran 21 tests in 0.077s
OK
```

```powershell
python -m unittest discover tests
```
Output:
```text
Ran 349 tests in 67.855s
OK
```

```powershell
git diff --check
```
Output:
*(clean, no whitespace or formatting errors)*

---

## 9. Deviations & Blockers

- **Deviations from Preregistered Design:** None.
- **Blocking Issues:** None.

---

## 10. Audit Verdict

```text
FINAL VERDICT: READY_FOR_CANONICAL_BENCHMARK
```

V8 has passed all controlled smoke validations. The runtime behaves strictly according to design, adheres to all budget and safety invariants, preserves Frozen V7 answers non-destructively, serializes complete telemetry without privacy leakage, and correctly computes post-hoc attribution.

