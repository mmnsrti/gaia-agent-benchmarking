# V10 Pre-Implementation Audit Report

**Date:** September 18, 2026  
**Auditor:** Automated Benchmark Integrity Suite / Antigravity Agent  
**Target Version:** `V10 — Structured Planner → Plan-Guided Executor`  
**Scientific Parent Baseline:** `V9 — Upstream Candidate Recovery` (Frozen `v9-upstream-candidate-recovery`)  
**Parent Inference Commit:** `6369f427c4479073a6ca06531bdfd43e47cd613f`  
**Parent Canonical Result:** `73 / 165 = 44.24%`  
**Merged Main Baseline Commit:** `7e6f35bd27c83c23072e27a337d52e157d5904cd`  
**Branch:** `v10-planner-executor`  
**Evaluation Schema Version:** 8  
**Audit Status:** `PRE_IMPLEMENTATION`  
**Verdict:** `READY_FOR_IMPLEMENTATION`  

---

## 1. Executive Summary

This pre-implementation audit rigorously verifies the architectural design, experimental preregistration, resource bounds, generation accounting, information firewalls, deterministic fallback policies, and scientific governance for **Version 10 (V10) — Structured Planner → Plan-Guided Executor** prior to any runtime code implementation or benchmarking.

V10 defines a single, strictly controlled architectural intervention directly on top of the Frozen V9 baseline:
$$\text{V10} = \text{Frozen V9 with coarse Router replaced by Structured Planner and Worker replaced by Plan-Guided Executor}$$

The audit confirms that:
1. Upstream generation slots are strictly equalized at 2 (Slot 1: Planner, Slot 2: Executor), introducing **zero additional LLM generations** beyond the replaced router slot.
2. All tool budgets are strictly frozen: $\le 1$ Tavily search, $\le 1$ file processing, $\le 1$ Python execution per agent branch. The planner operates with 0 tools.
3. All downstream stages from Frozen V9 (Candidate Recovery, V5 Verifier, V6 Self-Evaluator, V7 Targeted Repair) are preserved verbatim.
4. The information firewall is unbreached: zero access to ground truth, test labels, or the official scorer across both paired branches.
5. Binding hypotheses ($H_1, H_2, H_{3a\dots 3e}$), two-tier evaluation protocols, transition taxonomies, decision rules, and 24 deterministic smoke scenarios are fully preregistered in `experiments/v10/`.

---

## 2. Mandatory Pre-Flight Governance Checklist

| Audit Question | Mandatory Invariant | Audit Response | Evidence / Specification Reference |
| :--- | :--- | :---: | :--- |
| **1. Scientific parent = Frozen V9?** | Must inherit from Frozen V9 (`6369f427...`) | **YES** | `experiments/v10/config.json`: `parent_version: "v9"`, `experiments/v9/` is immutable. |
| **2. Single intervention clearly isolated?** | Only Router $\to$ Planner and Worker $\to$ Executor replaced | **YES** | `experiments/v10/DESIGN.md` Section 1 & 4; downstream pipeline preserved. |
| **3. Extra web search?** | Web search calls $\le 1$ total; Planner = 0 | **NO** | `search_call_count_max: 1`, planner has `search: false`. |
| **4. Extra Python execution?** | Python executions $\le 1$ per agent branch; Planner = 0 | **NO** | `max_executions_per_task: 1`, `python_execution_count_per_agent_branch: 1`. |
| **5. Extra file read?** | File operations $\le 1$ total; Planner = 0 | **NO** | `file_call_count_max: 1`, planner has `file_reread: false`. |
| **6. Extra planner generation beyond replaced router slot?** | Upstream generation slots == 2 | **NO** | Router slot replaced by Planner slot; upstream generation count = 2. |
| **7. Frozen V9 recovery preserved?** | Triggers on eligible empty candidates only | **YES** | `candidate_recovery_configuration.enabled: true`, identical trigger semantics. |
| **8. Frozen V5/V6/V7 downstream preserved?** | Verifier, self-evaluator, repair active | **YES** | Configured with `answer-verifier-v1`, `self-evaluator-v1`, `targeted-repair-v1`. |
| **9. Ground-truth firewall preserved?** | Zero access to labels/scorer in prompts/agent | **YES** | Prompts strictly assembled without ground truth or test split metadata. |
| **10. Comparison protocol preregistered?** | Two-tier: Paired Upstream Ablation (Primary) & Matched Control (Secondary) | **YES** | `experiments/v10/PRE_BENCHMARK.md` Section 3; observational status declared for cross-run. |
| **11. Promotion rule preregistered?** | Anchored to paired $\Delta_{\text{upstream}} > 0$ AND canonical accuracy $> 44.24\%$ | **YES** | `experiments/v10/PRE_BENCHMARK.md` Section 6; both conditions mandatory. |
| **12. Ready for implementation?** | Design and preregistration complete | **YES** | All 5 required documents authored, verified, and aligned. |

---

## 3. Detailed Technical Verification

### 3.1 Lineage & Baseline Verification
- **Current Merged Main Baseline**: `7e6f35bd27c83c23072e27a337d52e157d5904cd`.
- **Target Branch**: `v10-planner-executor` branched directly from `main`.
- **Parent Inference Baseline**: Frozen V9 canonical commit `6369f427c4479073a6ca06531bdfd43e47cd613f`.
- **Parent Canonical Result**: 73 / 165 (44.24%).
- **Directory Integrity**: `experiments/v9/` and all its canonical artifacts remain strictly untouched and immutable.

### 3.2 Empirical Motivation & Problem Formulation
Canonical V9 data proved that candidate reachability ($96.36\%$) is no longer the primary bottleneck. Instead, errors are concentrated in upstream execution and reasoning:
- $65.48\%$ ($55/84$) of recovered candidates remained incorrect downstream.
- V7 targeted repair produced only $1$ net improvement across 75 triggered tasks.
- Aggregated risk diagnostics established high conditional error rates for execution ($78.3\%$) and evidence ($88.9\%$) failures.
V10 specifically targets these upstream failures by introducing explicit task decomposition and plan conditioning before execution occurs.

### 3.3 Strict Generation Accounting & Ablation Guarantee
```text
Frozen V9 Upstream:
  Slot 1: Capability Router Generation (DIRECT vs PYTHON)
  Slot 2: Upstream Worker Generation (DIRECT answer or PYTHON script)
  Total Upstream Generations = 2

V10 Upstream:
  Slot 1: Structured Planner Generation (MODE, OBJECTIVE, EVIDENCE, PLAN, ANSWER_TYPE)
  Slot 2: Plan-Guided Executor Generation (condition on plan; DIRECT answer or PYTHON script)
  Total Upstream Generations = 2
```
- **Zero Compute Confounder**: V10 does not spend extra LLM generation calls upstream.
- **Generation Caps**:
  - Non-recovery path: $\le 5$ logical generations (Planner + Executor + Verifier + Self-Eval + Repair).
  - Recovery path: $\le 6$ logical generations (Planner + Executor + Recovery + Verifier + Self-Eval + Repair).

### 3.4 Tool Budgets & Evaluation Harness Constraints
- Web search calls per task: $\le 1$ total (Planner = 0, Recovery = 0, Downstream = 0).
- File processing calls per task: $\le 1$ total (Planner = 0, Recovery = 0, Downstream = 0).
- Python executions per task: $\le 1$ per agent branch in evaluation harness (Planner = 0, Recovery = 0, Downstream = 0).
- Neither deployed agent receives double retrieval or file execution.
- Python execution timeout: 15.0 seconds; disallowed modules: `multiprocessing`, `ctypes`.

### 3.5 Deterministic Fallback Policy & Generation Safety
If the planner fails (provider timeout, API error, malformed output, unsupported mode, or missing keys):
- The agent does NOT call an extra router or replanner LLM generation.
- It deterministically constructs a safe local fallback plan:
  - `MODE: DIRECT`
  - `OBJECTIVE: Answer the question directly using available evidence.`
  - `EVIDENCE_NEEDED: Existing web search or file context.`
  - `PLAN: 1. Extract direct answer from evidence.`
  - `ANSWER_TYPE: short text`
- The executor executes this fallback plan in `MODE: DIRECT`.
- The failed planner attempt is recorded as 1 attempt; total upstream generations remain strictly 2.

### 3.6 Two-Tier Evaluation Methodology & Non-Causal Cross-Run Declaration
- **Primary Intervention Evaluation**: Shared-context paired upstream ablation.
  - Controls: identical question, search evidence, file context, tool budgets, and model configuration.
  - Focuses on candidate quality emitted at the upstream boundary: $\Delta_{\text{upstream}} = N_{\text{UPSTREAM\_IMPROVEMENT}} - N_{\text{UPSTREAM\_REGRESSION}}$.
  - Interpretation: Removes retrieval/context divergence and directly compares replaced upstream stages, while residual generation stochasticity remains (not described as a "perfect causal estimate").
- **Secondary Matched Full-Run Comparison**: Contemporaneous full Frozen V9 run.
  - Interpretation: Explicitly classified as **observational and non-causal** due to run-to-run sampling variance across separate stochastic executions.
  - Not used as the isolated intervention criterion.
- **Promotion Rule**: Anchored to BOTH paired upstream $\Delta_{\text{upstream}} > 0$ AND canonical V10 official accuracy $> 44.24\%$.

### 3.7 Telemetry & Schema 8 Invariants
- Schema version is updated to **8**.
- Paired harness records include: `shared_context_search_hash`, `shared_context_file_hash`, `v9_upstream_candidate`, `v10_upstream_candidate`, `upstream_transition`, etc.
- Strict privacy: No hidden thinking tokens, chain-of-thought traces, or raw prompt templates are logged to public JSONL records.
- Ground truth firewall: All scoring and transition labeling is computed strictly post-hoc.

---

## 4. Pre-Implementation Audit Verdict

```text
===============================================================================
V10 PRE-IMPLEMENTATION AUDIT RESULT:
===============================================================================
Scientific Parent Baseline:           Frozen V9 (v9-upstream-candidate-recovery)
Merged Main Commit:                   7e6f35bd27c83c23072e27a337d52e157d5904cd
Intervention:                         Structured Planner -> Plan-Guided Executor
Upstream Generation Slots:            2 (Slot 1: Planner, Slot 2: Executor)
Additional Planner Generation:        NO
Search Budget Changed:                NO (<= 1)
Python Budget Changed:                NO (<= 1 per agent branch)
File Budget Changed:                  NO (<= 1)
Candidate Recovery Preserved:         YES
Downstream V5/V6/V7 Preserved:        YES
Ground-Truth Firewall Intact:         YES
Deterministic Fallback Preregistered: YES
Primary Intervention Evaluation:      Shared-context paired upstream ablation
Secondary Matched Full-Run Control:   Contemporaneous Frozen V9 (observational/non-causal)
Matched Cross-Run Delta Causal:       NO (observational only)
Promotion Rule Anchored To:           Delta_upstream > 0 AND Canonical Accuracy > 44.24%
Smoke Scenarios Preregistered:        24 scenarios
Runtime Code Modified:                NO (0 runtime files modified)
Benchmark Executed:                   NO (0 tasks executed)
Frozen V9 Modified:                   NO (0 modifications in experiments/v9/)

FINAL VERDICT:                        READY_FOR_IMPLEMENTATION
===============================================================================
```
