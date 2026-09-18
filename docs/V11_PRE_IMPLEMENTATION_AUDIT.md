# V11 Pre-Implementation Audit Report

**Date:** September 19, 2026  
**Auditor:** Automated Benchmark Integrity Suite / Antigravity Agent  
**Target Version:** `V11 — Planner-Guided Adaptive Evidence Retrieval`  
**Scientific Parent Baseline:** `V10 — Structured Planner → Plan-Guided Executor` (Frozen `v10-planner-executor`)  
**Parent Inference Commit:** `314d0aecd01a1679a96d85256044c01c8b6c30ce`  
**Parent Canonical Result:** `84 / 165 = 50.91%`  
**Merged Main Baseline Commit:** `0761b81330540cdc67fe2d662aef049bc87d9d8f`  
**Branch:** `v11-adaptive-evidence-retrieval`  
**Evaluation Schema Version:** 9  
**Audit Status:** `PRE_IMPLEMENTATION`  
**Verdict:** `READY_FOR_IMPLEMENTATION`  

---

## 1. Executive Summary

This pre-implementation audit rigorously verifies the architectural design, experimental preregistration, resource bounds, generation accounting, information firewalls, deterministic fallback policies, and scientific governance for **Version 11 (V11) — Planner-Guided Adaptive Evidence Retrieval** prior to any runtime code implementation or benchmarking.

V11 defines a single, strictly controlled architectural intervention directly on top of the Frozen V10 baseline:
$$\text{V11} = \text{Frozen V10} + \text{at most ONE planner-triggered targeted follow-up web search}$$

The audit confirms that:
1. **Single Intervention Isolated:** The intervention exclusively targets evidence insufficiency by allowing Planner v2 to assess context sufficiency and optionally request at most one follow-up search.
2. **Zero Extra LLM Generations:** Upstream generation slots remain strictly equalized at 2 (Slot 1: Planner v2, Slot 2: Executor). Search 2 is an operational web search tool call, not an extra LLM generation.
3. **Strict Search Budgets:** Total web searches per deployed task are capped at $\le 2$ (Search 1: $\le 1$, Search 2: $\le 1$). Non-triggered tasks execute exactly 1 search.
4. **Deterministic Safety Invariants:** Fallback plans enforce `EVIDENCE_STATUS: SUFFICIENT` and `FOLLOWUP_QUERY: NONE`, guaranteeing that parser fallback never triggers Search 2. Duplicate queries are deterministically skipped.
5. **Preserved Downstream Stages:** Candidate Recovery (Frozen V9), Answer Verifier (Frozen V5), Self-Evaluator (Frozen V6), and Targeted Repair (Frozen V7) are preserved verbatim.
6. **Information Firewall:** Zero access to ground-truth answers, correctness flags, or the official scorer at runtime.
7. **Preregistered Governance:** Binding hypotheses ($H_1, H_2, H_{3a\dots 3f}$), 13 binding promotion gates, schema version 9, and 28 deterministic smoke scenarios are fully preregistered in `experiments/v11/`.

---

## 2. Mandatory Pre-Flight Governance Checklist

| Audit Question | Mandatory Invariant | Audit Response | Evidence / Specification Reference |
| :--- | :--- | :---: | :--- |
| **1. Scientific parent = Frozen V10?** | Must inherit from Frozen V10 (`314d0ae...`) | **YES** | `experiments/v11/config.json`: `scientific_parent: "frozen_v10"`, `experiments/v10/` is immutable. |
| **2. Single intervention clearly isolated?** | Only Planner v2 retrieval decision + optional Search 2 | **YES** | `experiments/v11/DESIGN.md` Section 2; all other components frozen. |
| **3. Extra LLM generation upstream?** | Upstream generation slots == 2 | **NO** | Search 2 is non-LLM tool call; Slot 1 is Planner v2, Slot 2 is Executor. |
| **4. Follow-up search bounded?** | Search 2 calls $\le 1$ per task | **YES** | `experiments/v11/config.json`: `followup_search_max: 1`. |
| **5. Total search budget bounded?** | Total web searches $\le 2$ per task | **YES** | `experiments/v11/config.json`: `total_search_max: 2`. |
| **6. Fallback cannot search?** | Planner failure enforces `SUFFICIENT` & `NONE` | **YES** | `experiments/v11/DESIGN.md` Section 7; deterministic fallback invariant. |
| **7. Duplicate query protection?** | Search 2 query matching Search 1 is skipped | **YES** | `experiments/v11/DESIGN.md` Section 8; `second_search_skipped_duplicate_query`. |
| **8. Frozen V10 downstream preserved?** | Recovery, Verifier, Self-Eval, Repair active | **YES** | Configured verbatim; zero downstream code/prompt edits. |
| **9. Schema version 9 preregistered?** | Telemetry schema upgraded to version 9 | **YES** | `experiments/v11/config.json`: `evaluation_schema_version: 9`. |
| **10. Paired methodology coherent?** | Triggered-cohort shared-plan paired ablation | **YES** | `experiments/v11/PRE_BENCHMARK.md` Section 3; isolates Search 2 at boundary. |
| **11. Promotion rules preregistered?** | All 13 binding promotion gates defined before code | **YES** | `experiments/v11/PRE_BENCHMARK.md` Section 6. |
| **12. Ground-truth firewall preserved?** | Zero runtime access to labels or scorer | **YES** | Strict post-hoc evaluation only; zero label leakage. |
| **13. Deterministic smoke matrix defined?** | Exactly 28 zero-network smoke scenarios | **YES** | `experiments/v11/PRE_BENCHMARK.md` Section 9. |
| **14. Ready for implementation?** | Design and preregistration complete | **YES** | All required design documents authored and verified. |

---

## 3. Detailed Technical Verification

### 3.1 Lineage & Baseline Verification
- **Current Merged Main Baseline:** `0761b81330540cdc67fe2d662aef049bc87d9d8f`.
- **Target Branch:** `v11-adaptive-evidence-retrieval` branched directly from `main`.
- **Parent Inference Baseline:** Frozen V10 canonical commit `314d0aecd01a1679a96d85256044c01c8b6c30ce`.
- **Parent Canonical Score:** 84 / 165 (50.91%).
- **Directory Integrity:** `experiments/v10/` and all its canonical artifacts remain strictly untouched and immutable.

### 3.2 Empirical Motivation & Problem Formulation
Canonical Frozen V10 telemetry established that while structured planning improved upstream accuracy (+8 net tasks), tasks diagnosed with `EVIDENCE` risk remained severely bottlenecked:
- 32 / 36 (88.89%) of `EVIDENCE`-risk tasks were incorrect.
- Single-search retrieval with the raw question frequently missed critical secondary entities, dates, or specifications.
- Post-hoc Targeted Repair produced only +1 net improvement across the benchmark, proving that text-only repair cannot resolve fundamental evidence starvation.
V11 targets this failure mode specifically by enabling bounded follow-up retrieval during planning.

### 3.3 Strict Generation Accounting & Upstream Slots
```text
Frozen V10 Upstream:
  Slot 1: Structured Planner Generation (`planner-v1`)
  Slot 2: Plan-Guided Executor Generation (`executor-direct-v1` / `executor-python-v1`)
  Total Upstream Slots = 2

V11 Upstream:
  Slot 1: Structured Planner v2 Generation (`planner-v2-adaptive-evidence`)
  [Optional Non-LLM Search 2: Tavily Tool Call, N ≤ 1]
  Slot 2: Plan-Guided Executor Generation (`executor-direct-v1` / `executor-python-v1`)
  Total Upstream Slots = 2
```
- **Zero Additional LLM Generations:** Search 2 is an API tool call, not an LLM invocation.
- **Generation Caps:**
  - Non-recovery path: $\le 5$ logical generations (Planner + Executor + Verifier + Self-Eval + Repair).
  - Recovery path: $\le 6$ logical generations (Planner + Executor + Recovery + Verifier + Self-Eval + Repair).

### 3.4 Search Budget Enforcement & Duplicate Protection
- **Initial Search 1:** Exactly $\le 1$ Tavily call with raw user question (capped at 1,500 characters).
- **Follow-Up Search 2:** Exactly $\le 1$ Tavily call with normalized follow-up query.
- **Total Searches:** $\le 2$ per deployed task. Non-triggered tasks execute exactly 1 search.
- **Duplicate Protection:** If `normalized(Search 2 query) == normalized(Search 1 query)`, Search 2 is skipped and logged.
- **Search 3 Impossibility:** No code path or loop allows a third search execution.

### 3.5 Fallback Safety Invariant
If Planner v2 generation produces malformed text, times out, or fails parsing:
- The parser deterministically falls back to a safe local plan with:
  - `EVIDENCE_STATUS: SUFFICIENT`
  - `FOLLOWUP_QUERY: NONE`
- **Critical Safety Invariant:** A failed or malformed planner generation **never** triggers Search 2.

### 3.6 Executor Semantic Drift Minimization
- The Plan-Guided Executor continues to receive only the operational plan fields:
  `MODE`, `OBJECTIVE`, `EVIDENCE_NEEDED`, `PLAN`, `ANSWER_TYPE`.
- The retrieval-control fields (`EVIDENCE_STATUS`, `FOLLOWUP_QUERY`) are excluded from executor reasoning instructions.
- Executor prompts (`executor-direct-v1`, `executor-python-v1`) remain conceptually preserved from Frozen V10.

### 3.7 Evaluation Methodology & Attribution
1. **Primary Protocol (Within-Task Paired Ablation):**  
   Evaluates triggered tasks where both branches receive the exact same question, Search 1 evidence, file context, planner output, and plan. Branch A runs without Search 2; Branch B runs with Search 2. Both stop at the pre-recovery candidate boundary.
   - Primary metric: $\Delta_{\text{followup}} = N_{\text{RETRIEVAL\_IMPROVEMENT}} - N_{\text{RETRIEVAL\_REGRESSION}} > 0$.
2. **Canonical Protocol (Full Benchmark):**  
   Evaluates the full end-to-end V11 agent across all 165 GAIA validation tasks, requiring official accuracy $> 50.91\%$ ($> 84 / 165$).
3. **Contemporaneous Matched Control Excluded:**  
   A contemporaneous full-run matched V10 control is explicitly not required for promotion, eliminating separate-run sampling noise.

---

## 4. Final Pre-Implementation Audit Verdict

```text
================================================================================
V11 PRE-IMPLEMENTATION AUDIT VERDICT: READY_FOR_IMPLEMENTATION
================================================================================
```

### Rationale
All mandatory pre-flight criteria, architectural constraints, budget invariants, information firewalls, deterministic fallback policies, evaluation protocols, and 28 deterministic smoke scenarios have been comprehensively verified and preregistered. No runtime code, prompts, or benchmarks have been modified. Version 11 is approved for bounded runtime implementation.

