# V9 — Upstream Candidate Recovery: Pre-Benchmark Preregistration Document

**Status**: PREREGISTERED_PRE_BENCHMARK  
**Parent Baseline**: Frozen V7 (`v7-targeted-repair`)  
**Target Version**: V9 (`v9-upstream-candidate-recovery`)  
**Schema Version**: 7  
**Date**: September 2026  

---

## 1. Document Purpose & Binding Scientific Preregistration

This document constitutes the **formal, binding preregistration** for the scientific evaluation of **V9 — Upstream Candidate Recovery**.

In accordance with empirical methodology established in previous benchmark iterations (V5–V8):
1. All hypotheses, evaluation metrics, decision boundaries, transition taxonomies, and failure-handling procedures are fixed **prior to benchmark execution**.
2. No post-hoc modification of success thresholds, trigger conditions, or scoring rules is permitted after viewing benchmark results.
3. Any deviation from the protocols documented herein invalidates the experimental trial.

---

## 2. Preregistered Hypotheses

### Primary Hypothesis ($H_1$)
> *In the GAIA 2023 Validation benchmark, where upstream candidate starvation accounts for approximately half of all task failures (~49.7%), introducing at most one bounded text-only candidate-recovery generation operating on existing evidence will recover a non-trivial fraction of starved tasks into valid candidates, producing a strictly positive net correctness gain ($\Delta = \text{improvements} - \text{regressions} > 0$) within the same task executions.*

### Secondary Hypotheses
- **$H_{2a}$ (Zero Non-Triggered Degradation)**: For all tasks where the upstream pipeline successfully produces a candidate answer, V9 does not intervene, yielding a non-triggered answer preservation rate of exactly **$100.0\%$**.
- **$H_{2b}$ (Reachability Expansion)**: Candidate reachability (the fraction of tasks producing a non-empty candidate answer) will increase significantly from the baseline rate of $\sim 50.3\%$ to at least $\ge 65.0\%$.
- **$H_{2c}$ (Downstream Safeguard Efficacy)**: Recovered candidate answers will flow seamlessly through existing V5 verifier and V6/V7 repair stages, with V5 `KEEP`/`REVISE` and V7 `KEEP`/`REPLACE` operating on recovered candidates without runtime exception or schema invalidation.

---

## 3. Evaluation Methodology: Within-Run Primary vs. Matched Cross-Run Secondary

### Primary Evaluation: Within-Run Causal Measurement
The primary scientific evaluation of V9 is the **within-run, pre-recovery vs. post-recovery transition measurement** on the exact same execution trace.

Because both the pre-recovery state (`pre_recovery_candidate`) and final state (`final_answer`) exist within the identical runtime execution, this comparison controls perfectly for:
- Web search snippet variance
- Upstream routing stochasticity
- File parsing edge cases
- Provider network latency differences

### Secondary Evaluation: Contemporaneous Matched Frozen V7 Run
If a separate Frozen V7 benchmark is executed contemporaneously, it is designated as a **secondary, observational cross-run comparison**:
- Cross-run comparisons between separate stochastic executions can diverge upstream due to LLM sampling variance.
- Therefore, cross-run delta is reported for completeness, but the within-run paired delta is the sole basis for the formal decision rule.

---

## 4. Preregistered Transition Taxonomy

For every task, the official vendored GAIA scorer evaluates both the pre-recovery candidate and the final answer post-hoc:

| Transition Name | Pre-Recovery Candidate Correct? | Final Post-Recovery Answer Correct? | Recovery Triggered? | Scientific Interpretation |
| :--- | :---: | :---: | :---: | :--- |
| **`IMPROVEMENT`** | False (or Empty `""`) | True | Yes | Starved or failed task successfully recovered and corrected. |
| **`REGRESSION`** | True | False | Yes | Valid answer damaged by recovery pipeline (theoretically impossible for starved tasks where candidate was empty). |
| **`STABLE_CORRECT`** | True | True | No | Baseline correct answer preserved verbatim. |
| **`STABLE_FAILURE`** | False | False | Yes / No | Task remained incorrect despite recovery, or recovery failed cleanly. |
| **`NON_TRIGGERED_PRESERVED`** | True / False | Identical | No | Tasks where recovery was bypassed; answer preserved 100% bit-for-bit. |

---

## 5. Primary & Secondary Metrics

### Primary Metrics
1. **Candidate Reachability Before V9**:
   $$\text{Reachability}_{\text{pre}} = \frac{N_{\text{non-empty pre-recovery candidate}}}{N_{\text{total tasks}}}$$
2. **Candidate Reachability After V9**:
   $$\text{Reachability}_{\text{post}} = \frac{N_{\text{non-empty post-recovery candidate}}}{N_{\text{total tasks}}}$$
3. **Reachability Delta**:
   $$\Delta \text{Reachability} = \text{Reachability}_{\text{post}} - \text{Reachability}_{\text{pre}}$$
4. **Recovery Trigger Rate**:
   $$\text{Trigger Rate} = \frac{N_{\text{recovery triggered}}}{N_{\text{total tasks}}}$$
5. **Recovery Success Rate**:
   $$\text{Recovery Success Rate} = \frac{N_{\text{valid non-empty recovery parsed}}}{N_{\text{recovery triggered}}}$$
6. **Recovered Candidate Accuracy**:
   $$\text{Accuracy}_{\text{recovered}} = \frac{N_{\text{recovered correct}}}{N_{\text{recovery success}}}$$
7. **Net Within-Run Correctness Delta**:
   $$\Delta_{\text{net}} = N_{\text{IMPROVEMENT}} - N_{\text{REGRESSION}}$$
8. **Non-Triggered Answer Preservation Rate**:
   $$\text{Preservation Rate}_{\text{non-triggered}} = \frac{N_{\text{identical non-triggered answers}}}{N_{\text{non-triggered tasks}}} \quad (\text{Target: } 100.0\%)$$

### Secondary Failure-Class Breakdown Metrics
Recovery effectiveness will be reported individually for each failure class:
- `EMPTY_RESPONSE` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)
- `FUNCTION_CALL_ONLY` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)
- `THOUGHT_ONLY` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)
- `PYTHON_EXECUTION_FAILURE` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)
- `PYTHON_OUTPUT_MISSING_MARKER` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)
- `PYTHON_CODE_EXTRACTION_FAILURE` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)
- `DIRECT_EXTRACTION_FAILURE` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)

---

## 6. Formal Scientific Decision Rule

Following completion of the canonical 165-task benchmark, the outcome will be governed strictly by the following decision boundary:

```text
PROMOTION (V9 Promoted as Baseline for V10):
Condition:
  1. Net Within-Run Delta > 0 (Improvements > Regressions)
  2. Non-Triggered Answer Preservation Rate == 100.0%
  3. Zero Added Tools (Search = 0, Python = 0, File = 0 during recovery)
  4. Generation Cap Respected (llm_generation_attempts <= 6 for all tasks)
  5. Operational Run Validity Confirmed (No provider collapse)

NEUTRAL / INSUFFICIENT (V9 Frozen with Documented Limitations):
Condition:
  1. Net Within-Run Delta == 0 (Improvements == Regressions)
  OR
  2. Improvements > 0, but offset by equal regressions downstream.
Outcome:
  Version is frozen; candidate recovery without active re-retrieval documented as insufficient.

FAILURE (V9 Rejected):
Condition:
  1. Net Within-Run Delta < 0 (Regressions > Improvements)
  OR
  2. Non-Triggered Answer Preservation Rate < 100.0% (Defect in bypass logic)
  OR
  3. Generation cap violated (> 6 generations).
Outcome:
  Version is rejected.
```

---

## 7. Deterministic Pre-Benchmark Smoke Test Plan

Prior to canonical benchmark execution, V9 must pass **11 deterministic, no-network smoke tests** verifying every state machine transition and error handling path:

| Scenario | Worker / Pipeline State | Expected Recovery Behavior | Expected Downstream Behavior | Verification Assertion |
| :---: | :--- | :--- | :--- | :--- |
| **A** | Normal DIRECT worker generates `"42"`. | Ineligible (`eligible=False`). Recovery not attempted. | V5/V6/V7 evaluate normally. | `post_recovery_candidate == "42"`, `preservation == 100%`. |
| **B** | Normal PYTHON worker outputs `FINAL_ANSWER: 100`. | Ineligible (`eligible=False`). Recovery not attempted. | V5/V6/V7 evaluate normally. | `post_recovery_candidate == "100"`, `preservation == 100%`. |
| **C** | Worker returns `FUNCTION_CALL_ONLY` (or `MALFORMED_FUNCTION_CALL`). | Eligible (`eligible=True`). Recovery called; returns `FINAL: Paris`. | Flows to V5 verifier with candidate `"Paris"`. | `candidate_recovery_success == True`, `post_recovery == "Paris"`. |
| **D** | Worker returns `THOUGHT_ONLY` (reasoning parts present, no text part). | Eligible (`eligible=True`). Recovery called; returns `FINAL: 3.14`. | Flows to V5 verifier with candidate `"3.14"`. | `candidate_recovery_success == True`, `post_recovery == "3.14"`. |
| **E** | Worker returns `EMPTY_RESPONSE` (empty string / whitespace). | Eligible (`eligible=True`). Recovery called; returns `FINAL: Blue`. | Flows to V5 verifier with candidate `"Blue"`. | `candidate_recovery_success == True`, `post_recovery == "Blue"`. |
| **F** | Worker encounters `PYTHON_EXECUTION_FAILURE` (script throws exception). | Eligible (`eligible=True`). Recovery called; returns `FINAL: 99`. | Flows to V5 verifier with candidate `"99"`. | `candidate_recovery_success == True`, `post_recovery == "99"`. |
| **G** | Worker encounters `PYTHON_OUTPUT_MISSING_MARKER` (exit 0, no marker). | Eligible (`eligible=True`). Recovery called; returns `FINAL: Gold`. | Flows to V5 verifier with candidate `"Gold"`. | `candidate_recovery_success == True`, `post_recovery == "Gold"`. |
| **H** | Worker encounters `DIRECT_EXTRACTION_FAILURE` (unmatched text). | Eligible (`eligible=True`). Recovery called; returns `FINAL: Mars`. | Flows to V5 verifier with candidate `"Mars"`. | `candidate_recovery_success == True`, `post_recovery == "Mars"`. |
| **I** | Recovery generation returns empty or malformed text (e.g. code fences). | Triggered; parser rejects schema (`empty_recovery_response` / `missing_final_marker`). | Candidate remains `""`; V5/V6/V7 safely bypass; final answer `""`. | `post_recovery_candidate == ""`, zero unhandled exception. |
| **J** | Recovery generation encounters provider API timeout / exception. | Triggered; exception caught non-destructively. | Candidate remains `""`; V5/V6/V7 safely bypass; final answer `""`. | `post_recovery_candidate == ""`, zero crash. |
| **K** | Budget & Tool Isolation Enforcement. | Full trace executed with recovery. | LLM generations $\le 6$; added searches = 0, added Python = 0. | `assert llm_generation_attempts <= 6`, zero tool invocations in recovery. |

---

## 8. Canonical Benchmark Execution Plan

The future canonical benchmark will be conducted across the entire official validation split:

### Benchmark Specification
- **Dataset**: GAIA (General AI Assistants) 2023 Validation Set
  - Level 1: 53 tasks
  - Level 2: 86 tasks
  - Level 3: 26 tasks
  - **Total**: 165 tasks
- **Model**: `gemini-2.5-flash-lite`
- **Inference Configuration**:
  - `temperature`: `null` (default provider sampling)
  - `max_output_tokens`: 2048
  - `thinking_level`: `medium`
- **Inter-Task Delay**: Exactly 5.0 seconds (rate-limit mitigation)
- **Scorer**: Official GAIA vendored scorer (`evaluation/scorer.py`), unchanged.

---

## 9. Operational Provider Collapse Invalidation & Quarantine Policy

To prevent infrastructure failures from corrupting scientific conclusions, the following operational invalidation rules are established:

### Invalidation Criteria
A benchmark level or run is declared **OPERATIONALLY INVALID** if:
1. **Exhaustive Multi-Key Depletion**: All available Gemini API keys in the multi-key failover pool fail simultaneously due to persistent HTTP 429 (`RESOURCE_EXHAUSTED`) or network disconnection.
2. **Provider Request Failures**: Unhandled provider exceptions exceed $\ge 5\%$ of tasks in a level.
3. **Premature Run Termination**: Benchmark run aborts prior to executing all tasks in the level.

### Quarantine Protocol
- Any invalid run must be immediately moved to `experiments/quarantine/` with a forensic audit report documenting the operational root cause.
- Invalid runs must **never** be scored for scientific evaluation, nor used to judge the efficacy of V9.
- A clean rerun must be conducted only after provider quota or network connectivity is fully restored.

---

## 10. Repository Governance: Promotion vs. Freeze

- If V9 meets all Promotion criteria, the branch `v9-upstream-candidate-recovery` will be merged, and V9 will become the parent baseline for V10.
- If V9 does not meet Promotion criteria, it will be frozen in `experiments/v9/` with a complete `FROZEN.md` and `POST_BENCHMARK_AUDIT.md`, documenting candidate recovery limitations for the academic community.

