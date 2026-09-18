# V10 — Structured Planner → Plan-Guided Executor: Pre-Benchmark Preregistration Document

**Status**: `PREREGISTERED_PRE_BENCHMARK`  
**Parent Baseline**: Frozen V9 (`v9-upstream-candidate-recovery`)  
**Target Version**: V10 (`v10-planner-executor`)  
**Schema Version**: 8  
**Baseline Main Commit**: `7e6f35bd27c83c23072e27a337d52e157d5904cd`  
**Date**: September 2026  

---

## 1. Document Purpose & Binding Scientific Preregistration

This document establishes the **formal, binding preregistration** for **Version 10 (V10) — Structured Planner → Plan-Guided Executor**.

Under empirical benchmarking protocols established across V5 through V9:
1. All research hypotheses, comparison protocols, transition taxonomies, metric definitions, and decision thresholds are permanently established **prior to benchmark implementation and execution**.
2. No post-hoc modification of decision rules, plan schemas, fallback semantics, or success thresholds is permitted after benchmark execution.
3. Any procedural deviation from the preregistered protocol invalidates the experimental trial.

---

## 2. Preregistered Hypotheses

### Primary Hypothesis ($H_1$ — Paired Upstream Intervention)
> *Under a shared-context paired upstream ablation using identical question, search evidence, and file context, replacing the Frozen V9 Router → Worker pair with Structured Planner → Plan-Guided Executor will produce a strictly positive upstream candidate correctness net delta:*
> $$\Delta_{\text{upstream}} = N_{\text{UPSTREAM\_IMPROVEMENT}} - N_{\text{UPSTREAM\_REGRESSION}} > 0$$
> *without increasing retrieval, file, Python, or upstream generation budgets.*

### End-to-End Performance Hypothesis ($H_2$ — Benchmark Reference)
> *Canonical V10 end-to-end official GAIA accuracy will exceed the Frozen V9 canonical reference of:*
> $$73 / 165 = 44.24\%$$
> *(Treated as performance evidence, not an isolated causal estimate).*

### Secondary Hypotheses
- **$H_{3a}$ (Reduction in Execution and Evidence Errors)**: The conditional error rate for tasks assessed with `EXECUTION` risk ($78.3\%$ in V9) and `EVIDENCE` risk ($88.9\%$ in V9) will decrease, reflecting superior task decomposition and explicit evidence targeting.
- **$H_{3b}$ (Candidate Reachability Preservation)**: High candidate reachability achieved in Frozen V9 ($\ge 90.0\%$, V9 canonical: $96.36\%$) will be maintained.
- **$H_{3c}$ (Reduction in Upstream Starvation / Recovery Trigger Rate)**: Clearer execution objectives will reduce worker starvation, lowering the candidate recovery trigger rate below V9's baseline rate of $54.55\%$ ($90/165$).
- **$H_{3d}$ (Deterministic Plan Parsing Reliability)**: The deterministic line-oriented plan parser will successfully parse $\ge 95.0\%$ of planner outputs without triggering fallback.
- **$H_{3e}$ (Python Execution Viability)**: Plan-guided code generation will achieve $\ge 80.0\%$ execution completion rates for tasks routed to `MODE: PYTHON`.

---

## 3. Evaluation Methodology: Two-Tier Evaluation Hierarchy

Because the V10 scientific intervention replaces the upstream `Router → Worker` pair before any candidate answer exists, V10 preregisters two distinct evaluation layers:

### 3.1 Tier 1 (Primary): Shared-Context Paired Upstream Ablation
For each GAIA task:
```text
Question
   │
   ▼
ONE shared Frozen search result (snapshotted)
ONE shared Frozen file/attachment context (snapshotted)
   │
   ├───────────────────────────────────────────┐
   ▼                                           ▼
Branch A:                                   Branch B:
Frozen V9 Capability Router                 V10 Structured Planner
   │                                           │
   ▼                                           ▼
Frozen V9 Worker                            V10 Plan-Guided Executor
   │                                           │
   ▼                                           ▼
V9 Upstream Candidate                       V10 Upstream Candidate
```
- **Controlled Elements**: Identical question, identical search evidence, identical file context, identical tool budgets, and identical model configuration.
- **Primary Intervention Boundary**: Direct comparison of candidate quality emitted at the upstream boundary before downstream candidate recovery, verification, self-evaluation, or repair occurs. Downstream mechanisms are frozen and do not isolate the upstream intervention.
- **Methodological Characterization**: This paired protocol removes retrieval and context divergence and directly compares the replaced upstream stages, while residual generation stochasticity remains. It is explicitly **not** characterized as a "perfect causal estimate" or "fully causal."

### 3.2 Tier 2 (Secondary): Contemporaneous Full Frozen V9 Matched Control
- A canonical V10 full 165-task benchmark is paired with a contemporaneous Frozen V9 full 165-task control run executed under matched infrastructure and 5.0s delay.
- Evaluates full end-to-end accuracy including downstream safeguards.
- **Methodological Characterization**: Cross-run comparisons between separate stochastic executions are subject to LLM sampling variance. Therefore, this secondary comparison is explicitly classified as **observational and non-causal**. The resulting cross-run transition matrix is reported for observational context, but is NOT used as the isolated intervention criterion.

---

## 4. Preregistered Transition Taxonomies

### 4.1 Primary Upstream Paired Transition Matrix
Evaluates the candidate answers produced by Branch A and Branch B using the official vendored GAIA scorer (`evaluation/scorer.py`) post-hoc:

| Transition Name | Frozen V9 Upstream Candidate | V10 Upstream Candidate | Scientific Interpretation |
| :--- | :---: | :---: | :--- |
| **`UPSTREAM_IMPROVEMENT`** | False (or Empty `""`) | True | Upstream candidate failed under Router $\to$ Worker but correctly generated by Planner $\to$ Executor. |
| **`UPSTREAM_REGRESSION`** | True | False (or Empty `""`) | Upstream candidate correct under Router $\to$ Worker but damaged by Planner $\to$ Executor. |
| **`UPSTREAM_STABLE_CORRECT`** | True | True | Both upstream approaches produce correct candidates. |
| **`UPSTREAM_STABLE_FAILURE`** | False | False | Both upstream approaches fail to produce a correct candidate. |

The primary paired intervention metric is:
$$\Delta_{\text{upstream}} = N_{\text{UPSTREAM\_IMPROVEMENT}} - N_{\text{UPSTREAM\_REGRESSION}}$$

### 4.2 Secondary End-to-End Cross-Run Transition Matrix (Observational)
Compares contemporaneous Frozen V9 final answers to V10 final answers across the full pipeline:
- `E2E_IMPROVEMENT` ($0 \to 1$)
- `E2E_REGRESSION` ($1 \to 0$)
- `E2E_STABLE_CORRECT` ($1 \to 1$)
- `E2E_STABLE_FAILURE` ($0 \to 0$)
- Net cross-run delta: $\Delta_{\text{e2e\_obs}} = N_{\text{E2E\_IMPROVEMENT}} - N_{\text{E2E\_REGRESSION}}$ (observational context only).

---

## 5. Metrics Specification

### Primary Outcome Metrics
1. **Primary Paired Upstream Delta**:
   $$\Delta_{\text{upstream}} = N_{\text{UPSTREAM\_IMPROVEMENT}} - N_{\text{UPSTREAM\_REGRESSION}}$$
2. **Official Canonical Accuracy**:
   $$\text{Accuracy}_{\text{V10}} = \frac{N_{\text{correct}}}{165} \quad (\text{Target: } > 44.24\%)$$

### Secondary & Diagnostic Metrics
1. **Candidate Reachability**:
   $$\text{Reachability} = \frac{N_{\text{non-empty post-recovery candidate}}}{165} \quad (\text{Target: } \ge 90.0\%)$$
2. **Recovery Trigger Rate**:
   $$\text{Trigger Rate} = \frac{N_{\text{candidate recovery triggered}}}{165} \quad (\text{Baseline: } 54.55\%)$$
3. **Planner Parse Success Rate**:
   $$\text{Parse Success Rate} = \frac{N_{\text{planner parse success}}}{N_{\text{planner attempted}}} \quad (\text{Target: } \ge 95.0\%)$$
4. **Planner Mode Distribution**:
   Counts and percentages for `MODE: DIRECT` vs `MODE: PYTHON`.
5. **Python Execution Success Rate**:
   $$\text{Python Success Rate} = \frac{N_{\text{exit code 0}}}{N_{\text{python executions attempted}}} \quad (\text{Target: } \ge 80.0\%)$$
6. **Conditional Error Rates by Risk Type**:
   Post-hoc error rates grouped by V6 self-evaluation risk type (`EXECUTION`, `EVIDENCE`, `CALCULATION`, `REASONING`, `NONE`).
7. **Resource & Token Overhead**:
   Mean input, output, and thinking tokens for planner and executor stages.

---

## 6. Formal Scientific Decision Rule

Following completion of the canonical benchmark and paired upstream ablation, version promotion is governed strictly by the following criteria:

```text
PROMOTION (V10 Promoted as Baseline for V11):
Required Conditions (ALL MUST HOLD):
  1. Shared-Context Upstream Paired Delta > 0:
     Delta_upstream = N(UPSTREAM_IMPROVEMENT) - N(UPSTREAM_REGRESSION) >= +1.
  2. Official Canonical Accuracy > 44.24%:
     Strictly exceeds Frozen V9 canonical reference (73 / 165 correct).
  3. Tool Budgets Strictly Preserved:
     - Web searches <= 1 total (Planner = 0)
     - File processing <= 1 total (Planner = 0)
     - Python executions <= 1 per agent branch (Planner = 0)
  4. Generation Cap Respected:
     - llm_generation_attempts <= 5 on non-recovery tasks
     - llm_generation_attempts <= 6 on recovery tasks
  5. Upstream Generation Slots == 2:
     - Planner generation = 1, Executor generation = 1.
  6. Frozen V9 Candidate Recovery Semantics Verbatim Preserved.
  7. Frozen V5/V6/V7 Downstream Safeguard Semantics Verbatim Preserved.
  8. Operational Validity Confirmed:
     - Zero unhandled provider collapse; all 165 official tasks recorded.

NEUTRAL / INSUFFICIENT (V10 Frozen with Documented Findings):
Condition:
  1. Primary Paired Upstream Delta == 0 (Delta_upstream == 0).
  OR
  2. Canonical accuracy <= 44.24% despite positive paired delta.
Outcome:
  Version is frozen in experiments/v10/; structured planning under equalized generation budget documented as insufficient to overcome execution bottleneck.

FAILURE / REJECTION (V10 Rejected):
Condition:
  1. Primary Paired Upstream Delta < 0 (Delta_upstream < 0, Regressions > Improvements).
  OR
  2. Tool or generation budgets violated (> 1 search, > 1 Python per branch, or > 6 generations).
  OR
  3. Operational failure rate >= 5% due to unhandled exceptions.
Outcome:
  V10 rejected; repository reverts to Frozen V9 baseline.
```

---

## 7. Deterministic Pre-Benchmark Smoke Test Matrix (24 Scenarios)

Prior to running canonical benchmarks, V10 must pass **24 deterministic, zero-network smoke scenarios** validating all planning modes, parser edges, fallback paths, budget bounds, downstream propagation, and paired harness invariants:

| Scenario | Subsystem / Input State | Expected Planner Behavior | Expected Executor / Downstream Behavior | Verification Assertion |
| :---: | :--- | :--- | :--- | :--- |
| **1** | Valid DIRECT plan format. | Parser extracts `MODE: DIRECT`, objective, evidence, 3 steps, `short text`. | Executor runs DIRECT prompt; candidate answer produced. | `planner_success == True`, `planner_mode == "DIRECT"`, `plan_step_count == 3`. |
| **2** | Valid PYTHON plan format. | Parser extracts `MODE: PYTHON`, objective, evidence, 4 steps, `number`. | Executor runs PYTHON prompt; generates Python code. | `planner_success == True`, `planner_mode == "PYTHON"`, `plan_step_count == 4`. |
| **3** | Malformed planner: missing `MODE:` key. | Parser rejects output; triggers fallback. | Falls back to deterministic `DIRECT` default plan. | `planner_fallback_used == True`, `planner_mode == "DIRECT"`. |
| **4** | Malformed planner: unsupported mode (`MODE: SQL`). | Parser rejects output; triggers fallback. | Falls back to deterministic `DIRECT` default plan. | `planner_fallback_used == True`, `planner_mode == "DIRECT"`. |
| **5** | Malformed planner: empty plan (0 steps). | Parser rejects output; triggers fallback. | Falls back to deterministic `DIRECT` default plan. | `planner_fallback_used == True`, `plan_step_count == 1`. |
| **6** | Malformed planner: missing `ANSWER_TYPE:` key. | Parser rejects output; triggers fallback. | Falls back to deterministic `DIRECT` default plan. | `planner_fallback_used == True`, `plan_answer_type == "short text"`. |
| **7** | Provider timeout during planner API call. | Caught non-destructively; no crash. | Falls back to deterministic `DIRECT` plan; zero extra LLM calls. | `planner_attempted == True`, `planner_success == False`, `upstream_generations == 2`. |
| **8** | Provider 500 error during planner API call. | Caught non-destructively; no crash. | Falls back to deterministic `DIRECT` plan; zero extra LLM calls. | `planner_attempted == True`, `planner_success == False`, `upstream_generations == 2`. |
| **9** | Minimum boundary plan: exactly 1 step. | Parser succeeds; validates 1 step. | Executor executes single-step plan. | `planner_success == True`, `plan_step_count == 1`. |
| **10** | Maximum boundary plan: exactly 5 steps. | Parser succeeds; validates 5 steps. | Executor executes 5-step plan. | `planner_success == True`, `plan_step_count == 5`. |
| **11** | Planner success + Executor DIRECT success. | Emits `FINAL: 42`. | Candidate `"42"` flows to verifier. | `candidate_answer == "42"`, recovery not triggered. |
| **12** | Planner success + Executor PYTHON success. | Script executes, stdout has `FINAL_ANSWER: 100`. | Candidate `"100"` flows to verifier. | `candidate_answer == "100"`, `python_executions == 1`. |
| **13** | Planner success + Executor empty candidate (`""`). | Candidate empty; eligible failure. | Triggers Frozen V9 candidate recovery. | `candidate_recovery_triggered == True`, recovery attempted. |
| **14** | Planner success + Executor Python script crash. | Exit code 1; no marker in stdout. | Triggers Frozen V9 candidate recovery (`PYTHON_EXECUTION_FAILURE`). | `candidate_recovery_triggered == True`, `failure_class == "PYTHON_EXECUTION_FAILURE"`. |
| **15** | Candidate recovery after executor starvation. | Recovery succeeds with `FINAL: Paris`. | Candidate `"Paris"` flows into V5 verifier $\to$ V6 $\to$ V7. | `post_recovery_candidate == "Paris"`, verifier evaluated. |
| **16** | Non-starved executor output bypasses recovery. | Non-empty candidate `"Blue"` produced. | Recovery strictly bypassed (100% boundary preservation). | `candidate_recovery_triggered == False`, candidate preserved. |
| **17** | Full pipeline execution (non-recovery path). | Plan $\to$ Exec $\to$ Verifier $\to$ Self-Eval $\to$ Repair. | All stages record telemetry in order. | `llm_generation_attempts <= 5`, schema version 8. |
| **18** | Full pipeline execution (recovery path). | Plan $\to$ Exec $\to$ Recovery $\to$ Verifier $\to$ Self-Eval $\to$ Repair. | All stages record telemetry in order. | `llm_generation_attempts <= 6`, schema version 8. |
| **19** | Strict Tool Budgets & Isolation. | Planner and Recovery have 0 tools. | Search $\le 1$, File $\le 1$, Python $\le 1$ per agent branch. | `added_tools == 0`, runtime assertions hold. |
| **20** | Information Firewall Audit. | Prompts audited for forbidden tokens. | Ground truth, test labels, official scorer absent. | Pure isolated inference inputs. |
| **21** | Shared Context Delivery: Search Hash Invariance. | Single Tavily search executed and snapshotted. | Both Branch A and Branch B receive identical search string. | `hash(A.search) == hash(B.search)`, duplicate searches == 0. |
| **22** | Shared Context Delivery: File Hash Invariance. | Single file read executed and snapshotted. | Both Branch A and Branch B receive identical file context. | `hash(A.file) == hash(B.file)`, duplicate file reads == 0. |
| **23** | Paired Upstream Transition Scoring. | Post-hoc scoring of `v9_candidate` and `v10_candidate`. | Transition computed strictly offline after execution completes. | Scorer outputs match preregistered transition classes. |
| **24** | Paired Harness Ground-Truth Firewall. | Paired execution runs to completion. | Runtime traces contain zero ground-truth tokens. | Neither branch context contains reference answer. |

---

## 8. Canonical Benchmark Execution Parameters

When validated and approved for benchmarking, the canonical run will adhere to:
- **Dataset**: GAIA 2023 Validation Set (165 Tasks: 53 Level 1, 86 Level 2, 26 Level 3).
- **Model**: `gemini-3.5-flash-lite`.
- **Inference Parameters**: `thinking_level: medium`, `max_output_tokens: 2048`, `temperature: null`.
- **Rate-Limit Inter-Task Delay**: Exactly 5.0 seconds.
- **Scorer**: Official GAIA leaderboard scorer (`evaluation/scorer.py`, commit `9f133d7136...`).
- **Telemetry Schema**: Version 8 JSONL records.
