# V5 Final 165-Task Analysis: One-Shot Post-Answer Verification on GAIA

## Executive Summary

This document presents the final scientific analysis of **V5 (One-Shot Post-Answer Verification)** evaluated on the complete 165-task GAIA validation benchmark, compared alongside a contemporaneously executed, matched **V4 (Explicit Two-Stage Capability Router)** control baseline.

### Key Results

1. **Within-V5 Verification Mechanism**:
   - Pre-verification correctness: **53 / 165 tasks (32.12%)**
   - Post-verification correctness: **53 / 165 tasks (32.12%)**
   - Improvements ($0 \rightarrow 1$): **0 tasks**
   - Regressions ($1 \rightarrow 0$): **0 tasks**
   - Stable Correct ($1 \rightarrow 1$): **53 tasks**
   - Stable Failure ($0 \rightarrow 0$): **112 tasks**
   - Net accuracy impact: **0 tasks (0.00 percentage points)**
   - Candidate availability: 81 tasks produced non-empty candidate answers and were verified; 84 tasks had empty candidates and bypassed verification.
   - Verifier actions: **78 KEEP**, **3 REVISE**, **0 fallbacks**.
   - Within the canonical V5 run, the verifier produced no net change in official GAIA correctness. Three answers were revised, but none changed official scorer correctness.

2. **Matched System-Level Comparison**:
   - V5 overall accuracy: **53 / 165 tasks (32.12%)**
   - Matched V4 overall accuracy: **57 / 165 tasks (34.55%)**
   - Observed system-level difference: **-4 tasks (-2.42 percentage points)**
   - The observed -4-task system-level difference occurred across separate stochastic runs and may reflect differences in upstream generation, routing, provider behavior, retrieval outputs, execution outcomes, and the additional V5 generation exposure. The matched comparison does not isolate a pure causal effect of verification.

3. **Verifier Action Funnel and Conservatism**:
   - **Eligibility**: 81 / 165 tasks (49.09%) yielded non-empty candidate answers from upstream workers; 84 / 165 tasks (50.91%) had empty candidates upstream and bypassed verification.
   - **Verdicts**: On the 81 eligible tasks, the verifier issued **78 KEEP (96.30%)** and **3 REVISE (3.70%)** decisions.
   - **Revision Outcomes**: All 3 revised tasks resulted in net-neutral outcomes (1 remained stable correct, 2 remained stable failure; 0 net accuracy change).
   - **Failure-Safe Preservation**: 100% of KEEP decisions and all fallbacks strictly preserved the upstream candidate answer.

---

## Experimental Definition

V5 is defined architecturally as:

$$\text{V5} = \text{frozen V4} + \text{one-shot conservative post-answer verification/revision}$$

### Upstream Architecture (Frozen V4)
- **Web Search**: At most one Tavily search query ($N \le 1$) when enabled.
- **File Tool**: At most one deterministic file extraction ($N \le 1$) for tasks requiring attachments.
- **Capability Router**: An explicit routing generation directing the task to either `DIRECT` or `PYTHON` worker tracks. Native Gemini function calling is disabled (`mode="NONE"`).
- **Worker Execution**:
  - `DIRECT`: Worker generates a response text directly.
  - `PYTHON`: Worker emits a code block executed in a deterministic local sandbox ($N \le 1$ execution). Native function calling is disabled (`mode="NONE"`).
- **Sampling Configuration**: Executed under the provider-default sampling configuration (where temperature was not explicitly fixed by project configuration).

### Downstream Verification Mechanism
- **Eligibility Filter**: If the upstream worker outputs an empty candidate, the verifier is bypassed immediately to maintain empty-candidate failure safety.
- **Single-Pass Evaluation**: If a candidate answer is present, a dedicated verifier LLM call evaluates the question, search evidence, file context, and candidate answer.
- **Structured Verdicts**:
  - `KEEP`: Retain the upstream candidate answer without modification.
  - `REVISE`: Substitute an alternative answer.
- **No Active Capabilities**: The verifier has no tool access, cannot invoke Python, cannot execute web searches, and cannot retry.
- **Hard Generation Cap**: Total LLM generation calls per task are strictly capped at $\le 3$ (1 router + 1 worker + 1 verifier).

---

## Canonical Dataset Integrity

- **Validation Split**: All 165 tasks of the GAIA validation set (Level 1: 53, Level 2: 86, Level 3: 26).
- **Task Identity Parity**: Task IDs match 100% pairwise between V5 and the matched V4 control run, with zero duplicate rows.
- **Scorer Provenance**: Evaluated uniformly using `official-gaia-leaderboard` (`commit 9f133d71362e77b3539f1514f31b9c101a545fec`).

---

## Overall Results

The table below summarizes performance across the 165 GAIA validation tasks for V5 and the matched V4 control run:

| Level | Total Tasks | V5 Correct | V5 Acc (%) | V5 Completed | V5 Comp (%) | Matched V4 Correct | Matched V4 Acc (%) | Matched V4 Completed | Matched V4 Comp (%) | Task Delta | Accuracy Delta (pp) | Completed Delta |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
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

## Completion and Candidate Availability

In benchmark evaluation, **operational completion** (`completion_success=True`) requires normal model termination (`finish_reason == "STOP"`) with a non-empty response string. Truncated generations (`MAX_TOKENS`) evaluate to `False`.

In V5:
- **Operational Completion (`completion_success`)**: 78 / 165 tasks (47.27%).
- **Candidate Answer Availability**: 81 / 165 tasks (49.09%).
- **Verifier Eligibility**: 81 / 165 tasks (49.09%).

The 3-task difference between candidate availability (81) and operational completion (78) represents tasks where upstream workers generated text allowing candidate extraction, but encountered generation limits (`finish_reason == "MAX_TOKENS"`), resulting in `completion_success=False`. Under GAIA benchmark rules, incomplete tasks cannot score as correct.

---

## Attachment Analysis

Performance segmented by whether the task required processing an attached file:

| Level | Subset | Task Count | V5 Correct | V5 Acc (%) | Matched V4 Correct | Matched V4 Acc (%) | Task Delta | pp Delta |
|:---|:---|---:|---:|---:|---:|---:|---:|---:|
| **Level 1** | Attachment | 11 | 2 | 18.18% | 3 | 27.27% | -1 | -9.09 pp |
| | Non-Attachment | 42 | 26 | 61.90% | 26 | 61.90% | 0 | 0.00 pp |
| **Level 2** | Attachment | 20 | 4 | 20.00% | 4 | 20.00% | 0 | 0.00 pp |
| | Non-Attachment | 66 | 16 | 24.24% | 20 | 30.30% | -4 | -6.06 pp |
| **Level 3** | Attachment | 7 | 0 | 0.00% | 0 | 0.00% | 0 | 0.00 pp |
| | Non-Attachment | 19 | 5 | 26.32% | 4 | 21.05% | +1 | +5.26 pp |
| **Overall** | **Attachment** | **38** | **6** | **15.79%** | **7** | **18.42%** | **-1** | **-2.63 pp** |
| | **Non-Attachment** | **127** | **47** | **37.01%** | **50** | **39.37%** | **-3** | **-2.36 pp** |
| | **Total** | **165** | **53** | **32.12%** | **57** | **34.55%** | **-4** | **-2.42 pp** |

Attachment tasks presented substantial difficulty across both systems, with an overall accuracy of 15.79% (V5) and 18.42% (Matched V4). Non-attachment accuracy was 37.01% (V5) and 39.37% (Matched V4).

---

## Router Analysis

The router architecture separates reasoning into `DIRECT` text generation and `PYTHON` programmatic generation. Observed routing distributions across the two separate runs:

| Metric | V5 System | Matched V4 System |
|:---|---:|---:|
| **DIRECT Routed Tasks** | 72 / 165 (43.64%) | 66 / 165 (40.00%) |
| **DIRECT Correct** | 43 / 72 (59.72%) | 42 / 66 (63.64%) |
| **PYTHON Routed Tasks** | 93 / 165 (56.36%) | 99 / 165 (60.00%) |
| **PYTHON Correct** | 10 / 93 (10.75%) | 15 / 99 (15.15%) |
| **Router Fallback Count** | 1 / 165 (0.61%) | 1 / 165 (0.61%) |

### Route Consistency Between Runs
Across the two separate runs:
- **PYTHON $\rightarrow$ PYTHON**: 83 tasks (V4 correct: 12, V5 correct: 10)
- **DIRECT $\rightarrow$ DIRECT**: 56 tasks (V4 correct: 39, V5 correct: 35)
- **DIRECT $\rightarrow$ PYTHON**: 10 tasks (V4 correct: 3, V5 correct: 0)
- **PYTHON $\rightarrow$ DIRECT**: 16 tasks (V4 correct: 3, V5 correct: 8)

Route agreement between the two separate runs was 139 / 165 tasks (84.24%). The remaining 26 tasks exhibited different route classifications under the provider-default sampling configuration.

---

## Python Funnel

The Python execution funnel tracks the conversion of tasks routed to `PYTHON` into successfully executed code and verified answers:

| Funnel Stage | V5 System | Matched V4 System |
|:---|---:|---:|
| **Routed to PYTHON** | 93 | 99 |
| **Python Code Executed** | 14 (15.05%) | 25 (25.25%) |
| **Execution Succeeded (Exit 0)** | 12 (85.71% of executed) | 19 (76.00% of executed) |
| **Execution Failed** | 2 (14.29% of executed) | 6 (24.00% of executed) |
| **Executed & Scorer Correct** | 10 (71.43% of executed) | 15 (60.00% of executed) |
| **Routed but Not Executed** | 79 (84.95%) | 74 (74.75%) |
| **Not Executed & Correct** | 0 (0.00%) | 0 (0.00%) |

### Why Did Routed Tasks Fail to Execute?
In 79 tasks in V5 (and 74 in V4), tasks routed to Python did not execute code:
- In 73 tasks in V5 and 63 in V4, the Python worker run encountered a provider-reported `MALFORMED_FUNCTION_CALL` finish-reason anomaly despite native function calling being disabled (`mode="NONE"`).
- In 2 tasks in V5, the worker produced empty responses.
- In 2 tasks in V5 where code executed, failures occurred: 1 `SecurityPolicyError` and 1 `MissingFinalAnswerMarker`.

When Python code executed to completion, its accuracy was high: **71.43% in V5 (10/14)** and **60.00% in V4 (15/25)**. However, upstream worker code emission reliability remained a primary constraint.

---

## Verification Mechanism

Within the V5 pipeline, isolating pre-verification from post-verification answers yielded the following transition distribution:

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

| Pre-Verification Status | Post-Verification Status | Task Count | Transition Category | Net Correctness Change |
|:---|:---|---:|:---|---:|
| **Correct** | **Correct** | 53 | Stable Correct | 0 |
| **Correct** | **Incorrect** | 0 | Regression | 0 |
| **Incorrect** | **Correct** | 0 | Improvement | 0 |
| **Incorrect** | **Incorrect** | 112 | Stable Failure | 0 |
| **Total** | **Total** | **165** | - | **0 tasks (0.00 pp)** |

- **Bypassed on Missing Candidate**: 84 tasks.
- **Eligible Candidates Evaluated**: 81 tasks.
- **Verdicts Issued**: 78 KEEP, 3 REVISE, 0 fallback.

---

## KEEP Analysis

Among the 81 eligible candidate answers evaluated by the verifier:
- **Total KEEP Verdicts**: 78 tasks (96.30% of eligible).
- **Candidate Preservation**: In 78 of 78 tasks (100%), the post-verification answer matched the pre-verification candidate answer exactly.
- **Accuracy within KEEP Tasks**:
  - Correct candidate preserved: 52 tasks.
  - Incorrect candidate preserved: 26 tasks.
  - KEEP rate among incorrect eligible candidates: **26 / 28 (92.86%)**.
- The verifier preserved most incorrect candidates that reached it, demonstrating a high acceptance rate for candidate answers that appeared plausible in context.

---

## REVISE Analysis

The verifier issued a `REVISE` verdict on 3 tasks (3.70% of eligible candidates). In all three cases, the revision did not change official scorer correctness:

| Task ID | Level | Pre Correct | Post Correct | Transition | Answer Changed | Revision Class | Sanitized Outcome Description |
|:---|---:|:---:|:---:|:---:|:---:|:---|:---|
| `99c9cc74-fdc8-46c6-8f8d-3ce2d3bfeea3` | 1 | True | True | Stable Correct | False | formatting normalization | Candidate answer was already correct under official scoring. Verifier confirmed and preserved normalized answer format. |
| `7673d772-ef80-4f0f-a602-1bf4485c9b43` | 1 | False | False | Stable Failure | True | factual/content revision | Upstream candidate was a markdown list. Verifier revised it to a concise term, but the revised answer remained incorrect under the official scorer. |
| `e4e91f1c-1dcd-439e-9fdd-cb976f5293fd` | 2 | False | False | Stable Failure | True | list reduction | Upstream worker encountered token truncation (MAX_TOKENS). Verifier revision produced text compatible with expected answer format/content, but the task remained officially incorrect under the benchmark completion/scoring state. |

**Empirical Result**: Zero improvements, zero regressions. Net verifier accuracy change: **0.00 pp**.

---

## V5 vs Matched V4

Observed task-level transition pairing between the separate V4 and V5 runs:

| Transition Category | Level 1 | Level 2 | Level 3 | Total Tasks |
|:---|---:|---:|---:|---:|
| **Both Correct** | 24 | 14 | 4 | **42** |
| **Both Wrong** | 20 | 56 | 21 | **97** |
| **V4 Wrong $\rightarrow$ V5 Correct (Observed System Improvement)** | 4 | 6 | 1 | **11** |
| **V4 Correct $\rightarrow$ V5 Wrong (Observed System Regression)** | 5 | 10 | 0 | **15** |
| **Observed Net Difference** | **-1** | **-4** | **+1** | **-4** |

The observed -4-task difference represents the net of 11 tasks that were incorrect in V4 but correct in V5, and 15 tasks that were correct in V4 but incorrect in V5. The observed V5-vs-matched-V4 difference arose across separate stochastic runs and should not be attributed to any single mechanism without stronger causal evidence. This cross-run difference may reflect upstream stochastic variation, including differences in routing, worker generation, retrieval outputs, provider behavior, and execution outcomes.

---

## Failure Analysis

Across the 112 tasks where V5 was scored incorrect:

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

1. **Category A: Missing Candidate / Upstream Failure (84 / 112 = 75.00% of failures)**
   - Tasks failed to generate a candidate answer; verifier was bypassed.
   - Provider-reported `MALFORMED_FUNCTION_CALL` finish-reason anomaly despite native function calling disabled: 76 tasks.
   - Python sandbox execution failures or missing answer markers: 6 tasks.
   - Empty worker responses: 2 tasks.

2. **Category B: Completed Candidate Incorrect (28 / 112 = 25.00% of failures)**
   - Tasks produced a candidate answer, but it was incorrect under official scoring.
   - Verifier issued KEEP (preserved incorrect candidate): 26 tasks (92.86% of wrong candidates).
   - Verifier issued REVISE (revised answer remained incorrect): 2 tasks (7.14% of wrong candidates).

3. **Attachment Failures**:
   - 32 of 38 attachment tasks failed (84.21%), concentrated in `.xlsx` (12/13), `.png` (8/8), `.mp3` (2/3), and `.zip` (2/2).

---

## Operational Overhead

Observed runtime telemetry across the separate benchmark executions:

| Metric | Observed V5 | Observed Matched V4 | Observed Difference |
|:---|---:|---:|---:|
| **Mean End-to-End Latency** | 28.28s | 22.63s | +5.65s |
| **Median End-to-End Latency** | 15.87s | 13.26s | +2.61s |
| **Mean Router Latency** | 9.43s | 7.97s | +1.46s |
| **Mean Worker Latency** | 12.78s | 11.47s | +1.31s |
| **Mean Verifier Latency (when invoked)** | 7.13s | N/A | N/A |
| **Mean Total Tokens** | 3,246.1 | 3,143.7 | +102.4 tokens |
| **Mean Verifier Tokens (when invoked)** | 2,671.2 | N/A | N/A |
| **Maximum LLM Calls per Task** | 3 | 2 | +1 call |

The observed end-to-end system-level latency difference was +5.65 seconds on average across all 165 tasks. On tasks where the verifier was invoked (81 tasks), the verification stage itself averaged 7.13 seconds and 2,671.2 tokens.

---

## Limitations

1. **Separate Stochastic Runs**: The comparison between V5 and matched V4 was conducted across separately executed runs under the provider-default sampling configuration (where temperature was not explicitly fixed by the project configuration), introducing run-to-run sampling variance in routing and generation.
2. **Level 2 Delay Discrepancy**: V5 Level 2 ran with a 1.0s inter-task delay, whereas matched V4 Level 2 ran with a 5.0s delay. While telemetry confirms healthy API response rates on both sides, inter-task throttling was not identical.
3. **Provider Anomalies**: Upstream Python workers frequently encountered `MALFORMED_FUNCTION_CALL` finish reasons despite function calling being disabled, causing 76 tasks to produce no candidate answer and constricting the verifier eligibility pool.
4. **Limited Revision Sample**: Only 3 tasks received REVISE verdicts, limiting statistical observations of revision efficacy.
5. **Passive Verification Scope**: The verifier operated solely on static text without the ability to query new web data or execute code.

---

## Scientific Conclusion

In this canonical V5 run, one-shot conservative post-answer verification produced zero improvements and zero regressions under the official GAIA scorer, leaving accuracy unchanged at 53/165. V5 as a complete system solved 53/165 tasks versus 57/165 for the matched V4 control, but the separate-run comparison does not isolate a pure causal verifier effect.

1. **The V5 post-answer verification stage demonstrated conservative failure safety**, achieving zero regressions ($1 \rightarrow 0$) and zero corruption of valid candidate answers across all 165 tasks.
2. **The conservative verification mechanism produced no empirical accuracy gain** ($\Delta = 0.00\text{ pp}$ within V5), with the verifier accepting 92.86% of incorrect candidates that reached it, alongside significant upstream candidate starvation (50.91% empty candidates).
3. **The observed -4 task system difference (-2.42 pp) between V5 and matched V4 occurred across separate runs**, which may reflect differences in upstream routing, worker generation, retrieval outputs, provider behavior, and execution outcomes rather than an isolated verifier effect.
4. **In this V5 configuration, a single conservative text-only post-answer verifier did not improve official GAIA accuracy.** While passive post-answer verification preserved existing correct answers, it did not resolve errors on incorrect candidate answers in this evaluation.

Future versions could test whether verification mechanisms with additional evidence-gathering, execution, or targeted re-checking capabilities perform differently.
