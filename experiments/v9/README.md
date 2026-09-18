# V9 — Upstream Candidate Recovery

**Status**: `PREREGISTERED_PRE_IMPLEMENTATION`  
**Branch**: `v9-upstream-candidate-recovery`  
**Scientific Parent**: Frozen V7 (`v7-targeted-repair`)  
**Architecture**: Design A — Upstream Worker Candidate Recovery  
**Status**: `CANONICAL_BENCHMARK_COMPLETE`
**Branch**: `v9-upstream-candidate-recovery`
**Canonical Inference Commit**: `6369f427c4479073a6ca06531bdfd43e47cd613f`
**Scientific Parent**: Frozen V7 (`v7-targeted-repair`)
**Architecture**: Design A — Upstream Worker Candidate Recovery
**Model**: `gemini-3.5-flash-lite` (inherited from Frozen V7)
**Date**: September 2026  
**Evaluation Scope**: Full GAIA 2023 Validation Set (165 Tasks: 53 Level 1, 86 Level 2, 26 Level 3)
**Date**: September 2026

See [`docs/V9_POST_BENCHMARK_AUDIT.md`](../../docs/V9_POST_BENCHMARK_AUDIT.md) for the comprehensive scientific post-benchmark audit, within-run paired intervention analysis, downstream safeguard interactions, failure taxonomy breakdown, and promotion recommendation. Deterministic SHA-256 hashes are recorded in [`ARTIFACT_MANIFEST.sha256`](ARTIFACT_MANIFEST.sha256).

---

## Overview

Version 9 (V9) investigates **Upstream Candidate Recovery** to overcome the primary bottleneck identified in V7 and V8: **candidate starvation**.

In the GAIA benchmark, nearly half (~49.7%) of all tasks fail upstream without emitting any candidate answer (`""`), leaving them structurally unreachable by downstream verification (V5), self-evaluation (V6), or targeted repair (V7).

V9 introduces at most **one bounded, text-only recovery generation** for explicitly eligible upstream failures, while strictly preserving 100.0% of candidate answers at the recovery boundary for tasks that already produce a candidate.

---

## Canonical Headline Results (GAIA 2023 Validation Set, 165 Tasks)

### 1. Canonical V9 Benchmark Scores

| Level | Tasks | Completed | Completion Rate | Correct Tasks | Accuracy | Request Failures |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 53 | 52 | 98.11% | 33 | 62.26% | 0 |
| **Level 2** | 86 | 85 | 98.84% | 34 | 39.53% | 0 |
| **Level 3** | 26 | 26 | 100.00% | 6 | 23.08% | 0 |
| **Overall** | **165** | **163** | **98.79%** | **73** | **44.24%** | **0** |

### 2. Candidate Reachability Funnel

- **Pre-Recovery Non-Empty Candidates**: 75 / 165 (45.45%)
- **Post-Recovery Non-Empty Candidates**: 159 / 165 (96.36%)
- **Net Reachability Gain**: **+84 tasks (+50.91 percentage points)**
- **Recovery Triggered**: 90 / 165 (54.55%)
- **Recovery Attempted**: 90 / 90 (100.00%)
- **Recovery Succeeded**: 84 / 90 (93.33%)
- **Recovered Candidate Accuracy (Official Scorer)**: 26 / 84 (30.95%)

### 3. Primary Within-Run Paired Intervention Measurement

Comparing the constructed Frozen V7 baseline state against the final V9 answer within the exact same runtime task executions:

| Metric | Level 1 (N=53) | Level 2 (N=86) | Level 3 (N=26) | Overall (N=165) |
| :--- | :---: | :---: | :---: | :---: |
| **Pre-Intervention Baseline Correct** | 22 (41.51%) | 20 (23.26%) | 3 (11.54%) | **45 (27.27%)** |
| **Post-Intervention V9 Final Correct** | 33 (62.26%) | 34 (39.53%) | 6 (23.08%) | **73 (44.24%)** |
| **Improvements ($0 \rightarrow 1$)** | 11 | 14 | 3 | **28** |
| **Regressions ($1 \rightarrow 0$)** | 0 | 0 | 0 | **0** |
| **Stable Correct ($1 \rightarrow 1$)** | 22 | 20 | 3 | **45** |
| **Stable Failure ($0 \rightarrow 0$)** | 20 | 52 | 20 | **92** |
| **Within-Run Net Delta** | **+11 (+20.75 pp)** | **+14 (+16.28 pp)** | **+3 (+11.54 pp)** | **+28 tasks (+16.97 pp)** |

### 4. Downstream Safeguard Transition Matrix (Recovered Candidates, N=84)

| Transition Metric | Count | Percentage | Architectural Interpretation |
| :--- | :---: | :---: | :--- |
| **`RECOVERY_CORRECT_FINAL_CORRECT`** | 25 | 29.76% | Downstream safeguards preserved correct recovered candidate. |
| **`RECOVERY_CORRECT_FINAL_WRONG`** | 1 | 1.19% | Downstream safeguard altered a correct candidate (L2 `4d51c4bf...`). |
| **`RECOVERY_WRONG_FINAL_CORRECT`** | 3 | 3.57% | Downstream safeguards (V5/V7) rescued an imperfect recovered candidate. |
| **`RECOVERY_WRONG_FINAL_WRONG`** | 55 | 65.48% | Recovered candidate remained incorrect through downstream pipeline. |
| **Total Evaluated Recoveries** | **84** | **100.00%** | Full closure of recovered cohort. |

### 5. Core Safety & Resource Invariants

- **Non-Triggered Recovery-Boundary Preservation Rate**: **100.00% (75 / 75 tasks)** — strictly zero non-triggered answer mutations.
- **Generation Cap Adherence**: Maximum logical generations observed = 6 (budget $\le 6$). Zero violations. Non-triggered tasks $\le 5$.
- **Zero Added Tools**: Zero search calls added, zero Python executions added, zero file operations added during candidate recovery.
- **Operational Validity**: Zero provider-collapse events; all 165 tasks executed to completion.
- **Operational Validity**: Zero provider-collapse events. All 165 official task IDs were structurally executed and recorded. Pipeline completion was 163 / 165 (98.79%).

### 6. Contemporaneous Matched Frozen V7 Control (Secondary Observational)

- **Matched V7 Overall Score**: **51 / 165 (30.91%)** (L1: 25/53, L2: 23/86, L3: 3/26)
- **V9 vs Matched V7 Observational Delta**: **+22 tasks (+13.33 percentage points)**
- *Methodological note*: Cross-run difference is observational and non-causal due to run-to-run sampling variance; the within-run paired measurement (+28 tasks, +16.97 pp) is the primary causal result.
- *Methodological note*: The preregistered primary measurement for V9 is the within-run paired intervention measurement (+28 tasks, +16.97 pp). The matched Frozen V7 comparison is secondary, observational, and non-causal because it is based on a separate stochastic execution. The within-run paired intervention measurement avoids the separate-run sampling divergence that affects the matched V7 comparison and is the preregistered primary decision metric. It should not be described as a perfect causal estimate or as eliminating all sources of uncertainty.

---

## Directory Contents

| File | Purpose |
| :--- | :--- |
| [`DESIGN.md`](./DESIGN.md) | Comprehensive technical design: architecture, state machine, eligibility function, mutually exclusive failure taxonomy, recovery prompt contract, schema, budgets, telemetry, and safety invariants. |
| [`PRE_BENCHMARK.md`](./PRE_BENCHMARK.md) | Binding pre-benchmark preregistration: hypotheses, primary/secondary metrics, within-run paired intervention design, 18 deterministic smoke test scenarios, and scientific decision rule. |
| [`ARTIFACT_MANIFEST.sha256`](./ARTIFACT_MANIFEST.sha256) | Deterministic SHA-256 digests for all predictions, detailed evals, and summary JSON files. |
| `summary_level_1.json` | Official execution metrics and token telemetry for Level 1. |
| `summary_level_2.json` | Official execution metrics and token telemetry for Level 2. |
| `summary_level_3.json` | Official execution metrics and token telemetry for Level 3. |

---

## Scientific Governance & Rules of Engagement

1. **Preregistration Precedes Implementation**: No runtime code is altered until design and preregistration are fully reviewed and committed.
2. **Strict Invariant**: Non-Triggered Recovery-Boundary Preservation Rate must be strictly $100.0\%$.
3. **No Added Tools**: Candidate recovery operates strictly on already-gathered runtime evidence (zero new web searches, zero new Python executions, zero file rereads).
4. **Transport vs. Scientific Separation**: Multi-key credential failover in `agent/llm.py` and `tools/web_search.py` is operational transport infrastructure, completely separated from the V9 scientific generation budget ($\le 1$ recovery generation).
5. **No Premature Benchmarking**: No GAIA benchmark runs may be launched until runtime implementation and unit/smoke tests are fully verified.
