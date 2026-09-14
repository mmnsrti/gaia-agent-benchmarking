# V8 — Bounded Active Evidence Verification

**Status:** FROZEN<br>
**RESEARCH VERDICT:** REJECTED_AS_AN_IMPROVEMENT<br>
**FREEZE VERDICT:** FROZEN_WITH_DOCUMENTED_NEGATIVE_RESULT<br>
**PROMOTION VERDICT:** DO_NOT_PROMOTE<br>
**Parent Baseline:** Frozen V7 (`v7-targeted-repair`)<br>
**Successor Baseline for V9:** Frozen V7 (Branch: `v7-targeted-repair`)<br>
**Branch:** `v8-active-evidence-verification`

See [`docs/V8_POST_BENCHMARK_AUDIT.md`](../../docs/V8_POST_BENCHMARK_AUDIT.md) for the comprehensive scientific post-benchmark audit, within-run transition analysis, diagnostic calibration, candidate starvation forensics, and freeze review. Full freeze specification is recorded in [`FROZEN.md`](FROZEN.md). Deterministic SHA-256 hashes are recorded in [`ARTIFACT_MANIFEST.sha256`](ARTIFACT_MANIFEST.sha256).

---

## 1. Research Definition & Architecture

Version 8 (V8) evaluates bounded active evidence verification downstream of the frozen V7 pipeline:

```text
V8 = Frozen V7 + at most one bounded active web evidence retrieval + at most one bounded evidence-based adjudication
```

### Research Question
> *When Frozen V7 reaches a non-empty answer whose upstream V6 diagnostic is a valid SUSPECT with RISK_TYPE: EVIDENCE, does one additional bounded web retrieval followed by one bounded evidence-based adjudication correct more erroneous answers than it harms correct answers?*

### Architecture & Runtime Invariants
1. **Upstream Frozen Pipeline**: Completely identical to frozen V7 (initial search $\le 1$, file extraction $\le 1$, capability router selecting `DIRECT` vs `PYTHON`, route-specific workers, candidate eligibility guards, one-shot verifier `KEEP`/`REVISE`, read-only self-evaluator emitting `PASS`/`SUSPECT`, and targeted repair generation).
2. **Selective Trigger Guard**: Active evidence verification is triggered if and only if:
   - Upstream V7 reaches a non-empty answer.
   - The upstream self-evaluator produced a valid `SUSPECT` assessment with `risk_type: EVIDENCE`.
   - `PASS` evaluations, non-`EVIDENCE` risks (`REASONING`, `CALCULATION`, etc.), and empty candidate answers **never** trigger active verification.
3. **Deterministic Query Formulation**: Query is strictly constructed as `f"{question.strip()}\n{current_answer.strip()}"`. No LLM query reformulation, no search tuning.
4. **Bounded Search Budget**: At most **1** additional Tavily web search (`search_depth="basic"`, `max_results=5`). Total task search calls $\le 2$. Search retries = 0. If search returns empty or fails, verification aborts and preserves the upstream answer.
5. **Bounded Adjudication Budget**: Exactly **1** LLM adjudication attempt (`mode="NONE"`, zero tools, zero Python, zero file operations, provider retries = 0). Allowed actions: `KEEP` or `REPLACE`. Overall task LLM generation attempts capped at $\le 6$.
6. **Deterministic Fallback Safety**: If search fails or adjudication fails, the upstream Frozen V7 answer is preserved verbatim (`active_verification_answer_changed = False`).
7. **Ground-Truth Firewall**: The agent operates with zero access to ground truth answers or scorer outputs. All evaluations are executed strictly post-hoc using the official GAIA leaderboard scorer.

---

## 2. Canonical Headline Results (GAIA 2023 Validation Set, 165 Tasks)

### Primary Within-Run Intervention Measurement

Because V8 logs both `pre_active_verification_answer` / `pre_active_verification_correct` and `post_active_verification_answer` / `final_correct` within the exact same execution trace, the causal effect of active evidence verification is evaluated with zero cross-run sampling variance:

| Metric | Level 1 (N=53) | Level 2 (N=86) | Level 3 (N=26) | Overall (N=165) |
| :--- | :---: | :---: | :---: | :---: |
| **Pre-Active-Verification Correct** | 20 (37.74%) | 25 (29.07%) | 4 (15.38%) | **49 (29.70%)** |
| **Post-Active-Verification Correct** | 20 (37.74%) | 25 (29.07%) | 3 (11.54%) | **48 (29.09%)** |
| **Net Within-Run Intervention Delta** | **0 (0.00 pp)** | **0 (0.00 pp)** | **-1 (-3.85 pp)** | **-1 task (-0.61 pp)** |
| Completed Tasks | 53 (100.0%) | 86 (100.0%) | 26 (100.0%) | **165 (100.0%)** |
| Triggered Interventions | 5 | 7 | 3 | **15** |
| Improvements ($0 \rightarrow 1$) | 0 | 0 | 0 | **0** |
| Regressions ($1 \rightarrow 0$) | 0 | 0 | 1 | **1** |
| Stable Correct ($1 \rightarrow 1$) | 0 | 0 | 1 | **1** |
| Stable Failure ($0 \rightarrow 0$) | 5 | 7 | 1 | **13** |
| Not Triggered | 48 | 79 | 23 | **150** |
| **Correction Rate** ($0 \rightarrow 1$ / Triggered Erroneous) | 0.00% (0/5) | 0.00% (0/7) | 0.00% (0/1) | **0.00% (0/13)** |
| **Harm Rate** ($1 \rightarrow 0$ / Triggered Correct) | N/A (0/0) | N/A (0/0) | 50.0% (1/2) | **50.0% (1/2)** |

> **Primary Scientific Finding**: In this canonical benchmark run, bounded active evidence verification produced **0 improvements**, **1 regression**, and a net within-run change of **-1 task (-0.61 pp)** across 165 GAIA tasks.

### Regression Case Detail
- **Task ID**: `00d579ea-0889-4fd9-a771-2c8d79835c8d` (Level 3)
- **Question**: Identification of Norbert Wiener's doctoral student who became president of MIT.
- **Pre-Active Candidate**: `'Claude Shannon'` (Correct under GAIA evaluation)
- **Active Search**: Retrieved articles mentioning Jerome Wiesner alongside Norbert Wiener and Claude Shannon.
- **Active Adjudication**: Action `REPLACE`, substituting `'Jerome Wiesner'`.
- **Post-Active Answer**: `'Jerome Wiesner'` (Incorrect)
- **Transition**: $1 \rightarrow 0$ (`REGRESSION`).

---

## 3. Active Verification Funnel & Adjudication Breakdown

Across all 165 benchmark tasks:

```text
Total Tasks (165)
  └── Non-Empty Candidate Answers: 83 (50.3%)
        └── Upstream Evaluator SUSPECT: 18 (21.7% of candidates)
              └── SUSPECT + RISK_TYPE: EVIDENCE: 15 (83.3% of SUSPECT)
                    └── Eligible & Triggered: 15 (100.0%)
                          └── Searches Attempted: 15
                                ├── Usable Evidence Retrieved: 14 (93.3%)
                                │     └── Adjudication Attempted: 14 (100.0%)
                                │           ├── Valid Action KEEP: 13 (92.9%)
                                │           └── Valid Action REPLACE: 1 (7.1% -> Regression)
                                └── Search Empty / Failed: 1 (6.7% -> Verbatim Fallback)
```

- **Adjudication Conservatism**: The adjudicator selected `KEEP` in 13 out of 14 valid adjudications (92.9%), correctly identifying that the retrieved snippets did not conclusively disprove the candidate, but consequently correcting 0 errors.
- **The Only Replacement Produced a Regression**: In the single instance where the adjudicator selected `REPLACE`, external web noise led the model to swap a correct answer for an incorrect one.

---

## 4. Upstream Diagnostic Accuracy (Anchored to Pre-Repair Ground Truth)

Evaluating self-evaluation failure detection against **pre-repair ground truth correctness**:

| Metric | Value | Meaning |
| :--- | :---: | :--- |
| **Eligible Candidates** | 83 / 165 | Non-empty candidate answers reaching self-evaluator |
| **Diagnostic Coverage** | 83 / 83 (100.0%) | Valid evaluations on eligible candidates |
| **True Positives (TP)** | **15** | Erroneous answers correctly flagged as `SUSPECT` |
| **False Positives (FP)** | **3** | Correct answers mistakenly flagged as `SUSPECT` |
| **True Negatives (TN)** | **47** | Correct answers appropriately classified as `PASS` |
| **False Negatives (FN)** | **18** | Erroneous answers missed by evaluator (`PASS`) |
| **Precision** | **83.33%** (15 / 18) | Reliability of the `SUSPECT` trigger |
| **Recall (Eligible Candidates)** | **45.45%** (15 / 33) | Fraction of candidate-bearing errors detected |
| **Specificity** | **94.00%** (47 / 50) | Correct candidate answers preserved |
| **F1 Score** | **0.5882** | Harmonic mean of precision and recall |

---

## 5. Candidate Starvation & System Error Reach

| Reach Metric | Count / Value | Proportion |
| :--- | :---: | :---: |
| **Total Benchmark Tasks** | 165 | 100.0% |
| **Total Pre-Active Errors** | 116 | 70.30% |
| **No-Candidate Tasks (Starved)** | 82 | 49.70% of tasks |
| **Starved System Errors** | 82 | **70.69% of all errors (82 / 116)** |
| **Candidate-Bearing Errors** | 34 | 29.31% of all errors (34 / 116) |
| **Active Verification Reachable Errors** | 13 | 11.21% of all errors (13 / 116) |
| **End-to-End Corrected Errors** | 0 / 116 | **0.00%** |

Candidate starvation remains the paramount architectural bottleneck: **70.69%** of all errors occurred prior to candidate answer generation (e.g. router/worker syntax errors, empty generations), placing them permanently beyond the reach of downstream verification.

---

## 6. Contemporaneous Matched Frozen V7 Control Comparison

A contemporaneous matched run of Frozen V7 was executed alongside V8 under identical environment, provider, and network conditions:

| Level | Matched Frozen V7 Correct | Canonical V8 Final Correct | Cross-Run Delta (Tasks) | Cross-Run Delta (pp) |
| :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 21 / 53 (39.62%) | 20 / 53 (37.74%) | -1 | -1.89 pp |
| **Level 2** | 21 / 86 (24.42%) | 25 / 86 (29.07%) | +4 | +4.65 pp |
| **Level 3** | 3 / 26 (11.54%) | 3 / 26 (11.54%) | 0 | 0.00 pp |
| **Overall** | **45 / 165 (27.27%)** | **48 / 165 (29.09%)** | **+3** | **+1.82 pp** |

### Cross-Run 2x2 Contingency Matrix
- **Both Correct**: 35
- **Both Wrong**: 107
- **Matched V7 Wrong $\rightarrow$ V8 Correct**: 13
- **Matched V7 Correct $\rightarrow$ V8 Wrong**: 10
- **Total Tasks**: $35 + 107 + 13 + 10 = 165$

> **Methodological Note on Cross-Run vs Within-Run Deltas:**
> The cross-run difference (+3 tasks, +1.82 pp) is strictly **observational and non-causal**. Within the V8 run itself, the active verification intervention directly caused **-1 task (-0.61 pp)**. The positive cross-run difference is driven by upstream sampling stochasticity in the worker/router stages between separate executions, not by active verification.

---

## 7. Canonical Artifacts & Verification Manifest

Deterministic SHA-256 digests for all canonical evaluation artifacts in `experiments/v8/`:

| Artifact | SHA-256 Checksum | Size (Bytes) | Verification Status |
| :--- | :--- | :---: | :---: |
| `predictions_level_1.jsonl` | `dbae4a9f1688bcf108c4fa187329a301a9160b4e640ab75a41855cbf5cf1cc68` | 2,248,111 | Verified (53/53) |
| `predictions_level_2.jsonl` | `79b26a2fee23ec91f0c4fbe3925e02eb0b3837388aa963f9b4390e2b47ab315f` | 3,458,958 | Verified (86/86) |
| `predictions_level_3.jsonl` | `6de6f0d9e209cf4bf921f84d5f4c0781636121756a73c6d93b0714c8ed97b450` | 1,057,945 | Verified (26/26) |
| `detailed_eval_level_1.jsonl` | `87f3c509d069465ab5bb341bb4bb517048a295a2d39a81b947b3289903fddff8` | 633,671 | Verified (53/53) |
| `detailed_eval_level_2.jsonl` | `235e7d390f80b2e6b2bfca85b59df639e64f9f3f85c002d00a93861038b3afc7` | 1,017,114 | Verified (86/86) |
| `detailed_eval_level_3.jsonl` | `1aa96949fd0ae3739de3e26858d7b0f6ecd7cba1fce3dfa4a9aba4183953d3a6` | 310,349 | Verified (26/26) |
| `summary_level_1.json` | `dafb99ed77a09148bd119e816829e6402da9ba7fafd3c64edb2c553b209c3e04` | 11,092 | Verified |
| `summary_level_2.json` | `1052597d7f3802837b300df5631913dada9c372df082f9656ffd462ea341217d` | 11,094 | Verified |
| `summary_level_3.json` | `ab617eb2118d952005ad86f4c11cda27c5acdf09d2bcf22a0a1b071fb75f281c` | 10,786 | Verified |

---

## 8. Governance, Freeze Verdict & Succession Policy

- **Research Verdict**: `REJECTED_AS_AN_IMPROVEMENT`
- **Freeze Verdict**: `FROZEN_WITH_DOCUMENTED_NEGATIVE_RESULT`
- **Promotion Verdict**: `DO_NOT_PROMOTE`
- **Architectural Lineage for V9**: Successor baseline is **Frozen V7** (`v7-targeted-repair`). V8 active evidence verification must **NOT** be inherited or merged into future versions.
- **Strategic Recommendation**: Post-answer verification has shown diminishing and negative returns across V7 and V8. Future architectural iterations should prioritize resolving upstream **candidate starvation** (recovering from function calling / syntax errors before candidate generation).

