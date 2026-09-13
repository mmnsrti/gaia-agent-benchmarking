# V7 — SUSPECT-Triggered Targeted Repair

**Status:** POST-BENCHMARK AUDITED (Freeze Candidate)  
**POST-BENCHMARK AUDIT:** PASSED  
**FREEZE READINESS:** READY_TO_FREEZE_WITH_DOCUMENTED_LIMITATIONS  
**Parent Baseline:** Frozen V6 (`v6-self-evaluation-agent`)  
**Branch:** `v7-targeted-repair`  

See [`docs/V7_POST_BENCHMARK_AUDIT.md`](../../docs/V7_POST_BENCHMARK_AUDIT.md) for the comprehensive scientific post-benchmark audit, causal transition analysis, diagnostic calibration, candidate starvation forensics, and freeze review. Deterministic SHA-256 hashes are recorded in [`ARTIFACT_MANIFEST.sha256`](ARTIFACT_MANIFEST.sha256).

---

## 1. Research Definition & Architecture

Version 7 (V7) investigates bounded, text-only targeted repair downstream of the frozen V6 self-evaluator:

```text
V7 = Frozen V6 + one bounded text-only repair generation triggered exclusively by valid SUSPECT
```

### Research Question
> *Can a targeted, bounded, single-turn text-only repair generation fix erroneous candidate answers identified as SUSPECT by self-evaluation, without harming correct answers or introducing tool calls/loops?*

### Architecture & Runtime Invariants
1. **Upstream Frozen Pipeline**: Completely identical to frozen V6 (search $\le 1$, file extraction $\le 1$, capability router selecting `DIRECT` vs `PYTHON`, route-specific workers, candidate eligibility guards, one-shot verifier `KEEP`/`REVISE`, and read-only self-evaluator emitting `PASS`/`SUSPECT`).
2. **Selective Trigger Guard**: Repair is triggered if and only if the self-evaluator produces a valid `SUSPECT` assessment on a non-empty candidate answer.
   - `PASS` evaluations **never** trigger repair.
   - Empty/missing candidate answers **never** trigger repair.
   - Ineligible or failed evaluations **never** trigger repair.
3. **Bounded Budget**: At most **1** repair generation attempt per task. The overall task generation attempt limit is capped at **$\le 5$** ($\le 4$ upstream + $\le 1$ repair).
4. **Tool Isolation**: The repair stage is strictly text-only (`mode="NONE"`). Zero search queries, zero Python executions, and zero file operations.
5. **Deterministic Fallback Safety**: If the repair generation fails, times out, or produces malformed text, the original pre-repair answer is preserved identically (`repair_answer_changed = False`).
6. **Ground-Truth Firewall**: The repair agent operates with zero knowledge of reference answers or scorer outputs. All scoring is executed post-hoc.

---

## 2. Canonical Headline Results (GAIA 2023 Validation Set, 165 Tasks)

### Within-Run Repair Performance (Direct Causal Effect)

Because V7 logs both `pre_repair_answer` / `pre_repair_correct` and `post_repair_answer` / `post_repair_correct` within the exact same execution trace, the causal effect of targeted repair is measured with zero cross-run sampling confounders:

| Metric | Level 1 (N=53) | Level 2 (N=86) | Level 3 (N=26) | Overall (N=165) |
| :--- | :---: | :---: | :---: | :---: |
| **Pre-Repair Correct** | 22 (41.51%) | 22 (25.58%) | 2 (7.69%) | **46 (27.88%)** |
| **Post-Repair Correct** | 22 (41.51%) | 22 (25.58%) | 2 (7.69%) | **46 (27.88%)** |
| **Net Repair Delta** | **0 (0.00 pp)** | **0 (0.00 pp)** | **0 (0.00 pp)** | **0 tasks (0.00 pp)** |
| Completed Tasks | 34 (64.15%) | 38 (44.19%) | 8 (30.77%) | **80 (48.48%)** |
| Improvements | 0 | 0 | 0 | **0** |
| Regressions | 0 | 0 | 0 | **0** |
| Stable Correct | 1 | 2 | 1 | **4** |
| Stable Failure | 4 | 5 | 6 | **15** |
| Not Triggered | 48 | 79 | 19 | **146** |
| **Correction Rate** | 0.00% (0/4) | 0.00% (0/5) | 0.00% (0/6) | **0.00% (0/15)** |
| **Harm Rate** | 0.00% (0/1) | 0.00% (0/2) | 0.00% (0/1) | **0.00% (0/4)** |

---

## 3. Repair Action Breakdown

Across all 165 GAIA tasks, exactly 19 tasks triggered targeted repair:

| Level | Triggered | Attempted | Valid Actions | KEEP | REPLACE | Failed (Fallback) | Answers Mutated |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 5 | 5 | 5 | 5 | 0 | 0 | 0 |
| **Level 2** | 7 | 7 | 6 | 6 | 0 | 1 | 0 |
| **Level 3** | 7 | 7 | 7 | 5 | 2 | 0 | 2 |
| **Total** | **19** | **19** | **18** | **16** | **2** | **1** | **2** |

- **KEEP Dominance (16 / 19, 84.21%)**: In the vast majority of triggered cases, the repair model correctly recognized that without new external evidence or tools, revising the answer would be speculative, preserving the existing answer.
- **REPLACE Actions (2 / 19, 10.53%)**:
  1. Task `ebbc1f13-d24d-40df-9068-adcf735b4240` (L3, `EVIDENCE` risk): Pre-repair `'El Pais'` $\rightarrow$ Post-repair `'The Country'`. (Both incorrect $\rightarrow$ `STABLE_FAILURE`).
  2. Task `c3a79cfe-8206-451f-aca8-3fec8ebe51d3` (L3, `FORMAT` risk): Pre-repair verbose text $\rightarrow$ Post-repair `'8'`. (Both incorrect $\rightarrow$ `STABLE_FAILURE`).
- **Failed Repair (1 / 19, 5.26%)**:
  - Task `c8b7e059-c60d-472e-ad64-3b04ae1166dc` (L2, `EXECUTION` risk): Failed with `malformed_repair_text`. The pre-repair candidate answer was preserved verbatim (`repair_answer_changed = False`).

---

## 4. Diagnostic Accuracy (Anchored to Pre-Repair Correctness)

Evaluating self-evaluation failure detection strictly against **pre-repair correctness**:

| Metric | Value | Meaning |
| :--- | :---: | :--- |
| **Eligible Tasks** | 78 / 165 | Non-empty candidate answers reaching self-evaluator |
| **Valid Evaluations** | 78 / 78 (100%) | Schema-compliant `PASS`/`SUSPECT` judgments |
| **True Positives (TP)** | **15** | Erroneous answers correctly flagged as `SUSPECT` |
| **False Positives (FP)** | **4** | Correct answers mistakenly flagged as `SUSPECT` |
| **True Negatives (TN)** | **42** | Correct answers appropriately classified as `PASS` |
| **False Negatives (FN)** | **17** | Erroneous answers missed by evaluator (`PASS`) |
| **Precision** | **78.95%** (15 / 19) | Reliability of the `SUSPECT` trigger |
| **Recall (Eligible)** | **46.88%** (15 / 32) | Fraction of candidate-bearing errors caught |
| **F1 Score** | **0.5882** | Harmonic mean of precision and recall |
| **Specificity** | **91.30%** (42 / 46) | Preservation of correct candidate answers |
| **False Alarm Rate (FAR)** | **8.70%** (4 / 46) | Low rate of false suspicion on correct answers |
| **Missed Error Rate (MER)** | **53.12%** (17 / 32) | Rate of uncaught errors among candidates |
| **Brier Score** | **0.2581** | Mean squared error of calibrated error probabilities |

---

## 5. Candidate Starvation & System Error Reach

| Reach Metric | Count / Value | Proportion |
| :--- | :---: | :---: |
| **Total Benchmark Tasks** | 165 | 100.0% |
| **Total Pre-Repair Errors** | 119 | 72.12% |
| **No-Candidate Tasks (Starved)** | 87 | 52.73% of tasks |
| **Starved System Errors** | 87 | **73.11% of all errors (87 / 119)** |
| **Candidate-Bearing Errors** | 32 | 26.89% of all errors (32 / 119) |
| **Erroneous Answers Triggered (TP)** | 15 | 12.61% of all errors (15 / 119) |
| **Opportunity Coverage (Reachable Errors)** | 15 / 32 | **46.88%** |
| **End-to-End Corrected Fraction** | 0 / 119 | **0.00%** |

Candidate starvation remains the dominant bottleneck in the agent architecture: **73.11%** of all failures occurred before a candidate answer was ever synthesized, rendering them completely unreachable by downstream repair.

---

## 6. Contemporaneous Matched Frozen V6 Control Comparison

| Level | Matched V6 Correct | V7 Post-Repair Correct | Cross-Run Delta (Tasks) | Cross-Run Delta (pp) |
| :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 24 / 53 (45.28%) | 22 / 53 (41.51%) | -2 | -3.77 pp |
| **Level 2** | 25 / 86 (29.07%) | 22 / 86 (25.58%) | -3 | -3.49 pp |
| **Level 3** | 3 / 26 (11.54%) | 2 / 26 (7.69%) | -1 | -3.85 pp |
| **Overall** | **52 / 165 (31.52%)** | **46 / 165 (27.88%)** | **-6** | **-3.64 pp** |

> **Methodological Note on Cross-Run Delta:**
> The cross-run delta (-6 tasks) is strictly **observational** and reflects upstream model stochasticity, prompt routing decisions, and completion variation across separate runs. The within-run repair delta is rigorously **0 tasks (0.00 pp)**.

---

## 7. Canonical Artifacts & Verification Manifest

Deterministic SHA-256 digests for all canonical evaluation artifacts in `experiments/v7/`:

| Artifact | SHA-256 Checksum | Size (Bytes) |
| :--- | :--- | :---: |
| `detailed_eval_level_1.jsonl` | `da7c0733d9943fe0593dd85368a5c3bb9aa0e4d75db18e97a3c3df5b4511d0bb` | 557,750 |
| `detailed_eval_level_2.jsonl` | `5c77749176391d1e43431ee27c08003fdfc97805b81a7b8e194ea7df49bf10e4` | 884,930 |
| `detailed_eval_level_3.jsonl` | `26ff694c9f1fc70bb073f8d384074c7df76f14a60ea51ce4a8ef7be60db4b4b2` | 271,768 |
| `predictions_level_1.jsonl` | `b99e0df232148d56b825bf0214a13f679776d6c340d048b61c9ec8d8ce8646b9` | 2,349,607 |
| `predictions_level_2.jsonl` | `0ea3beaa5e7aa79213dcde10378037a3479aebaa0c242ef9983fa9942ea39c63` | 3,456,861 |
| `predictions_level_3.jsonl` | `ca87ca3737b8be881b22e11894d075217e6515c5567b45ca4cb3dc2bc7198bb6` | 1,061,643 |
| `summary_level_1.json` | `5a74ef6b7b25055a40db3d04f2f01f8084a3290680a659ccfec5f187a54a0044` | 7,654 |
| `summary_level_2.json` | `e2a44f51950e386008ebec983b0f588c8351722cb5ba51ca7dfae8b02446975a` | 7,576 |
| `summary_level_3.json` | `378db1064bb661073cefb1dbd04cb5032338d3882725ec35118dd6e9b8973fa3` | 7,370 |

---

## 8. Limitations & Recommended Next Steps

1. **Text-Only Repair Limitation**: Without tool access (re-searching or re-executing Python), targeted repair cannot retrieve missing factual information or recompute complex calculations. In 15 of 19 cases, the error was rooted in missing evidence.
2. **Candidate Starvation**: Over 73% of errors stem from upstream pipeline failures to produce any answer candidate. Future iterations (V8) must address candidate generation reach rather than relying exclusively on post-candidate repair.
3. **Freeze Readiness**: The experimental package is clean, completely verified, deterministic, and ready for freeze under documented limitations:
   `READY_TO_FREEZE_WITH_DOCUMENTED_LIMITATIONS`.

