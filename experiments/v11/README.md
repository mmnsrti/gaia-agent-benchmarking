# V11 — Planner-Guided Adaptive Evidence Retrieval

**Status**: `PROPOSED / PREREGISTERED — NOT IMPLEMENTED`  
**Branch**: `v11-adaptive-evidence-retrieval`  
**Repository Parent Commit**: `0761b81330540cdc67fe2d662aef049bc87d9d8f`  
**Scientific Parent**: Frozen V10 (`v10-planner-executor`)  
**Canonical Frozen V10 Inference Commit**: `314d0aecd01a1679a96d85256044c01c8b6c30ce`  
**Canonical Frozen V10 Score**: `84 / 165 = 50.91%`  
**Architecture**: Search 1 → File Context → Planner v2 → [Optional Targeted Search 2] → Executor → Frozen V10 Downstream Pipeline  
**Model**: `gemini-3.5-flash-lite` (inherited from Frozen V7/V9/V10)  
**Evaluation Scope**: Full GAIA 2023 Validation Set (165 Tasks: 53 Level 1, 86 Level 2, 26 Level 3)  
**Runtime Implemented**: `NO`  
**Benchmark Executed**: `NO`  
**Date**: September 2026  

See [`DESIGN.md`](./DESIGN.md) for the complete architectural specification, contracts, and invariants; [`PRE_BENCHMARK.md`](./PRE_BENCHMARK.md) for binding hypotheses, evaluation protocol, and 28 deterministic smoke scenarios; and [`../../docs/V11_PRE_IMPLEMENTATION_AUDIT.md`](../../docs/V11_PRE_IMPLEMENTATION_AUDIT.md) for the pre-implementation governance audit.

---

## 1. Overview & Research Focus

Version 11 (V11) investigates **Planner-Guided Adaptive Evidence Retrieval** to resolve the central empirical bottleneck identified in Frozen V10: **evidence insufficiency**.

In Frozen V10:
- Structured planning raised upstream accuracy from $27.88\%$ to $32.73\%$ ($\Delta_{\text{upstream}} = +8$) and overall benchmark performance to $84 / 165 = 50.91\%$.
- However, tasks diagnosed with `EVIDENCE` risk exhibited an **$88.89\%$ (32 / 36)** error rate, essentially unchanged from Frozen V9 ($88.9\%$).
- When the initial, single broad web search fails to retrieve necessary factual information, neither structured planning nor post-hoc downstream repair can recover the correct answer.

V11 addresses this bottleneck by allowing the structured planner, during its single planning slot, to assess evidence sufficiency and optionally author **at most ONE targeted follow-up web search**.

---

## 2. Strict Experimental Constraints

To ensure causal attribution and avoid runaway search behavior, V11 enforces strict boundaries:
- **Zero Additional LLM Generations**: Upstream slots remain strictly fixed at **2** (Slot 1: Planner v2, Slot 2: Plan-Guided Executor). Follow-up search is an operational tool call, not an extra LLM generation.
- **Search Budget**: At most **2** web searches per deployed task (Search 1: $\le 1$, Search 2: $\le 1$). Non-triggered tasks execute exactly 1 search.
- **Duplicate Protection**: If Search 2's query matches Search 1 after normalization, Search 2 is skipped.
- **Fallback Invariant**: Deterministic planner fallback defaults to `SUFFICIENT` / `NONE` and **never** triggers Search 2.
- **Preserved Downstream**: Frozen V9 Candidate Recovery, Frozen V5 Verifier, Frozen V6 Self-Evaluator, and Frozen V7 Targeted Repair remain verbatim.

---

## 3. Two-Tier Evaluation Framework

1. **Primary Evaluation (Intervention Ablation):**  
   **Triggered-Cohort Shared-Plan Paired Retrieval Ablation** (`run_v11_paired.py`): For tasks where the planner requests follow-up evidence, both branches evaluate the exact same plan with and without Search 2 evidence at the upstream boundary.  
   - Metric: $\Delta_{\text{followup}} = N_{\text{RETRIEVAL\_IMPROVEMENT}} - N_{\text{RETRIEVAL\_REGRESSION}} > 0$.
2. **Canonical Evaluation (Governance & Performance Gate):**  
   Full 165-task GAIA validation run requiring official accuracy $> 50.91\%$ ($> 84 / 165$ correct).

---

## 4. Directory Contents

| File | Description |
| :--- | :--- |
| [`config.json`](./config.json) | Complete experimental configuration, budget limits, telemetry fields, and frozen parameters (Schema version 9). |
| [`DESIGN.md`](./DESIGN.md) | Technical architecture, planner-v2 grammar, fallback policy, query normalization, Search 2 failure policy, and evidence integration format. |
| [`PRE_BENCHMARK.md`](./PRE_BENCHMARK.md) | Formal binding preregistration: hypotheses $H_1, H_2, H_{3a\dots 3f}$, paired protocol, transition taxonomy, promotion gates, and 28 deterministic smoke scenarios. |
| [`../../docs/V11_PRE_IMPLEMENTATION_AUDIT.md`](../../docs/V11_PRE_IMPLEMENTATION_AUDIT.md) | Pre-implementation governance audit verifying all pre-execution checks and architectural boundaries. |

