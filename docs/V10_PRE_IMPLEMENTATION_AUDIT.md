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
2. All tool budgets are strictly frozen: $\le 1$ Tavily search, $\le 1$ file processing, $\le 1$ Python execution. The planner operates with 0 tools.
3. All downstream stages from Frozen V9 (Candidate Recovery, V5 Verifier, V6 Self-Evaluator, V7 Targeted Repair) are preserved verbatim.
4. The information firewall is unbreached: zero access to ground truth, test labels, or the official scorer.
5. Binding hypotheses, evaluation protocols, transition taxonomies, decision rules, and 20 deterministic smoke scenarios are fully preregistered in `experiments/v10/`.

---

## 2. Mandatory Pre-Flight Governance Checklist

| Audit Question | Mandatory Invariant | Audit Response | Evidence / Specification Reference |
| :--- | :--- | :---: | :--- |
| **1. Scientific parent = Frozen V9?** | Must inherit from Frozen V9 (`6369f427...`) | **YES** | `experiments/v10/config.json`: `parent_version: "v9"`, `experiments/v9/` is immutable. |
| **2. Single intervention clearly isolated?** | Only Router $\to$ Planner and Worker $\to$ Executor replaced | **YES** | `experiments/v10/DESIGN.md` Section 1 & 4; downstream pipeline preserved. |
| **3. Extra web search?** | Web search calls $\le 1$ total; Planner = 0 | **NO** | `search_call_count_max: 1`, planner has `search: false`. |
| **4. Extra Python execution?** | Python executions $\le 1$ total; Planner = 0 | **NO** | `max_executions_per_task: 1`, planner has `python: false`. |
| **5. Extra file read?** | File operations $\le 1$ total; Planner = 0 | **NO** | `file_call_count_max: 1`, planner has `file_reread: false`. |
| **6. Extra planner generation beyond replaced router slot?** | Upstream generation slots == 2 | **NO** | Router slot replaced by Planner slot; upstream generation count = 2. |
| **7. Frozen V9 recovery preserved?** | Triggers on eligible empty candidates only | **YES** | `candidate_recovery_configuration.enabled: true`, identical trigger semantics. |
| **8. Frozen V5/V6/V7 downstream preserved?** | Verifier, self-evaluator, repair active | **YES** | Configured with `answer-verifier-v1`, `self-evaluator-v1`, `targeted-repair-v1`. |
| **9. Ground-truth firewall preserved?** | Zero access to labels/scorer in prompts/agent | **YES** | Prompts strictly assembled without ground truth or test split metadata. |
| **10. Comparison protocol preregistered?** | Contemporaneous matched Frozen V9 control | **YES** | `experiments/v10/PRE_BENCHMARK.md` Section 3; observational status declared. |
| **11. Promotion rule preregistered?** | Quantitative decision boundary fixed | **YES** | `experiments/v10/PRE_BENCHMARK.md` Section 6; requires $\Delta_{\text{net}} > 0$ and $> 44.24\%$. |
| **12. Ready for implementation?** | Design and preregistration complete | **YES** | All 5 required documents authored and verified. |

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

### 3.4 Tool Budgets & Sandbox Constraints
- Web search calls per task: $\le 1$ (Planner = 0, Recovery = 0, Downstream = 0).
- File processing calls per task: $\le 1$ (Planner = 0, Recovery = 0, Downstream = 0).
- Python executions per task: $\le 1$ (Planner = 0, Recovery = 0, Downstream = 0).
- Python execution timeout: 15.0 seconds.
- Disallowed Python modules: `multiprocessing`, `ctypes`.

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

### 3.6 Evaluation Protocol & Non-Causal Cross-Run Declaration
- Primary comparison: Contemporaneous matched Frozen V9 control run (165 tasks) executed under identical rate limits (5.0s delay) and model configurations.
- Cross-run comparison is explicitly classified as **observational and non-causal** due to run-to-run sampling variance.
- Primary decision metric: Net Task Delta ($\Delta_{\text{net}} = N_{\text{IMPROVEMENT}} - N_{\text{REGRESSION}} > 0$) alongside official accuracy exceeding $44.24\%$.

### 3.7 Telemetry & Schema 8 Invariants
- Schema version is updated to **8**.
- Public prediction records include structured planner fields (`planner_attempted`, `planner_mode`, `plan_step_count`, `plan_answer_type`, `planner_fallback_used`, etc.).
- Strict privacy: No hidden thinking tokens, chain-of-thought traces, or raw prompt templates are logged to public JSONL records.

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
Python Budget Changed:                NO (<= 1)
File Budget Changed:                  NO (<= 1)
Candidate Recovery Preserved:         YES
Downstream V5/V6/V7 Preserved:        YES
Ground-Truth Firewall Intact:         YES
Deterministic Fallback Preregistered: YES
Comparison Protocol Preregistered:    YES
Promotion Rule Preregistered:         YES
Smoke Scenarios Preregistered:        20 scenarios
Runtime Code Modified:                NO (0 runtime files modified)
Benchmark Executed:                   NO (0 tasks executed)
Frozen V9 Modified:                   NO (0 modifications in experiments/v9/)

FINAL VERDICT:                        READY_FOR_IMPLEMENTATION
===============================================================================
```

