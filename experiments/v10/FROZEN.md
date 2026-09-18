# V10 — Structured Planner → Plan-Guided Executor

**Status:** FROZEN  
**Branch:** `v10-planner-executor`  
**Scientific Parent:** Frozen V9 (`v9-upstream-candidate-recovery`)  
**Freeze Verdict:** `FROZEN_AND_PROMOTED_AS_V11_BASELINE`  
**Canonical Inference Commit:** `314d0aecd01a1679a96d85256044c01c8b6c30ce`  
**Canonical Results Commit:** `c8f76b3fa8a1775da710665c0f683d4843a817dd`  
**Artifact Completion Commit:** `390ac110bfce264b802b5db42f81884d41e64b49`  
**Post-Benchmark Audit Commit:** `5bb65499eb237e70eb10fa96150341ed0b044886`  
**Final Corrected Audit Source Head:** `dd8e6fb4562d8d492a33409fba34aacf6b27496e`  
**Freeze Source Head:** `dd8e6fb4562d8d492a33409fba34aacf6b27496e`  
**Evaluation Schema:** 8  
**Model:** `gemini-3.5-flash-lite`  
**Thinking Level:** `medium`  
**Max Output Tokens:** 2048  
**Temperature:** null/provider default  
**Date:** September 2026  

---

## 1. Scientific Intervention & Scope

Version 10 (V10) investigates **Structured Planning and Plan-Guided Execution** to resolve the primary failure class identified in Frozen V9: **upstream execution and reasoning flaws**.

$$\text{V10} = \text{Frozen V9 with Capability Router } \to \text{ Worker replaced by Structured Planner } \to \text{ Plan-Guided Executor}$$

### What V10 Does
- Replaces the coarse upstream `capability-router-v1` with a dedicated, contract-enforced **Structured Planner** (`planner-v1`, `mode="NONE"`).
- Replaces the upstream worker with a **Plan-Guided Executor** conditioned explicitly on the question, existing retrieved evidence, and the structured plan (`executor-direct-v1` or `executor-python-v1`).
- Enforces a deterministic line-oriented plan grammar specifying:
  - `MODE: DIRECT | PYTHON`
  - `OBJECTIVE: <single concise sentence>`
  - `EVIDENCE_NEEDED: <key evidence identified>`
  - `PLAN: 1. ... 2. ... 3. ...`
  - `ANSWER_TYPE: <number|name|list|date|short text>`
- Enforces a deterministic fallback parser that falls back safely to `DIRECT` if parsing fails or times out.
- Strictly preserves the Frozen V9 candidate recovery mechanism and the Frozen V5–V7 downstream verification, self-evaluation, and repair pipeline.

### Architectural Constraint: Equalized Slot Replacement
- **Slot Replacement Invariant:** V10 is strictly a slot replacement, **not** an additional upstream generation layer.
- Upstream generation slots remain strictly equalized at **2 slots**:
  - Slot 1: Structured Planner (1 generation)
  - Slot 2: Plan-Guided Executor (1 generation)
- Generation budgets remain identical to Frozen V9:
  - Non-recovery path: $\le 5$ logical generations
  - Candidate-recovery path: $\le 6$ logical generations

---

## 2. Final Architecture & Execution Flow

```text
GAIA Question + Optional Attachment File
     ↓
ONE Tavily Search (Original Question as Query, Capped at 1,500 Chars, N ≤ 1)
     ↓
ONE File Context Preparation if applicable (N ≤ 1)
     ↓
Stage 1: Structured Planner (`planner-v1`, mode="NONE", N ≤ 1)
     ↓
Stage 2: Plan-Guided Executor (`executor-direct-v1` or `executor-python-v1`, N ≤ 1)
     ↓
Candidate Formulation Boundary (`pre_recovery_candidate`)
     │
     ├── [Upstream Candidate Non-Empty]
     │        ↓
     │   RECOVERY BYPASSED (Zero recovery LLM calls)
     │   post_recovery_candidate = pre_recovery_candidate (100.0% Preservation Invariant)
     │        ↓
     │   Proceed to Downstream Pipeline
     │
     └── [Upstream Candidate Empty `""`]
              ↓
         Deterministic Failure Taxonomy Classification (10 Mutually Exclusive Classes)
              │
              ├── [Ineligible Class: PROVIDER_ERROR / UNKNOWN_NO_CANDIDATE]
              │        ↓
              │   RECOVERY INELIGIBLE (Zero recovery LLM calls)
              │   post_recovery_candidate = ""
              │        ↓
              │   Downstream Safeguards Safely Bypass → Final Answer = ""
              │
              └── [Eligible Class: e.g. PYTHON_CODE_EXTRACTION_FAILURE, etc.]
                       ↓
                   Stage 2b: Frozen V9 Bounded Candidate Recovery (`candidate-recovery-v1`, mode="NONE", N ≤ 1)
                   (Inputs: Question, Web Evidence, File Context, Raw Executor Output, Failure Reason)
                       ↓
                   Deterministic Recovery Parser (`FINAL: <answer>`)
                       ├── [Parse Success] → post_recovery_candidate = Parsed Answer
                       └── [Parse Failure / Timeout] → post_recovery_candidate = "" (Clean Fallback)
                            ↓
Stage 3: Frozen V5 Answer Verifier (`answer-verifier-v1`, mode="NONE", N ≤ 1)
     ↓
Stage 4: Frozen V6 Self-Evaluator (`self-evaluator-v1`, mode="NONE", N ≤ 1)
     ↓
Stage 5: Frozen V7 Targeted Repair (`targeted-repair-v1`, mode="NONE", N ≤ 1, if SUSPECT)
     ↓
Final Benchmark Answer
```

---

## 3. Strict Frozen Resource Invariants

Across all 165 canonical benchmark task traces, the following strict invariants were verified with zero violations:

| Resource Constraint | Preregistered Bound | Observed Maximum | Violations |
| :--- | :---: | :---: | :---: |
| **Web Searches** | $\le 1$ per task | 1 | 0 |
| **File Processing** | $\le 1$ per task | 1 | 0 |
| **Python Executions** | $\le 1$ per deployed branch | 1 | 0 |
| **Planner Generations** | $\le 1$ | 1 | 0 |
| **Executor Generations** | $\le 1$ | 1 | 0 |
| **Candidate Recovery Generations** | $\le 1$ | 1 | 0 |
| **Verifier Generations** | $\le 1$ | 1 | 0 |
| **Self-Evaluator Generations** | $\le 1$ | 1 | 0 |
| **Targeted Repair Generations** | $\le 1$ | 1 | 0 |
| **Logical Generations (Non-Recovery)** | $\le 5$ | 5 | 0 |
| **Logical Generations (Recovery Path)** | $\le 6$ | 6 | 0 |
| **Recovery-Added Tool Calls** | 0 searches, 0 Python runs | 0 searches, 0 Python runs | 0 |

---

## 4. Primary Scientific Result: Shared-Context Paired Upstream Ablation

In accordance with `experiments/v10/DESIGN.md` and `experiments/v10/PRE_BENCHMARK.md`, the primary evaluation of V10 is the **Shared-Context Paired Upstream Ablation**:
- **Protocol:** For each task, web search evidence and file context were acquired once and snapshotted. This identical context was fed into both:
  - **Branch A:** Frozen V9 Router $\to$ Frozen V9 Worker $\to$ V9 upstream candidate
  - **Branch B:** V10 Structured Planner $\to$ V10 Plan-Guided Executor $\to$ V10 upstream candidate
- **Methodological Characterization:** The paired protocol controls question, retrieved search evidence, file context, model configuration, and tool budgets across both upstream branches. Residual generation stochasticity remains. The measurement must not be described as a perfect causal estimate.
- **Context Integrity:** 0 search hash mismatches and 0 file hash mismatches across all 165 pairs.

### Paired Upstream Transition Matrix (165 Tasks)

| Transition Name | Definition | Level 1 (N=53) | Level 2 (N=86) | Level 3 (N=26) | Overall (N=165) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **`UPSTREAM_IMPROVEMENT`** | V9 candidate wrong $\to$ V10 candidate correct | 4 | 7 | 2 | **13 (7.88%)** |
| **`UPSTREAM_REGRESSION`** | V9 candidate correct $\to$ V10 candidate wrong | 2 | 2 | 1 | **5 (3.03%)** |
| **`UPSTREAM_STABLE_CORRECT`** | Both candidates correct | 19 | 18 | 4 | **41 (24.85%)** |
| **`UPSTREAM_STABLE_FAILURE`** | Both candidates wrong / empty | 28 | 59 | 19 | **106 (64.24%)** |
| **Total Tasks** | | **53** | **86** | **26** | **165 (100.0%)** |

$$\Delta_{\text{upstream}} = N_{\text{UPSTREAM\_IMPROVEMENT}} - N_{\text{UPSTREAM\_REGRESSION}} = 13 - 5 = \mathbf{+8 \text{ tasks}}$$
$$\Delta_{\text{upstream\_pp}} = \frac{+8}{165} \times 100 = \mathbf{+4.85 \text{ percentage points}}$$

- **Frozen V9 Upstream Correct:** 46 / 165 (27.88%)
- **V10 Upstream Correct:** 54 / 165 (32.73%)
- **Primary Hypothesis $H_1$:** $\Delta_{\text{upstream}} > 0$ — **PASS**.

---

## 5. Canonical V10 Benchmark Performance

Evaluated on the full GAIA 2023 Validation Set (165 tasks across Levels 1, 2, and 3):

| Level | Tasks | Completed Tasks | Pipeline Completion Rate | Correct Tasks | Accuracy | Request Failures |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 53 | 52 | 98.11% | 33 | **62.26%** | 0 |
| **Level 2** | 86 | 83 | 96.51% | 43 | **50.00%** | 0 |
| **Level 3** | 26 | 26 | 100.00% | 8 | **30.77%** | 0 |
| **Overall** | **165** | **161** | **97.58%** | **84** | **50.91%** | **0** |

- **Structural Benchmark Coverage:** **165 / 165 tasks (100.0% structurally recorded)**, 165 unique IDs, 0 duplicates.
- **Pipeline Completion:** **161 / 165 tasks (97.58%)** completed without parse fallback.
- **Operational Failures:** **0 request failures**, **0 unhandled provider errors**.
- **Note on Metrics:** Structural coverage (165/165) and pipeline completion (161/165) are distinct metrics and must not be conflated.

---

## 6. Historical Frozen V9 Reference Comparison

This historical comparison provides descriptive context against the Frozen V9 canonical benchmark and is not the primary isolated intervention metric:

| Level | Historical Frozen V9 Reference | Canonical V10 Performance | Descriptive Difference |
| :---: | :---: | :---: | :---: |
| **Level 1** | 33 / 53 (62.26%) | 33 / 53 (62.26%) | +0 tasks (+0.00 pp) |
| **Level 2** | 34 / 86 (39.53%) | 43 / 86 (50.00%) | +9 tasks (+10.47 pp) |
| **Level 3** | 6 / 26 (23.08%) | 8 / 26 (30.77%) | +2 tasks (+7.69 pp) |
| **Overall** | **73 / 165 (44.24%)** | **84 / 165 (50.91%)** | **+11 tasks (+6.67 pp)** |

- **Hypothesis $H_2$:** Canonical V10 accuracy strictly exceeds the Frozen V9 historical reference ($84 > 73$) — **PASS**.

---

## 7. Candidate Reachability & Recovery Dynamics

- **Pre-Recovery Non-Empty Candidates:** 114 / 165 (69.09%)
- **Post-Recovery Non-Empty Candidates:** 161 / 165 (97.58%)
- **Net Reachability Expansion:** **+47 reachable candidates (+28.49 percentage points)**
- **Candidate Recovery Trigger Count:** 51 / 165 (**30.91%**, vs 54.55% in Frozen V9)
- **Recovery Success Count:** 47 / 51 (**92.16%**)
- **Clean Recovery Fallbacks:** 4 / 51 (7.84%)
- **Non-Triggered Boundary Preservation:** 114 / 114 (**100.00%**)

---

## 8. Planner Reliability & Execution Distribution

- **Planner Attempts:** 165 / 165
- **Planner Parse Success:** 164 / 165 (**99.39%**)
- **Planner Fallbacks:** 1 / 165 (**0.61%**)
- **Mode Distribution:**
  - `DIRECT`: 99 / 165 (60.00%)
  - `PYTHON`: 66 / 165 (40.00%)
- **Plan-Guided Executor Outcomes:**
  - Emitted upstream candidate: 114 / 165 (69.09%)
  - Emitted empty candidate (triggered recovery): 51 / 165 (30.91%)

---

## 9. Preregistered Secondary Hypotheses

| Hypothesis | Preregistered Condition | Observed Result | Status |
| :--- | :--- | :--- | :---: |
| **$H_1$ (Primary)** | $\Delta_{\text{upstream}} > 0$ | $\Delta_{\text{upstream}} = 13 - 5 = \mathbf{+8}$ | **PASS** |
| **$H_2$** | Canonical accuracy $> 44.24\%$ ($> 73 / 165$) | $84 / 165 = \mathbf{50.91\%}$ ($+11$ tasks) | **PASS** |
| **$H_{3a}$** | Conditional error rate reduction on `EXECUTION` and `EVIDENCE` risks | `EXECUTION`: $17/27 = 62.96\%$ (vs $78.3\%$ in V9, **improved**)<br>`EVIDENCE`: $32/36 = 88.89\%$ (vs $88.9\%$ in V9, **essentially unchanged**) | **PARTIALLY_SUPPORTED** |
| **$H_{3b}$** | Downstream reachability $\ge 95.0\%$ | $161 / 165 = \mathbf{97.58\%}$ | **PASS** |
| **$H_{3c}$** | Candidate recovery trigger rate $\le 45.0\%$ | $51 / 165 = \mathbf{30.91\%}$ | **PASS** |
| **$H_{3d}$** | Planner parse success rate $\ge 95.0\%$ | $164 / 165 = \mathbf{99.39\%}$ | **PASS** |
| **$H_{3e}$** | Python execution success rate $\ge 80.0\%$ | $17 / 44 = \mathbf{38.64\%}$ | **FAIL** |

> [!NOTE]
> **Downstream Descriptive Context on $H_{3a}$**: One task flagged with `EXECUTION` risk was subsequently repaired by Targeted Repair, yielding a final post-repair error rate of $16 / 27 = 59.26\%$. This is reported as descriptive downstream context only and is not the preregistered upstream $H_{3a}$ metric.
>
> **Methodological Status of $H_{3e}$**: $H_{3e}$ is an exploratory secondary metric evaluating raw script execution reliability. It is non-binding and does not constitute a promotion veto post-hoc.

---

## 10. Canonical Completion Failures

The canonical V10 run exhibited exactly **4 pipeline completion failures** ($161 / 165 = 97.58\%$ completion rate):
1. **Level 1 (`257e8417-386f-40c2-9e84-dfae5914ab01`)**: Candidate Recovery returned an empty output.
2. **Level 2 (`317d7b32-9cb7-4f27-a068-18e95085d770`)**: Candidate Recovery returned an empty output.
3. **Level 2 (`94ce503a-c800-4100-bc5e-32fa4c0a5fcf`)**: Python execution failure where recovery output was not parsed.
4. **Level 2 (`b06f525c-0676-4767-93be-dc68f18398e0`)**: Candidate Recovery returned an empty output.

All 4 tasks completed structurally with 0 request failures and 0 unhandled provider errors, and were handled safely by the existing pipeline fallback mechanisms.

---

## 11. Contemporaneous Matched Frozen V9 Secondary Control

The contemporaneous matched Frozen V9 run executed alongside V10 suffered an unhandled provider-side outage:
- **Recorded Score:** 25 / 165 (15.15%)
- **Pipeline Completion:** 37 / 165 (22.42%)
- **Router Provider Failures:** 127 / 165 (77.0%)
  - Level 1: 16 / 53 router failures
  - Level 2: 85 / 86 router failures
  - Level 3: 26 / 26 router failures
- **Audit Classification:** `INVALID_SECONDARY_CONTROL_PROVIDER_COLLAPSE`
- **Scientific Status:** The nominal observational delta ($\Delta_{\text{e2e\_observational}} = +59$) is **EXCLUDED_FROM_SCIENTIFIC_INTERPRETATION**. The matched run is invalid and does not represent Frozen V9 performance. The valid historical Frozen V9 baseline remains 73 / 165 = 44.24%. No replacement control was executed.

---

## 12. Artifact Integrity & Provenance

Canonical benchmark artifacts are recorded in Git and verified against `experiments/v10/CANONICAL_RUN_MANIFEST.json`:
- **Canonical Results Commit:** `c8f76b3fa8a1775da710665c0f683d4843a817dd`
- **Artifact Completion Commit:** `390ac110bfce264b802b5db42f81884d41e64b49`
- **SHA-256 Digest Verification:** All 24 manifest-listed non-manifest artifacts matched identically (0 mismatches).
- **Provenance Manifest:** `CANONICAL_RUN_MANIFEST.json` is itself tracked in Git as the authoritative provenance record.
- **Completeness:** All 12 previously ignored prediction and detailed evaluation JSONL artifacts are tracked and immutable.

---

## 13. Final Promotion Gates

| Gate # | Promotion Criterion | Preregistered Requirement | Canonical V10 Value | Verdict |
| :---: | :--- | :--- | :--- | :---: |
| **1** | Primary Paired Upstream Delta | $\Delta_{\text{upstream}} > 0$ | $+8$ tasks | **PASS** |
| **2** | Canonical GAIA Accuracy | $> 44.24\%$ ($> 73 / 165$) | $84 / 165 = 50.91\%$ | **PASS** |
| **3** | Tool Budgets | $\le 1$ search, $\le 1$ file, $\le 1$ Python run | Max observed: 1, Added: 0 | **PASS** |
| **4** | Generation Budgets | $\le 5$ (non-recovery), $\le 6$ (recovery) | Max observed: 5 and 6 | **PASS** |
| **5** | Upstream Slots | Exactly 2 logical generations | Equalized at 2 | **PASS** |
| **6** | Frozen Recovery Preservation | 100.0% preservation on non-triggered tasks | 114 / 114 (100.00%) | **PASS** |
| **7** | Frozen Downstream Preservation | V5/V6/V7 preserved verbatim | Fully preserved | **PASS** |
| **8** | Canonical Operational Validity | 165 tasks structurally evaluated, 0 request failures | 165 tasks, 0 request failures | **PASS** |

```text
ALL BINDING PROMOTION GATES: PASS
```

---

## 14. Final Scientific Freeze Verdict

```text
================================================================================
V10 FREEZE VERDICT:        FROZEN_AND_PROMOTED_AS_V11_BASELINE
RESEARCH VERDICT:          SUPPORTED_AS_AN_IMPROVEMENT
PROMOTION RECOMMENDATION:  PROMOTE_V10_AS_V11_BASELINE
================================================================================
```

### Scientific Rationale
Version 10 satisfied every binding promotion gate preregistered in `experiments/v10/PRE_BENCHMARK.md`. Structured planning and plan-guided execution achieved a positive paired upstream delta ($\Delta_{\text{upstream}} = +8$) under identical contexts and raised end-to-end benchmark accuracy to 84 / 165 (50.91%), exceeding the historical Frozen V9 baseline by +11 tasks (+6.67 pp). V10 is formally frozen and promoted as the scientific baseline for Version 11.

---

## 15. V11 Scientific Baseline Handoff

```text
Scientific Parent for V11: Frozen V10 (v10-planner-executor)
Inference Baseline Commit: 314d0aecd01a1679a96d85256044c01c8b6c30ce
Canonical V10 Baseline Score: 84 / 165 = 50.91%
```

- Any future V11 experiment must begin from **Frozen V10** behavior and introduce a separately documented and preregistered intervention.
- Future V11 development must respect V10 canonical provenance and must not retroactively alter V10 runtime code, prompts, canonical benchmark artifacts, or frozen conclusions.
- The exact V11 architecture and hypothesis are **NOT** defined in this document and must be established in a dedicated preregistration phase.

---

## 16. Observed Bottlenecks for V11 Research

Empirical findings from the canonical V10 benchmark highlight three specific bottlenecks for future investigation:

1. **Python Script Execution Reliability ($H_{3e}$ Failure):**  
   Only **17 / 44 (38.64%)** of Python executions succeeded without error. Python worker models frequently suffered from syntax errors, unhandled edge cases, and missing package dependencies, triggering candidate recovery on 51 tasks.
2. **Evidence Insufficiency ($H_{3a}$ Resistance):**  
   Tasks assessed with `EVIDENCE` risk exhibited an **88.89% (32 / 36)** failure rate, essentially identical to Frozen V9 (88.9%). Structured planning cannot compensate when required external evidence was missed during the initial single web search.
3. **Downstream Targeted Repair Stagnation:**  
   Targeted Repair produced only **+1 net improvement** across the entire 165-task benchmark ($16 \text{ KEEP} / 0 \text{ REPLACE}$ on Level 1; $32 \text{ KEEP} / 2 \text{ REPLACE}$ on Level 2; $14 \text{ KEEP} / 2 \text{ REPLACE}$ on Level 3). Text-only post-hoc repair remains largely ineffective when the underlying execution lacks evidence.

