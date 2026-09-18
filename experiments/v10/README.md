# V10 — Structured Planner → Plan-Guided Executor

**Status**: `PREREGISTERED_PRE_IMPLEMENTATION`  
**Branch**: `v10-planner-executor`  
**Baseline Main Commit**: `7e6f35bd27c83c23072e27a337d52e157d5904cd`  
**Scientific Parent**: Frozen V9 (`v9-upstream-candidate-recovery`)  
**Frozen V9 Inference Commit**: `6369f427c4479073a6ca06531bdfd43e47cd613f`  
**Frozen V9 Final Benchmark Result**: `73 / 165 = 44.24%`  
**Architecture**: Structured Planner → Plan-Guided Executor (+ Frozen V9 Downstream Pipeline)  
**Model**: `gemini-3.5-flash-lite` (inherited from Frozen V7/V9)  
**Evaluation Scope**: Full GAIA 2023 Validation Set (165 Tasks: 53 Level 1, 86 Level 2, 26 Level 3)  
**Date**: September 2026  

See [`DESIGN.md`](./DESIGN.md) for the complete architectural specification, contracts, and invariants; [`PRE_BENCHMARK.md`](./PRE_BENCHMARK.md) for binding hypotheses, evaluation protocol, and deterministic smoke scenarios; and [`../../docs/V10_PRE_IMPLEMENTATION_AUDIT.md`](../../docs/V10_PRE_IMPLEMENTATION_AUDIT.md) for the pre-implementation governance audit.

---

## 1. Overview & Research Focus

Version 10 (V10) investigates **Structured Planning and Plan-Guided Execution** to address the empirical failure bottleneck identified in Frozen V9: **upstream execution and reasoning flaws**.

In Frozen V9:
- **Candidate Starvation was largely overcome**: Candidate reachability expanded from $45.45\%$ (75/165) to $96.36\%$ (159/165), achieving a net gain of $+50.91$ percentage points.
- **Residual Bottleneck**: Only $26 / 84$ ($30.95\%$) of recovered candidates were correct upon generation, and over $65\%$ ($55 / 84$) remained incorrect after all downstream safeguards.
- **Downstream Repair Limits**: Downstream V7 targeted repair triggered on 75 tasks across the benchmark, but generated only $1$ net improvement ($0 + 0 + 1$). Post-hoc text-only repair cannot resolve fundamental upstream failures where the task objective was misinterpreted, necessary evidence was ignored, or the execution strategy was unsound.

V10 addresses this limitation at the source by replacing the coarse upstream:
```text
Router → Worker
```
with:
```text
Structured Planner → Plan-Guided Executor
```

---

## 2. Strict Experimental Ablation Constraint

To ensure rigorous scientific attribution, V10 enforces a strict slot replacement:
- **Zero Additional Upstream Generations**: The coarse capability router (which merely emitted `DIRECT` or `PYTHON`) is converted into a **Structured Planner**. The worker generation becomes a **Plan-Guided Executor**.
- **Upstream Generation Count**: Strictly preserved at **2 generations** (Slot 1: Planner, Slot 2: Executor).
- **Generation Budget**: Maximum logical generation limits remain unchanged from Frozen V9:
  - Non-recovery path: $\le 5$ logical generations (Planner $\to$ Executor $\to$ Verifier $\to$ Self-Eval $\to$ Repair)
  - Recovery path: $\le 6$ logical generations (Planner $\to$ Executor $\to$ Candidate Recovery $\to$ Verifier $\to$ Self-Eval $\to$ Repair)
- **Tool Budgets Strictly Frozen**:
  - Web searches: $\le 1$ (Planner: 0, Executor: 0 beyond initial tool phase)
  - File processing: $\le 1$
  - Python executions: $\le 1$ per agent branch (Planner: 0, Executor: $\le 1$ when mode is `PYTHON`)

V10 tests whether **structured task decomposition and explicit plan guidance** improve upstream accuracy under identical compute, tool, and generation budgets.

---

## 3. Diagnostic Signal from Canonical V9 Data

Canonical V9 self-evaluation risk diagnostics across all 165 tasks reveal high conditional error rates for tasks exhibiting execution or evidence deficiencies:

| Assessed Risk Type | Assessed Tasks ($N$) | Incorrect Tasks | Correct Tasks | Conditional Error Rate |
| :--- | :---: | :---: | :---: | :---: |
| **`CALCULATION`** | 1 | 1 | 0 | **100.0%** |
| **`REASONING`** | 1 | 1 | 0 | **100.0%** |
| **`EVIDENCE`** | 27 | 24 | 3 | **88.9%** |
| **`EXECUTION`** | 46 | 36 | 10 | **78.3%** |
| **`NONE`** | 81 | 24 | 57 | **29.6%** |

*(Total assessed = 156 tasks; 9 tasks unreached or omitted self-eval)*

Tasks flagged with `EXECUTION` ($78.3\%$ error rate) and `EVIDENCE` ($88.9\%$ error rate) account for the vast majority of identifiable errors. Structuring the planner to explicitly specify the required evidence and the operational steps directly targets these dominant error classes.

---

## 4. Architectural Summary

```text
[GAIA Question + Attachment]
            │
            ▼
┌────────────────────────────────────────────────────────┐
│ INITIAL TOOL PHASE (Frozen V9)                         │
│ - Tavily Search (at most 1)                            │
│ - File / Attachment Processing (at most 1)             │
└────────────────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────────────────┐
│ STRUCTURED PLANNER (Replaces Router Slot)             │
│ - Zero tools, text-only generation                     │
│ - Deterministic Line-Oriented Contract:                │
│     MODE: DIRECT | PYTHON                              │
│     OBJECTIVE: <single concise sentence>               │
│     EVIDENCE_NEEDED: <key evidence identified>         │
│     PLAN: 1. ... 2. ... 3. ...                         │
│     ANSWER_TYPE: <number|name|list|date|short text>    │
│ - Deterministic fallback on malformed output           │
└────────────────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────────────────┐
│ PLAN-GUIDED EXECUTOR (Replaces Worker Slot)            │
│ - Conditioned on Question, Evidence, and Plan          │
│ - If DIRECT: Direct evidence-grounded answer           │
│ - If PYTHON: Generates executable code (<=1 run)       │
└────────────────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────────────────┐
│ FROZEN V9 DOWNSTREAM PIPELINE                          │
│ 1. Candidate Recovery (at most 1, empty candidate only)│
│ 2. V5 Answer Verifier (KEEP vs REVISE)                 │
│ 3. V6 Self-Evaluator (PASS vs SUSPECT + Risk Diagnostic│
│ 4. V7 Targeted Repair (KEEP vs REPLACE if SUSPECT)     │
└────────────────────────────────────────────────────────┘
            │
            ▼
      Final Answer
```

---

## 5. Preregistered Two-Tier Evaluation & Decision Framework

Because the scientific intervention occurs upstream and directly replaces the `Router → Worker` pair, V10 preregisters two distinct evaluation layers:

### 5.1 Primary Evaluation: Shared-Context Paired Upstream Ablation
- **Structure**: For each task, the question, web search evidence, and file context are acquired once and snapshotted. This identical context is fed into both:
  - **Branch A**: Frozen V9 Capability Router $\to$ Frozen V9 Worker $\to$ V9 upstream candidate
  - **Branch B**: V10 Structured Planner $\to$ V10 Plan-Guided Executor $\to$ V10 upstream candidate
- **Primary Metric**: Evaluates the candidate answers produced at the upstream boundary using the official GAIA scorer:
  - $\text{UPSTREAM\_IMPROVEMENT}$: V9 candidate wrong/empty $\to$ V10 candidate correct
  - $\text{UPSTREAM\_REGRESSION}$: V9 candidate correct $\to$ V10 candidate wrong/empty
  - $\text{UPSTREAM\_STABLE\_CORRECT}$: both correct
  - $\text{UPSTREAM\_STABLE\_FAILURE}$: both wrong
  - **Primary Paired Upstream Delta**:
    $$\Delta_{\text{upstream}} = N_{\text{UPSTREAM\_IMPROVEMENT}} - N_{\text{UPSTREAM\_REGRESSION}}$$
- **Methodological Status**: This paired protocol removes retrieval and context divergence and directly compares the replaced upstream stages, while residual generation stochasticity remains. It is not described as a "perfect causal estimate" or "fully causal."

### 5.2 Secondary Evaluation: Contemporaneous Full Frozen V9 Matched Control
- A canonical V10 full 165-task benchmark is paired with a contemporaneous Frozen V9 full 165-task run executed under identical environment settings and 5.0s rate-limit delays.
- Evaluates the full end-to-end pipeline through downstream verification, self-evaluation, and repair.
- **Methodological Status**: Explicitly classified as **observational and non-causal** due to run-to-run sampling variance across separate stochastic executions. It is reported for broader context and is NOT used as the isolated intervention criterion.

### 5.3 Promotion Rule
Promotion of V10 as the baseline for V11 requires meeting BOTH:
1. **Primary Paired Intervention Criterion**: $\Delta_{\text{upstream}} > 0$
2. **Canonical Benchmark Performance Criterion**: Canonical V10 official accuracy $> 44.24\%$ ($> 73 / 165$ correct)
alongside all frozen resource budgets and invariants.

---

## 6. Directory Contents

| File | Description |
| :--- | :--- |
| [`config.json`](./config.json) | Complete experimental configuration, two-tier evaluation specification, and frozen parameters (Schema version 8). |
| [`DESIGN.md`](./DESIGN.md) | In-depth technical architecture, shared-context paired harness, contracts, deterministic grammar, fallback policy, generation budgets, and safety invariants. |
| [`PRE_BENCHMARK.md`](./PRE_BENCHMARK.md) | Formal binding preregistration: hypotheses $H_1, H_2, H_{3a\dots 3e}$, evaluation protocol, transition taxonomy, decision rule, and 24 deterministic smoke scenarios. |
| [`../../docs/V10_PRE_IMPLEMENTATION_AUDIT.md`](../../docs/V10_PRE_IMPLEMENTATION_AUDIT.md) | Pre-implementation governance audit answering all mandatory pre-flight checks. |
