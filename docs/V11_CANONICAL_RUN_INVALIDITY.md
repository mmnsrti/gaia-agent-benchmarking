# V11 Canonical Run Operational Invalidity Incident Report

**Document Status:** OFFICIAL RESULTS INTEGRITY RECORD
**Investigation Scope:** V11 Canonical Benchmark Execution (165 GAIA Validation Tasks)
**Scientific Parent:** Frozen V10 (`314d0aecd01a1679a96d85256044c01c8b6c30ce`)
**Canonical Inference Commit:** `02b368b030e2c86c2e534d6012149f819e8d136a`
**Canonical Results Commit:** `d1a604669fa976fba0339ee823696759379fcad2`
**Preregistration Commit:** `59f6944ff92f94e6ef2122bb98a0079d021d411b`
**Pre-Benchmark Audit HEAD:** `733ef84127b2951bb5345ff01f1f42435575895a`
**Date:** September 2026

---

## 1. Executive Summary & Scientific Verdict

During the canonical execution of the V11 benchmark on the full 165-task GAIA validation split, external API provider infrastructure collapsed across both web search and LLM model services, resulting in **24 provider-caused unhandled task failures out of 165 tasks (14.55%)**, alongside severe upstream retrieval degradation (**125 / 165 Search 1 failures = 75.76%**; **80 / 91 Search 2 failures = 87.91%**).

Under the binding preregistration rule established prior to implementation and audit:
> *"Widespread provider infrastructure failure or API collapse (>10% unhandled task failures) => INVALID canonical run"*
> (`experiments/v11/PRE_BENCHMARK.md`, Section 7; `docs/V11_PRE_BENCHMARK_AUDIT.md`, Section 21)

This attempt satisfies the preregistered condition for operational invalidity.

```text
================================================================================
CANONICAL RUN VERDICT:    INVALID_CANONICAL_RUN
PROMOTION DECISION:       INVALID_RUN_NO_DECISION
CANONICAL H2 STATUS:      NOT_EVALUABLE_ON_INVALID_CANONICAL_RUN
OBSERVED CANONICAL SCORE: 55 / 165 (33.33%) — OBSERVED_INVALID_RUN_SCORE (DESCRIPTIVE ONLY)
PRIMARY PAIRED H1:        VALID / PASS (Delta_followup = +15 > 0)
================================================================================
```

### Governance Principles Enforced
1. **No Rerun During This Correction:** No task was rerun, retried, or altered based on results.
2. **No Raw Data Modification:** All raw prediction JSONL records, paired raw ledgers, and level evaluation files remain immutable historical records.
3. **No Selective Retries:** No cherry-picked retries or level-specific restarts occurred.
4. **Separate Scientific Layers:** The primary paired retrieval ablation executed prior to provider collapse remains independently valid and positive; the canonical end-to-end evaluation is declared operationally invalid.

---

## 2. Preregistered Operational Invalidity Rule

In `experiments/v11/PRE_BENCHMARK.md` (Section 7, "Operational Validity & Neutral Outcome Definitions") and `docs/V11_PRE_BENCHMARK_AUDIT.md` (Section 21), the binding rule states:

```text
A benchmark run is declared INVALID if any of the following occur:
- Incomplete validation split (< 165 tasks evaluated).
- Ground-truth reference leakage or scorer execution at agent runtime.
- Any violation of search or generation budget invariants.
- Runtime or prompt modifications introduced after pre-benchmark audit lock.
- Widespread provider infrastructure failure or API collapse (> 10% unhandled task failures).
```

The protocol also distinguishes isolated search failures from systemic collapse:
> *"An individual Search 2 failure (e.g., HTTP 429 or timeout) must fall back cleanly to Search 1 evidence and complete the task. Isolated search failures are recorded in telemetry and do not invalidate the run."*

Here, the threshold of **> 10% unhandled task failures** caused by provider collapse was significantly breached (**14.55%**), accompanied by an unprecedented 75.76% failure rate in primary search and 87.91% in follow-up search due to API plan usage limits (`ForbiddenError`).

---

## 3. Independent Raw Recomputation of Provider Collapse

Direct analysis of the raw, untouched prediction files (`predictions_level_1.jsonl`, `predictions_level_2.jsonl`, `predictions_level_3.jsonl`) confirms the exact nature and progression of the infrastructure failure:

### Per-Level Telemetry Breakdown

| Metric | Level 1 (53 Tasks) | Level 2 (86 Tasks) | Level 3 (26 Tasks) | Overall (165 Tasks) |
|---|---|---|---|---|
| **Total Tasks Evaluated** | 53 | 86 | 26 | 165 |
| **Completion Failures** | 2 | 1 | 24 | 27 |
| **Search 1 Successes** | 40 | 0 | 0 | 40 (24.24%) |
| **Search 1 Failures (ForbiddenError)** | 13 | 86 | 26 | 125 (75.76%) |
| **Search 2 Attempts** | 22 | 64 | 5 | 91 |
| **Search 2 Successes** | 11 | 0 | 0 | 11 (12.09%) |
| **Search 2 Failures (ForbiddenError)** | 11 | 64 | 5 | 80 (87.91%) |
| **Planner `provider_api_error`** | 0 | 0 | 21 | 21 (12.73%) |
| **Executor `provider_api_error`** | 0 | 0 | 24 | 24 (14.55%) |
| **Provider-Caused Completion Failures** | 0 | 0 | 24 | 24 (14.55%) |

### Chronological Failure Progression
1. **Level 1 (Tasks 1–53):** Search quota was healthy for the first 40 tasks. At Task 31, Tavily API keys hit quota limits (`ForbiddenError: This request exceeds your plan's set usage limit`). Key rotation exhausted all 11 keys. Tasks 41–53 operated without search results.
2. **Level 2 (Tasks 54–139):** All 86 tasks experienced Search 1 failures (0% search success). 64 follow-up searches were attempted; all 64 failed due to search quota exhaustion. Agent fallback logic allowed tasks to complete degraded reasoning, yielding 26 correct answers.
3. **Level 3 (Tasks 140–165):** In addition to 100% search failure, Gemini API provider errors escalated severely (`provider_api_error`), causing 21 planner failures and 24 executor failures. 24 of the 26 tasks failed to complete, yielding a level accuracy of 3.85% (1/26).

---

## 4. Operational Invalidity Threshold Calculation

The minimum indisputable set of provider-caused unhandled task failures is defined strictly as:
$$\text{completion\_success} == \text{False} \land (\text{planner\_error\_type} == \text{"provider\_api\_error"} \lor \text{executor\_error\_type} == \text{"provider\_api\_error"})$$

Across all 165 canonical records:
$$\text{Provider-Caused Unhandled Task Failures} = 24$$
$$\text{Provider Unhandled Failure Rate} = \frac{24}{165} = 14.5455\% \approx 14.55\%$$

$$\text{Preregistered Threshold} = 10.00\%$$
$$\mathbf{14.55\% > 10.00\% \implies \text{OPERATIONAL INVALIDITY TRIGGERED}}$$

This condition independently invalidates the canonical run under the preregistered protocol.

---

## 5. Status of Canonical Gate H2

The observed canonical accuracy across the 165 tasks was:
- **Level 1:** 28 / 53 (52.83%)
- **Level 2:** 26 / 86 (30.23%)
- **Level 3:** 1 / 26 (3.85%)
- **Overall Observed:** 55 / 165 (33.33%)

Under scientific rigor:
- Because the benchmark run is operationally invalid due to provider collapse, this observed score is classified as **`OBSERVED_INVALID_RUN_SCORE`** and retained strictly for historical provenance and descriptive analysis.
- The status of Gate H2 is formally designated as:
  $$\mathbf{\text{Canonical } H_2 \text{ Status: } \text{NOT\_EVALUABLE\_ON\_INVALID\_CANONICAL\_RUN}}$$
- Neither an H2 PASS nor a valid scientific H2 FAIL is recorded for this attempt.

---

## 6. Status of Primary Paired Retrieval Ablation (H1)

The primary paired retrieval ablation was executed during **Phase A**, prior to the severe model provider failures:
- **Eligible Cohort ($N$):** 79 / 165 tasks
- **Search 2 Provider Success:** 79 / 79 (100.0%)
- **Branch A (without Search 2):** 15 / 79 correct (18.99%)
- **Branch B (with Search 2):** 30 / 79 correct (37.97%)
- **Transition Breakdown:**
  - `RETRIEVAL_IMPROVEMENT`: 21
  - `RETRIEVAL_REGRESSION`: 6
  - `RETRIEVAL_STABLE_CORRECT`: 9
  - `RETRIEVAL_STABLE_FAILURE`: 43
- **Primary Metric:**
  $$\Delta_{\text{followup}} = 21 - 6 = \mathbf{+15 > 0}$$

The paired experiment operates under within-task shared-context controls and did not suffer provider collapse during its execution (0 provider failures across all 79 Search 2 executions).

Therefore, **Hypothesis $H_1$ is scientifically VALID and PASSED**. The paired retrieval mechanism itself demonstrated a statistically decisive net positive effect (+18.98 percentage points, +15 tasks) on the follow-up-eligible cohort.

---

## 7. Status of Secondary Diagnostics (H3a–H3f)

Because the canonical benchmark suffered widespread provider collapse, the observed secondary diagnostics from the canonical run are designated as **`DESCRIPTIVE_FROM_INVALID_CANONICAL_ATTEMPT`**:
- **$H_{3a}$ (EVIDENCE Conditional Error):** 41 / 47 = 87.23% (Frozen V10: 32 / 36 = 88.89%) [Descriptive]
- **$H_{3b}$ (Recovery Trigger Rate):** 47 / 165 = 28.48% (Frozen V10: 51 / 165 = 30.91%) [Descriptive]
- **$H_{3c}$ (Post-Recovery Reachability):** 138 / 165 = 83.64% (Target: $\ge 95.0\%$, impacted by Level 3 model provider dropouts) [Descriptive]
- **$H_{3d}$ (Planner Parse Rate):** 141 / 165 = 85.45% (Target: $\ge 95.0\%$, impacted by Level 3 model provider dropouts) [Descriptive]
- **$H_{3e}$ (Retrieval Categories):** 50 Sufficient, 0 Duplicate, 11 Search 2 Success, 80 Search 2 Provider Failure, 0 Search 2 Empty, 24 Planner Fallback (Sum: 165) [Descriptive]
- **$H_{3f}$ (Search Novelty):** 11 / 91 with $\ge 1$ new URL (12.09%), mean 0.53, median 0.0 [Descriptive]

---

## 8. Integrity Statement & Next Steps

This document records the exact findings of the independent post-execution integrity audit:
1. **No benchmark tasks were rerun.**
2. **No prediction records or scores were modified.**
3. **No cherry-picking or post-hoc threshold adjustment occurred.**
4. **The governance classification of the canonical attempt was corrected from a neutral outcome to an invalid run in strict adherence to the preregistered rule.**
5. **Any future canonical re-execution must be evaluated as a formal, separate governance decision and executed under fully restored provider infrastructure.**
