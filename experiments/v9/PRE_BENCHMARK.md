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
- **$H_{2a}$ (Zero Non-Triggered Degradation)**: For all tasks where the upstream pipeline successfully produces a candidate answer, V9 does not intervene, yielding a Non-Triggered Recovery-Boundary Preservation Rate of exactly **$100.0\%$**.
- **$H_{2b}$ (Reachability Expansion — Descriptive Target)**: Candidate reachability (the fraction of tasks producing a non-empty candidate answer) will increase from the baseline rate of $\sim 50.3\%$ toward a descriptive target of $\ge 65.0\%$. *(Note: Candidate reachability is a mechanism metric, not an outcome metric, and does not substitute for correctness in the promotion decision rule).*
- **$H_{2c}$ (Downstream Safeguard Efficacy)**: Recovered candidate answers will flow through existing V5 verifier and V6/V7 repair stages without runtime exception or schema invalidation, allowing downstream safeguards to verify and repair recovered candidates.

---

## 3. Evaluation Methodology: Within-Run Primary vs. Matched Cross-Run Secondary

### Primary Evaluation: Within-Run Paired Intervention Measurement
The primary scientific evaluation of V9 is the **within-run paired intervention measurement** comparing the pre-recovery state (`pre_recovery_candidate`) and final state (`final_answer`) within the exact same execution trace.

Because both states are recorded in the same runtime task execution, this paired pre/post measurement eliminates run-to-run environment drift:
- Identical web search queries and retrieved evidence
- Identical upstream router stochasticity
- Identical file parsing execution
- Identical provider network conditions

### Secondary Evaluation: Contemporaneous Matched Frozen V7 Run
If a separate Frozen V7 benchmark is executed contemporaneously, it is designated as a **secondary, observational cross-run comparison**:
- Cross-run comparisons between separate stochastic executions can diverge upstream due to LLM sampling variance.
- Therefore, cross-run comparison is reported for observational context, but the within-run paired intervention delta is the sole basis for the formal decision rule.

---

## 4. Preregistered Transition Taxonomy & Structural Asymmetry

For every task, the official vendored GAIA scorer evaluates both the baseline candidate state and the final answer post-hoc:

| Transition Name | Baseline Candidate Correct? | Final Post-Recovery Answer Correct? | Recovery Triggered? | Scientific Interpretation |
| :--- | :---: | :---: | :---: | :--- |
| **`IMPROVEMENT`** | False (or Empty `""`) | True | Yes | Starved or failed task successfully recovered and corrected. |
| **`REGRESSION`** | True | False | Yes / No | Valid answer damaged (see structural asymmetry below). |
| **`STABLE_CORRECT`** | True | True | No | Baseline correct answer preserved. |
| **`STABLE_FAILURE`** | False | False | Yes / No | Task remained incorrect despite recovery, or recovery failed cleanly. |
| **`NON_TRIGGERED_PRESERVED`** | True / False | Identical at boundary | No | Recovery was bypassed; candidate preserved 100% at recovery boundary. |

### Structural Asymmetry of Regressions in V9
In V8 active evidence verification, an already-correct candidate could be directly degraded to an incorrect answer (`1 → 0`). In contrast, V9 candidate recovery is **strictly candidate-starvation-gated**:
- It triggers exclusively when the upstream candidate answer is empty (`""`).
- Because an empty candidate is deterministically evaluated as incorrect ($0$), a direct $1 \to 0$ regression **cannot occur at the recovery boundary itself**.
- Potential regressions in V9 are structurally limited to:
  1. **Non-Triggered Mutation Defect**: A software defect erroneously triggers recovery on a task that already had a correct candidate and damages it (violating the recovery-boundary preservation invariant).
  2. **Downstream Safeguard Damage**: A recovered candidate was correct, but downstream V5 verification or V7 repair subsequently altered it to an incorrect answer (`RECOVERY_CORRECT_FINAL_WRONG`).
  3. **Resource / Generation Budget Violation**: Execution exceeds generation caps.

---

## 5. Downstream Effect Metrics for Recovered Candidates

Because recovered candidates flow through V5 verifier, V6 self-evaluator, and V7 targeted repair, the evaluation tracks explicit downstream transition metrics for all recovered tasks:

| Metric Name | Recovered Candidate Correct? | Final Answer Correct? | Downstream Effect |
| :--- | :---: | :---: | :--- |
| **`RECOVERY_CORRECT_FINAL_CORRECT`** | True | True | Downstream safeguards successfully preserved the correct recovered candidate. |
| **`RECOVERY_CORRECT_FINAL_WRONG`** | True | False | Downstream safeguards (V5 verifier or V7 repair) damaged a correct recovered candidate. |
| **`RECOVERY_WRONG_FINAL_CORRECT`** | False | True | Downstream safeguards rescued and corrected an imperfect recovered candidate. |
| **`RECOVERY_WRONG_FINAL_WRONG`** | False | False | Recovered candidate was wrong and remained wrong after downstream evaluation. |

---

## 6. Primary & Secondary Metrics

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
   $$\text{Accuracy}_{\text{recovered}} = \frac{N_{\text{recovered candidate correct}}}{N_{\text{recovery success}}}$$
7. **Within-Run End-to-End Net Delta**:
   $$\Delta_{\text{net}} = N_{\text{IMPROVEMENT}} - N_{\text{REGRESSION}}$$
8. **Non-Triggered Recovery-Boundary Preservation Rate**:
   $$\text{Preservation Rate}_{\text{boundary}} = \frac{N_{\text{non-triggered with post\_recovery\_candidate == pre\_recovery\_candidate}}}{N_{\text{all non-triggered tasks}}} \quad (\text{Target: } 100.0\%)$$

### Secondary Failure-Class Breakdown Metrics
Recovery effectiveness will be reported individually for each mutually exclusive failure class:
- `PYTHON_OUTPUT_MISSING_MARKER` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)
- `PYTHON_EXECUTION_FAILURE` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)
- `PYTHON_CODE_EXTRACTION_FAILURE` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)
- `MALFORMED_FUNCTION_CALL` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)
- `FUNCTION_CALL_ONLY` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)
- `THOUGHT_ONLY` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)
- `DIRECT_EXTRACTION_FAILURE` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)
- `EMPTY_RESPONSE` ($N_{\text{eligible}}, N_{\text{recovered}}, N_{\text{correct}}$)

---

## 7. Formal Scientific Decision Rule

Following completion of the canonical 165-task benchmark, version promotion will be governed strictly by the following decision boundary:

```text
PROMOTION (V9 Promoted as Baseline for V10):
Required Conditions:
  1. Within-Run End-to-End Net Delta > 0 (Improvements > Regressions)
  2. Non-Triggered Recovery-Boundary Preservation Rate == 100.0%
  3. Zero Added Tools (Search = 0, Python = 0, File = 0 during recovery)
  4. Generation Cap Respected (llm_generation_attempts <= 6 for all tasks; <= 5 on non-triggered tasks)
  5. Operational Run Validity Confirmed (No provider collapse)

Note: Reachability increase is a descriptive mechanism metric, NOT a promotion requirement.
Reachability without net correctness improvement is insufficient for promotion.

NEUTRAL / INSUFFICIENT (V9 Frozen with Documented Limitations):
Condition:
  1. Net Within-Run Delta == 0 (Improvements == Regressions)
  OR
  2. Candidate reachability increases, but recovered candidate accuracy is zero or net correctness is non-positive.
Outcome:
  Version is frozen; candidate recovery without active re-retrieval documented as insufficient.

FAILURE (V9 Rejected):
Condition:
  1. Net Within-Run Delta < 0 (Regressions > Improvements)
  OR
  2. Non-Triggered Recovery-Boundary Preservation Rate < 100.0% (Defect in bypass logic)
  OR
  3. Generation cap violated (> 6 generations).
Outcome:
  Version is rejected.
```

---

## 8. Deterministic Pre-Benchmark Smoke Test Plan (18 Scenarios)

Prior to canonical benchmark execution, V9 must pass **18 deterministic, no-network smoke tests** independently verifying every state machine transition, failure class, and error path:

| Scenario | Subsystem / Worker State | Expected Recovery Behavior | Expected Downstream Behavior | Verification Assertion |
| :---: | :--- | :--- | :--- | :--- |
| **1** | Normal DIRECT worker generates `"42"`. | Ineligible (`eligible=False`). Recovery not attempted. | V5/V6/V7 evaluate normally. | `post_recovery == "42"`, boundary preservation == 100%. |
| **2** | Normal PYTHON worker outputs `FINAL_ANSWER: 100`. | Ineligible (`eligible=False`). Recovery not attempted. | V5/V6/V7 evaluate normally. | `post_recovery == "100"`, boundary preservation == 100%. |
| **3** | Worker failure: `PYTHON_OUTPUT_MISSING_MARKER` (exit 0, no marker). | Eligible (`eligible=True`). Recovery called; returns `FINAL: Gold`. | Flows to V5 verifier with candidate `"Gold"`. | `candidate_recovery_success == True`, `post_recovery == "Gold"`. |
| **4** | Worker failure: `PYTHON_EXECUTION_FAILURE` (script throws exception). | Eligible (`eligible=True`). Recovery called; returns `FINAL: 99`. | Flows to V5 verifier with candidate `"99"`. | `candidate_recovery_success == True`, `post_recovery == "99"`. |
| **5** | Worker failure: `PYTHON_CODE_EXTRACTION_FAILURE` (no code block). | Eligible (`eligible=True`). Recovery called; returns `FINAL: Alpha`. | Flows to V5 verifier with candidate `"Alpha"`. | `candidate_recovery_success == True`, `post_recovery == "Alpha"`. |
| **6** | Worker failure: `MALFORMED_FUNCTION_CALL` (finish reason flagged). | Eligible (`eligible=True`). Recovery called; returns `FINAL: Beta`. | Flows to V5 verifier with candidate `"Beta"`. | `candidate_recovery_success == True`, `post_recovery == "Beta"`. |
| **7** | Worker failure: `FUNCTION_CALL_ONLY` (parts present, no text part). | Eligible (`eligible=True`). Recovery called; returns `FINAL: Paris`. | Flows to V5 verifier with candidate `"Paris"`. | `candidate_recovery_success == True`, `post_recovery == "Paris"`. |
| **8** | Worker failure: `THOUGHT_ONLY` (reasoning present, no text part). | Eligible (`eligible=True`). Recovery called; returns `FINAL: 3.14`. | Flows to V5 verifier with candidate `"3.14"`. | `candidate_recovery_success == True`, `post_recovery == "3.14"`. |
| **9** | Worker failure: `DIRECT_EXTRACTION_FAILURE` (unmatched text). | Eligible (`eligible=True`). Recovery called; returns `FINAL: Mars`. | Flows to V5 verifier with candidate `"Mars"`. | `candidate_recovery_success == True`, `post_recovery == "Mars"`. |
| **10** | Worker failure: `EMPTY_RESPONSE` (last-resort semantic empty text). | Eligible (`eligible=True`). Recovery called; returns `FINAL: Blue`. | Flows to V5 verifier with candidate `"Blue"`. | `candidate_recovery_success == True`, `post_recovery == "Blue"`. |
| **11** | Provider failure bypass: `worker_error_type == "provider_timeout"`. | Ineligible (`eligible=False`). Recovery MUST NOT trigger. | Candidate remains `""`; V5/V6/V7 safely bypass; final answer `""`. | `candidate_recovery_triggered == False`, `post_recovery == ""`. |
| **12** | Provider failure bypass: `worker_error_type == "provider_api_error"`. | Ineligible (`eligible=False`). Recovery MUST NOT trigger. | Candidate remains `""`; V5/V6/V7 safely bypass; final answer `""`. | `candidate_recovery_triggered == False`, `post_recovery == ""`. |
| **13** | Taxonomy precedence: function-call-only with empty raw text. | Classified as `FUNCTION_CALL_ONLY`, strictly NOT `EMPTY_RESPONSE`. | Recovery called with correct classification. | `failure_class == "FUNCTION_CALL_ONLY"`. |
| **14** | Taxonomy precedence: thought-only with empty raw text. | Classified as `THOUGHT_ONLY`, strictly NOT `EMPTY_RESPONSE`. | Recovery called with correct classification. | `failure_class == "THOUGHT_ONLY"`. |
| **15** | Recovery failure: recovery emits empty / whitespace text. | Triggered; parser rejects schema (`empty_recovery_response`). | Candidate remains `""`; V5/V6/V7 safely bypass; final answer `""`. | `post_recovery == ""`, zero crash. |
| **16** | Recovery failure: recovery emits malformed output (code fences). | Triggered; parser rejects schema (`markdown_code_fence`). | Candidate remains `""`; V5/V6/V7 safely bypass; final answer `""`. | `post_recovery == ""`, zero crash. |
| **17** | Recovery failure: provider timeout during recovery API call. | Triggered; exception caught non-destructively. | Candidate remains `""`; V5/V6/V7 safely bypass; final answer `""`. | `post_recovery == ""`, zero crash. |
| **18** | Budget & Tool Isolation Enforcement. | Full trace executed with recovery. | LLM generations $\le 6$; added searches = 0, added Python = 0. | `assert llm_generation_attempts <= 6`, zero added tools. |

---

## 9. Canonical Benchmark Execution Plan

The future canonical benchmark will be conducted across the entire official validation split:

### Benchmark Specification
- **Dataset**: GAIA (General AI Assistants) 2023 Validation Set
  - Level 1: 53 tasks
  - Level 2: 86 tasks
  - Level 3: 26 tasks
  - **Total**: 165 tasks
- **Model**: `gemini-3.5-flash-lite` (preserving Frozen V7 configuration from `experiments/v7/config.json`)
- **Inference Configuration**:
  - `temperature`: `null` (default provider sampling)
  - `max_output_tokens`: 2048
  - `thinking_level`: `medium`
- **Inter-Task Delay**: Exactly 5.0 seconds (rate-limit mitigation)
- **Scorer**: Official GAIA vendored scorer (`evaluation/scorer.py`), unchanged.

---

## 10. Operational Provider Collapse Invalidation & Quarantine Policy

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

## 11. Repository Governance: Promotion vs. Freeze

- If V9 meets all Promotion criteria, the branch `v9-upstream-candidate-recovery` will be merged, and V9 will become the parent baseline for V10.
- If V9 does not meet Promotion criteria, it will be frozen in `experiments/v9/` with a complete `FROZEN.md` and `POST_BENCHMARK_AUDIT.md`, documenting candidate recovery limitations for the academic community.
