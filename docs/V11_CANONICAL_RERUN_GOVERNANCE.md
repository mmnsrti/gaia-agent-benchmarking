# V11 — Canonical Rerun Governance

**Status:** PREREGISTERED_ATTEMPT_2_NOT_EXECUTED
**Document Version:** 1.0
**Repository:** `mmnsrti/gaia-agent-benchmarking`
**Branch:** `v11-adaptive-evidence-retrieval`
**Locked Canonical Inference Commit:** `02b368b030e2c86c2e534d6012149f819e8d136a`
**Scientific Parent:** Frozen V10 (`314d0aecd01a1679a96d85256044c01c8b6c30ce`, 84 / 165 = 50.91%)
**Preregistration Methodology Commit:** `59f6944ff92f94e6ef2122bb98a0079d021d411b`
**Original Canonical Results Commit:** `d1a604669fa976fba0339ee823696759379fcad2`
**Operational Validity Correction Commit:** `cebefd44bf84c5199e7e35c0a013cd16cf234c8b`
**Post-Benchmark Audit Commit:** `8f3febf12e8d60cc2cb38656342f99c92776d797`
**Post-Audit Formatting Commit:** `222c871fc5a1c7a0d10e4450c8f53368d297fa42`
**Date:** September 2026

---

## 1. Motivation

V11 introduces Planner-Guided Adaptive Evidence Retrieval, enabling the structured planner to request at most one bounded follow-up web search when it determines that first-pass retrieval is insufficient to execute its plan. During the initial canonical benchmark execution on the full 165-task GAIA validation suite (Canonical Attempt #1), external API infrastructure collapsed across both Tavily search and Gemini model endpoints.

This infrastructure failure resulted in 24 provider-caused unhandled task failures out of 165 tasks (14.55%), directly violating the preregistered operational invalidity threshold (>10% unhandled task failures). Consequently, Attempt #1 was formally classified as `INVALID_CANONICAL_RUN`.

This governance document establishes the formal, binding preregistration protocol for a single full re-execution: **V11 Canonical Attempt #2**. The objective of Attempt #2 is strictly to resolve the canonical end-to-end performance gate ($H_2$) under stable provider infrastructure, while maintaining absolute code and prompt immutability.

---

## 2. Attempt #1 Invalidity

The operational invalidity of Attempt #1 was established through independent raw recomputation of all 165 task prediction records (`predictions_level_1.jsonl`, `predictions_level_2.jsonl`, `predictions_level_3.jsonl`):

1. **Fatal Provider Completion Failures:**
   $$\text{completion\_success} == \text{False} \land (\text{planner\_error\_type} == \text{"provider\_api\_error"} \lor \text{executor\_error\_type} == \text{"provider\_api\_error"})$$
   Exactly 24 tasks met this condition (all located in Level 3).
   $$\text{Provider Unhandled Failure Rate} = \frac{24}{165} = 14.55\% > 10.00\% \implies \text{OPERATIONAL INVALIDITY TRIGGERED}$$

2. **Systemic Web Search Quota Collapse:**
   - Search 1 failures due to Tavily account plan limits (`ForbiddenError: This request exceeds your plan's set usage limit`): 125 / 165 (75.76%).
   - Search 2 failures due to Tavily plan limits: 80 / 91 (87.91%).
   - Across Levels 2 and 3, Search 1 success was exactly 0 / 112 (0.0%).

3. **Level 3 Infrastructure Collapse:**
   - 21 planner provider API errors and 24 executor provider API errors out of 26 tasks.
   - 24 / 26 tasks failed completion, depressing Level 3 accuracy to 1 / 26 (3.85%).

4. **Status of $H_2$ and Observed Score:**
   - $H_2$ status is `NOT_EVALUABLE_ON_INVALID_CANONICAL_RUN`.
   - The observed score of 55 / 165 (33.33%) is classified strictly as `OBSERVED_INVALID_RUN_SCORE` (descriptive only).
   - Attempt #1 was an operationally invalid run, **not** a valid scientific refutation of $H_2$. Therefore, $H_2$ remains completely unresolved.

---

## 3. Preserved H1 Result

The rerun governance explicitly decouples the primary paired retrieval ablation ($H_1$) from the canonical end-to-end evaluation ($H_2$).

The Primary Paired Retrieval Ablation ($H_1$) executed prior to the infrastructure collapse and satisfied all preregistered criteria:
- **Eligible Cohort:** $N = 79$ tasks meeting all 5 follow-up eligibility criteria.
- **Provider Stability:** 79 / 79 (100.0%) successful Search 2 executions on Branch B.
- **Branch A (1-Search Baseline):** 15 / 79 correct (18.99%).
- **Branch B (Adaptive Retrieval):** 30 / 79 correct (37.97%).
- **Transition Matrix:**
  - $N_{\text{RETRIEVAL\_IMPROVEMENT}} = 21$
  - $N_{\text{RETRIEVAL\_REGRESSION}} = 6$
  - $N_{\text{STABLE\_CORRECT}} = 9$
  - $N_{\text{STABLE\_FAILURE}} = 43$
- **Net Paired Difference:**
  $$\Delta_{\text{followup}} = 21 - 6 = +15 > 0$$
- **Final Status:** **`VALID / PASS`**.

### Invariant: H1 Will NOT Be Rerun
The primary paired experiment is permanently closed and validated. Attempt #2 is authorized **solely for the canonical end-to-end evaluation ($H_2$)**. Rerunning, re-sampling, or replacing the paired $H_1$ experiment is strictly prohibited.

---

## 4. Why One Full Rerun Is Scientifically Permitted

Attempt #2 is authorized under standard scientific benchmarking methodology to replace a demonstrably invalid measurement:

> **Core Governance Principle:**
> Attempt #2 is authorized because Attempt #1 was declared operationally invalid under an objective threshold fixed in the preregistration protocol before results were observed.
>
> The rerun is **not** authorized because the observed score was low.
>
> The observed 55 / 165 score is not a valid $H_2$ measurement and must not motivate implementation changes before Attempt #2.

A benchmark suite is an empirical measurement instrument. When the measurement apparatus fails externally (14.55% provider-caused unhandled task aborts exceeding the 10% tolerance), the resulting reading is void. Repeating the measurement under certified apparatus conditions, using the exact frozen code and identical evaluation suite, is scientifically sound and methodologically required to resolve the research question.

---

## 5. Locked Runtime

All executions for Attempt #2 must run from the detached canonical inference commit:

```text
02b368b030e2c86c2e534d6012149f819e8d136a
```

No code, prompt, tool, or configuration commit may be introduced. Documentation, audit, and governance commits do not alter the locked runtime state.

### Execution Parameters
- **Model:** `gemini-3.5-flash-lite`
- **Thinking Level:** `medium`
- **Max Output Tokens:** 2048
- **Temperature:** `null` (provider default)
- **Primary Search (Search 1):** Tavily basic search, `max_results=5`
- **Adaptive Follow-Up Search (Search 2):** Tavily basic search, `max_results=5`
- **Dataset:** GAIA 2023 Validation Set (165 tasks)
- **Schema Version:** 9

---

## 6. Provider Health Gate

Attempt #2 cannot begin until a separate, comprehensive provider-health preflight passes. The health check must be executed and audited **BEFORE any GAIA task is deployed**.

### Health Check Restrictions
- **Zero GAIA Leakage:** Probes must use harmless, synthetic questions (e.g., public facts, synthetic math, or generic entity lookup). GAIA questions, entities, or hints are strictly forbidden.
- **Scientific Immutability:** The health check must verify infrastructure health without altering scientific configurations.
  - **Forbidden:** Changing models, changing search providers, modifying `max_results`, altering thinking levels, changing prompts, injecting retries, adding search provider fallbacks, or modifying key-rotation logic.
  - **Permitted:** Replenishing account credits, adding or replacing valid API keys in environment variables, and establishing network connectivity.

### Tavily Search Health Requirements
Deterministic non-GAIA probes must establish:
1. Primary Tavily search endpoint is callable without error.
2. Zero `ForbiddenError` or usage plan limit errors.
3. Usable structured search snippets are returned.
4. **Capacity Verification:** V11's worst-case search demand across 165 tasks is up to 330 logical Tavily calls (165 Search 1 + up to 165 Search 2). Available API key capacity must be reasonably established for the complete run. Attempt #2 must **not** begin based on a single probe while account quota remains near exhaustion.

### Gemini Model Health Requirements
Deterministic non-GAIA probes must establish:
1. `gemini-3.5-flash-lite` responds cleanly.
2. Planner-like generation succeeds with valid formatted output.
3. Executor-like generation succeeds with valid final candidate output.
4. Zero `provider_api_error`, zero `RESOURCE_EXHAUSTED`, and zero quota exhaustion.
5. Key capacity and rate limits are sufficient for the full expected generation budget across 165 tasks.

---

## 7. Attempt #2 Artifact Isolation

All artifacts produced by Attempt #2 must be written to a dedicated, isolated directory:

```text
experiments/v11/canonical_attempt_2/
```

Attempt #2 artifacts must never be written into or overwrite Attempt #1 paths.

### Expected Artifact Paths
- **Runtime Prediction Artifacts:**
  - `experiments/v11/canonical_attempt_2/predictions_level_1.jsonl`
  - `experiments/v11/canonical_attempt_2/predictions_level_2.jsonl`
  - `experiments/v11/canonical_attempt_2/predictions_level_3.jsonl`
- **Post-Hoc Evaluation & Summary Artifacts:**
  - `experiments/v11/canonical_attempt_2/summary_level_1.json`
  - `experiments/v11/canonical_attempt_2/summary_level_2.json`
  - `experiments/v11/canonical_attempt_2/summary_level_3.json`
  - `experiments/v11/canonical_attempt_2/detailed_eval_level_1.jsonl`
  - `experiments/v11/canonical_attempt_2/detailed_eval_level_2.jsonl`
  - `experiments/v11/canonical_attempt_2/detailed_eval_level_3.jsonl`
  - `experiments/v11/canonical_attempt_2/overall_summary.json`
  - `experiments/v11/canonical_attempt_2/CANONICAL_RUN_MANIFEST.json`

---

## 8. Complete-Rerun Requirement

Attempt #2 must be a full, complete, fresh end-to-end execution across all 165 GAIA validation tasks:
- **Level 1:** Exactly 53 tasks
- **Level 2:** Exactly 86 tasks
- **Level 3:** Exactly 26 tasks
- **Total:** Exactly 165 tasks

### Strict Prohibitions
- **FORBIDDEN:** Rerunning only Level 2.
- **FORBIDDEN:** Rerunning only Level 3.
- **FORBIDDEN:** Rerunning only provider-failed tasks.
- **FORBIDDEN:** Reusing Level 1 predictions from Attempt #1.
- **FORBIDDEN:** Reusing successful task predictions from Attempt #1.

---

## 9. Infrastructure Monitoring

To avoid the observability gap experienced during Attempt #1, external monitoring must be performed between level executions without altering agent runtime logic.

### Telemetry Inspection Timing
Between levels (after Level 1 finishes runtime and before Level 2 starts; after Level 2 finishes runtime and before Level 3 starts), external scripts or auditors may inspect operational telemetry fields only.

### Allowed Telemetry Fields
- `request_success`
- `completion_success`
- `search_success`
- `search_error_type`
- `planner_error_type`
- `executor_error_type`
- `second_search_error_type`

### Strictly Forbidden Telemetry / Inspection
- Inspecting task correctness or accuracy.
- Loading or comparing ground-truth reference answers.
- Running the official GAIA scoring module before all 165 runtime predictions are finalized.
- Inspecting per-task correctness to decide whether to proceed or abort.

---

## 10. Abort / Resume Rules

### Infrastructure Abort Rule
If inter-level telemetry inspection reveals systemic provider collapse:
- Provider-caused unhandled task failures exceeding the preregistered >10% threshold in the completed level, or
- Sustained, unrecoverable provider collapse (`ForbiddenError`, `provider_api_error`, or `RESOURCE_EXHAUSTED` across consecutive tasks),

the execution must be **aborted immediately** before consuming additional tasks. An aborted attempt must be recorded as `INVALID_ATTEMPT_2` and preserved permanently. Aborted runs must not be selectively patched or scored.

### Infrastructure Interruption / Resume Policy
If execution is interrupted by a transient infrastructure event (e.g., local process termination, power disruption, or transient network blip) **BEFORE any scoring or evaluation has taken place**, execution may be resumed on the same Attempt #2 artifact file (omitting `--no-resume`).

Resume is authorized **strictly on infrastructure grounds**, never on correctness grounds. Once any evaluation or scoring has commenced, no further runtime generation is permitted.

---

## 11. Ground-Truth Firewall

To ensure zero ground-truth leakage and maintain rigorous double-blind evaluation:
1. All runtime executions must specify the custom output path via `--output`.
2. All runtime executions must be run with `--no-eval`.
3. Commands must be equivalent to:
   ```powershell
   python -m evaluation.run_level `
     --version v11 `
     --level 1 `
     --output experiments/v11/canonical_attempt_2/predictions_level_1.jsonl `
     --no-resume `
     --no-eval `
     --delay 5.0
   ```
4. Level 1 predictions must **not** be scored before Levels 2 and 3 complete runtime execution.
5. Official scoring must be executed post-hoc only after all 165 prediction records are safely written to disk.

---

## 12. Operational Validity Rules

After all 165 task prediction records are generated for Attempt #2, the run will be audited against the **identical preregistered validity criteria** as Attempt #1:

A benchmark run is declared `INVALID_CANONICAL_RUN` if **any** of the following occur:
1. Incomplete validation suite (< 165 tasks evaluated).
2. Ground-truth reference leakage or scorer execution at agent runtime.
3. Violation of search or generation budget invariants:
   - Web searches per deployed task $> 2$.
   - Second search calls per deployed task $> 1$.
   - Search 2 triggered without valid follow-up eligibility (`INSUFFICIENT` + non-duplicate query).
   - Planner fallback triggers Search 2 (fallback must return `SUFFICIENT` + `NONE`).
   - File processing operations $> 1$ per deployed task.
   - Python code executions $> 1$ per deployed task.
   - Upstream LLM slots $\ne 2$ (Planner + Executor).
   - Nominal path generations $> 5$.
   - Recovery path generations $> 6$.
   - Downstream pipeline (Recovery $\to$ Verifier $\to$ Self-Eval $\to$ Repair) altered from Frozen V10.
4. Runtime or prompt modifications introduced after pre-benchmark audit lock.
5. Widespread provider infrastructure failure (> 10% unhandled task failures).

Isolated, clean search fallbacks (HTTP 429, timeout, empty snippets) that fall back safely to Search 1 evidence do not invalidate the run.

---

## 13. H2 Decision Rule

The canonical accuracy gate ($H_2$) will be evaluated **if and only if Attempt #2 is confirmed to be operationally valid**:

```text
================================================================================
H2 DECISION RULE FOR VALID ATTEMPT #2:
--------------------------------------------------------------------------------
IF Attempt #2 is Operationally Valid:
  IF Correct Tasks > 84 / 165 (> 50.91%):
    H2 Status:           PASS
    Combined Outcome:    SUPPORTED_AS_AN_IMPROVEMENT
    Promotion Decision:  PROMOTE_V11 (Promote as new repository baseline)
  ELSE (Correct Tasks <= 84 / 165):
    H2 Status:           FAIL
    Combined Outcome:    NEUTRAL / NOT_SUPPORTED_AS_AN_IMPROVEMENT
    Promotion Decision:  DO_NOT_PROMOTE_V11 (Frozen V10 remains baseline)

IF Attempt #2 is Operationally Invalid:
  H2 Status:             NOT_EVALUABLE_ON_INVALID_CANONICAL_RUN
  Promotion Decision:    INVALID_RUN_NO_DECISION
  Action:                STOP. Do NOT execute Attempt #3 automatically.
================================================================================
```

---

## 14. Secondary Diagnostics

For an operationally valid Attempt #2, secondary diagnostic hypotheses $H_{3a}$–$H_{3f}$ will be computed exclusively from Attempt #2 predictions:
- **$H_{3a}$:** EVIDENCE Conditional Error Rate ($< 88.89\%$).
- **$H_{3b}$:** Candidate Recovery Trigger Rate ($< 30.91\%$).
- **$H_{3c}$:** Post-Recovery Reachability Floor ($\ge 95.0\%$).
- **$H_{3d}$:** Planner-v2 Parse Success Rate ($\ge 95.0\%$).
- **$H_{3e}$:** Follow-Up Retrieval Operational Tracking across 6 mutually exclusive categories (`SUFFICIENT_NON_TRIGGERED`, `INSUFFICIENT_DUPLICATE_QUERY`, `FOLLOWUP_ELIGIBLE_SEARCH2_SUCCESS`, `FOLLOWUP_ELIGIBLE_SEARCH2_PROVIDER_FAILURE`, `FOLLOWUP_ELIGIBLE_SEARCH2_EMPTY_RESULTS`, `PLANNER_FALLBACK`).
- **$H_{3f}$:** Search Novelty Diagnostics (proportion $\ge 1$ new URL, mean/median new URLs).
- **Python Execution Diagnostics:** Route count, execution count, execution success rate.

### Invariant: Non-Binding Diagnostics
Secondary diagnostics remain strictly **non-binding**. Failure on any secondary metric cannot block promotion if $H_1$, $H_2$, and all invariants pass. Conversely, secondary success cannot override a failure on $H_1$ or $H_2$. Attempt #1 degraded diagnostic values must not be pooled or blended into Attempt #2 diagnostics.

---

## 15. Attempt #1 Preservation

All artifacts from Attempt #1 must remain permanently preserved in `experiments/v11/` as immutable historical evidence:
- `paired_retrieval_raw.jsonl`
- `paired_retrieval_raw.enrollment.jsonl`
- `paired_summary.json`
- `paired_detailed.jsonl`
- `predictions_level_1.jsonl`
- `predictions_level_2.jsonl`
- `predictions_level_3.jsonl`
- `summary_level_1.json`
- `summary_level_2.json`
- `summary_level_3.json`
- `detailed_eval_level_1.jsonl`
- `detailed_eval_level_2.jsonl`
- `detailed_eval_level_3.jsonl`
- `overall_summary.json`
- `CANONICAL_RUN_MANIFEST.json`

These files establish the permanent scientific audit trail of the Attempt #1 infrastructure collapse.

---

## 16. Attempt #2 Manifest Requirements

Upon completion of Attempt #2 runtime and scoring, a dedicated manifest file must be generated:

```text
experiments/v11/canonical_attempt_2/CANONICAL_RUN_MANIFEST.json
```

The manifest must record:
- `attempt_id`: `canonical_attempt_2`
- `canonical_inference_commit`: `02b368b030e2c86c2e534d6012149f819e8d136a`
- `rerun_governance_commit`: Commit hash of this governance document
- `original_invalid_results_commit`: `d1a604669fa976fba0339ee823696759379fcad2`
- `original_invalidity_correction_commit`: `cebefd44bf84c5199e7e35c0a013cd16cf234c8b`
- `post_benchmark_audit_commit`: `8f3febf12e8d60cc2cb38656342f99c92776d797`
- SHA-256 cryptographic checksums for all prediction, summary, and evaluation files in `experiments/v11/canonical_attempt_2/`.

---

## 17. No-Tuning / No-Selective-Retry Guarantee

To uphold the highest standards of empirical integrity:
1. **Zero Tuning:** No hyperparameter, prompt, model temperature, or heuristic tuning has been or will be performed based on GAIA task outcomes.
2. **Zero GAIA Leakage:** No agent logic or prompt has been modified using GAIA ground-truth references.
3. **Zero Cherry-Picking:** No selective rerunning of failed tasks, specific levels, or particular domains is authorized.
4. **Single-Attempt Limit:** Exactly one fresh, full canonical execution is authorized.

---

## 18. Authorization Boundary

```text
================================================================================
AUTHORIZATION BOUNDARY FOR V11 CANONICAL ATTEMPT #2:
--------------------------------------------------------------------------------
1. This document authorizes the preregistered protocol for Attempt #2 ONLY.
2. Exactly ONE full fresh canonical re-execution is authorized under the
   unchanged V11 inference commit (02b368b030e2c86c2e534d6012149f819e8d136a).
3. If Attempt #2 is also declared infrastructure-invalid:
   STOP. Do NOT automatically execute Attempt #3.
   A third attempt would require a new, independent governance review.
   This rule strictly prevents indefinite rerunning until a favorable score appears.
4. THIS DOCUMENT DOES NOT EXECUTE THE PROVIDER HEALTH CHECK.
5. THIS DOCUMENT DOES NOT EXECUTE ANY GAIA BENCHMARK TASKS.
================================================================================
```
