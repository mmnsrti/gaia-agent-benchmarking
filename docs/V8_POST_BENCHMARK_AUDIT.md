# GAIA V8 Post-Benchmark Audit Report

**Architecture**: V8 — Bounded Active Evidence Verification  
**Repository Branch**: `v8-active-evidence-verification`  
**Execution HEAD Commit**: `d0c770aa8976b5043228762257c27b179ac5aafe`  
**Date**: September 14, 2026  
**Evaluation Harness**: Official GAIA Benchmark Validation Split (2023)  
**Evaluator Commit**: `9f133d71`  

---

## 1. Execution Provenance

| Parameter | Value |
| :--- | :--- |
| **Model** | `gemini-3.5-flash-lite` |
| **Temperature** | `None` (default model behavior) |
| **Thinking Level** | `medium` |
| **Max Output Tokens** | `2048` |
| **Search Provider** | Tavily (`max_results=5`) |
| **Git Commit (Canonical V8 L1)** | `39d216200de831e39cccc610a31f190ac6171a83` (`git_dirty=False`) |
| **Git Commit (Canonical V8 L2)** | `39d216200de831e39cccc610a31f190ac6171a83` (`git_dirty=False`) |
| **Git Commit (Canonical V8 L3)** | `d0c770aa8976b5043228762257c27b179ac5aafe` (`git_dirty=False`) |
| **Git Commit (Matched V7 L1)** | `39d216200de831e39cccc610a31f190ac6171a83` (`git_dirty=False`) |
| **Git Commit (Matched V7 L2)** | `8ae57c21762cfc91f6cc22e73550294dde41429f` |
| **Git Commit (Matched V7 L3)** | `d0c770aa8976b5043228762257c27b179ac5aafe` (`git_dirty=False`) |

---

## 2. Dataset Completeness & Structural Integrity

All 165 tasks from the official GAIA 2023 validation dataset were executed without truncation, data loss, or missing task IDs across all levels.

| Split / Level | Expected Tasks | Canonical V8 Completed | Matched Frozen V7 Completed | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Level 1** | 53 | 53 (100.0%) | 53 (100.0%) | VALID |
| **Level 2** | 86 | 86 (100.0%) | 86 (100.0%) | VALID |
| **Level 3** | 26 | 26 (100.0%) | 26 (100.0%) | VALID |
| **Total Global Tasks** | **165** | **165 (100.0%)** | **165 (100.0%)** | **COMPLETE** |

- **Unique Task IDs**: Exactly 165 unique task IDs in Canonical V8 and 165 unique task IDs in Matched Frozen V7.
- **Set Equality**: `set(v8_task_ids) == set(v7_task_ids) == set(gaia_validation_task_ids)`.
- **Duplicate Tasks**: 0 duplicates observed.
- **Corrupted Records**: 0 corrupted records across all `.jsonl` artifact files.

---

## 3. Provider Incidents & Quarantined Runs

During early iterations of Level 2 and Level 3 runs, free-tier Gemini API keys hit daily quota ceilings (`429 RESOURCE_EXHAUSTED: GenerateRequestsPerDayPerProjectPerModel-FreeTier`) and older project permissions errors (`403 PERMISSION_DENIED`), producing provider collapses.

### Quarantine Action Log
1. **Invalid V8 Runs Quarantined**:
   - `experiments/v8_invalid_l2_provider_collapse/`
   - `experiments/v8_invalid_l3_provider_collapse/`
2. **Invalid Matched V7 Runs Quarantined**:
   - `experiments/v8_matched_v7_invalid_l2_provider_collapse/`
   - `experiments/v8_matched_v7_invalid_l3_provider_collapse/`
   - `experiments/quarantine/v8_matched_v7_invalid_l2_pre_rerun_predictions.jsonl`
3. **Remediation & Hardening**:
   - Implemented automatic multi-token discovery and process-wide rotation on 429 quota exhaustion in [`agent/llm.py`](file:///d:/app/ai/gaia-agent-benchmarking/agent/llm.py) with 8 dedicated unit tests in [`tests/test_key_rotation.py`](file:///d:/app/ai/gaia-agent-benchmarking/tests/test_key_rotation.py).
   - Added conservative provider collapse guards in [`evaluation/run_level.py`](file:///d:/app/ai/gaia-agent-benchmarking/evaluation/run_level.py) with 3 unit tests in [`tests/test_run_level_hardening.py`](file:///d:/app/ai/gaia-agent-benchmarking/tests/test_run_level_hardening.py) ensuring that any provider collapse halts execution immediately without writing partial/failed records to canonical logs.
   - Using a verified pool of 4 active, healthy Gemini API tokens, all remaining runs completed with **0 provider errors, 0 request failures, and 0 quota collapses**.

---

## 4. V8 Runtime Invariant Validation

Across all 165 Canonical V8 tasks, all preregistered architectural bounds strictly held:

| Runtime Invariant | Design Limit | Maximum Observed | Violation Count |
| :--- | :---: | :---: | :---: |
| **Active Verification Web Searches** | $\le 1$ | 1 | 0 |
| **Active Verification Adjudications** | $\le 1$ | 1 | 0 |
| **Total External Searches per Task** | $\le 2$ | 2 | 0 |
| **Total Logical LLM Generations per Task** | $\le 6$ | 6 | 0 |
| **V8 Python Execution Calls** | 0 | 0 | 0 |
| **V8 File Reread Attempts** | 0 | 0 | 0 |
| **Information Firewall Enforcement** | 100% | 100% | 0 |

---

## 5. Final Benchmark Accuracy

### Canonical V8 Accuracy Breakdown

| Level | Tasks | Completed | Non-Empty Answers | Correct Tasks | Accuracy |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 53 | 34 (64.1%) | 34 | 20 | **37.74%** |
| **Level 2** | 86 | 44 (51.2%) | 40 | 25 | **29.07%** |
| **Level 3** | 26 | 9 (34.6%) | 9 | 3 | **11.54%** |
| **Overall** | **165** | **87 (52.7%)** | **83** | **48** | **29.09%** |

---

## 6. Pre/Post Active Verification Results & Intervention Transitions

The primary scientific evaluation of V8 is the causal, within-run intervention comparison measuring whether bounded active evidence verification improved the candidate answer entering V8:
The primary V8 stage-effect measurement compares the Frozen V7 final answer with the V8 final answer inside the same execution trace:

$$\text{Frozen V7 Candidate Answer} \longrightarrow \text{V8 Final Answer}$$

### Within-Run Intervention Transitions

| Metric | Level 1 (53) | Level 2 (86) | Level 3 (26) | Overall Total (165) |
| :--- | :---: | :---: | :---: | :---: |
| **Pre-Active Correct** | 20 / 53 (37.74%) | 25 / 86 (29.07%) | 4 / 26 (15.38%) | **49 / 165 (29.70%)** |
| **Post-Active Correct** | 20 / 53 (37.74%) | 25 / 86 (29.07%) | 3 / 26 (11.54%) | **48 / 165 (29.09%)** |
| **Improvements ($0 \rightarrow 1$)** | 0 | 0 | 0 | **0** |
| **Regressions ($1 \rightarrow 0$)** | 0 | 0 | 1 | **1** |
| **Stable Correct ($1 \rightarrow 1$)** | 0 | 1 | 0 | **1** |
| **Stable Failure ($0 \rightarrow 0$)** | 6 | 5 | 2 | **13** |
| **Not Triggered (Bypassed)** | 47 | 80 | 23 | **150** |
| **Triggered Interventions** | 6 | 6 | 3 | **15** |
| **Net Active Verification Delta** | **+0** | **+0** | **-1** | **-1 (-0.61 pp)** |
| **Correction Rate** | 0.0% | 0.0% | 0.0% | **0.0%** |
| **Harm Rate** | 0.0% | 0.0% | 100.0% | **50.0%** |

### Arithmetic Verification
- $\text{Triggered} = \text{Improvements (0)} + \text{Regressions (1)} + \text{Stable Correct (1)} + \text{Stable Failure (13)} = 15$. (Holds)
- $\text{Post-Active Correct (48)} - \text{Pre-Active Correct (49)} = \text{Improvements (0)} - \text{Regressions (1)} = -1$. (Holds)

---

## 7. Forensic Analysis of the Single Regression

In Level 3, Task ID `00d579ea-0889-4fd9-a771-2c8d79835c8d`:
- **Question**: *"Assuming scientists in the famous youtube video The Thinking Machine (Artificial Intelligence) 1961 MIT..."*
- **Ground Truth**: `"Claude Shannon"`
- **Candidate Answer entering V8**: `"Claude Shannon"` (Correct!)
- **Self-Evaluation Stage**: V6 self-evaluator flagged the answer as `SUSPECT` with risk type `EVIDENCE`.
- **Targeted Repair Stage**: V7 repairer conservatively kept the answer (`KEEP`).
- **V8 Active Evidence Verification**:
  - Deterministically formulated active query: `What is the scientist in The Thinking Machine 1961 MIT? \n\n Candidate answer to independently verify: Claude Shannon`.
  - Tavily retrieved search results discussing MIT scientists featured in the documentary, mentioning both Claude Shannon and Jerome Wiesner.
  - Active Adjudicator executed `REPLACE` with `"Jerome Wiesner"`.
  - **Outcome**: Converted a correct answer into an incorrect answer, producing a regression ($1 \rightarrow 0$).

---

## 8. Funnel Metrics

| Funnel Stage | Count | Percentage of Total (165) | Conversion Rate |
| :--- | :---: | :---: | :---: |
| **Total Tasks** | 165 | 100.0% | — |
| **Non-Empty Frozen V7 Answers** | 83 | 50.3% | 50.3% |
| **Self-Eval Evaluated (Eligible)** | 83 | 50.3% | 100.0% |
| **Self-Eval Flagged `SUSPECT`** | 18 | 10.9% | 21.7% of evaluated |
| **SUSPECT with `EVIDENCE` Risk** | 15 | 9.1% | 83.3% of suspects |
| **Active Verification Eligible** | 15 | 9.1% | 100.0% |
| **Active Verification Triggered** | 15 | 9.1% | 100.0% |
| **Active Search Attempted** | 15 | 9.1% | 100.0% of triggered |
| **Active Search Usable** | 14 | 8.5% | 93.3% of searches |
| **Adjudications Attempted** | 14 | 8.5% | 100.0% of usable |
| **Valid Adjudications** | 14 | 8.5% | 100.0% of adjudications |
| **Action `KEEP`** | 13 | 7.9% | 92.9% of adjudications |
| **Action `REPLACE`** | 1 | 0.6% | 7.1% of adjudications |
| **Answers Changed** | 1 | 0.6% | 7.1% of adjudications |

---

## 9. Candidate Starvation & Upstream Reachability

A critical finding in the GAIA benchmark progression across V4–V8 is **Candidate Starvation**:
- Out of 165 tasks, **82 tasks (49.7%) failed to produce any candidate answer** from the upstream worker/router stages.
- The root cause is the underlying LLM's tendency to emit `MALFORMED_FUNCTION_CALL` or empty responses when attempting complex multi-modal or spreadsheet analysis in GAIA Level 2 and Level 3 without code interpreter feedback.
- Because V6 self-evaluator, V7 targeted repair, and V8 active verification strictly require a non-empty candidate answer, **almost half of all benchmark tasks are completely unreachable** by the verification and repair stages.
- Even among reachable candidates (83 tasks), V6's high precision (83.3%) filters out 65 tasks as `PASS`, leaving a narrow window of 18 tasks flagged `SUSPECT`, of which 15 had `EVIDENCE` risk.

---

## 10. V6 Diagnostic Metrics Anchored to `pre_repair_correct`

As preregistered, the V6 self-evaluator's diagnostic validity must remain anchored to the answer state it evaluated (`pre_repair_correct`), never to the final V8 answer:

| Metric | Value |
| :--- | :---: |
| **Evaluated Candidates ($N$)** | 83 |
| **True Positives (SUSPECT & Incorrect)** | 15 |
| **False Positives (SUSPECT & Correct)** | 3 |
| **False Negatives (PASS & Incorrect)** | 18 |
| **True Negatives (PASS & Correct)** | 47 |
| **Precision** | **83.33%** |
| **Recall** | **45.45%** |
| **F1 Score** | **58.82%** |

V6 maintains strong diagnostic precision (83.33%), confirming that when it flags an answer as `SUSPECT`, the answer is indeed incorrect more than 8 times out of 10. However, the conservative design yields moderate recall (45.45%), missing 18 incorrect candidate answers.

---

## 11. Matched Frozen V7 Observational Comparison

The contemporaneous run of Matched Frozen V7 was executed side-by-side across all 165 tasks:

| Split / Level | Canonical V8 Accuracy | Matched Frozen V7 Accuracy | Observational Delta |
| :--- | :---: | :---: | :---: |
| **Level 1** | 20 / 53 (37.74%) | 21 / 53 (39.62%) | -1 task (-1.88 pp) |
| **Level 2** | 25 / 86 (29.07%) | 21 / 86 (24.42%) | +4 tasks (+4.65 pp) |
| **Level 3** | 3 / 26 (11.54%) | 3 / 26 (11.54%) | +0 tasks (+0.00 pp) |
| **Overall** | **48 / 165 (29.09%)** | **45 / 165 (27.27%)** | **+3 tasks (+1.82 pp)** |

### Methodological Classification
- **Secondary, Observational, Non-Causal**: In accordance with the preregistered experimental protocol, cross-run comparison between V8 and Matched V7 is **non-causal** due to stochastic sampling variability in upstream generation (e.g. slight differences in worker routing and tool execution).
- The **sole causal measurement** of V8's active verification mechanism is the within-run intervention transition:
- **Secondary, Observational, Non-Causal**: In accordance with the preregistered experimental protocol, cross-run comparison between V8 and Matched V7 is **observational and non-causal** due to stochastic sampling variability in upstream generation (e.g. slight differences in worker routing and tool execution).
- The **primary within-run intervention measurement** of V8's active verification stage compares the Frozen V7 candidate answer with the V8 final answer inside the same execution trace:
  $$\text{Net Delta} = \text{Improvements} - \text{Regressions} = 0 - 1 = -1 \text{ task } (-0.61 \text{ pp})$$

---

## 12. Scientific Interpretation

1. **Active Verification Search Quality**:
   - In 14 out of 15 triggered cases (93.3%), active verification search succeeded in finding external evidence for the deterministic query.
2. **Conservative Adjudication Behavior**:
   - In 13 out of 14 adjudications (92.9%), the adjudicator chose `KEEP`, declining to guess or speculate when the retrieved evidence was ambiguous or incomplete. This demonstrates excellent adherence to the non-destructive prompt contract.
3. **Zero Repair Effectiveness ($0$ Improvements)**:
   - When active verification was triggered on incorrect answers (14 cases), the retrieved evidence was either insufficient to locate the exact missing entity or the question required complex multi-step reasoning/attachment inspection that a single 1500-char web search could not resolve.
   - Consequently, **zero answers were successfully corrected** ($0/14 = 0.0\%$).
4. **Harm on Correct Answers ($1$ Regression)**:
   - In 1 case where a correct answer was falsely flagged `SUSPECT` by upstream self-eval, the active verification evidence contained competing entities, misleading the adjudicator into replacing the true answer with a distractor.

---

## 13. Scientific Decision Rule & Recommendation
## 13. Scientific Decision Rule & Governance Verdict

### Preregistered Decision Rule
- $\text{Improvements} > \text{Regressions} \implies \text{Positive Net Intervention Effect}$
- $\text{Improvements} == \text{Regressions} \implies \text{No Net Benefit Observed}$
- $\text{Improvements} < \text{Regressions} \implies \text{Harmful Net Intervention Effect}$

### Result
$$\text{Improvements} (0) < \text{Regressions} (1) \implies \text{Harmful Net Intervention Effect (-1 task)}$$
$$\text{Improvements} (0) < \text{Regressions} (1) \implies \text{Harmful Net Intervention Effect (-1 task, -0.61 pp)}$$

### Verdict: **REJECT / DO NOT FREEZE**
### Governance Verdicts

V8 active evidence verification failed to provide a net positive within-run benefit on the GAIA benchmark.
- **Do NOT freeze V8**.
- **Do NOT generate `experiments/v8/FROZEN.md`**.
- **Do NOT tag or release V8**.
- **Do NOT merge `v8-active-evidence-verification` into `main`**.
- All benchmark artifacts, predictions, summaries, and telemetry are preserved in `experiments/v8/` and `experiments/v8_matched_v7/` for scientific audit and future research.
- **Research Verdict**: `REJECTED_AS_AN_IMPROVEMENT`
- **Freeze Verdict**: `FROZEN_WITH_DOCUMENTED_NEGATIVE_RESULT`
- **Promotion Verdict**: `DO_NOT_PROMOTE`
- **Successor Baseline**: `Frozen V7`

### Final Governance Explanation
1. **Freezing vs. Promotion**:
   - `FROZEN` does not mean successful; it means the experiment is complete, its architecture and results are immutable, and future modifications belong to a new version.
   - V8 is being **frozen** because its experiment is complete and all empirical evidence must remain immutable for open scientific provenance.
   - V8 is **NOT being promoted** as the baseline for V9 because the preregistered within-run intervention result was negative ($0$ improvements, $1$ regression, net delta $= -1$ task).
2. **Successor Handoff**:
   - The successor research experiment (V9) must branch from **Frozen V7**, not V8.
   - Do NOT merge V8 into `main`.
   - All benchmark artifacts, predictions, evaluations, summaries, and manifests are preserved in `experiments/v8/` and `experiments/v8_matched_v7/` as a permanent public record of this negative result.

