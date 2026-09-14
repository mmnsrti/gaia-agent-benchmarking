# V8 Controlled Smoke Validation

## 1. Overview and Scientific Purpose

This directory contains the public-safe artifacts from the **V8 Controlled Smoke Validation**.

V8 introduces **Bounded Active Evidence Verification** to the frozen V7 baseline:
```text
V8 = Frozen V7
   + at most one bounded active web evidence retrieval
   + at most one bounded evidence-based adjudication
```

The purpose of this smoke validation is **not** to evaluate accuracy or benchmark performance, but to verify operational integrity, boundary guards, usable-evidence gating, adjudication parsing, failure-preservation semantics, strict budget enforcement, telemetry serialization, and post-hoc attribution machinery across all critical execution branches before canonical GAIA benchmarking.

---

## 2. Experimental Discipline & Invariants

1. **Trigger Guard Contract**:
   Active evidence verification triggers if and only if:
   - `pre_active_verification_answer` is non-empty.
   - `self_eval_success` is `True`.
   - `self_eval_assessment` is `"SUSPECT"`.
   - `self_eval_risk_type` is `"EVIDENCE"`.
   Any other assessment (`PASS`) or risk type (`REASONING`, `FORMAT`, `EXECUTION`, `CALCULATION`, `UNKNOWN`) completely bypasses active verification (0 searches, 0 adjudications).

2. **Deterministic Query Contract**:
   The active search query is constructed strictly via:
   ```python
   build_active_evidence_query(
       question: str,
       current_answer: str,
   )
   ```
   Formatting:
   ```text
   <original question>

   Candidate answer to independently verify:
   <Frozen V7 final answer>
   ```
   No entity extraction, keyword extraction, rewriting, stop-word filtering, or LLM planning is permitted. Query truncation is handled exclusively by the search tool (`cleaned_query[:1500]`).

3. **Usable Evidence Gating**:
   Adjudication is executed if and only if the active search succeeds **and** returns at least one result snippet (`result_count > 0`). If search fails or returns zero results:
   - Adjudication is bypassed (`active_verification_adjudication_attempted = False`).
   - Adjudication generation attempts are 0 (`active_verification_generation_attempts = 0`).
   - Action is recorded as `None` (`active_verification_action = None`).
   - The candidate answer is preserved verbatim.

4. **Failure Preservation Invariant**:
   Any search failure, zero search results, provider exception, timeout, unexpected finish reason, or parser error preserves the Frozen V7 candidate answer verbatim:
   ```text
   post_active_verification_answer == pre_active_verification_answer
   final_answer == pre_active_verification_answer
   active_verification_answer_changed == False
   ```
   Under no circumstances is an automatic failure counted as `KEEP`.

5. **Budget Enforcements**:
   - V8 additional searches: $\le 1$ (cumulative run total $\le 2$).
   - V8 adjudication generations: $\le 1$ (cumulative run total $\le 6$).
   - V8 Python calls: strictly 0.
   - V8 file rereads: strictly 0.

6. **Privacy Firewall**:
   Raw prompts (`active_verification_prompt`) and unparsed model outputs (`active_verification_raw_response`) are excluded from serialized benchmark artifacts (`smoke_cases.jsonl`), preserving the privacy contract.

7. **Post-Hoc Attribution**:
   Ground truth and scorers are never accessed during runtime. Only post-hoc analysis categorizes within-run intervention transitions:
   - `IMPROVEMENT`: initially incorrect $\rightarrow$ corrected by REPLACE.
   - `REGRESSION`: initially correct $\rightarrow$ corrupted by REPLACE.
   - `STABLE_CORRECT`: initially correct $\rightarrow$ maintained by KEEP or failure preservation.
   - `STABLE_FAILURE`: initially incorrect $\rightarrow$ maintained by KEEP or failure preservation.
   - `NOT_TRIGGERED`: bypassed by eligibility guards.

---

## 3. Scenario Matrix & Results

| Case ID | Scenario | Eligible | Triggered | Search Usable | Adj Attempted | Action | Answer Changed | Observed Searches | Observed Gen Attempts | Transition | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `case_a_pass_bypass` | Case A — PASS bypass | No | No | No | No | None | No | 1 (0 active) | 4 (0 active) | `NOT_TRIGGERED` | **PASS** |
| `case_b_reasoning_bypass` | Case B — non-EVIDENCE bypass | No | No | No | No | None | No | 1 (0 active) | 5 (0 active) | `NOT_TRIGGERED` | **PASS** |
| `case_c_eligible_evidence_keep` | Case C — EVIDENCE + valid KEEP | Yes | Yes | Yes | Yes | KEEP | No | 2 (1 active) | 6 (1 active) | `STABLE_CORRECT` | **PASS** |
| `case_d_eligible_evidence_replace` | Case D — EVIDENCE + valid REPLACE | Yes | Yes | Yes | Yes | REPLACE | Yes | 2 (1 active) | 6 (1 active) | `IMPROVEMENT` | **PASS** |
| `case_e1_search_exception_preservation` | Case E1 — Search failure preservation | Yes | Yes | No | No | None | No | 2 (1 active) | 5 (0 active) | `STABLE_CORRECT` | **PASS** |
| `case_e2_search_zero_results_preservation` | Case E2 — Search zero-results preservation | Yes | Yes | No | No | None | No | 2 (1 active) | 5 (0 active) | `STABLE_CORRECT` | **PASS** |
| `case_f1_parser_failure_preservation` | Case F1 — Adjudication parser failure | Yes | Yes | Yes | Yes | None | No | 2 (1 active) | 6 (1 active) | `STABLE_CORRECT` | **PASS** |
| `case_f2_provider_timeout_preservation` | Case F2 — Adjudication provider timeout | Yes | Yes | Yes | Yes | None | No | 2 (1 active) | 6 (1 active) | `STABLE_CORRECT` | **PASS** |

**Summary**: 8 / 8 cases passed (100%).

---

## 4. Invariant Verification Checklist

- [x] **PASS bypass**: Completely bypassed active search and adjudication.
- [x] **Non-EVIDENCE SUSPECT bypass**: Completely bypassed active search and adjudication.
- [x] **Eligible EVIDENCE + KEEP**: Search succeeded, adjudication emitted valid `KEEP`, answer maintained.
- [x] **Eligible EVIDENCE + REPLACE**: Search succeeded, adjudication emitted valid `REPLACE`, answer updated.
- [x] **Search failure / zero-results preservation**: Adjudication skipped, answer preserved verbatim, action recorded as `None`.
- [x] **Adjudication provider/parser failure preservation**: Answer preserved verbatim, action recorded as `None`.
- [x] **Query contract**: Exact query string verified matching `build_active_evidence_query`.
- [x] **Failure preservation**: All 4 failure paths preserved candidate answers verbatim.
- [x] **Automatic failure not counted as KEEP**: Verified `active_verification_action is None` in all failure paths.
- [x] **Budget caps**: Max additional search = 1, max adjudication gen = 1, total searches $\le 2$, total LLM gens $\le 6$, Python calls = 0, file rereads = 0.
- [x] **Telemetry serialization**: Schema version 7 serialized with all 19 required telemetry fields.
- [x] **Post-hoc attribution**: Pure within-run attribution validated without ground-truth leakage.

---

## 5. Artifact Files

- `smoke_summary.json`: Machine-readable summary of executed scenarios, invariant verifications, budget assertions, and within-run metrics.
- `smoke_cases.jsonl`: Public-safe records with complete schema version 7 telemetry for each controlled smoke case.

