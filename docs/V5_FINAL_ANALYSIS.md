# V5 Final Scientific Analysis: One-Shot Post-Answer Verification on GAIA

## 1. Executive Summary

This document presents the definitive scientific analysis of **V5 (One-Shot Post-Answer Verification)** evaluated on the complete 165-task GAIA validation benchmark, compared directly against a contemporaneously executed, matched **V4 (Explicit Two-Stage Capability Router)** baseline run.

### Core Scientific Findings

1. **Pure Verifier Intervention Effect (Within V5): Zero Net Change ($\Delta = 0.00\text{ pp}$)**
   - Pre-verification correctness: **53 / 165 tasks (32.12%)**
   - Post-verification correctness: **53 / 165 tasks (32.12%)**
   - Improvements ($0 \rightarrow 1$): **0 tasks**
   - Regressions ($1 \rightarrow 0$): **0 tasks**
   - Stable Correct ($1 \rightarrow 1$): **53 tasks**
   - Stable Failure ($0 \rightarrow 0$): **112 tasks**
   - **Conclusion**: Within the V5 system, the verifier exhibited absolute conservative safety ($\text{regressions} = 0$), but failed to achieve any empirical accuracy gain ($\text{improvements} = 0$).

2. **System-Level Matched Benchmark Performance: $53/165$ (32.12%) vs Matched V4 $57/165$ (34.55%)**
   - V5 achieved **53 / 165 (32.12%)** overall accuracy.
   - Matched V4 achieved **57 / 165 (34.55%)** overall accuracy.
   - Observed system-level difference: **-4 tasks (-2.42 pp)**.
   - **Causal Decomposition**: Because the within-V5 verifier delta is exactly **0 tasks**, this -4 task system difference is entirely attributable to upstream stochastic worker execution variance and upstream operational completion differences between runs, not to verifier degradation.

3. **Verifier Action Funnel and Conservatism**
   - **Eligibility**: 81 / 165 tasks (49.09%) yielded non-empty candidate answers from upstream workers; 84 / 165 tasks (50.91%) failed upstream and were safely bypassed.
   - **Verdicts**: On the 81 eligible tasks, the verifier issued **78 KEEP (96.30%)** and **3 REVISE (3.70%)** decisions.
   - **Revision Outcomes**: All 3 revised tasks resulted in net-neutral outcomes (1 remained stable correct, 2 remained stable failure; 0 net accuracy change).
   - **Failure-Safe Preservation**: 100% of KEEP decisions and all fallbacks strictly preserved the upstream candidate answer.

---

## 2. Scientific Definition of V5

V5 is formally defined as:

$$\text{V5} = \text{frozen V4} + \text{one-shot post-answer verification/revision}$$

### Upstream V4 Architecture (Strictly Preserved)
1. **Search Tool**: Single Tavily search call ($N \le 1$), if search enabled.
2. **File Processing**: Deterministic `FileTool` extraction ($N \le 1$) for tasks requiring attachments.
3. **Capability Router**: Explicit router LLM call selecting between `DIRECT` and `PYTHON` execution tracks.
4. **Route-Specific Worker**:
   - `DIRECT`: Worker generates candidate answer directly.
   - `PYTHON`: Worker generates code block; code is executed in an isolated deterministic sandbox ($N \le 1$ execution).
   - Both router and workers operate with native Gemini function calling disabled (`mode="NONE"`).

### Downstream Verifier Stage (The V5 Intervention)
- **Eligibility Guard**: If the upstream worker fails to produce a candidate answer (e.g., execution timeout, malformed output, empty answer), the verifier is **bypassed immediately**. No LLM call is made, preserving empty-candidate failure safety.
- **Single-Pass Verification**: When a non-empty candidate exists, a dedicated verifier LLM call evaluates the question, search evidence, file context, and candidate answer.
- **Structured Output**: The verifier outputs either:
  - `KEEP`: The candidate answer is retained without modification.
  - `REVISE`: An alternative answer is supplied and replaces the candidate.
- **No Iterative Loops**: The verifier is executed at most once. It has no tool access, cannot invoke Python, cannot execute web searches, and cannot retry.
- **Hard Generation Cap**: The system generation count is strictly bounded at $\le 3$ (1 router + 1 worker + 1 verifier).

---

## 3. Dataset Integrity and Baseline Matching

- **Dataset**: Full 165-task GAIA validation set (split across 53 Level 1, 86 Level 2, and 26 Level 3 tasks).
- **Task Identity Validation**: 100% of task IDs match exactly between V5 and the matched V4 control run. Zero duplicate task executions were detected.
- **Scorer Provenance**: All evaluations were performed using the official GAIA scoring harness:
  - Scorer: `official-gaia-leaderboard`
  - Git Commit / Hash: `9f133d71362e77b3539f1514f31b9c101a545fec`

---

## 4. Overall Benchmark Results

The table below summarizes performance across the 165 GAIA validation tasks for V5 and the matched V4 control run:

| Level | Tasks | V5 Correct | V5 Acc (%) | V5 Completed | V5 Comp (%) | Matched V4 Correct | Matched V4 Acc (%) | Matched V4 Completed | Matched V4 Comp (%) | Task Delta | Accuracy Delta (pp) | Completed Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Level 1** | 53 | 28 | 52.83% | 31 | 58.49% | 29 | 54.72% | 39 | 73.58% | -1 | -1.89 pp | -8 |
| **Level 2** | 86 | 20 | 23.26% | 37 | 43.02% | 24 | 27.91% | 38 | 44.19% | -4 | -4.65 pp | -1 |
| **Level 3** | 26 | 5 | 19.23% | 10 | 38.46% | 4 | 15.38% | 8 | 30.77% | +1 | +3.85 pp | +2 |
| **Overall** | **165** | **53** | **32.12%** | **78** | **47.27%** | **57** | **34.55%** | **85** | **51.52%** | **-4** | **-2.42 pp** | **-7** |

### Primary Observations
- In Level 1, V5 scored 28/53 (52.83%) vs V4's 29/53 (54.72%), a delta of -1 task.
- In Level 2, V5 scored 20/86 (23.26%) vs V4's 24/86 (27.91%), a delta of -4 tasks.
- In Level 3, V5 scored 5/26 (19.23%) vs V4's 4/26 (15.38%), a delta of +1 task.
- Across all 165 tasks, V5 achieved 53 correct (32.12%) vs matched V4's 57 correct (34.55%).

---

## 5. Completion and Usability Analysis

Under GAIA benchmarking protocol, a task is recorded as an **operational completion success** (`completion_success=True`) only when the agent terminates normally with `finish_reason == "STOP"` and produces a non-empty final response string. Truncated answers (`MAX_TOKENS`) or abnormal terminations evaluate to `False`.

In V5, three distinct concepts govern answer availability:
1. **Operational Completion (`completion_success`)**: 78 / 165 tasks (47.27%).
2. **Candidate Answer Available (`pre_verification_answer` non-empty)**: 81 / 165 tasks (49.09%).
3. **Verifier Eligible**: 81 / 165 tasks (49.09%). Exactly equal to candidate availability.

The 3-task discrepancy between candidate availability (81) and operational completion (78) represents tasks where an upstream worker produced text that allowed candidate extraction, but the worker encountered an operational limitation (such as `MAX_TOKENS` during chain-of-thought generation) resulting in `completion_success=False`.

---

## 6. Attachment vs Non-Attachment Breakdown

Performance segmented by whether the task required processing an attached file:

| Subset | Tasks | V5 Correct | V5 Acc (%) | Matched V4 Correct | Matched V4 Acc (%) | Task Delta | pp Delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| **With Attachment** | 38 | 6 | 15.79% | 7 | 18.42% | -1 | -2.63 pp |
| **Without Attachment** | 127 | 47 | 37.01% | 50 | 39.37% | -3 | -2.36 pp |
| **Total** | **165** | **53** | **32.12%** | **57** | **34.55%** | **-4** | **-2.42 pp** |

### Per-Level Attachment Performance
- **Level 1 Attachment** (9 tasks): V5 = 4 correct (44.44%), V4 = 4 correct (44.44%), $\Delta = 0$.
- **Level 1 Non-Attachment** (44 tasks): V5 = 24 correct (54.55%), V4 = 25 correct (56.82%), $\Delta = -1$.
- **Level 2 Attachment** (22 tasks): V5 = 2 correct (9.09%), V4 = 3 correct (13.64%), $\Delta = -1$.
- **Level 2 Non-Attachment** (64 tasks): V5 = 18 correct (28.12%), V4 = 21 correct (32.81%), $\Delta = -3$.
- **Level 3 Attachment** (7 tasks): V5 = 0 correct (0.00%), V4 = 0 correct (0.00%), $\Delta = 0$.
- **Level 3 Non-Attachment** (19 tasks): V5 = 5 correct (26.32%), V4 = 4 correct (21.05%), $\Delta = +1$.

---

## 7. Capability Router Analysis

The router architecture separates reasoning into `DIRECT` text generation and `PYTHON` programmatic generation.

| Metric | V5 System | Matched V4 System |
|---|---:|---:|
| **DIRECT Routed Tasks** | 72 / 165 (43.64%) | 66 / 165 (40.00%) |
| **DIRECT Correct** | 43 / 72 (59.72%) | 42 / 66 (63.64%) |
| **PYTHON Routed Tasks** | 93 / 165 (56.36%) | 99 / 165 (60.00%) |
| **PYTHON Correct** | 10 / 93 (10.75%) | 15 / 99 (15.15%) |
| **Router Fallback Rate** | 1 / 165 (0.61%) | 1 / 165 (0.61%) |

### Route Consistency Between Runs
Across the two 165-task runs:
- **PYTHON $\rightarrow$ PYTHON**: 83 tasks (V4 correct: 12, V5 correct: 10)
- **DIRECT $\rightarrow$ DIRECT**: 56 tasks (V4 correct: 39, V5 correct: 35)
- **DIRECT $\rightarrow$ PYTHON**: 10 tasks (V4 correct: 3, V5 correct: 0)
- **PYTHON $\rightarrow$ DIRECT**: 16 tasks (V4 correct: 3, V5 correct: 8)

Total route agreement across runs: **139 / 165 tasks (84.24%)**. The remaining 26 tasks experienced stochastic routing flips inherent in LLM-based router generation at temperature 0.

---

## 8. Python Execution Funnel Analysis

The Python execution funnel tracks the conversion of tasks routed to `PYTHON` into successfully executed code and verified answers:

| Funnel Stage | V5 System | Matched V4 System |
|---|---:|---:|
| **Routed to PYTHON** | 93 | 99 |
| **Python Code Executed** | 14 (15.05%) | 25 (25.25%) |
| **Execution Succeeded** | 12 (85.71% of executed) | 19 (76.00% of executed) |
| **Execution Failed** | 2 (14.29% of executed) | 6 (24.00% of executed) |
| **Executed & Scorer Correct** | 10 (71.43% of executed) | 15 (60.00% of executed) |
| **Routed but Not Executed** | 79 (84.95%) | 74 (74.75%) |
| **Not Executed & Correct** | 0 (0.00%) | 0 (0.00%) |

### Why Did Routed Tasks Fail to Execute?
In 79 tasks in V5 (and 74 tasks in V4), the Python worker failed to generate an executable Python block.
- **Worker `MALFORMED_FUNCTION_CALL` Anomalies**: 73 of the 79 unexecuted tasks (92.41%) in V5 and 63 of the 74 tasks (85.14%) in V4 terminated abruptly because the upstream Gemini model emitted a `MALFORMED_FUNCTION_CALL` finish reason, even though native function calling was explicitly disabled (`mode="NONE"`).
- **Empty Worker Responses**: 2 tasks in V5 produced empty output.
- **Python Execution Failures**: 2 tasks executed code that threw errors: 1 `SecurityPolicyError` (prohibited system call attempt) and 1 `MissingFinalAnswerMarker`.

When Python code actually executed to completion, its accuracy was very high: **71.43% in V5 (10/14)** and **60.00% in V4 (15/25)**. However, the bottleneck remains upstream worker code emission reliability.

---

## 9. Primary Verifier Mechanism Analysis (Within V5)

This section isolates the **exact causal effect of the verifier intervention** within the V5 pipeline.

```
Total Benchmark Tasks (165)
          |
   [Candidate Check]
   /               \
Empty (84)      Candidate Present (81)
  |                       |
Bypassed (84)      Verifier Invoked (81)
  |                  /              \
  |             KEEP (78)         REVISE (3)
  |             /       \         /        \
  |       Correct (52) Wrong (26) Cor(1)   Fail(2)
  |            |          |        |        |
Stable Fail (84)     Stable Fail (26)  St.Cor(1) St.Fail(2)
```

### Transition Matrix

| Pre-Verification Status | Post-Verification Status | Count | Classification | Net Accuracy Impact |
|---|---|---:|---|---:|
| **Correct** | **Correct** | 53 | Stable Correct | 0 |
| **Correct** | **Incorrect** | 0 | Regression | 0 |
| **Incorrect** | **Correct** | 0 | Improvement | 0 |
| **Incorrect** | **Incorrect** | 112 | Stable Failure | 0 |
| **Total** | **Total** | **165** | - | **Net $\Delta = 0$** |

### Detailed Breakdown of the 3 REVISE Tasks

| Task ID | Level | Pre-Correct | Post-Correct | Verdict | Pre-Answer Summary | Post-Answer Summary | Outcome | Classification |
|---|---:|:---:|:---:|:---:|---|---|---|---|
| `99c9cc74-fdc8-46c6-8f8d-3ce2d3bfeea3` | 1 | True | True | REVISE | Strawberry recipe ingredients list | Strawberry recipe ingredients list | Stable Correct | Normalization / formatting confirmation |
| `7673d772-ef80-4f0f-a602-1bf4485c9b43` | 1 | False | False | REVISE | Legal witness rule markdown list | `business` (Ground truth: `inference`) | Stable Failure | Word extraction error |
| `e4e91f1c-1dcd-439e-9fdd-cb976f5293fd` | 2 | False | False | REVISE | Truncated reasoning snippet | `cloak` (Worker had `MAX_TOKENS`) | Stable Failure | Operational completion invalidation |

Across all three revisions:
1. `99c9cc74`: The candidate answer was already correct. The verifier confirmed the ingredients list in identical normalized form. Correctness remained `True`.
2. `7673d772`: Upstream worker returned an entire markdown list of legal rules instead of the specific rule title. The verifier correctly recognized that a single term was required, but revised it to `"business"` instead of ground-truth `"inference"`. Correctness remained `False`.
3. `e4e91f1c`: The upstream worker hit `MAX_TOKENS` during generation. The verifier extracted the concise word `"cloak"`. However, because the upstream worker truncated, benchmark rules strictly mandate `completion_success=False`, precluding scorer credit. Correctness remained `False`.

**Empirical Result**: Zero improvements, zero regressions. Net verifier accuracy change: **0.00 pp**.

---

## 10. Matched System-Level Transitions (V5 vs Matched V4)

To understand why V5 achieved 53 correct while matched V4 achieved 57 correct, we examine the cross-system task transitions:

| Category | Definition | Task Count |
|---|---|---:|
| **Both Correct** | Correct in both V4 and V5 | 42 |
| **Both Wrong** | Incorrect in both V4 and V5 | 97 |
| **System Improvement** | Incorrect in V4 $\rightarrow$ Correct in V5 | 11 |
| **System Regression** | Correct in V4 $\rightarrow$ Incorrect in V5 | 15 |
| **Net System Delta** | Improvements (11) - Regressions (15) | **-4** |

### Per-Level System Transitions
- **Level 1**: Both Correct = 24, Both Wrong = 20, V4 Wrong $\rightarrow$ V5 Correct = 4, V4 Correct $\rightarrow$ V5 Wrong = 5 (Net = -1).
- **Level 2**: Both Correct = 14, Both Wrong = 56, V4 Wrong $\rightarrow$ V5 Correct = 6, V4 Correct $\rightarrow$ V5 Wrong = 10 (Net = -4).
- **Level 3**: Both Correct = 4, Both Wrong = 21, V4 Wrong $\rightarrow$ V5 Correct = 1, V4 Correct $\rightarrow$ V5 Wrong = 0 (Net = +1).

### Causal Attribution Analysis
Could the -4 task deficit be caused by the verifier?
- **Mathematical Impossibility**: We established in Section 9 that the verifier caused exactly **0 regressions** and **0 improvements** across all 165 tasks. For every task in V5, the final answer accuracy was identical to the pre-verification answer accuracy ($\Delta_{\text{verifier}} = 0$).
- **Upstream Stochasticity**: The 11 improvements and 15 regressions occurred upstream of the verifier, caused by:
  1. Router divergence on 26 tasks (Section 7).
  2. Worker generation variance (e.g. 14 Python executions in V5 vs 25 in V4).
  3. API-level provider anomalies (`MALFORMED_FUNCTION_CALL` firing on 76 tasks in V5 vs 65 tasks in V4).

Therefore, the -4 task difference is an upstream variance artifact between runs, completely independent of the verification mechanism.

---

## 11. Failure Taxonomy and Mechanism Analysis

Out of 165 tasks, V5 failed on **112 tasks (67.88%)**. These failures fall cleanly into two mutually exclusive, comprehensive categories:

```
Total Failures (112)
    |
    ├── Category A: Upstream Missing Candidate (84 / 112 = 75.00%)
    |     ├── Worker MALFORMED_FUNCTION_CALL Anomaly: 76 (67.86% of failures)
    |     ├── Python Execution Failure / Timeout: 6 (5.36% of failures)
    |     └── Empty Worker Response: 2 (1.79% of failures)
    |
    └── Category B: Completed Candidate Incorrect (28 / 112 = 25.00%)
          ├── Verifier Issued KEEP (Preserved Incorrect): 26 (23.21% of failures)
          └── Verifier Issued REVISE (Still Incorrect): 2 (1.79% of failures)
```

### Key Failure Insights
1. **Upstream Dominance (75.0% of failures)**: Three-quarters of all failures occurred before the verifier could even be invoked. The primary failure mode was the Gemini API `MALFORMED_FUNCTION_CALL` anomaly on Python workers.
2. **Verifier Blindness on Incorrect Candidates (25.0% of failures)**: On the 28 tasks where an incorrect candidate was submitted to the verifier, the verifier issued KEEP on 26 of them (92.86%). The verifier exhibited strong confirmation bias, accepting plausible-sounding but factually or numerically incorrect candidate answers.
3. **Attachment Difficulty**: Attachment tasks suffered an 84.21% failure rate (32/38 failed), driven by unsupported multimodal formats (`.mp3`, `.zip`, `.pdb`), complex spreadsheet operations (`.xlsx`, 12/13 failed), and image reasoning without vision tools (`.png`, 8/8 failed).

---

## 12. Operational Metrics and Overhead

Evaluating the resource cost of adding the one-shot verification stage:

| Metric | V5 System | Matched V4 System | Net Overhead of V5 |
|---|---:|---:|---:|
| **Average End-to-End Latency** | 28.28s | 22.63s | +5.65s (+25.0%) |
| **Median End-to-End Latency** | 15.87s | 13.26s | +2.61s (+19.7%) |
| **Average Router Latency** | 9.43s | 7.97s | +1.46s |
| **Average Worker Latency** | 12.78s | 11.47s | +1.31s |
| **Average Verifier Latency** | 7.13s (when run) | N/A | +7.13s |
| **Average Input Tokens** | 2,399.2 | 2,317.2 | +82.0 tokens |
| **Average Output Tokens** | 190.9 | 181.6 | +9.3 tokens |
| **Average Thinking Tokens** | 666.4 | 646.1 | +20.3 tokens |
| **Average Total Tokens** | 3,246.1 | 3,143.7 | +102.4 tokens (+3.3%) |
| **Average Verifier Tokens** | 2,671.2 (when run) | N/A | 2,671.2 tokens |
| **Maximum LLM Calls per Task** | 3 | 2 | +1 call |

Adding the verifier added approximately 5.65 seconds of end-to-end latency per task across the full benchmark (7.13 seconds on eligible tasks) and a modest 3.3% increase in total token consumption.

---

## 13. Methodological Limitations

1. **Known Timing Discrepancy in Level 2**: V5 Level 2 was run with the default inter-task delay (1.0s), while matched V4 Level 2 was run with a 5.0s delay. Because delay is strictly an external rate-limit throttling parameter, and provider telemetry confirms healthy API execution on both sides (identical router fallback rates of 1/86 and 100% search success), this discrepancy is classified as an operational non-blocking limitation.
2. **Provider Anomaly Confound**: The presence of the Gemini `MALFORMED_FUNCTION_CALL` anomaly severely constricted the downstream verifier eligibility funnel by eliminating 76 potential candidate answers.
3. **No External Grounding for Verifier**: The verifier had access only to the frozen upstream search results and extracted file text. It had no ability to query new web information or run code to verify calculations.

---

## 14. Scientific Conclusion

Based on rigorous statistical and architectural analysis of the full 165-task benchmark:

1. **The V5 post-answer verification stage demonstrated flawless failure safety**, achieving zero regressions ($1 \rightarrow 0$) and zero corruption of valid candidate answers across all 165 tasks.
2. **The conservative verification mechanism produced no empirical accuracy gain** ($\Delta = 0.00\text{ pp}$ within V5), driven by strong confirmation bias on incorrect candidates (92.86% KEEP rate on wrong answers) and severe upstream candidate starvation (50.91% empty candidates).
3. **The observed -4 task system difference (-2.42 pp) between V5 and matched V4 is causally decoupled from the verifier**, resulting entirely from upstream worker stochasticity and provider-level completion failures.
4. **Post-answer verification without active tool use or execution feedback is insufficient to resolve complex agentic benchmark failures**, demonstrating that verification mechanisms require active verification capabilities (such as test execution or targeted search) rather than passive textual reflection.

