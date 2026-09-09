# V3 — Controlled Single-Shot Python Execution Baseline

Status: FROZEN

Branch: `v3-python-execution`

Parent Baseline: Frozen V2 (`v2-file-attachments-final`, commit `96f5b229c7c0ae8e58b83855c97ca7564ee495ef`)

---

## 1. Research Definition & Capability Boundary

```text
V3 = V2 + controlled single-shot local Python execution
```

The research question evaluated by V3 is:
> *How much does adding controlled local Python execution improve GAIA performance beyond single-shot web retrieval and direct attachment access?*

### Strict Capability Invariants
V3 enforces strict capability bounds to prevent confounding the ablation:
- **Single Gemini Generation**: Exactly one Gemini call per task (`llm_generation_count == 1`).
- **At Most One Python Execution**: Maximum one Python execution per task (`python_execution_count in {0, 1}`).
- **No Second LLM Synthesis**: Direct extraction of the Python stdout answer without an extra LLM reasoning turn.
- **No Python Retry**: Execution failures immediately fall back to model direct answer if present; no multi-turn debugging.
- **No Autonomous Tool Loops**: Model cannot iteratively invoke tools.
- **Tools Disabled at Generation**: Gemini function calling disabled (`mode="NONE"`).
- **Web Search Invariance**: Exactly one Tavily search per task on the original question (`search_depth="basic"`, `max_results=5`).
- **FileTool Invariance**: Frozen V2 file extraction semantics preserved unchanged.
- **Prohibited Capabilities**: No planner/router, no multi-hop search, no query rewriting, no verification/reflection, no OCR, no browser automation, and no RAG.

---

## 2. Configuration Manifest

- **Project Version**: `v3`
- **Research Label**: controlled single-shot Python execution
- **Parent Baseline**: frozen V2
- **Model**: `gemini-3.5-flash-lite`
- **Thinking Level**: `medium`
- **Max Output Tokens**: `2048`
- **Temperature**: provider default / `None`
- **Prompt Version**: `python-execution-v1`
- **Official Scorer Commit**: `9f133d71362e77b3539f1514f31b9c101a545fec`
- **Dataset**: GAIA 2023 Validation split (165 tasks: Level 1: 53, Level 2: 86, Level 3: 26)
- **Search Configuration**:
  - Provider: Tavily
  - Depth: basic
  - Max results: 5
  - Executions per task: maximum 1
  - Query used: original question (capped at 1,500 characters)
  - Retries: 0
- **Python Execution Configuration**:
  - Max executions per task: 1
  - Timeout: 15.0 seconds
  - Output length cap: 20,000 characters
  - Mode: isolated subprocess (`-I`)
  - Working directory: ephemeral temporary directory (`tempfile.mkdtemp`)
  - Attachment security: read-only copies
  - Security policy: static AST validation blocking dangerous modules (`subprocess`, `socket`, `urllib`, `requests`, `aiohttp`, `importlib`, `ctypes`, `multiprocessing`), dangerous functions (`os.system`, `eval`, `exec`, `compile`), and path traversal (`..` or absolute paths)
  - Isolation boundary: best-effort research execution isolation
  - Retries permitted: 0
  - Fallback on failure: deterministic extraction from model direct text if available
- **Frozen Invariants**:
  - `llm_generation_count == 1`
  - `python_execution_count in {0, 1}`

---

## 3. Canonical Controlled Results

Scored using the official GAIA leaderboard evaluation suite against the contemporaneous matched V2 control on the complete GAIA 2023 Validation set (165 tasks).

### Benchmark Performance Summary

| Metric | Matched V2 Control | Canonical V3 | Controlled Delta |
| :--- | :---: | :---: | :---: |
| **Overall Accuracy** | **39.39%** (65 / 165) | **29.09%** (48 / 165) | **-10.30 pp** |
| Level 1 Accuracy | 58.49% (31 / 53) | 45.28% (24 / 53) | -13.21 pp |
| Level 2 Accuracy | 34.88% (30 / 86) | 26.74% (23 / 86) | -8.14 pp |
| Level 3 Accuracy | 15.38% (4 / 26) | 3.85% (1 / 26) | -11.53 pp |
| **Attachment Tasks** | **42.11%** (16 / 38) | **21.05%** (8 / 38) | **-21.05 pp** |
| **Non-Attachment Tasks** | **38.58%** (49 / 127) | **31.50%** (40 / 127) | **-7.09 pp** |
| **Completion Rate** | **65.45%** (108 / 165) | **78.18%** (129 / 165) | **+12.73 pp** |

### Execution & Operational Counts
- **Total Tasks**: 165
- **Completed Tasks**: 129 / 165 (78.18%)
- **Python Executed**: 95 / 165 (57.58%)
- **Python Success**: 26 / 95 (27.37%)
- **Python Failures**: 69 / 95 (72.63%)
- **Python Fallbacks**: 69 / 95 (72.63%)

---

## 4. Task Transition Analysis

Pairwise comparison of task outcomes between matched V2 control and V3:

| Transition Category | Count | Percentage |
| :--- | :---: | :---: |
| **Improvements** (V2 Fail → V3 Correct) | 8 | 4.85% |
| **Regressions** (V2 Correct → V3 Fail) | 25 | 15.15% |
| **Stable Correct** (V2 Correct → V3 Correct) | 40 | 24.24% |
| **Stable Failure** (V2 Fail → V3 Fail) | 92 | 55.76% |
| **Total Tasks** | **165** | **100.00%** |

**Net Task Delta**: 8 - 25 = **-17 tasks** (-10.30 pp).

---

## 5. Audited Regression Mechanism Decomposition

A rigorous audit of all 25 observed regressions demonstrates:

| Regression Mechanism Category | Count | Percentage of Regressions |
| :--- | :---: | :---: |
| Python execution failure-associated regressions | 12 | 48.00% |
| Provider-response anomaly-associated regressions | 10 | 40.00% |
| Successful-Python wrong-answer regressions | 3 | 12.00% |
| Ordinary completed direct-answer regressions | 0 | 0.00% |
| **Total Regressions** | **25** | **100.00%** |

### Key Regression Takeaway
**22 of 25 regressions (88.0%)** were associated with either Python execution failures or upstream provider anomalies (`MALFORMED_FUNCTION_CALL`), rather than erroneous calculations following successful code execution.

*(Note: These associations describe operational co-occurrence and do not imply a single causal factor.)*

---

## 6. Python Failure Taxonomy

Across all 69 tasks where the agent attempted Python execution but failed to obtain an answer from the interpreter:

| Failure Taxonomy Category | Count | Percentage of Failures | Description |
| :--- | :---: | :---: | :--- |
| `MissingFinalAnswerMarker` | 60 | 86.96% | Subprocess exited cleanly (code 0) but stdout lacked the required `FINAL_ANSWER:` marker |
| `SecurityPolicyError` | 5 | 7.25% | Rejected by static AST validator (e.g. attempted network, subprocess, or forbidden modules) |
| Unavailable Dependency | 4 | 5.80% | Runtime `ModuleNotFoundError` (missing external packages in the environment) |
| Timeout | 0 | 0.00% | Process did not exceed the 15.0s limit |
| Other Runtime Crash | 0 | 0.00% | No uncaught runtime crashes |
| **Total Python Failures** | **69** | **100.00%** | |

**Main Reliability Finding**:
> 60 of 69 Python execution failures (86.96%) were clean process executions that failed the required `FINAL_ANSWER:` extraction contract.

---

## 7. Successful-Python Matched Subset Analysis

On the subset of 26 tasks where Python executed and successfully satisfied the extraction contract:
- **V3 Correct**: 12 / 26 (46.15%)
- **Matched V2 Correct**: 12 / 26 (46.15%)
- **Improvements**: 3
- **Regressions**: 3
- **Stable Correct**: 9
- **Stable Failure**: 11
- **Net Transition**: 0

### Methodological Caveat
> **Endogenous Routing Warning**: This subgroup comparison is strictly descriptive. Python routing was chosen endogenously by the model based on task complexity, perceived computational difficulty, and prompt phrasing. Because routing was not randomized, this comparison does not measure a causal effect of Python execution.

---

## 8. Final Research Summary

### Experimental Result
> Under the frozen single-generation V3 policy, adding controlled Python execution reduced matched GAIA accuracy from 39.39% to 29.09% (-10.30 percentage points), while completion increased from 65.45% to 78.18%.

### Mechanism Finding
> Most observed regressions were associated with Python execution failures or provider-response anomalies rather than incorrect outputs following successful Python execution.

### Successful-Python Subset
> On the 26 tasks where Python execution completed successfully, V3 and matched V2 each solved 12 tasks, with 3 improvements and 3 regressions.

Immediately state that this subgroup comparison is descriptive because Python routing is endogenous.

### Main Reliability Finding
> 60 of 69 Python execution failures (86.96%) were clean process executions that failed the required `FINAL_ANSWER:` extraction contract.

### Scientific Boundaries & Inferences
- Do not claim that Python is inherently harmful.
- Do not claim that routing alone caused the regression.
- Do not claim that V4 will fix V3.

---

## 9. Canonical Artifact Locations

All canonical evaluation records, predictions, summaries, and analysis artifacts are preserved and immutable:

- **V3 Predictions**:
  - `experiments/v3/predictions_level_1.jsonl`
  - `experiments/v3/predictions_level_2.jsonl`
  - `experiments/v3/predictions_level_3.jsonl`
- **V3 Summaries**:
  - `experiments/v3/summary_level_1.json`
  - `experiments/v3/summary_level_2.json`
  - `experiments/v3/summary_level_3.json`
- **V3 Detailed Evaluation**:
  - `experiments/v3/detailed_eval_level_1.jsonl`
  - `experiments/v3/detailed_eval_level_2.jsonl`
  - `experiments/v3/detailed_eval_level_3.jsonl`
- **Matched V2 Controls**:
  - `experiments/v3_matched_v2/predictions_level_1.jsonl`
  - `experiments/v3_matched_v2/predictions_level_2.jsonl`
  - `experiments/v3_matched_v2/predictions_level_3.jsonl`
  - `experiments/v3_matched_v2/detailed_eval_level_1.jsonl`
  - `experiments/v3_matched_v2/detailed_eval_level_2.jsonl`
  - `experiments/v3_matched_v2/detailed_eval_level_3.jsonl`
  - `experiments/v3_matched_v2/summary_level_1.json`
  - `experiments/v3_matched_v2/summary_level_2.json`
  - `experiments/v3_matched_v2/summary_level_3.json`
- **V3 Post-Benchmark Error Analysis**:
  - `experiments/v3/error_analysis_level_1.json`
  - `experiments/v3/error_analysis_level_2.json`
  - `experiments/v3/error_analysis_level_3.json`
  - `experiments/v3/error_analysis_overall.json`
  - `experiments/v3/v2_v3_task_transitions.json`
  - `experiments/v3/v2_v3_error_comparison.json`
  - `experiments/v3/comparison_summary.json`
  - `experiments/v3/python_execution_analysis.json`

---

## 10. Freeze Rule

V3 is frozen as the immutable research baseline for controlled single-shot local Python execution:

```text
V3 = V2 + controlled single-shot local Python execution
```

Future work must not alter V3 results, agent runtime behavior, prompts, model settings, tool configurations, or benchmark evaluations. Any subsequent planner/router, iterative loop, or verification work belongs to V4.
