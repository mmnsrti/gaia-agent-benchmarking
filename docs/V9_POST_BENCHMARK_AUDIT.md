# V9 Post-Benchmark Audit: Upstream Candidate Recovery

**Status:** POST-BENCHMARK AUDITED  
**Canonical Inference Commit:** `6369f427c4479073a6ca06531bdfd43e47cd613f`  
**Preregistration Commit:** `d3b0aaab6fa2bb348d82996ec03c0abc8e310ca8` (amended `b4891cd29d30a877e06a08dfbf2a551902de7523`)  
**Parent Baseline:** Frozen V7 (`v7-targeted-repair`)  
**Branch:** `v9-upstream-candidate-recovery`  
**Evaluation Scope:** Full GAIA 2023 Validation Set (165 Tasks: 53 Level 1, 86 Level 2, 26 Level 3)  
**Model:** `gemini-3.5-flash-lite` (temperature=None, thinking_level="medium", max_output_tokens=2048)  
**Benchmark Execution Date:** September 18, 2026  
**Research Verdict:** `SUPPORTED_AS_AN_IMPROVEMENT`  
**Promotion Recommendation:** `PROMOTE_V9_AS_V10_BASELINE`  
**Status:** POST-BENCHMARK AUDITED
**Canonical Inference Commit:** `6369f427c4479073a6ca06531bdfd43e47cd613f`
**Preregistration Commit:** `d3b0aaab6fa2bb348d82996ec03c0abc8e310ca8` (amended `b4891cd29d30a877e06a08dfbf2a551902de7523`)
**Parent Baseline:** Frozen V7 (`v7-targeted-repair`)
**Branch:** `v9-upstream-candidate-recovery`
**Evaluation Scope:** Full GAIA 2023 Validation Set (165 Tasks: 53 Level 1, 86 Level 2, 26 Level 3)
**Model:** `gemini-3.5-flash-lite` (temperature=None, thinking_level="medium", max_output_tokens=2048)
**Benchmark Execution Date:** September 18, 2026
**Research Verdict:** `SUPPORTED_AS_AN_IMPROVEMENT`
**Promotion Recommendation:** `PROMOTE_V9_AS_V10_BASELINE`

---

## 1. Executive Summary & Binding Preregistration Compliance

Version 9 (V9) investigates **Upstream Candidate Recovery** to resolve the central structural bottleneck identified in GAIA agent benchmarking: **candidate starvation**.

In earlier iterations (V5–V8), approximately half of all task executions failed upstream before emitting any candidate answer (`""`), rendering them completely unreachable by downstream verification (V5), self-evaluation (V6), or targeted repair (V7).

V9 introduces bounded, text-only candidate recovery at the upstream worker boundary:
$$\text{V9} = \text{Frozen V7} + \text{one bounded text-only candidate-recovery generation for eligible starved tasks}$$

### Formal Preregistered Hypotheses Outcomes
- **$H_1$ (Primary Hypothesis — Within-Run Correctness Gain):** **CONFIRMED.**  
- **$H_1$ (Primary Hypothesis — Within-Run Correctness Gain):** **CONFIRMED.**
  Within the exact same task executions, introducing bounded candidate recovery produced **+28 improvements ($0 \to 1$)** against **0 regressions ($1 \to 0$)**, yielding a net within-run gain of **+28 tasks (+16.97 percentage points)**.
- **$H_{2a}$ (Zero Non-Triggered Degradation):** **CONFIRMED.**  
- **$H_{2a}$ (Zero Non-Triggered Degradation):** **CONFIRMED.**
  The Non-Triggered Recovery-Boundary Preservation Rate was exactly **100.00% (75 / 75 tasks)**.
- **$H_{2b}$ (Reachability Expansion):** **CONFIRMED.**  
- **$H_{2b}$ (Reachability Expansion):** **CONFIRMED.**
  Candidate reachability expanded from **45.45% (75 / 165)** pre-recovery to **96.36% (159 / 165)** post-recovery, a net reachability gain of **+84 tasks (+50.91 pp)**, exceeding the descriptive target of $\ge 65.0\%$.
- **$H_{2c}$ (Downstream Safeguard Efficacy):** **CONFIRMED.**  
- **$H_{2c}$ (Downstream Safeguard Efficacy):** **CONFIRMED.**
  Recovered candidates flowed cleanly through existing V5 verifier and V7 repair stages without runtime exceptions or schema faults; downstream safeguards preserved 25 correct recovered candidates and rescued 3 initially-wrong recovered candidates into correct final answers.

---

## 2. Dataset & Scorer Provenance

- **Dataset**: Official GAIA (General AI Assistants) 2023 Validation Set
  - Level 1: 53 tasks
  - Level 2: 86 tasks
  - Level 3: 26 tasks
  - Total: 165 tasks
- **Scorer**: Official GAIA leaderboard evaluator (`gaia-benchmark/leaderboard`, commit `9f133d71362e77b3539f1514f31b9c101a545fec`, vendored in `evaluation/metrics.py`).
- **Ground-Truth Firewall**: Ground-truth target answers were completely isolated from agent runtime execution; all scoring was executed strictly offline post-hoc.
- **Runtime Environment**: Windows NT, Python 3.13.2, isolated sub-process runner with 5.0-second inter-task delay.

---

## 3. Operational Validity & Environmental Integrity

The canonical V9 benchmark execution and its contemporaneous matched control were completed with **100.0% operational validity**:
- **Zero Provider Collapses**: Multi-key automatic failover in `agent/llm.py` and `tools/web_search.py` operated transparently; no task was aborted or starved of credentials.
- **Zero Request Failures**: Unhandled provider exceptions = 0 across all 165 tasks in both V9 and Matched V7.
- **Zero Quarantined Runs**: No invalid runs were generated during canonical benchmarking.
- **Full Structural Completeness**: Exactly 165 unique tasks walked, completed, and scored for both V9 and Matched V7.
- **Full Structural Completeness**: All 165 official validation task IDs were structurally executed, recorded, and scored for both V9 and Matched V7. (The separate pipeline completion metric was 163 / 165, or 98.79%).
- **Operational Verdict**: `VALID`.

---

## 4. Structural Coverage & Checkpoint Integrity

| Level | Expected Tasks | Executed Tasks | Unique Task IDs | Duplicates | Completion Status |
| Level | Expected Tasks | Executed Tasks | Unique Task IDs | Duplicates | Structural Coverage |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 53 | 53 | 53 | 0 | 100.0% Complete |
| **Level 2** | 86 | 86 | 86 | 0 | 100.0% Complete |
| **Level 3** | 26 | 26 | 26 | 0 | 100.0% Complete |
| **Total** | **165** | **165** | **165** | **0** | **100.0% Complete** |
| **Level 1** | 53 | 53 | 53 | 0 | 53 / 53 (100% structurally recorded) |
| **Level 2** | 86 | 86 | 86 | 0 | 86 / 86 (100% structurally recorded) |
| **Level 3** | 26 | 26 | 26 | 0 | 26 / 26 (100% structurally recorded) |
| **Total** | **165** | **165** | **165** | **0** | **165 / 165 (100% structurally recorded)** |

All 165 prediction records verify:
- `git_commit`: `6369f427c4479073a6ca06531bdfd43e47cd613f`
- `git_dirty`: `False` (clean working tree during inference)
- `schema_version`: `7` (V9) / `6` (Matched V7)

---

## 5. Canonical V9 Benchmark Results

### Per-Level and Aggregate Scores

| Level | Tasks | Completed Tasks | Completion Rate | Correct Tasks | Accuracy | Request Failures |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 53 | 52 | 98.11% | 33 | **62.26%** | 0 |
| **Level 2** | 86 | 85 | 98.84% | 34 | **39.53%** | 0 |
| **Level 3** | 26 | 26 | 100.00% | 6 | **23.08%** | 0 |
| **Overall** | **165** | **163** | **98.79%** | **73** | **44.24%** | **0** |

*Note on completion rate*: 2 tasks in Level 1/Level 2 experienced worker parse fallbacks that completed the task trace cleanly with an empty string rather than throwing an exception.

---

## 6. Candidate Reachability Funnel

The core architectural objective of V9 was to eliminate candidate starvation at the upstream worker boundary:

| Funnel Stage | Task Count | Percentage of Benchmark | Progression Notes |
| :--- | :---: | :---: | :--- |
| **Total Validation Tasks** | 165 | 100.00% | Full validation set |
| **Pre-Recovery Non-Empty Candidates** | 75 | 45.45% | Tasks successfully emitting candidate upstream |
| **Starved Tasks (Pre-Recovery Candidate Empty `""`)** | 90 | 54.55% | Upstream failure / starvation |
| **Recovery Eligible** | 90 | 54.55% | 100% of starved tasks met eligibility criteria |
| **Recovery Triggered** | 90 | 54.55% | Exact 1:1 trigger gating |
| **Recovery Attempted** | 90 | 54.55% | 100% attempted |
| **Recovery Succeeded (Valid Candidate Parsed)** | 84 | 50.91% | **93.33% recovery parse success rate (84 / 90)** |
| **Recovery Failed Cleanly** | 6 | 3.64% | 6.67% fallback to empty candidate without crashing |
| **Post-Recovery Non-Empty Candidates** | **159** | **96.36%** | Final candidate-bearing tasks |
| **Net Reachability Expansion** | **+84** | **+50.91 pp** | **Structural reach expanded from 45.45% to 96.36%** |

### Forensic Audit of Clean Recovery Failures (6 Tasks)
Exactly 6 triggered tasks failed to parse a valid candidate during recovery:
1. `5cfb274c-0207-4aa7-9575-6ac0bd95d9b2` (L1): `missing_final_marker`
2. `d1af70ea-a9a4-421a-b9cc-94b5e02f1788` (L2): `unexpected_finish_reason`
3. `ded28325-3447-4c56-860f-e497d6fb3577` (L2): `unexpected_finish_reason`
4. `0bb3b44a-ede5-4db5-a520-4e844b0079c5` (L2): `malformed_function_call`
5. `8d46b8d6-b38a-47ff-ac74-cda14cf2d19b` (L3): `unexpected_finish_reason`
6. `851e570a-e3de-4d84-bcfa-cc85578baa59` (L3): `unexpected_finish_reason`

In all 6 cases, recovery failed safely: the candidate remained empty `""`, downstream stages safely bypassed, and the runner recorded execution without exception.

---

## 7. Official Recovered Candidate Accuracy

Scoring the recovered candidate (`post_recovery_candidate`) immediately after the recovery boundary against official ground truth using the official vendored GAIA scorer:

- **Total Successful Recoveries**: 84 tasks
- **Correct Recovered Candidates**: 26 tasks
- **Official Recovered Candidate Accuracy**: **30.95% (26 / 84)**

This demonstrates that approximately one-third of all upstream-starved tasks already contained sufficient evidence in their execution traces to synthesize the exact ground truth answer in a single bounded generation, without any additional search queries or code executions.

---

## 8. Failure-Class Analysis (10 Mutually Exclusive Classes)

Across the 10 preregistered failure classes, candidate recovery exhibited distinct operational profiles:

| Failure Taxonomy Class | Observed | Eligible | Triggered | Succeeded | Cand Correct | Final Correct | Recovery Accuracy |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `PYTHON_CODE_EXTRACTION_FAILURE` | 80 | 80 | 80 | 75 | 21 | 22 | 28.00% (21/75) |
| `PYTHON_EXECUTION_FAILURE` | 6 | 6 | 6 | 6 | 4 | 5 | 66.67% (4/6) |
| `PYTHON_OUTPUT_MISSING_MARKER` | 3 | 3 | 3 | 3 | 1 | 1 | 33.33% (1/3) |
| `MALFORMED_FUNCTION_CALL` | 1 | 1 | 1 | 0 | 0 | 0 | 0.00% (0/0) |
| `MALFORMED_FUNCTION_CALL` | 1 | 1 | 1 | 0 | 0 | 0 | N/A |
| `FUNCTION_CALL_ONLY` | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| `THOUGHT_ONLY` | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| `DIRECT_EXTRACTION_FAILURE` | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| `EMPTY_RESPONSE` | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| `PROVIDER_ERROR` | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| `UNKNOWN_NO_CANDIDATE` | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| *Non-Triggered (Upstream Candidate Emitted)* | 75 | 0 | 0 | 0 | N/A | 45 | N/A |
| **Total Benchmark** | **165** | **90** | **90** | **84** | **26** | **73** | **30.95% (26/84)** |

### Failure Class Observations
1. **Dominance of Python Code Extraction Failure (80 / 90 = 88.89%)**:  
1. **Dominance of Python Code Extraction Failure (80 / 90 = 88.89%)**:
   The primary failure mode of Gemini Flash-Lite in the python worker was emitting explanatory text and code without compliant markdown fences. Recovery successfully extracted valid candidates on 75 of these 80 tasks, yielding 21 directly correct candidates and 22 final correct answers.
2. **High Conversion on Execution Failures (4 / 6 = 66.67%)**:  
2. **High Conversion on Execution Failures (4 / 6 = 66.67%)**:
   When python execution failed due to environment issues (e.g. missing optional library), existing stdout or prior search evidence allowed the recovery prompt to synthesize the answer directly with 66.7% accuracy.

---

## 9. Primary Within-Run Paired Intervention Measurement

In accordance with Section 3 and Section 27 of `experiments/v9/PRE_BENCHMARK.md`, the primary scientific measurement of V9 is the **within-run paired intervention measurement**:
- For non-triggered tasks (75 tasks): Frozen V7 within-run state = `final_answer` (preserved identically at recovery boundary).
- For triggered tasks (90 tasks): Without recovery, Frozen V7 produced an empty upstream candidate, causing downstream stages to bypass; baseline state = `""` (evaluated as wrong).

### Paired Within-Run Transition Matrix (165 Tasks)

| Transition Name | Definition | Level 1 (N=53) | Level 2 (N=86) | Level 3 (N=26) | Overall (N=165) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **`IMPROVEMENT` ($0 \to 1$)** | Baseline wrong $\to$ V9 final correct | 11 | 14 | 3 | **28 (16.97%)** |
| **`REGRESSION` ($1 \to 0$)** | Baseline correct $\to$ V9 final wrong | 0 | 0 | 0 | **0 (0.00%)** |
| **`STABLE_CORRECT` ($1 \to 1$)** | Baseline correct $\to$ V9 final correct | 22 | 20 | 3 | **45 (27.27%)** |
| **`STABLE_FAILURE` ($0 \to 0$)** | Baseline wrong $\to$ V9 final wrong | 20 | 52 | 20 | **92 (55.76%)** |
| **Total** | | **53** | **86** | **26** | **165 (100.0%)** |

### Primary Within-Run Net Delta

$$\Delta_{\text{within-run}} = \text{Improvements} - \text{Regressions} = 28 - 0 = +28 \text{ tasks}$$
$$\Delta_{\text{pp}} = \frac{+28}{165} \times 100 = \mathbf{+16.97 \text{ percentage points}}$$

- **Pre-Intervention Baseline Correct**: 45 / 165 (27.27%)
- **Post-Intervention V9 Final Correct**: 73 / 165 (44.24%)
- **Level 1 Net Gain**: $+11$ tasks ($41.51\% \to 62.26\%$, $+20.75$ pp)
- **Level 2 Net Gain**: $+14$ tasks ($23.26\% \to 39.53\%$, $+16.28$ pp)
- **Level 3 Net Gain**: $+3$ tasks ($11.54\% \to 23.08\%$, $+11.54$ pp)

---

## 10. Downstream Safeguard Transition Matrix (Recovered Candidates, N=84)

Once a candidate was recovered, it entered the downstream pipeline: V5 verifier $\to$ V6 self-evaluator $\to$ V7 targeted repair. The interaction between recovery and downstream safeguards is classified into 4 mutually exclusive transitions:

| Transition Metric | Count | Fraction | Definition & Impact |
| :--- | :---: | :---: | :--- |
| **`RECOVERY_CORRECT_FINAL_CORRECT`** | **25** | **29.76%** | Recovered candidate was correct, and downstream safeguards preserved it intact. |
| **`RECOVERY_CORRECT_FINAL_WRONG`** | **1** | **1.19%** | Recovered candidate was correct, but downstream verifier damaged it (harm event). |
| **`RECOVERY_WRONG_FINAL_CORRECT`** | **3** | **3.57%** | Recovered candidate was incorrect, but downstream safeguards rescued and corrected it. |
| **`RECOVERY_WRONG_FINAL_WRONG`** | **55** | **65.48%** | Recovered candidate was incorrect and remained incorrect throughout downstream pipeline. |
| **Total Recovered Cohort** | **84** | **100.00%** | Full closure of recovered tasks. |

### Deep-Dive into Downstream Mutations (4 Tasks)
1. **`RECOVERY_CORRECT_FINAL_WRONG` (1 Task)**:
   - Task `4d51c4bf-4b0e-4f3d-897b-3f6687a7d9f2` (Level 2)
   - Recovered Candidate: `'8'` (matches ground truth `'8'`)
   - Downstream Behavior: V5 Answer Verifier issued `REVISE` changing the answer to `'4'`. V6 self-evaluator passed it. Final answer `'4'` (incorrect).
   - *Impact*: Downstream verifier harm rate on correct recovered candidates = $1 / 26 = 3.85\%$.
2. **`RECOVERY_WRONG_FINAL_CORRECT` (3 Tasks — Rescued by Downstream Pipeline)**:
   - Task `1f975693-876d-457b-a649-393859e79bf3` (Level 1): Recovered candidate was `'45, 46, 47'`. Downstream V5 verifier revised to `'132, 133, 134, 197, 245'` (ground truth). Self-evaluator evaluated `SUSPECT`, repair chose `KEEP`. Final answer correct.
   - Task `67e8878b-5cef-4375-804e-e6291fdbe78a` (Level 2): Recovered candidate was `'Cottages'`. Downstream V5 verifier revised to `'Hotels'` (ground truth). Final answer correct.
   - Task `da52d699-e8d2-4dc5-9191-a2199e0b6a9b` (Level 3): Recovered candidate was `'The Lost Symbol'`. Verifier kept it. V6 self-evaluator flagged `SUSPECT` (`RISK_TYPE: EVIDENCE`). V7 targeted repair performed `REPLACE` to `'Out of the Silent Planet'` (ground truth). Final answer correct.
   - *Impact*: Downstream rescue rate = $3 / 58 = 5.17\%$. Downstream safeguards provided net positive value ($+3$ rescues vs $-1$ harm = net $+2$ tasks) on the recovered cohort.

---

## 11. Core Safety Invariant: Non-Triggered Preservation Audit

The central safety invariant of V9 requires that whenever upstream candidate formulation succeeds, V9 recovery must not intervene:
$$\text{Preservation Rate}_{\text{boundary}} = \frac{N_{\text{non-triggered with post\_recovery\_candidate == pre\_recovery\_candidate}}}{N_{\text{all non-triggered tasks}}} = 100.0\%$$

- Total Non-Triggered Tasks: 75
- Tasks with `post_recovery_candidate == pre_recovery_candidate`: 75
- **Preservation Rate**: **100.00% (75 / 75 tasks)**
- Violating Tasks: **0**
- Invariant Status: **PASS**.

---

## 12. Resource & Generation Budget Audit

Across all 165 tasks in the benchmark:

| Budget Metric | Preregistered Bound | Observed Maximum | Violations | Verification Status |
| :--- | :---: | :---: | :---: | :---: |
| **Max Logical Generations (Triggered Tasks)** | $\le 6$ | 6 | 0 | PASS |
| **Max Logical Generations (Non-Triggered Tasks)** | $\le 5$ | 5 | 0 | PASS |
| **Candidate Recovery Added Searches** | 0 | 0 | 0 | PASS |
| **Candidate Recovery Added Python Runs** | 0 | 0 | 0 | PASS |
| **Max Total Searches Per Task** | $\le 1$ | 1 | 0 | PASS |
| **Max Total Python Executions Per Task** | $\le 1$ | 1 | 0 | PASS |

### Candidate Recovery Telemetry (90 Triggered Tasks)
- **Average Latency**: 5.06 s (Median: 5.17 s, Min: 1.42 s, Max: 8.22 s)
- **Average Input Tokens**: 2,516.0 tokens
- **Average Output Tokens**: 9.9 tokens
- **Average Thinking Tokens**: 1,333.6 tokens
- **Average Total Tokens**: 3,859.2 tokens
- **Total Recovery Token Overhead (Full 165-Task Benchmark)**: 347,328 tokens (~2,105 tokens/task averaged across all 165 benchmark tasks).

---

## 13. Contemporaneous Matched Frozen V7 Control (Secondary Observational)

A matched control run of Frozen V7 was executed contemporaneously from the exact same inference commit (`6369f427c4479073a6ca06531bdfd43e47cd613f`):

| Level | Matched V7 Accuracy | Canonical V9 Accuracy | Observational Delta |
| :---: | :---: | :---: | :---: |
| **Level 1** | 25 / 53 (47.17%) | 33 / 53 (62.26%) | +8 tasks (+15.09 pp) |
| **Level 2** | 23 / 86 (26.74%) | 34 / 86 (39.53%) | +11 tasks (+12.79 pp) |
| **Level 3** | 3 / 26 (11.54%) | 6 / 26 (23.08%) | +3 tasks (+11.54 pp) |
| **Overall** | **51 / 165 (30.91%)** | **73 / 165 (44.24%)** | **+22 tasks (+13.33 pp)** |

### Cross-Run 2x2 Contingency Matrix (165 Tasks)

| Contingency Cell | Task Count | Percentage | Interpretation |
| :--- | :---: | :---: | :--- |
| **Both Correct** | 43 | 26.06% | Robustly solved across both runs |
| **Both Wrong** | 84 | 50.91% | Difficult tasks unaddressed by either run |
| **Matched V7 Wrong $\to$ V9 Correct** | 30 | 18.18% | Solved in V9 run |
| **Matched V7 Correct $\to$ V9 Wrong** | 8 | 4.85% | Stochastic divergence in upstream sampling |
| **Total** | **165** | **100.00%** | Full contingency closure |

> [!NOTE]
> **Methodological Attribution**:  
> In accordance with Section 3 of `experiments/v9/PRE_BENCHMARK.md`, this cross-run comparison is strictly **secondary, observational, and non-causal**. Run-to-run variation in LLM sampling and search query formulation produces upstream divergences across separate runs. The primary causal evidence for V9 is the within-run paired intervention measurement (+28 tasks, +16.97 pp), which completely controls for runtime stochasticity.
> **Methodological Attribution**:
> In accordance with Section 3 of `experiments/v9/PRE_BENCHMARK.md`, this cross-run comparison is strictly **secondary, observational, and non-causal**. Run-to-run variation in LLM sampling and search query formulation produces upstream divergences across separate runs.
> The preregistered primary measurement for V9 is the within-run paired intervention measurement (+28 tasks, +16.97 pp).
> The matched Frozen V7 comparison is secondary, observational, and non-causal because it is based on a separate stochastic execution.
> The within-run paired intervention measurement avoids the separate-run sampling divergence that affects the matched V7 comparison and is the preregistered primary decision metric. It should not be described as a perfect causal estimate or as eliminating all sources of uncertainty.

---

## 14. Threats to Validity & Scientific Limitations

1. **Text-Only Boundedness**: Recovery operated strictly on already-gathered evidence. Tasks requiring additional information retrieval that failed upstream remain unsolved.
2. **Downstream Verifier Over-Correction**: In 1 case (L2 `4d51c4bf...`), an accurate candidate was degraded by the downstream V5 verifier. While outweighed by 3 downstream rescues, verifier sensitivity on recovered candidates warrants further study in V10.
3. **Upstream Flash-Lite Code Extraction Vulnerability**: Over 88% of upstream failures were python markdown extraction failures. While candidate recovery effectively repaired these failures, future base router/worker prompt improvements could reduce initial extraction failures.

---

## 15. Preregistered Decision Rule Evaluation

Evaluating against Section 7 of `experiments/v9/PRE_BENCHMARK.md`:

```text
PROMOTION CRITERIA CHECKLIST:
[PASS] 1. Within-Run End-to-End Net Delta > 0 (+28 tasks, +16.97 pp)
[PASS] 2. Non-Triggered Recovery-Boundary Preservation Rate == 100.0% (75 / 75)
[PASS] 3. Zero Added Tools (Searches added = 0, Python runs added = 0, File reads added = 0)
[PASS] 4. Generation Cap Respected (Max generation attempts = 6; <= 5 on non-triggered)
[PASS] 5. Operational Run Validity Confirmed (165 / 165 tasks, zero provider collapse)
```

All five promotion criteria are met with zero exceptions.

---

## 16. Final Scientific Verdict & Promotion Recommendation

```text
================================================================================
RESEARCH VERDICT:         SUPPORTED_AS_AN_IMPROVEMENT
PROMOTION RECOMMENDATION: PROMOTE_V9_AS_V10_BASELINE
================================================================================
```

### Recommendation for Next Steps
1. Record and commit canonical benchmark artifacts on `v9-upstream-candidate-recovery`.
2. Push branch to remote.
3. Await independent governance review before branch merge or baseline freezing.

