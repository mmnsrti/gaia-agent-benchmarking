# V10 — Formal Post-Benchmark Audit

**Status:** `READY_FOR_FREEZE`  
**Date:** September 19, 2026  
**Auditor:** Automated Benchmark Integrity Suite / Antigravity Agent  
**Branch:** `v10-planner-executor`  
**Scientific Parent:** Frozen V9 (`v9-upstream-candidate-recovery`)  
**Historical Parent Reference:** `6369f427c4479073a6ca06531bdfd43e47cd613f` (73 / 165 = 44.24%)  
**Canonical Inference Commit:** `314d0aecd01a1679a96d85256044c01c8b6c30ce`  
**Canonical Results Commit:** `c8f76b3fa8a1775da710665c0f683d4843a817dd`  
**Artifact Completion Commit:** `390ac11f422e1b124806a6442c55ce54117ae87b`  
**Evaluation Schema Version:** 8  

---

## 1. Executive Summary & Audit Verdict

This formal post-benchmark audit assesses the canonical experimental results of **Version 10 (V10) — Structured Planner → Plan-Guided Executor** against the binding preregistration in `experiments/v10/DESIGN.md` and `experiments/v10/PRE_BENCHMARK.md`.

### Core Scientific Verdict
```text
SCIENTIFIC RESULT: SUPPORTED_AS_AN_IMPROVEMENT
PROMOTION DECISION: PROMOTE_V10_AS_V11_BASELINE
FREEZE STATUS:      READY_FOR_FREEZE
```

All 8 binding promotion criteria are satisfied:
1. **Primary Paired Upstream Metric:** $\Delta_{\text{upstream}} = +8 > 0$ (**PASS**). V10 produces 54 correct upstream candidates vs 46 for Frozen V9 under identical retrieved evidence snapshots (13 improvements vs 5 regressions).
2. **Canonical GAIA Accuracy:** Canonical V10 achieves **84 / 165 = 50.91%** (**PASS**), strictly exceeding the Frozen V9 historical canonical benchmark of 73 / 165 = 44.24% by **+11 correct tasks (+6.67 percentage points)**.
3. **Tool Budgets:** Strict adherence to $\le 1$ Tavily search, $\le 1$ file processing, and $\le 1$ Python execution per agent branch (**PASS**, 0 violations).
4. **Generation Budgets:** Strict compliance with $\le 5$ logical generations for non-recovery and $\le 6$ for candidate-recovery tasks (**PASS**, 0 violations).
5. **Upstream Generation Slots:** Exactly 2 slots equalized between Slot 1 (Structured Planner) and Slot 2 (Plan-Guided Executor) (**PASS**).
6. **Preserved Downstream Stages:** Frozen V9 Candidate Recovery, Frozen V5 Answer Verifier, Frozen V6 Self-Evaluator, and Frozen V7 Targeted Repair preserved verbatim (**PASS**).
7. **Canonical Operational Validity:** All 165 official GAIA validation tasks structurally evaluated with 0 request failures and 0 unhandled provider errors (**PASS**).
8. **Artifact Completeness:** All 12 previously ignored raw prediction and detailed evaluation JSONL artifacts force-added, verified, and locked against the canonical run manifest (**PASS**).

---

## 2. Canonical Commit & Provenance Audit

| Attribute | Preregistered / Required | Audited Artifact Value | Audit Verdict |
| :--- | :--- | :--- | :---: |
| **Inference Commit** | `314d0aecd01a1679a96d85256044c01c8b6c30ce` | `314d0aecd01a1679a96d85256044c01c8b6c30ce` | **VERIFIED** |
| **Model** | `gemini-3.5-flash-lite` | `gemini-3.5-flash-lite` | **VERIFIED** |
| **Thinking Level** | `medium` | `medium` | **VERIFIED** |
| **Max Output Tokens** | `2048` | `2048` | **VERIFIED** |
| **Temperature** | `null` (default greedy) | `null` | **VERIFIED** |
| **Schema Version** | `8` | `8` | **VERIFIED** |
| **Results Scope** | Results artifacts only; zero runtime edits | Clean diff vs docs-head | **VERIFIED** |

---

## 3. Primary Evaluation: Shared-Context Paired Upstream Ablation

The primary causal experiment evaluated whether replacing the coarse capability router with the structured planner improves upstream candidate quality when retrieval and tool evidence are strictly identical.

- **Harness:** `evaluation/run_v10_paired.py`
- **Output:** `experiments/v10/paired_upstream_raw.jsonl`, `experiments/v10/paired_summary.json`, `experiments/v10/paired_detailed.jsonl`
- **Scope:** 165 / 165 validation tasks (165 unique task IDs, 0 duplicates)
- **Shared-Context Invariance:**
  - `shared_search_hash_mismatch_count`: Exactly **0**
  - `shared_file_hash_mismatch_count`: Exactly **0**

### 3.1 Upstream Candidate Performance
| Branch | Candidate Generation Mechanism | Correct Candidates | Upstream Accuracy |
| :--- | :--- | :---: | :---: |
| **Branch A** | Frozen V9 Capability Router → Worker | 46 / 165 | 27.88% |
| **Branch B** | V10 Structured Planner → Plan-Guided Executor | 54 / 165 | 32.73% |
| **Difference** | Interventional Net Impact | **+8 tasks** | **+4.85 pp** |

### 3.2 Paired Transition Matrix
| Transition State | Definition | Count | % of Dataset |
| :--- | :--- | :---: | :---: |
| `UPSTREAM_IMPROVEMENT` | Frozen V9 incorrect $\to$ V10 correct | **13** | 7.88% |
| `UPSTREAM_REGRESSION` | Frozen V9 correct $\to$ V10 incorrect | **5** | 3.03% |
| `UPSTREAM_STABLE_CORRECT` | Both Frozen V9 and V10 correct | **41** | 24.85% |
| `UPSTREAM_STABLE_FAILURE` | Both Frozen V9 and V10 incorrect | **106** | 64.24% |
| **Total Tasks** | Arithmetic Sum Check ($13 + 5 + 41 + 106$) | **165** | 100.0% |

$$\Delta_{\text{upstream}} = N(\text{UPSTREAM\_IMPROVEMENT}) - N(\text{UPSTREAM\_REGRESSION}) = 13 - 5 = +8$$

**Result:** **`PASS`** (Supports primary preregistered hypothesis H1).

### 3.3 Upstream Telemetry Insights
- **Upstream Empty Candidate Starvation:** Reduced from 85 tasks (51.5%) in Frozen V9 to 54 tasks (32.7%) in V10.
- **Planner Parsing Success:** 164 / 165 tasks (99.39%) successfully parsed without grammar errors; only 1 task triggered the deterministic fallback.
- **Python Execution in Paired Harness:** Increased from 18 executions in Branch A to 41 executions in Branch B, demonstrating that explicit structured planning enabled the executor to formulate and run Python scripts where the coarse router failed to do so.

---

## 4. Canonical Full V10 Benchmark Evaluation

- **Harness:** `evaluation/run_level.py` (`--version v10 --no-resume --delay 5.0 --enforce-task-count`)
- **Predictions:** `experiments/v10/predictions_level_{1,2,3}.jsonl`
- **Summaries:** `experiments/v10/summary_level_{1,2,3}.json`, `experiments/v10/overall_summary.json`
- **Structural Coverage:** 165 / 165 tasks (53 L1, 86 L2, 26 L3)
- **Pipeline Completion:** 161 / 165 tasks (97.58%)
- **Request Failures:** Exactly 0

### 4.1 Canonical Official Accuracy Breakdown
| Level | Tasks | Correct | Canonical V10 Accuracy | Frozen V9 Canonical Baseline | Absolute Delta |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 53 | 33 | **62.26%** | 31 / 53 (58.49%) | +2 tasks (+3.77 pp) |
| **Level 2** | 86 | 43 | **50.00%** | 36 / 86 (41.86%) | +7 tasks (+8.14 pp) |
| **Level 3** | 26 | 8 | **30.77%** | 6 / 26 (23.08%) | +2 tasks (+7.69 pp) |
| **Overall** | **165** | **84** | **50.91%** | **73 / 165 (44.24%)** | **+11 tasks (+6.67 pp)** |

Arithmetic check: $33 + 43 + 8 = 84$.  
**Result:** **`PASS`** (Satisfies Gate 2: $\text{Accuracy}_{\text{V10}} > 44.24\%$).

### 4.2 Audit of the Four Canonical Completion Failures
Four tasks failed pipeline completion ($161 / 165$ completion success):
1. `e142056d-56ab-4352-b091-b56054bd1359` (L1): `request_success: True`, `planner_mode: PYTHON`, executor finished with `malformed_function_call_finish_reason`, candidate recovery triggered, failed code extraction (`PYTHON_CODE_EXTRACTION_FAILURE`).
2. `50ad0280-0819-4bd9-b275-5de32d3b5bcb` (L1): `request_success: True`, `planner_mode: PYTHON`, executor failed, candidate recovery triggered, failed code extraction (`PYTHON_CODE_EXTRACTION_FAILURE`).
3. `ded28325-3447-4c56-860f-e497d6fb3577` (L2): `request_success: True`, `planner_mode: PYTHON`, executor failed, candidate recovery triggered, failed code extraction (`PYTHON_CODE_EXTRACTION_FAILURE`).
4. `0bb3b44a-ede5-4db5-a520-4e844b0079c5` (L2): `request_success: True`, `planner_mode: DIRECT`, executor finished with `malformed_function_call_finish_reason`, candidate recovery triggered, failed with `MALFORMED_FUNCTION_CALL`.

**Operational Finding:** All 4 tasks were processed with `request_success: True`, `error_type: None`, and `error_message: None`. Zero HTTP 429 quota exhaustion, zero HTTP 500 server errors, and zero transport timeouts occurred. All 4 represent bounded model execution failures handled gracefully by the recovery safety pipeline.

---

## 5. Preregistered Secondary Hypotheses Evaluation

| Hypothesis | Description | Preregistered Target | Empirical V10 Value | Status |
| :--- | :--- | :---: | :---: | :---: |
| **H1** | Paired upstream improvement | $\Delta_{\text{upstream}} > 0$ | **+8** ($13 - 5$) | **PASS** |
| **H2** | Canonical accuracy vs Frozen V9 | $> 73 / 165$ ($> 44.24\%$) | **84 / 165 (50.91%)** | **PASS** |
| **H3a** | Error rate reduction on diagnosed risks | EXECUTION $< 78.3\%$<br>EVIDENCE $< 88.9\%$ | EXECUTION: **59.26%** (16/27)<br>EVIDENCE: **88.89%** (32/36) | **PARTIALLY_SUPPORTED** |
| **H3b** | Post-recovery candidate reachability | $\ge 90.0\%$ | **97.58%** (161/165) | **PASS** |
| **H3c** | Candidate recovery trigger rate | $< 54.55\%$ (baseline: 90/165) | **30.91%** (51/165) | **PASS** |
| **H3d** | Planner strict grammar parse rate | $\ge 95.0\%$ | **99.39%** (164/165) | **PASS** |
| **H3e** | Python execution success rate | $\ge 80.0\%$ | **38.64%** (17/44) | **FAIL** |

### Hypothesis Commentary
- **H3a (Risk Reductions):** EXECUTION error rate dropped significantly from $78.3\%$ in Frozen V9 to $59.26\%$ in V10, validating that structured step-by-step planning mitigated execution confusion. However, EVIDENCE error rate remained essentially unchanged ($88.89\%$ vs $88.9\%$), reflecting that upstream planning cannot overcome unretrieved or missing evidence.
- **H3e (Python Execution Reliability):** While Python requests/executions rose to 44, only 17 executed without non-zero exit codes or script exceptions (38.64% success rate). This secondary hypothesis failure highlights the key technical frontier for V11.

---

## 6. Audit of the Contemporaneous Matched Frozen V9 Control

### 6.1 Telemetry Findings
The secondary contemporaneous matched Frozen V9 control run executed under identical infrastructure conditions recorded:
- **Level 1:** 24 / 53 correct (45.28%), 16 / 53 router fallbacks.
- **Level 2:** 1 / 86 correct (1.16%), 85 / 86 router fallbacks (`model_version: null`).
- **Level 3:** 0 / 26 correct (0.00%), 26 / 26 router fallbacks (`model_version: null`).
- **Overall:** 25 / 165 correct (15.15%), 37 / 165 pipeline completion, 127 / 165 router fallbacks.

Detailed inspection of the prediction JSONL records confirmed that in **127 of 165 tasks (77.0%)**, `router_error_type: "provider_api_error"` occurred.

### 6.2 Classification & Non-Veto Decision
1. **Classification:** **`INVALID_SECONDARY_CONTROL_PROVIDER_COLLAPSE`**.
2. **Exclusion:** The 25 / 165 score and the resulting nominal cross-run matrix ($\Delta_{\text{e2e\_observational}} = +59$) are **excluded from scientific interpretation**.
3. **Preregistration Non-Veto:** In `experiments/v10/PRE_BENCHMARK.md`, the matched V9 run is formally specified as **Secondary / Observational / Non-Causal**. It is not listed among the 8 binding promotion gates. Its provider collapse does not compromise the valid primary paired ablation ($\Delta_{\text{upstream}} = +8$) or the valid canonical V10 run (84/165).

---

## 7. Resource Caps & Invariant Gates

| Gate Dimension | Contract Specification | Audited Status | Compliance |
| :--- | :--- | :---: | :---: |
| **Search Budget** | $\le 1$ Tavily search per task (0 added by recovery) | Max observed: 1, Added: 0 | **PASS** |
| **File Budget** | $\le 1$ FileTool parse per task (0 added by recovery) | Enforced by single snapshot context | **PASS** |
| **Python Budget** | $\le 1$ Python run per branch (0 added by recovery) | Max observed: 1, Added: 0 | **PASS** |
| **Non-Recovery Cap** | $\le 5$ logical generations (Planner + Executor + Verifier + Self-Eval + Repair) | Max observed: 5 | **PASS** |
| **Recovery Cap** | $\le 6$ logical generations (Planner + Executor + Recovery + Verifier + Self-Eval + Repair) | Max observed: 6 | **PASS** |
| **Upstream Slots** | Exactly 2 logical generations | Equalized at 2 | **PASS** |
| **Firewall Integrity** | Zero runtime access to ground truth or reference answers | Verified in paired & level harnesses | **PASS** |

---

## 8. Artifact Completeness & Repository Integrity

All 25 canonical result artifacts are now tracked in Git and verified with identical SHA-256 digests against `experiments/v10/CANONICAL_RUN_MANIFEST.json`:

```text
experiments/v10/paired_upstream_raw.jsonl     (a91550a706d4...)  VERIFIED
experiments/v10/paired_summary.json          (3104e63c8a29...)  VERIFIED
experiments/v10/paired_detailed.jsonl        (128f764d3c8a...)  VERIFIED
experiments/v10/predictions_level_1.jsonl    (37834ade9504...)  VERIFIED
experiments/v10/summary_level_1.json         (8a0b60403713...)  VERIFIED
experiments/v10/detailed_eval_level_1.jsonl  (4e927934fd8d...)  VERIFIED
experiments/v10/predictions_level_2.jsonl    (55aee7021fc0...)  VERIFIED
experiments/v10/summary_level_2.json         (1853c3d87a11...)  VERIFIED
experiments/v10/detailed_eval_level_2.jsonl  (6e1c4878df17...)  VERIFIED
experiments/v10/predictions_level_3.jsonl    (d9c234bc447e...)  VERIFIED
experiments/v10/summary_level_3.json         (561527183dac...)  VERIFIED
experiments/v10/detailed_eval_level_3.jsonl  (b99070fa2923...)  VERIFIED
experiments/v10/overall_summary.json         (7d1d8613cc31...)  VERIFIED
experiments/v10/CANONICAL_RUN_MANIFEST.json  (6d480053de5b...)  VERIFIED

experiments/v10_matched_v9/predictions_level_1.jsonl    (238fc403c5d4...)  VERIFIED
experiments/v10_matched_v9/summary_level_1.json         (5b2cc0d854fd...)  VERIFIED
experiments/v10_matched_v9/detailed_eval_level_1.jsonl  (1eb617701039...)  VERIFIED
experiments/v10_matched_v9/predictions_level_2.jsonl    (5d5dbac374ae...)  VERIFIED
experiments/v10_matched_v9/summary_level_2.json         (5cd61ebc2587...)  VERIFIED
experiments/v10_matched_v9/detailed_eval_level_2.jsonl  (94b204f42431...)  VERIFIED
experiments/v10_matched_v9/predictions_level_3.jsonl    (bee0aad881c1...)  VERIFIED
experiments/v10_matched_v9/summary_level_3.json         (f2319a566c38...)  VERIFIED
experiments/v10_matched_v9/detailed_eval_level_3.jsonl  (0fbb38517a3d...)  VERIFIED
experiments/v10_matched_v9/overall_summary.json         (afbbdf40524b...)  VERIFIED
experiments/v10_matched_v9/secondary_cross_run_summary.json (5b2cf319e70e...) VERIFIED
experiments/v10_matched_v9/README.md                    (Notice created)   VERIFIED
```

---

## 9. Primary Scientific Findings & Handoff to V11

### 9.1 What V10 Solved
1. **Decomposition & Plan Conditioning:** The Structured Planner effectively eliminated the coarse routing bottleneck. Breaking tasks into `MODE`, `OBJECTIVE`, `EVIDENCE_NEEDED`, `PLAN`, and `ANSWER_TYPE` provided structured guidance that raised upstream accuracy from $27.88\%$ to $32.73\%$ ($+4.85\text{ pp}$) on identical contexts.
2. **Upstream Candidate Reachability:** Initial candidate availability rose to $69.09\%$ (vs $45.45\%$ in Frozen V9), and downstream reachability reached $97.58\%$, with Candidate Recovery triggering on only $30.91\%$ of tasks (down from $54.55\%$).
3. **Benchmark-Level Performance:** End-to-end correctness advanced to **84 / 165 (50.91%)**, surpassing Frozen V9 by $+11$ tasks across all three levels.

### 9.2 Remaining Bottlenecks for V11
1. **Python Script Execution Reliability (H3e):** While more Python execution was attempted (44 tasks), script crashes, missing libraries, or syntax issues resulted in only a $38.64\%$ execution success rate.
2. **Evidence Sufficiency (H3a):** EVIDENCE-risk failure remained high ($88.89\%$). While planning structures the task, it cannot compensate for unretrieved information or shallow search results.
3. **Targeted Repair Stagnation:** Targeted Repair triggered on SUSPECT candidates but rarely replaced answers ($16 \text{ KEEP} / 0 \text{ REPLACE}$ on L1; $32 \text{ KEEP} / 2 \text{ REPLACE}$ on L2; $14 \text{ KEEP} / 2 \text{ REPLACE}$ on L3), yielding only $+1$ net improvement overall.

