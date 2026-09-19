# V11 — Post-Benchmark Audit

**Status:** CANONICAL_ATTEMPT_INVALID
**Branch:** `v11-adaptive-evidence-retrieval`
**Scientific Parent:** Frozen V10 (`314d0aecd01a1679a96d85256044c01c8b6c30ce`)
**Preregistration Commit:** `59f6944ff92f94e6ef2122bb98a0079d021d411b`
**Canonical Inference Commit:** `02b368b030e2c86c2e534d6012149f819e8d136a`
**Original Results Commit:** `d1a604669fa976fba0339ee823696759379fcad2`
**Validity Correction Commit:** `cebefd44bf84c5199e7e35c0a013cd16cf234c8b`
**Schema:** 9
**Date:** September 2026

---

## 1. Executive Verdict

This post-benchmark audit independently inspects and classifies the empirical outcomes of the V11 experimental program (Planner-Guided Adaptive Evidence Retrieval) on the full 165-task GAIA 2023 Validation Set.

The experimental campaign comprised two distinct scientific protocols:
1. **Primary Paired Retrieval Ablation (H1):** Executed during Phase A on the 79 follow-up-eligible tasks under shared question, Search 1 evidence, file context, and operational plan. This ablation completed with zero provider failures and demonstrated a positive paired net difference of $\Delta_{\text{followup}} = +15$ (Branch A: 15/79 = 18.99%, Branch B: 30/79 = 37.97%, Improvements: 21, Regressions: 6). **Hypothesis H1 is scientifically VALID and PASSES the preregistered directional criterion.**
2. **Canonical End-to-End Evaluation Attempt (H2):** Executed during Phases C–E across all 165 validation tasks. During this execution, external provider infrastructure suffered widespread collapse across both search services (125/165 Search 1 failures = 75.76%; 80/91 Search 2 failures = 87.91% due to `ForbiddenError` plan limit exhaustion) and model inference in Level 3 (21 planner `provider_api_error` failures; 24 executor `provider_api_error` failures). This collapse resulted in **24 provider-caused unhandled task failures out of 165 tasks (14.55%)**, exceeding the binding preregistered invalidity threshold of >10%.

Under the preregistered governance rules:
- The canonical end-to-end attempt is classified as **`INVALID_CANONICAL_RUN`**.
- The observed end-to-end score of 55 / 165 (33.33%) is classified as **`OBSERVED_INVALID_RUN_SCORE`** (descriptive only).
- Gate H2 status is **`NOT_EVALUABLE_ON_INVALID_CANONICAL_RUN`**. Neither a valid H2 PASS nor a valid H2 FAIL occurred.
- The project baseline remains **`Frozen V10` (84 / 165 = 50.91%)**.
- The promotion decision is **`INVALID_RUN_NO_DECISION`**.

---

## 2. Provenance & Pre-Flight State

The benchmark was executed from the exact locked canonical inference candidate in a clean detached HEAD state:

```text
Scientific Branch:               v11-adaptive-evidence-retrieval
Pre-Benchmark Audit Commit:      733ef84127b2951bb5345ff01f1f42435575895a
Locked Inference Commit:         02b368b030e2c86c2e534d6012149f819e8d136a
Original Results Commit:         d1a604669fa976fba0339ee823696759379fcad2
Validity Correction Commit:      cebefd44bf84c5199e7e35c0a013cd16cf234c8b
Scientific Parent / Baseline:    Frozen V10 (314d0aecd01a1679a96d85256044c01c8b6c30ce)
Parent Reference Accuracy:       84 / 165 (50.91%)
Model Configuration:             gemini-3.5-flash-lite, thinking_level=medium, max_output_tokens=2048
Evaluation Dataset:              GAIA 2023 Validation Set (165 Tasks: 53 L1, 86 L2, 26 L3)
```

Working tree verification confirmed that HEAD was at `cebefd44bf84c5199e7e35c0a013cd16cf234c8b` with a completely clean working tree.

---

## 3. Runtime Lock Verification

An independent diff against the locked canonical inference commit confirmed zero runtime code divergence:

```powershell
git diff 02b368b030e2c86c2e534d6012149f819e8d136a HEAD -- agent prompts tools evaluation tests
```
**Result:** Empty output (zero lines of difference).

All commits after `02b368b` consist strictly of documentation, audit records, and raw/summary benchmark artifacts. No modification was made to runtime agent logic, prompt strings, tool wrappers, evaluation scripts, or smoke tests.

---

## 4. Raw Artifact Integrity & Immutability

The historical raw prediction artifacts and paired raw files recorded in original results commit `d1a604669fa976fba0339ee823696759379fcad2` were compared directly against the current commit `cebefd44bf84c5199e7e35c0a013cd16cf234c8b`:

```powershell
git diff d1a604669fa976fba0339ee823696759379fcad2 cebefd44bf84c5199e7e35c0a013cd16cf234c8b -- `
  experiments/v11/paired_retrieval_raw.jsonl `
  experiments/v11/paired_retrieval_raw.enrollment.jsonl `
  experiments/v11/paired_summary.json `
  experiments/v11/paired_detailed.jsonl `
  experiments/v11/predictions_level_1.jsonl `
  experiments/v11/predictions_level_2.jsonl `
  experiments/v11/predictions_level_3.jsonl `
  experiments/v11/summary_level_1.json `
  experiments/v11/summary_level_2.json `
  experiments/v11/summary_level_3.json `
  experiments/v11/detailed_eval_level_1.jsonl `
  experiments/v11/detailed_eval_level_2.jsonl `
  experiments/v11/detailed_eval_level_3.jsonl
```
**Result:** Empty output (zero differences).

All 13 primary raw, enrollment, detailed, and level summary files remain byte-identical to the original execution commit. Only `overall_summary.json` and `CANONICAL_RUN_MANIFEST.json` were updated in `cebefd4` to reflect the operational invalidity classification and updated manifest hash.

---

## 5. Primary Paired Retrieval Ablation (H1) Audit

The primary paired retrieval experiment evaluated the marginal benefit of one bounded, planner-guided follow-up web search under strictly shared context:
- **Tasks Scanned:** 165 / 165
- **Sidecar Enrollment Ledger:** 165 records (79 eligible, 86 non-eligible)
- **Primary Raw Records:** 79 records (100% verified `followup_eligible == True`)
- **Primary Detailed Records:** 79 records
- **Search 2 Provider Executions:** 79 attempted, 79 successful, 0 provider failures (100% provider success rate during Phase A)

### Paired Outcome Recomputation

| Branch / Metric | Correct Tasks | Accuracy | Empty Candidates | Python Runs |
|---|---|---|---|---|
| **Branch A (Without Follow-Up Search)** | 15 / 79 | 18.99% | 24 | 6 |
| **Branch B (With Follow-Up Search)** | 30 / 79 | 37.97% | 15 | 13 |

### Transition Matrix Breakdown

$$\begin{array}{llr}
\text{RETRIEVAL\_IMPROVEMENT} & \text{(Wrong in A} \to \text{Correct in B)}: & 21 \\
\text{RETRIEVAL\_REGRESSION} & \text{(Correct in A} \to \text{Wrong in B)}: & 6 \\
\text{RETRIEVAL\_STABLE\_CORRECT} & \text{(Correct in both branches)}: & 9 \\
\text{RETRIEVAL\_STABLE\_FAILURE} & \text{(Wrong in both branches)}: & 43 \\
\hline
\textbf{Total Cohort} & & \mathbf{79}
\end{array}$$

$$\Delta_{\text{followup}} = N_{\text{RETRIEVAL\_IMPROVEMENT}} - N_{\text{RETRIEVAL\_REGRESSION}} = 21 - 6 = \mathbf{+15 > 0}$$

### Methodological and Inferential Note
No inferential statistical significance test (e.g., McNemar test, permutation test) was preregistered or performed. Therefore, H1 supports the preregistered directional criterion ($\Delta_{\text{followup}} > 0$) as an intervention-oriented paired estimate under shared plan and context, but does not constitute a separate statistical-significance claim.

---

## 6. Canonical Structural Coverage Audit

Direct line-by-line programmatic parsing of the three canonical prediction records verified:
- **Level 1 (`predictions_level_1.jsonl`):** 53 valid records, 53 unique task IDs
- **Level 2 (`predictions_level_2.jsonl`):** 86 valid records, 86 unique task IDs
- **Level 3 (`predictions_level_3.jsonl`):** 26 valid records, 26 unique task IDs
- **Total Unique Tasks:** 165 / 165 (100.0% structural coverage)

All records confirmed `project_version == "v11"` and `schema_version == 9`. Structural coverage was completely achieved. However, structural completeness does not imply operational validity.

---

## 7. Provider Infrastructure Collapse Audit

During the canonical evaluation run (Phases C–E), external APIs experienced catastrophic degradation:

### 1. Web Search API Collapse (Tavily)
- At Task 31 in Level 1, Tavily API keys encountered usage cap exhaustion:
  `ForbiddenError: This request exceeds your plan's set usage limit. Please upgrade your plan or contact support@tavily.com`
- Key rotation exhausted all 11 backup keys in the active pool.
- **Search 1 Outage:** Across all 165 tasks, 125 first-pass searches failed with `ForbiddenError` (Level 1: 13/53; Level 2: 86/86 = 100%; Level 3: 26/26 = 100%). Overall Search 1 failure rate: **75.76% (125 / 165)**.
- **Search 2 Outage:** Of 91 follow-up searches attempted by the agent, 80 failed due to quota exhaustion (Level 1: 11/22; Level 2: 64/64 = 100%; Level 3: 5/5 = 100%). Overall Search 2 failure rate: **87.91% (80 / 91)**.

### 2. LLM Model API Collapse (Gemini in Level 3)
- In Level 3, external model calls experienced systemic infrastructure dropouts:
  - **Planner Failures:** 21 of 26 tasks suffered `planner_error_type == "provider_api_error"`.
  - **Executor Failures:** 24 of 26 tasks suffered `executor_error_type == "provider_api_error"`.
  - **Completion Collapse:** 24 of 26 Level 3 tasks failed to complete (`completion_success == False`), yielding empty candidate answers.

---

## 8. Preregistered Operational Invalidity Threshold

The binding preregistration defines operational invalidity in `experiments/v11/PRE_BENCHMARK.md` (Section 7):
> *"Widespread provider infrastructure failure or API collapse (>10% unhandled task failures) => INVALID canonical run"*

The minimum indisputable provider-caused unhandled task failure condition is:
$$\text{completion\_success} == \text{False} \land (\text{planner\_error\_type} == \text{"provider\_api\_error"} \lor \text{executor\_error\_type} == \text{"provider\_api\_error"})$$

Recomputation across all 165 canonical records confirms:
$$\text{Provider-Caused Unhandled Task Failures} = 24 \text{ tasks (all in Level 3)}$$
$$\text{Provider Unhandled Failure Rate} = \frac{24}{165} = \mathbf{14.55\%}$$
$$\mathbf{14.55\% > 10.00\% \implies \text{OPERATIONAL INVALIDITY TRIGGERED}}$$

This condition independently invalidates the canonical run.

---

## 9. Canonical Gate H2 Status

The observed end-to-end score across the 165 tasks was:
- **Level 1:** 28 / 53 (52.83%)
- **Level 2:** 26 / 86 (30.23%)
- **Level 3:** 1 / 26 (3.85%)
- **Total Observed:** 55 / 165 (33.33%) [Frozen V10 reference: 84 / 165 = 50.91%, $\Delta = -29$ tasks]

### Scientific Classification
Because operational validity failed due to provider collapse:
- The observed score is designated **`OBSERVED_INVALID_RUN_SCORE`** and retained strictly as descriptive historical provenance.
- Gate H2 status is **`NOT_EVALUABLE_ON_INVALID_CANONICAL_RUN`**.
- It is scientifically incorrect to declare an H2 FAIL or conclude that V11 is inferior to Frozen V10, as the agent operated with 75.76% of its primary search disabled and a complete model provider blackout in Level 3.

---

## 10. Binding Budget Audit

To distinguish infrastructure failure from implementation defect, all resource caps and budget invariants were audited across all 165 prediction records:

| Constraint / Invariant | Preregistered Cap | Observed Maximum | Violations |
|---|---|---|---|
| Primary Web Search Calls | $\le 1$ | 1 | 0 |
| Second Web Search Calls | $\le 1$ | 1 | 0 |
| Total Web Searches | $\le 2$ | 2 | 0 |
| File Processing Calls | $\le 1$ | 1 | 0 |
| Python Tool Executions | $\le 1$ | 1 | 0 |
| Upstream LLM Generation Slots | $== 2$ | 2 (Planner + Executor) | 0 |
| Logical Generation Attempts (Non-Recovery) | $\le 5$ | 5 | 0 |
| Logical Generation Attempts (Recovery) | $\le 6$ | 6 | 0 |
| Search 2 only after Follow-up Eligibility | Boolean invariant | 91 / 91 eligible | 0 |
| Planner Fallback never triggers Search 2 | Boolean invariant | 0 / 24 searches | 0 |
| Duplicate Query skips Search 2 | Boolean invariant | 0 duplicate queries | 0 |

**Result:** Exactly **0 binding budget violations** across all 165 tasks. The implementation adhered strictly to all architectural and tool constraints.

---

## 11. Frozen Downstream Integrity Audit

Downstream safeguards were verified to remain structurally and functionally identical to Frozen V10:
- **Candidate Recovery Agent (`candidate-recovery-v1`):** Engaged exclusively on starved/empty upstream candidates (47 triggered, 44 recovered).
- **Answer Verifier Agent (`answer-verifier-v1`):** Evaluated upstream answers (138 eligible, 138 attempted, 127 KEEP, 9 REVISE, 2 fallback).
- **Self-Evaluation Agent (`self-evaluator-v1`):** Assessed confidence and risk categories across 136 completed outputs.
- **Targeted Repair Agent (`targeted-repair-v1`):** Triggered on SUSPECT outputs (75 triggered, 66 KEEP, 7 REPLACE, 2 fallback).
- **Integrity Verdict:** **PASS** (Frozen V10 pipeline preserved verbatim).

---

## 12. Secondary Diagnostics (H3a–H3f) Audit

Secondary diagnostics derived from the canonical attempt are non-binding and labeled **`DESCRIPTIVE_FROM_INVALID_CANONICAL_ATTEMPT`**:

| Hypothesis / Metric | Observed Value | Directional Benchmark | Preregistered Status |
|---|---|---|---|
| **H3a (EVIDENCE Conditional Error)** | 41 / 47 = 87.23% | $< 88.89\%$ (V10: 32/36) | Descriptive (Direction Met) |
| **H3b (Recovery Trigger Rate)** | 47 / 165 = 28.48% | $< 30.91\%$ (V10: 51/165) | Descriptive (Direction Met) |
| **H3c (Post-Recovery Reachability)** | 138 / 165 = 83.64% | $\ge 95.0\%$ | Descriptive (Direction Unmet; degraded by L3 API collapse) |
| **H3d (Planner Parse Rate)** | 141 / 165 = 85.45% | $\ge 95.0\%$ | Descriptive (Direction Unmet; degraded by L3 API collapse) |
| **H3e (Retrieval Categories)** | 50 Sufficient, 0 Duplicate, 11 S2 Success, 80 S2 Failure, 0 S2 Empty, 24 Fallback (Sum: 165) | Mutually exclusive taxonomy | Complete Descriptive Reporting |
| **H3f (Search Novelty)** | 11 / 91 with $\ge 1$ new URL (12.09%), mean 0.53, median 0.0 | Descriptive novelty | Complete Descriptive Reporting |
| **Python Diagnostic** | 58 planned, 39 executed, 9 success (23.08%) | Descriptive execution | Non-binding diagnostic |

---

## 13. Manifest & SHA-256 Verification

The canonical run manifest (`experiments/v11/CANONICAL_RUN_MANIFEST.json`) lists 14 non-manifest artifacts. An independent verification pass recomputed the SHA-256 hash and byte size of all 14 files:

| Artifact Path | SHA-256 Hash | Size (Bytes) | Verification |
|---|---|---|---|
| `experiments/v11/paired_retrieval_raw.jsonl` | `0af0ca9ea2ca70a1ed48de865cdb42ad86aee4371e6e094d8c15b91e2cec8c9a` | 224,915 | PASS |
| `experiments/v11/paired_retrieval_raw.enrollment.jsonl` | `43282d95910820961c4efab8e595ef7c59e8693e769d0949154cf8c7095818ab` | 422,945 | PASS |
| `experiments/v11/paired_summary.json` | `d94037bec0cf0f1efd0ef53e27a0c08f1bc5bf3737182250af1361f55f001be3` | 1,822 | PASS |
| `experiments/v11/paired_detailed.jsonl` | `64a2c0fef20591b4dab9daf17326c62a7682eb238707ce146245e25c81bda313` | 238,279 | PASS |
| `experiments/v11/predictions_level_1.jsonl` | `ec219629ab28d628179a6991cc46e8e1c864ffe92e874391eb996ed402b38740` | 2,519,626 | PASS |
| `experiments/v11/predictions_level_2.jsonl` | `b7e1e1d124a239017ca0387ced4d5b87f8c0d47ae8a0a730ec4994aeedd2cce8` | 1,852,937 | PASS |
| `experiments/v11/predictions_level_3.jsonl` | `25244d73878573c63e055cb84c6288ff2a5780ae925e5b664b6c2da6d2b3d2ce` | 464,137 | PASS |
| `experiments/v11/summary_level_1.json` | `60b87c3a68bb9a38657ccf33f21047defd74458a5373aeb9b2f330ef52565365` | 13,391 | PASS |
| `experiments/v11/summary_level_2.json` | `58085899d0648718b6d4035b5b3fdbf7f6c1945077f185ec194c17d3b9e8520b` | 13,902 | PASS |
| `experiments/v11/summary_level_3.json` | `0a42cda3e7ab760eb0e9e0fe8fe973dc19528a69936910dfc07cdf66798cc200` | 11,523 | PASS |
| `experiments/v11/detailed_eval_level_1.jsonl` | `805b1926a1877e4f89562a540371d34f6540774087150b376d58e54571d2ffdb` | 703,024 | PASS |
| `experiments/v11/detailed_eval_level_2.jsonl` | `ea5a5c9e24bb2befc062b7283fe4fa5030afe6ebb0ea272fa8bf6b47a7d9ea78` | 723,816 | PASS |
| `experiments/v11/detailed_eval_level_3.jsonl` | `6a77a0a45e96f8b5aeadf91fc3de25e59c6b16b16a74dad44e8c5f81965d405a` | 207,771 | PASS |
| `experiments/v11/overall_summary.json` | `346fcf8e0e632590f6f48f54bf5fae11f123af997c87a3e23ce62c581a3a2926` | 5,870 | PASS |

**Result:** Exactly **14 / 14 verified** with **0 mismatches**.

---

## 14. No-Rerun & No-Selective-Retry Confirmation

Git history, timestamp audit, and file commit logs independently confirm:
1. No GAIA prediction JSONL was rerun or rewritten after initial generation.
2. No paired raw file was regenerated or modified.
3. No level evaluation summary or detailed evaluation file was rescored.
4. No score-driven cherry-picking or selective task retrying occurred.
5. All 165 tasks represent the raw, unedited execution of the system under live environment conditions.

---

## 15. Baseline Status

Because the canonical attempt is operationally invalid:
- **V11 CANNOT replace Frozen V10 as the scientific baseline.**
- The project baseline remains firmly locked at:
  $$\mathbf{\text{Current Scientific Baseline: Frozen V10 (84 / 165 = 50.91\%)}}$$
- V11 is neither a promoted baseline nor a failed baseline; its canonical evaluation remains incomplete due to external infrastructure collapse.

---

## 16. Scientific Limitations

1. **Provider Sensitivity:** Adaptive evidence retrieval depends fundamentally on reliable external search and model providers. Rate limiting and quota exhaustion across 11 Tavily keys severely crippled downstream reasoning in Level 2 and Level 3.
2. **Paired vs. End-to-End Separation:** While the paired mechanism demonstrated clear factual improvement on follow-up-eligible tasks when search was functional, end-to-end performance under sustained search outages cannot be evaluated from this run.

---

## 17. Rerun Governance Boundary

This audit strictly evaluates the completed execution and does **NOT** authorize or initiate a benchmark rerun.

Whether to conduct a full, infrastructure-controlled canonical re-execution is an independent governance decision that must satisfy:
1. Complete restoration and quota verification of all search and model provider keys.
2. Clean start from fresh artifacts (no reuse of degraded prediction files).
3. Full evaluation of all 165 tasks (no selective retrying of Level 2 or Level 3).
4. Zero code or prompt modifications relative to locked inference commit `02b368b`.
5. Explicit preregistration as a distinct canonical attempt.

---

## 18. Final Verdict

```text
================================================================================
V11 POST-BENCHMARK AUDIT VERDICT

PRIMARY PAIRED H1:
VALID / PASS
Delta_followup = +15

CANONICAL END-TO-END ATTEMPT:
INVALID_CANONICAL_RUN

INVALIDITY REASON:
WIDESPREAD_PROVIDER_INFRASTRUCTURE_COLLAPSE

PROVIDER-CAUSED UNHANDLED TASK FAILURES:
24 / 165 = 14.55%

PREREGISTERED INVALIDITY THRESHOLD:
>10%

CANONICAL H2:
NOT_EVALUABLE_ON_INVALID_CANONICAL_RUN

OBSERVED INVALID-RUN SCORE:
55 / 165 = 33.33%
DESCRIPTIVE ONLY

PROMOTION DECISION:
INVALID_RUN_NO_DECISION

SCIENTIFIC BASELINE:
FROZEN V10
84 / 165 = 50.91%

RUNTIME LOCK:
02b368b030e2c86c2e534d6012149f819e8d136a
================================================================================
```

