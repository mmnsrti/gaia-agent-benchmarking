# Contemporaneous Matched Frozen V7 Control

**Status**: COMPLETED  
**Scientific Behavior**: Frozen V7 (`v7-targeted-repair`)  
**Execution Environment**: Same V9 inference commit infrastructure (`6369f427c4479073a6ca06531bdfd43e47cd613f`)  
**Parent Baseline**: Frozen V7 (`v7-targeted-repair`)  
**Model**: `gemini-3.5-flash-lite`  
**Evaluation Scope**: Full GAIA 2023 Validation Set (165 Tasks: 53 Level 1, 86 Level 2, 26 Level 3)  
**Date**: September 2026  
**Status**: COMPLETED
**Scientific Behavior**: Frozen V7 (`v7-targeted-repair`)
**Execution Environment**: Same V9 inference commit infrastructure (`6369f427c4479073a6ca06531bdfd43e47cd613f`)
**Parent Baseline**: Frozen V7 (`v7-targeted-repair`)
**Model**: `gemini-3.5-flash-lite`
**Evaluation Scope**: Full GAIA 2023 Validation Set (165 Tasks: 53 Level 1, 86 Level 2, 26 Level 3)
**Date**: September 2026

---

## 1. Experimental Role & Scientific Purpose

This directory contains the canonical artifacts from the **contemporaneous matched Frozen V7 control run** executed alongside the V9 benchmark.

### Purpose
The matched control serves as an empirical reference point to document the observational performance of the Frozen V7 architecture under identical:
- Provider infrastructure and API endpoint state
- Multi-key transport failover configuration
- Runtime Python environment (Windows NT, Python 3.13.2)
- Temporal execution window (September 2026)
- Exact inference commit: `6369f427c4479073a6ca06531bdfd43e47cd613f`

### Methodological Interpretation
> [!IMPORTANT]
> **Secondary / Observational / Non-Causal**:  
> In accordance with Section 3 of `experiments/v9/PRE_BENCHMARK.md`, cross-run comparisons between separate stochastic executions are strictly **secondary, observational, and non-causal**.  
> Because separate stochastic runs diverge upstream due to LLM sampling variance, capability router selection, and search query variation, cross-run deltas reflect environmental and sampling stochasticity rather than an isolated intervention effect.  
> The **primary causal evaluation** of V9 is the **within-run paired intervention measurement** documented in [`experiments/v9/README.md`](../v9/README.md) and [`docs/V9_POST_BENCHMARK_AUDIT.md`](../../docs/V9_POST_BENCHMARK_AUDIT.md).
> **Secondary / Observational / Non-Causal**:
> In accordance with Section 3 of `experiments/v9/PRE_BENCHMARK.md`, cross-run comparisons between separate stochastic executions are strictly **secondary, observational, and non-causal**.
> Because separate stochastic runs diverge upstream due to LLM sampling variance, capability router selection, and search query variation, cross-run deltas reflect environmental and sampling stochasticity rather than an isolated intervention effect.
> The preregistered primary measurement for V9 is the within-run paired intervention measurement documented in [`experiments/v9/README.md`](../v9/README.md) and [`docs/V9_POST_BENCHMARK_AUDIT.md`](../../docs/V9_POST_BENCHMARK_AUDIT.md).

---

## 2. Benchmark Scores

Official scoring across all 165 GAIA validation tasks:

| Level | Tasks | Completed | Correct Tasks | Accuracy | Request Failures | Completion Failures |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 53 | 53 | 25 | 47.17% | 0 | 0 |
| **Level 2** | 86 | 86 | 23 | 26.74% | 0 | 0 |
| **Level 3** | 26 | 26 | 3 | 11.54% | 0 | 0 |
| **Overall** | **165** | **165** | **51** | **30.91%** | **0** | **0** |

---

## 3. Cross-Run Comparison with Canonical V9 (Observational)

Matching task-by-task against Canonical V9 (`73 / 165 = 44.24%`):

| Comparison Category | Count | Percentage |
| :--- | :---: | :---: |
| **Both Correct** | 43 | 26.06% |
| **Both Wrong** | 84 | 50.91% |
| **Matched V7 Wrong $\rightarrow$ V9 Correct** | 30 | 18.18% |
| **Matched V7 Correct $\rightarrow$ V9 Wrong** | 8 | 4.85% |
| **Total Validation Tasks** | **165** | **100.00%** |

- **Net Correct-Task Difference (V9 - Matched V7)**: $+22$ tasks
- **Net Percentage-Point Difference**: $+13.33$ percentage points

---

## 4. Artifact Integrity & Manifest

All execution records and summary statistics are hashed in [`ARTIFACT_MANIFEST.sha256`](ARTIFACT_MANIFEST.sha256):

| Artifact File | Size (Bytes) | Verification Status |
| :--- | :---: | :---: |
| `predictions_level_1.jsonl` | 2,301,467 | Verified (53/53 records) |
| `predictions_level_2.jsonl` | 3,529,937 | Verified (86/86 records) |
| `predictions_level_3.jsonl` | 1,082,655 | Verified (26/26 records) |
| `detailed_eval_level_1.jsonl` | 580,495 | Verified (53/53 records) |
| `detailed_eval_level_2.jsonl` | 941,447 | Verified (86/86 records) |
| `detailed_eval_level_3.jsonl` | 285,690 | Verified (26/26 records) |
| `summary_level_1.json` | 9,931 | Verified |
| `summary_level_2.json` | 9,545 | Verified |
| `summary_level_3.json` | 8,826 | Verified |

In accordance with `.gitignore`, raw `predictions_*.jsonl` files remain local canonical artifacts, while summary JSON files and the SHA-256 manifest are tracked in version control.

