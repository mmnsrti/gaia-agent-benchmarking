# V7 — SUSPECT-Triggered Targeted Repair

**Status:** FROZEN<br>
**POST-BENCHMARK AUDIT:** PASSED<br>
**FREEZE READINESS:** FROZEN_WITH_DOCUMENTED_LIMITATIONS<br>
**Parent Baseline:** Frozen V6 (`v6-self-evaluation-agent`)<br>
**Branch:** `v7-targeted-repair`

See [`docs/V7_POST_BENCHMARK_AUDIT.md`](../../docs/V7_POST_BENCHMARK_AUDIT.md) for the comprehensive scientific post-benchmark audit, within-run transition analysis, diagnostic calibration, candidate starvation forensics, and freeze review. Deterministic SHA-256 hashes are recorded in [`ARTIFACT_MANIFEST.sha256`](ARTIFACT_MANIFEST.sha256).

---

## 1. Research Definition & Architecture

Version 7 (V7) evaluates bounded, text-only targeted repair downstream of the frozen V6 self-evaluator:

```text
V7 = Frozen V6 + one bounded text-only repair generation triggered exclusively by valid SUSPECT
```

### Research Question
> *Can one bounded targeted repair generation, triggered only by a valid V6 SUSPECT assessment, correct more erroneous answers than it harms correct answers, without additional tools, new evidence retrieval, or retries?*

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

### Within-Run Pre/Post Repair Effect

Because V7 logs both `pre_repair_answer` / `pre_repair_correct` and `post_repair_answer` / `post_repair_correct` within the exact same execution trace, the observed repair-stage effect in this benchmark run is measured with zero cross-run sampling variance:

| Metric | Level 1 (N=53) | Level 2 (N=86) | Level 3 (N=26) | Overall (N=165) |
| :--- | :---: | :---: | :---: | :---: |
| **Pre-Repair Correct** | 22 (41.51%) | 22 (25.58%) | 2 (7.69%) | **46 (27.88%)** |
| **Post-Repair Correct** | 22 (41.51%) | 22 (25.58%) | 2 (7.69%) | **46 (27.88%)** |
| **Net Repair Delta** | **0 (0.00 pp)** | **0 (0.00 pp)** | **0 (0.00 pp)** | **0 tasks (0.00 pp)** |
| Completed Tasks | 34 (64.15%) | 38 (44.19%) | 8 (30.77%) | **80 (48.48%)** |
| Improvements ($0 \rightarrow 1$) | 0 | 0 | 0 | **0** |
| Regressions ($1 \rightarrow 0$) | 0 | 0 | 0 | **0** |
| Stable Correct ($1 \rightarrow 1$) | 1 | 2 | 1 | **4** |
| Stable Failure ($0 \rightarrow 0$) | 4 | 5 | 6 | **15** |
| Not Triggered | 48 | 79 | 19 | **146** |
| **Correction Rate** | 0.00% (0/4) | 0.00% (0/5) | 0.00% (0/6) | **0.00% (0/15)** |
| **Triggered Harm Rate** | 0.00% (0/1) | 0.00% (0/2) | 0.00% (0/1) | **0.00% (0/4)** |

> **Finding**: In this V7 benchmark run, the bounded targeted repair stage produced zero wrong-to-correct transitions and zero correct-to-wrong transitions, for a net within-run change of 0 correct tasks.

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
  1. Task `ebbc1f13-d24d-40df-9068-adcf735b4240` (L3, `EVIDENCE` risk): Pre-repair candidate `'El Pais'` $\rightarrow$ Post-repair answer `'The Country'`. Both incorrect $\rightarrow$ `STABLE_FAILURE`.
  2. Task `c3a79cfe-8206-451f-aca8-3fec8ebe51d3` (L3, `FORMAT` risk): Pre-repair candidate was a verbose paragraph $\rightarrow$ Post-repair answer `'8'`. Both incorrect $\rightarrow$ `STABLE_FAILURE`.
- **Failed Repair (1 / 19, 5.26%)**:
  - Task `c8b7e059-c60d-472e-ad64-3b04ae1166dc` (L2, `EXECUTION` risk): Failed with `malformed_repair_text`. The pre-repair candidate answer was preserved verbatim (`repair_answer_changed = False`). Not counted as `KEEP`.
- **Harm Safety Context**: Among the four initially-correct answers that were flagged `SUSPECT`, no regression was observed in this run ($0 / 4 = 0.00\%$). All four were protected by `KEEP` behavior. This observation is bounded by the small denominator ($N = 4$) and only two actual `REPLACE` actions.

---

## 4. Diagnostic Accuracy (Anchored to Pre-Repair Ground Truth)

Evaluating self-evaluation failure detection strictly against **pre-repair ground truth correctness**:

| Metric | Value | Meaning |
| :--- | :---: | :--- |
| **Eligible Candidates** | 78 / 165 | Non-empty candidate answers reaching self-evaluator |
| **Diagnostic Coverage** | 78 / 78 (100.0%) | Valid evaluations on eligible candidates (78/165 is candidate availability) |
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

Candidate starvation remains the dominant end-to-end limitation: **73.11%** of all failures occurred before a candidate answer was ever synthesized, rendering them completely unreachable by downstream repair.

---

## 6. Contemporaneous Matched Frozen V6 Control Comparison

| Level | Matched V6 Correct | V7 Post-Repair Correct | Cross-Run Delta (Tasks) | Cross-Run Delta (pp) |
| :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 24 / 53 (45.28%) | 22 / 53 (41.51%) | -2 | -3.77 pp |
| **Level 2** | 25 / 86 (29.07%) | 22 / 86 (25.58%) | -3 | -3.49 pp |
| **Level 3** | 3 / 26 (11.54%) | 2 / 26 (7.69%) | -1 | -3.85 pp |
| **Overall** | **52 / 165 (31.52%)** | **46 / 165 (27.88%)** | **-6** | **-3.64 pp** |

- **Cross-Run 2x2 Contingency Matrix**:
  - Both correct: 36
  - Both wrong: 103
  - Matched V6 wrong $\rightarrow$ V7 correct: 10
  - Matched V6 correct $\rightarrow$ V7 wrong: 16
  - Check: $36 + 103 + 10 + 16 = 165$ tasks.

> **Methodological Note on Cross-Run Delta:**
> The cross-run delta (-6 tasks) is strictly **observational and non-causal**. Within the V7 run itself, the direct causal delta of targeted repair was identically **0 tasks (0.00 pp)**. The cross-run difference reflects upstream model sampling stochasticity, capability routing choices, and provider completion variation across separate runs.

---

## 7. Canonical Artifacts & Verification Manifest

Deterministic SHA-256 digests for all canonical evaluation artifacts in `experiments/v7/`:

| Artifact | SHA-256 Checksum | Size (Bytes) | Verification Status |
| :--- | :--- | :---: | :---: |
| `predictions_level_1.jsonl` | `075cab93a74b191de23489696f3b1ca347e694f9dbf317f21b83744e464c3146` | 2,349,607 | Verified (53/53) |
| `predictions_level_2.jsonl` | `6181f9b9fa36e20af1a38db7bd9e78101dc37df9a006343922743ec7cd0b3878` | 3,456,861 | Verified (86/86) |
| `predictions_level_3.jsonl` | `cb38ce40cb05e83d561acd77247dd3d8c157ed771208c1e4e4484bc02a583c39` | 1,061,643 | Verified (26/26) |
| `detailed_eval_level_1.jsonl` | `6d6f4143d44b82cb6c5fe7959d0b389b791b25f271ab93523d189f1c3d864443` | 557,750 | Verified (53/53) |
| `detailed_eval_level_2.jsonl` | `dbebd86ad6cd45f38b37754f141ee82cf331e63d7d388fa9f56fe7ee301e904c` | 884,930 | Verified (86/86) |
| `detailed_eval_level_3.jsonl` | `46f05429834503abdc553a1350377866a53749244f601ee68fe5255d943e6fbf` | 271,768 | Verified (26/26) |
| `summary_level_1.json` | `8477a46ed5fb58d82b1c9365b23491cdf3c688be2fe636d7ffb2a0bd88484b1f` | 7,654 | Verified |
| `summary_level_2.json` | `66117e9d8ce0b9ee2b670af83342ca9355a35ec3b6e99b92fc152fc2fb3c65c1` | 7,576 | Verified |
| `summary_level_3.json` | `9d36d5f9e1c0f90736b58c95de1ae7a91075449e9f57654b2b7c64f05dd112cd` | 7,370 | Verified |

> **Artifact Storage Policy**: Raw prediction logs (`predictions_*.jsonl`) are local canonical artifacts ignored by Git under `.gitignore`. Aggregated summary files (`summary_*.json`) and `ARTIFACT_MANIFEST.sha256` are tracked in Git.

---

## 8. Scientific Limitations & Handoff to V8

1. **Evidence-Limitation Context**: The V7 repair stage was unable to acquire new evidence because active retrieval and tools were intentionally prohibited. Most SUSPECT triggers were evaluator-assigned EVIDENCE risks, while V7 was limited to reconsidering already-available evidence. This motivates studying bounded active verification in a future version.
2. **Harm Safety Boundedness**: While zero regressions were observed, this was supported by only four initially-correct triggered answers and two total replacement events.
3. **Candidate Starvation**: Over 73% of all system errors occurred upstream of candidate formulation. Downstream targeted repair cannot address candidate-starved tasks.
4. **V8 Increment Scope**: Handoff to V8 is strictly focused on **Bounded Active Verification** (`V8 = Frozen V7 + one bounded active verification capability`). Candidate starvation remains a separate future research direction.
