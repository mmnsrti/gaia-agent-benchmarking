# V4 — Explicit Two-Stage Capability Router

Status: FROZEN

Branch: `v4-planner-router`

Parent Baseline: Frozen V3 (`v3-python-execution-final`, commit `f1a8e9d9e6eb132ca6cf6a09048c1e7ceebad573`)

---

## 1. Research Definition & Capability Boundary

```text
V4 = frozen V3 + explicit two-stage DIRECT/PYTHON capability-routing architecture
```

The research question evaluated by V4 is:
> *How does adding an explicit capability-routing stage affect GAIA performance, completion, reliability, latency, and tool utilization relative to frozen V3?*

Secondary research question:
> *Does explicit routing alter the frequency and reliability profile of Python execution compared with V3's implicit self-routing policy?*

### System-Level Intervention Bundle Definition
The primary comparison between V4 and contemporaneous matched V3 does **NOT** measure an isolated causal effect of capability routing alone. Rather, V4 evaluates the **controlled system-level effect of introducing an explicit two-stage capability-routing architecture**, which inherently bundles:
1. **Explicit Router LLM Generation**: An upfront decision step classifying the task into `DIRECT` or `PYTHON`.
2. **Additional LLM Inference Turn**: Standard and recoverable execution uses two sequential LLM generations per task instead of one (`llm_generation_count == 2`).
3. **Route-Specific Worker Prompting**: Specialized system prompts tailored to direct answer synthesis (`router-direct-worker-v1`) or code generation (`router-python-worker-v1`).
4. **Deterministic Route Enforcement**: Hard architectural enforcement ensuring DIRECT routes cannot invoke Python and cannot be exposed to tool-calling failure modes.
5. **Changed Exposure to Provider Stochasticity**: Differential sensitivity to upstream provider `MALFORMED_FUNCTION_CALL` finish-reason anomalies and token budget dynamics.

These bundled components cannot be cleanly separated by the primary V3 &rarr; V4 comparison alone.

---

## 2. Execution Flow & Architecture

```text
GAIA Question + Optional Attachment File
     ↓
ONE Tavily Search (Original Question as Query, Capped at 1,500 Chars)
     ↓
FileTool (Deterministic local extraction inherited from frozen V2/V3)
     ↓
Stage 1: Router Generation (`capability-router-v1`, native function calling disabled, `mode="NONE"`)
     ↓
Deterministic Route Parser (Case-insensitive regex, strict validation, deterministic fallback to DIRECT)
     ↓
Stage 2: Deterministic Route Enforcement & Route-Specific Worker Dispatch
     │
     ├── [Route == DIRECT]
     │        ↓
     │   Worker Prompt: `router-direct-worker-v1`
     │        ↓
     │   Gemini worker generation with native function calling disabled (`mode="NONE"`)
     │        ↓
     │   Deterministic Final Answer Extraction (`FINAL: <answer>`)
     │   (Python execution strictly disabled; 0 execution attempts)
     │
     └── [Route == PYTHON]
              ↓
         Worker Prompt: `router-python-worker-v1`
              ↓
         Gemini worker generation with native function calling disabled (`mode="NONE"`);
         Python execution is orchestrated locally and deterministically after extracting a Python code block
              ↓
         [Worker emits ```python code block]
              ↓
         PythonTool Subprocess (`-I`, Ephemeral Dir, Timeout 15.0s, Cap 20k chars, Static AST Validation)
              ↓
         ├── [Success: stdout contains 'FINAL_ANSWER: <ans>']
         │        ↓
         │   Extract <ans> deterministically
         │
         └── [Failure / Missing Marker / AST Rejection / Timeout / Non-execution]
                  ↓
             Deterministic fallback to model direct text if available
             (Strictly no second LLM synthesis call, no retry, no debugging turn)
```

### Strict Capability Invariants
- **Generation Accounting**: Standard and recoverable V4 execution uses two LLM generation attempts: one router attempt and one worker attempt. If a fatal exception prevents worker dispatch, telemetry records the actual number of attempts rather than forcing the count to two.
- **Single-Shot Python Execution**: Maximum one Python execution per task (`python_execution_count in {0, 1}`).
- **Native Function Calling Disabled**: Router and both workers use Gemini with native function calling disabled (`mode="NONE"`). Python execution is orchestrated locally and deterministically after parsing worker output.
- **Strict Route Enforcement**: If routed to `DIRECT`, Python execution is structurally prohibited.
- **No Autonomous Tool Loops**: Model cannot iteratively decide to invoke further tools.
- **No Multi-Turn Debugging or Retries**: Router parse errors, worker anomalies, or Python execution crashes immediately fall back to deterministic handling; strictly no third LLM generation, no retry, no repair turn, and no verification loop.
- **Search Invariance**: Exactly one Tavily search per task on the original question (`search_depth="basic"`, `max_results=5`, query capped at 1,500 characters).
- **FileTool Invariance**: Frozen V2/V3 file extraction semantics preserved unchanged.
- **Prohibited Capabilities**: No autonomous planner-actor loops, no multi-hop web retrieval, no query rewriting, no reflection/verification agents, no OCR, no browser automation, and no RAG.

---

## 3. Configuration Manifest

- **Project Version**: `v4`
- **Research Label**: explicit two-stage capability routing
- **Parent Baseline**: frozen V3 (`v3-python-execution-final`)
- **Model**: `gemini-3.5-flash-lite`
- **Thinking Level**: `medium`
- **Max Output Tokens**: `2048`
- **Temperature**: provider default / `None`
- **Native Function Calling**: explicitly disabled for router and workers (`mode="NONE"`)
- **Prompt Versions**:
  - Router: `capability-router-v1`
  - Worker Direct: `router-direct-worker-v1`
  - Worker Python: `router-python-worker-v1`
  - Worker Fallback: `router-direct-worker-v1`
- **Official Scorer Commit**: `9f133d71362e77b3539f1514f31b9c101a545fec`
- **Dataset**: GAIA 2023 Validation split (165 tasks: Level 1: 53, Level 2: 86, Level 3: 26)
- **Search Configuration**:
  - Provider: Tavily
  - Depth: basic
  - Max results: 5
  - Executions per task: maximum 1
  - Query used: original question (capped at 1,500 characters)
  - Retries: 0
- **File Configuration**:
  - Supported extensions: `.txt`, `.md`, `.csv`, `.json`, `.py`, `.docx`, `.xlsx`, `.pptx`, `.png`, `.jpg`, `.jpeg`, `.pdf`, `.mp3`
  - Unsupported extensions: `.zip`, `.pdb`, `.jsonld`, `.xls`
  - Attached `.py` policy: source text only, never auto-executed
- **Python Execution Configuration**:
  - Max executions per task: 1
  - Timeout: 15.0 seconds
  - Output length cap: 20,000 characters
  - Mode: isolated subprocess (`-I`)
  - Working directory: ephemeral temporary directory (`tempfile.mkdtemp`)
  - Attachment security: read-only copies
  - Security policy: static AST validation blocking dangerous modules (`subprocess`, `socket`, `urllib`, `requests`, `aiohttp`, `importlib`, `ctypes`, `multiprocessing`), dangerous functions (`os.system`, `eval`, `exec`, `compile`), and path traversal
  - Isolation boundary: best-effort research execution isolation
  - Retries permitted: 0
  - Fallback on failure: deterministic extraction from model direct text if available
  - Extraction contract: `FINAL_ANSWER: <answer>`
- **Preserved Generation Invariants**:
  - Standard/recoverable execution: 2 LLM generation attempts (1 router + 1 worker)
  - `python_execution_count in {0, 1}`

---

## 4. Canonical Controlled Results

Scored using the official GAIA leaderboard evaluation suite against the contemporaneous matched V3 control on the complete GAIA 2023 Validation set (165 tasks).

### Benchmark Performance Summary

| Metric | Historical Frozen V3 | Matched V3 Control | Canonical V4 | Controlled Delta (vs Matched V3) |
| :--- | :---: | :---: | :---: | :---: |
| **Overall Accuracy** | **29.09%** (48 / 165) | **29.70%** (49 / 165) | **31.52%** (52 / 165) | **+1.82 pp (+3 tasks)** |
| Level 1 Accuracy | 45.28% (24 / 53) | 47.17% (25 / 53) | 52.83% (28 / 53) | +5.66 pp (+3 tasks) |
| Level 2 Accuracy | 26.74% (23 / 86) | 24.42% (21 / 86) | 24.42% (21 / 86) | +0.00 pp (0 tasks) |
| Level 3 Accuracy | 3.85% (1 / 26) | 11.54% (3 / 26) | 11.54% (3 / 26) | +0.00 pp (0 tasks) |
| **Attachment Tasks** | **21.05%** (8 / 38) | **18.42%** (7 / 38) | **15.79%** (6 / 38) | **-2.63 pp (-1 task)** |
| **Non-Attachment Tasks** | **31.50%** (40 / 127) | **33.07%** (42 / 127) | **36.22%** (46 / 127) | **+3.15 pp (+4 tasks)** |
| **Completion Rate** | **78.18%** (129 / 165) | **77.58%** (128 / 165) | **49.70%** (82 / 165) | **-27.88 pp (-46 tasks)** |

### Level-by-Level Completion Breakdown
- **Level 1 Completion**: V4 69.81% (37 / 53) vs Matched V3 81.13% (43 / 53) [&Delta; -11.32 pp]
- **Level 2 Completion**: V4 46.51% (40 / 86) vs Matched V3 74.42% (64 / 86) [&Delta; -27.91 pp]
- **Level 3 Completion**: V4 19.23% (5 / 26) vs Matched V3 80.77% (21 / 26) [&Delta; -61.54 pp]

---

## 5. Router Routing Distribution & Execution Funnel

### Canonical Router Decisions & Dispatches
Across all 165 tasks:
- **Final DIRECT Worker Dispatches**: `74` tasks
- **Final PYTHON Worker Dispatches**: `91` tasks
- **Of the 74 DIRECT dispatches, 4 originated from router fallback**:
  - Level 1: 0 fallbacks (32 direct decisions)
  - Level 2: 3 fallbacks (34 direct decisions + 3 router fallbacks = 37 direct worker dispatches)
  - Level 3: 1 fallback (8 direct decisions + 1 router fallback = 9 direct worker dispatches)
- **Sum Identity Verified**: `74 DIRECT + 91 PYTHON = 165 total tasks`.

### Python Execution Funnel Analysis
- **Tasks Routed to PYTHON**: `91`
- **Python Executions Attempted**: `18` tasks (19.78% route-to-execution rate)
- **Python Execution Successes**: `11` / 18 (61.11% execution success rate)
- **Python Execution Failures**: `7` / 18 (38.89%)
- **Unfulfilled Python Routes**: `73` tasks (where the worker was routed to Python but did not execute Python)
- **Python Fallbacks Total**: `80` tasks
- **Reconciliation Identity Verified**: `73 unfulfilled + 7 execution failures = 80 fallbacks`.

---

## 6. Task Transition Analysis

Pairwise comparison of task outcomes between contemporaneous matched V3 control and V4 across all 165 GAIA tasks:

| Transition Category | Count | Percentage |
| :--- | :---: | :---: |
| **Improvements** (Matched V3 Fail &rarr; V4 Correct) | 13 | 7.88% |
| **Regressions** (Matched V3 Correct &rarr; V4 Fail) | 10 | 6.06% |
| **Stable Correct** (Matched V3 Correct &rarr; V4 Correct) | 39 | 23.64% |
| **Stable Failure** (Matched V3 Fail &rarr; V4 Fail) | 103 | 62.42% |
| **Total Tasks** | **165** | **100.00%** |

**Net Task Delta**: 13 - 10 = **+3 tasks** (+1.82 pp).

### Transition Breakdown by Level
- **Level 1**: 5 Improvements, 2 Regressions, 23 Stable Correct, 23 Stable Failure (Net: +3 tasks)
- **Level 2**: 7 Improvements, 7 Regressions, 14 Stable Correct, 58 Stable Failure (Net: 0 tasks)
- **Level 3**: 1 Improvement, 1 Regression, 2 Stable Correct, 22 Stable Failure (Net: 0 tasks)

---

## 7. Audited Regression Mechanism Decomposition

A rigorous audit of all 10 observed regressions (where matched V3 was correct but V4 failed) reveals:

| Regression Mechanism Category | Count | Percentage of Regressions |
| :--- | :---: | :---: |
| Router decision PYTHON but worker provider anomaly (`MALFORMED_FUNCTION_CALL`) | 8 | 80.00% |
| Worker token budget exhaustion during Python generation (`MAX_TOKENS`) | 1 | 10.00% |
| Successful Python execution but answer truncated (`MAX_TOKENS`) | 1 | 10.00% |
| Successful Python wrong answer calculation | 0 | 0.00% |
| Completed DIRECT worker wrong answer | 0 | 0.00% |
| **Total Regressions** | **10** | **100.00%** |

### Key Regression Takeaway
- **8 of 10 regressions (80.0%)** were associated with worker-generation `MALFORMED_FUNCTION_CALL` provider finish-reason anomalies.
- **2 of 10 regressions (20.0%)** were associated with token budget exhaustion (`MAX_TOKENS`).
- **10 of 10 regressions (100.0%)** fall under the umbrella of worker-generation anomalies or token truncations.
- **Zero regressions** resulted from clean calculation errors after successful Python execution or ordinary completed direct-answer divergence.

*(Note: These associations describe operational co-occurrence in telemetry and do not imply a single causal factor.)*

---

## 8. Audited Failure Taxonomy & Confidence Tiers

Across all 113 tasks where V4 did not produce the correct benchmark answer, errors are classified into two methodological confidence tiers:

### Confidence Tiers Summary
- **High Confidence (Operational / Telemetry-backed)**: 90 / 113 tasks (79.65%)
- **Low Confidence (Heuristic / Observational)**: 23 / 113 tasks (20.35%)

### Distribution of Failure Categories

| Category | Tier | Count | Share | Telemetry Verification Basis |
| :--- | :---: | :---: | :---: | :--- |
| `Python route unfulfilled due provider anomaly` | High | 70 | 61.95% | Worker generation finished with `MALFORMED_FUNCTION_CALL` under Python route |
| `completed_direct_wrong_answer` | Low | 23 | 20.35% | Worker completed cleanly (`STOP`), but answer did not match ground truth (root cause unobservable) |
| `Python missing final marker` | High | 4 | 3.54% | Python process exited 0 but stdout lacked `FINAL_ANSWER:` |
| `Python route unfulfilled due MAX_TOKENS` | High | 3 | 2.65% | Worker generation truncated by 2048 token limit before code block finished |
| `direct incomplete generation (MAX_TOKENS)` | High | 3 | 2.65% | Direct worker truncated by 2048 token limit |
| `Python runtime failure` | High | 2 | 1.77% | Python process raised unhandled exception or missing package |
| `Python success wrong answer` | High | 2 | 1.77% | Python executed cleanly with `FINAL_ANSWER:` but output value was mathematically incorrect |
| `worker provider anomaly (DIRECT route)` | High | 2 | 1.77% | Direct worker generation failed provider-side |
| `router fallback direct incomplete` | High | 2 | 1.77% | Router parse fallback to DIRECT, worker failed provider-side |
| `Python syntax/AST rejection` | High | 1 | 0.88% | Python code blocked by static AST security validator |
| `router fallback direct wrong` | High | 1 | 0.88% | Router fallback completed, extracted answer incorrect |
| **Total Incorrect Tasks** | | **113** | **100.00%** | |

### Methodological Distinction on Confidence
- **High Confidence**: Directly verified from machine-readable telemetry fields (`finish_reason`, `error_type`, `exit_code`, AST validator logs).
- **Low Confidence (Heuristic)**: `completed_direct_wrong_answer` (23 tasks) represents completed model text that failed GAIA scoring. Machine telemetry confirms only that generation completed; it cannot observe whether the failure stemmed from incorrect reasoning, missing web evidence, misinterpreted search snippets, or formatting subtleties.

---

## 9. Python Execution Failure Taxonomy

Across the 7 executed Python failures:
- **`MissingFinalAnswerMarker`**: `4` / 7 (57.14%) — Code executed cleanly (exit code 0) but did not print the required `FINAL_ANSWER: <answer>` marker.
- **`runtime failure`**: `2` / 7 (28.57%) — Process raised an unhandled exception or missing dependency in the runtime environment.
- **`syntax / AST rejection`**: `1` / 7 (14.29%) — Code rejected by static AST security validator.
- **Total Executed Failures**: `4 + 2 + 1 = 7`.

---

## 10. Successful-Python Matched Subset Analysis

On the subset of 11 tasks where V4 routed to Python, generated valid code, executed the code, and cleanly satisfied the `FINAL_ANSWER:` extraction contract:
- **V4 Solved**: 9 / 11 tasks (81.82%)
- **Matched V3 Solved**: 8 / 11 tasks (72.73%)
- **Task Transitions**:
  - Improvements: 2
  - Regressions: 1
  - Stable Correct: 7
  - Stable Failure: 1

### Critical Methodological Warning
> **Endogenous Subgroup Warning**: This subgroup comparison is strictly descriptive. The 11 tasks were not randomly assigned to Python execution; they were selected endogenously by the router and worker models. Therefore, this accuracy (9/11 vs 8/11) reflects task selection and model propensity, not an experimental measurement of the isolated causal benefit of Python execution. It should not be characterized as proving Python effectiveness or high reliability in isolation.

---

## 11. Control Sensitivity & Operational Caveats

### Matched V3 Final-Task Provider Anomaly (Task `0bdb7c40`)
- **Event**: During the evaluation of Level 3 task `0bdb7c40-671d-4ad1-9ce3-986b159c0ddc` in matched V3, Gemini returned an unhandled HTTP 403 `PERMISSION_DENIED` during Step 4 (`llm_client.generate`).
- **Search Telemetry Artifact**: In the matched V3 summary, search successes report 164/165. Telemetry confirms Tavily search was executed upon entry; the reported search failure is an artifact of the runner exception handler defaulting metadata fields when the subsequent LLM call failed.
- **Bounded Sensitivity Analysis**: This operational asymmetry did not generate V4's +3 task advantage. Task `0bdb7c40` was also failed by V4 (due to worker `MALFORMED_FUNCTION_CALL`). Under the counterfactual where matched V3 hypothetically solved this task, V4's advantage would decrease from +3 to +2 tasks (+1.21 pp) rather than reverse direction.

---

## 12. Resource & Latency Tradeoffs

| Resource Metric | Matched V3 Control | Canonical V4 | System Delta |
| :--- | :---: | :---: | :---: |
| **Average Wall-Clock Latency** | 5.35 seconds | 10.62 seconds | **+5.27 s (+98.5%)** |
| **Average Total Tokens** | 3,044.5 tokens | 3,152.3 tokens | **+107.8 tokens (+3.5%)** |
| **LLM Generation Attempts per Task** | 1.00 attempt | 2.00 attempts (standard) | **+1.00 attempt (+100.0%)** |
| **Completion Rate** | 77.58% (128 / 165) | 49.70% (82 / 165) | **-27.88 pp (-35.9%)** |

### Tradeoff & Completion Summary
The two-stage capability router achieved a modest accuracy improvement (+1.82 pp, +3 tasks) but introduced substantial operational costs: doubled LLM inference calls, roughly doubled wall-clock latency, and a significant reduction in completion rate (49.70% vs 77.58%). The completion reduction was associated primarily with worker-generation `MALFORMED_FUNCTION_CALL` finish-reason anomalies and, to a smaller extent, MAX_TOKENS truncation and other generation failures.

---

## 13. Scientific Boundaries & Prohibited Inferences

1. **Do NOT claim routing alone caused the +3 task delta**: The intervention bundled an additional LLM generation, specialized worker prompts, deterministic route enforcement, and altered provider error exposure.
2. **Do NOT claim Python tool execution is solved or highly reliable**: Out of 91 tasks routed to Python, only 18 executed code, and 70 unfulfilled routes were associated with worker-generation `MALFORMED_FUNCTION_CALL` finish-reason anomalies.
3. **Do NOT claim the successful-Python subset proves tool efficacy**: The 9/11 vs 8/11 accuracy on the 11 completed Python tasks is an endogenous descriptive subset, not a causal estimate.
4. **Do NOT claim V4 is strictly superior to V3**: While solving 3 more tasks, V4 suffered a severe completion rate reduction (49.70% vs 77.58%) and doubled average latency.
5. **Do NOT claim V5 will fix V4**: Any subsequent architecture (e.g. multi-turn tool calling, reflection, or repair loops) represents a distinct hypothesis requiring independent pre-registration.

---

## 14. Canonical Artifact Locations

All canonical evaluation records, predictions, summaries, and analysis artifacts are preserved and immutable:

- **V4 Predictions**:
  - `experiments/v4/predictions_level_1.jsonl`
  - `experiments/v4/predictions_level_2.jsonl`
  - `experiments/v4/predictions_level_3.jsonl`
- **V4 Summaries**:
  - `experiments/v4/summary_level_1.json`
  - `experiments/v4/summary_level_2.json`
  - `experiments/v4/summary_level_3.json`
- **V4 Detailed Evaluation**:
  - `experiments/v4/detailed_eval_level_1.jsonl`
  - `experiments/v4/detailed_eval_level_2.jsonl`
  - `experiments/v4/detailed_eval_level_3.jsonl`
- **Matched V3 Controls**:
  - `experiments/v4_matched_v3/predictions_level_1.jsonl`
  - `experiments/v4_matched_v3/predictions_level_2.jsonl`
  - `experiments/v4_matched_v3/predictions_level_3.jsonl`
  - `experiments/v4_matched_v3/detailed_eval_level_1.jsonl`
  - `experiments/v4_matched_v3/detailed_eval_level_2.jsonl`
  - `experiments/v4_matched_v3/detailed_eval_level_3.jsonl`
  - `experiments/v4_matched_v3/summary_level_1.json`
  - `experiments/v4_matched_v3/summary_level_2.json`
  - `experiments/v4_matched_v3/summary_level_3.json`
- **Post-Benchmark Analysis & Comparison**:
  - `experiments/v4/config.json`
  - `experiments/v4/comparison_summary.json`
  - `experiments/v4/router_execution_analysis.json`
  - `experiments/v4/v3_v4_task_transitions.json`
  - `experiments/v4/v3_v4_error_comparison.json`
  - `experiments/v4/error_analysis_level_1.json`
  - `experiments/v4/error_analysis_level_2.json`
  - `experiments/v4/error_analysis_level_3.json`
  - `experiments/v4/error_analysis_overall.json`

---

## 15. Freeze Rule

V4 is frozen as the immutable research baseline for explicit two-stage capability routing:

```text
V4 = frozen V3 + explicit two-stage DIRECT/PYTHON capability-routing architecture
```

Future work must not alter V4 results, agent runtime behavior, prompts, model settings, tool configurations, or benchmark evaluations. Any subsequent planner/router, repair loop, or multi-turn agent work belongs to V5+.
