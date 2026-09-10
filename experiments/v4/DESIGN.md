# V4 Design Specification — Explicit Capability Routing

**Status**: PROPOSED DESIGN (Design-Only Phase — Not Implemented)  
**Parent Baseline**: Frozen V3 (`v3-python-execution-final`)  
**Proposed Branch**: `v4-capability-router`  
**Version Label Shorthand**: `V4 = frozen V3 + explicit capability router`  
**Full Experimental Characterization**: The controlled system-level effect of introducing an explicit two-stage capability-routing architecture and its associated additional inference and route-specific worker prompting.

---

## 1. Research Context & Problem Statement

### 1.1 Frozen V3 Context
The frozen V3 baseline evaluated controlled, single-shot local Python code execution on the GAIA 2023 Validation set (165 tasks):
- **V3 Accuracy**: `48 / 165 = 29.09%` (Level 1: `45.28%`, Level 2: `26.74%`, Level 3: `3.85%`)
- **Matched V2 Control**: `65 / 165 = 39.39%` (Level 1: `58.49%`, Level 2: `34.88%`, Level 3: `15.38%`)
- **Controlled Delta**: `-10.30 percentage points` (Completion delta: `+12.73 pp`, from `65.45%` to `78.18%`)

Crucial descriptive findings from the audited V3 post-benchmark analysis:
1. **Aggressive Implicit Self-Routing**: Under a single execution-aware prompt (`python-execution-v1`), the model chose Python on **`95 / 165` tasks (57.58%)**.
2. **Extraction Contract Fragility**: Of the 69 Python execution failures, **`60` (86.96%)** were clean process completions (exit code 0) that failed because the generated script did not satisfy the required `FINAL_ANSWER:` extraction contract.
3. **Regression Concentration**: Across all 25 observed regressions from matched V2, **`22 / 25` (88.0%)** were associated with either Python execution failures (`12`) or upstream provider anomalies (`10`), while only `3` occurred after successful Python execution, and `0` occurred on completed direct-answer tasks.

*(Note: In accordance with rigorous scientific hygiene, these associations describe operational co-occurrence and do not prove that Python or routing was the sole causal mechanism.)*

### 1.2 Proposed V4 Experimental Characterization
In V3, routing was **implicit and self-selected within a single generation**: given a prompt offering either direct answering or code generation, the model decided whether to produce code or text.

In V4, routing is **factored into an explicit architectural stage**:
1. An explicit **Router** LLM call evaluates the task and selects between two discrete capability paths: `DIRECT` or `PYTHON`.
2. A dedicated **Worker** LLM call executes the chosen path using a specialized, single-purpose prompt.

**Critical Methodological Definition**:
V4 must NOT be described as isolating or estimating the pure causal effect of routing. V4 differs from V3 through a multi-faceted intervention bundle consisting of:
- An explicit capability router generation
- An additional LLM inference call per task
- Route-specific worker prompting (`router-direct-worker-v1` vs. `router-python-worker-v1`)
- Deterministic enforcement of the selected execution route

Therefore, the primary research comparison is defined as:
> **The controlled system-level effect of introducing an explicit two-stage capability-routing architecture and its associated additional inference and route-specific worker prompting.**

The shorthand `V4 = frozen V3 + explicit capability router` serves strictly as a convenient version label, not as a claim of single-variable isolation. All comparisons are conducted as a **controlled matched comparison** against contemporaneous V3 controls.

### 1.3 Pre-Registered Primary Scientific Claims
To prevent post-hoc overclaims, acceptable scientific descriptions are explicitly pre-registered:

- **Acceptable Claim**:
  > "V4 measures the system-level effect of replacing V3's implicit self-routing architecture with an explicit two-stage routing architecture under matched evaluation conditions."
- **Acceptable Claim**:
  > "Any observed performance difference may reflect routing, additional inference, route-specific prompting, and altered provider-failure exposure."
- **Unacceptable Claim (Prohibited)**:
  > "V4 isolates the causal effect of routing."
- **Unacceptable Claim (Prohibited)**:
  > "The planner improves capability selection." (unless supported purely descriptively by post-benchmark data).

### 1.4 Research Questions
- **Primary Research Question**:
  > *How does adding an explicit capability-routing stage affect GAIA performance, completion, reliability, latency, and tool utilization relative to frozen V3?*
- **Secondary Research Question**:
  > *Does explicit routing alter the frequency and reliability profile of Python execution compared with V3's implicit self-routing policy?*

---

## 2. High-Level Architecture & Execution Flow

```text
               +----------------------------------+
               |          GAIA Question           |
               +----------------------------------+
                                |
                                v
               +----------------------------------+
               |     ONE Tavily Search Tool       |
               | (Original Question, max_res=5)   |
               +----------------------------------+
                                |
                                v
               +----------------------------------+
               |         Frozen FileTool          |
               | (If attachment present on disk)  |
               +----------------------------------+
                                |
                                v
               +----------------------------------+
               |      ROUTER GEMINI CALL          |
               |       (Generation #1)            |
               | Prompt: capability-router-v1     |
               +----------------------------------+
                                |
                                v
                   [Deterministic Route Parser]
                                |
               +----------------+----------------+
               |                                 |
       (Route: DIRECT or                 (Route: PYTHON)
     Pre-Registered Fallback)                    |
               |                                 |
               v                                 v
+-----------------------------+   +-----------------------------+
|    DIRECT WORKER GEMINI     |   |    PYTHON WORKER GEMINI     |
|       (Generation #2)       |   |       (Generation #2)       |
| Prompt: router-direct-wkr-v1|   | Prompt: router-python-wkr-v1|
+-----------------------------+   +-----------------------------+
               |                                 |
               v                                 v
      Output: FINAL: <ans>                Output: ```python ... ```
               |                                 |
               |                                 v
               |                  +-----------------------------+
               |                  |      Frozen PythonTool      |
               |                  |  (Ephemeral dir, -I, 15.0s) |
               |                  +-----------------------------+
               |                                 |
               |                        [Extract FINAL_ANSWER:]
               |                                 |
               |                  +--------------+--------------+
               |                  |                             |
               |              (Success)                 (Failure / Missing)
               |                  |                             |
               |                  v                             v
               |         Clean Final Answer            Deterministic Fallback
               |                                       (Empty string; NO retry;
               |                                        NO 3rd LLM call)
               +----------------+-------------------------------+
                                |
                                v
               +----------------------------------+
               |           AgentResult            |
               |  (llm_generation_attempts == 2)  |
               |  (python_execution_count in 0,1) |
               +----------------------------------+
```

### 2.1 Third-Generation Invariant Specification
- **Design Intent**: The architecture contains **no intended path requiring a third LLM generation**.
- **Implementation Requirement**: Implementation must rigorously enforce and test this invariant across all edge cases:
  1. **Router Malformation / Provider Anomaly**: Falls back deterministically to the `DIRECT` worker mode within Generation #2. Does NOT retry the router.
  2. **Worker Malformation**: If the DIRECT worker omits `FINAL:` or the PYTHON worker emits invalid code, the agent deterministically falls back to regex extraction or empty string. Does NOT call a synthesis LLM.
  3. **Python Execution Failure**: If the Python script times out, crashes, violates AST policy, or omits `FINAL_ANSWER:`, `python_fallback = True` is flagged, and the agent returns an empty string (or direct text if present in worker output). It NEVER invokes a code-repair or reflection LLM turn.
  4. **Superclass Method Decoupling**: As detailed in Section 15, `GAIARouterAgent` does NOT inherit from `GAIAPythonAgent.run()`, completely eliminating superclass prompt execution.
- **Status**: The proposed invariant `llm_generation_count == 2` is formally designated as a **design requirement pending implementation verification**.

---

## 3. Router Contract, Parsing, and Fallback Specification

### 3.1 Router Output Contract
To eliminate chain-of-thought confounds, the router is constrained to output ONLY the routing token:
```text
ROUTE: DIRECT
```
or
```text
ROUTE: PYTHON
```

The router prompt explicitly forbids:
- Chain-of-thought reasoning, scratchpad notes, or explanation
- Candidate answers or preliminary calculations
- Code snippets, library suggestions, or pseudo-code

### 3.2 Deterministic Parsing Algorithm
The router response string is parsed using a deterministic regex rule:
```python
def parse_router_decision(raw_text: str) -> Optional[str]:
    if not raw_text:
        return None
    # Match ROUTE: <DIRECT|PYTHON> on its own line or anchored
    pattern = r"(?:^|
)\s*ROUTE\s*:\s*(DIRECT|PYTHON)"
    matches = re.findall(pattern, raw_text, flags=re.IGNORECASE)
    if not matches:
        return None
    # Ambiguity check: if both DIRECT and PYTHON appear, reject as malformed
    normalized = {m.upper() for m in matches}
    if len(normalized) == 1:
        return normalized.pop()
    return None
```

### 3.3 Granular Router Error Taxonomy
Operational telemetry must NOT collapse all provider or syntax failures into a single bucket. Telemetry will record granular operational categories:

| Router Outcome State | `router_decision` | `router_success` | `router_fallback` | Granular `router_error_type` | Action Taken |
| :--- | :---: | :---: | :---: | :--- | :--- |
| Clean `ROUTE: DIRECT` | `DIRECT` | `True` | `False` | `None` | Dispatch to DIRECT worker |
| Clean `ROUTE: PYTHON` | `PYTHON` | `True` | `False` | `None` | Dispatch to PYTHON worker |
| Whitespace / Case variations | `DIRECT` or `PYTHON` | `True` | `False` | `None` | Normalizes cleanly via regex |
| Extra conversational text with unique route | `DIRECT` or `PYTHON` | `True` | `False` | `None` | Matched route extracted |
| Contradictory routes (`DIRECT` and `PYTHON`) | `DIRECT` | `False` | `True` | `ambiguous_route_text` | Fallback to DIRECT worker |
| No route token found | `DIRECT` | `False` | `True` | `missing_route_marker` | Fallback to DIRECT worker |
| Malformed text (unparseable tokens) | `DIRECT` | `False` | `True` | `malformed_router_text` | Fallback to DIRECT worker |
| Empty / whitespace-only output | `DIRECT` | `False` | `True` | `empty_provider_response` | Fallback to DIRECT worker |
| Provider `finish_reason == 'MALFORMED_FUNCTION_CALL'` | `DIRECT` | `False` | `True` | `malformed_function_call_finish_reason` | Fallback to DIRECT worker |
| Provider network / deadline timeout | `DIRECT` | `False` | `True` | `provider_timeout` | Fallback to DIRECT worker |
| Provider HTTP 5xx / unhandled API exception | `DIRECT` | `False` | `True` | `provider_api_error` | Fallback to DIRECT worker |

*Note: Router-stage and worker-stage provider anomalies are tracked separately in telemetry (`router_error_type` vs. `worker_error_type`).*

### 3.4 Reframe of DIRECT Fallback Policy
When the router output is malformed, ambiguous, or unavailable due to provider anomaly, the agent executes:
```text
Fallback: DIRECT
```
- **Operational Definition**: This is **a pre-registered conservative deterministic fallback that avoids initiating Python execution when the routing decision is unavailable**.
- **No Accuracy-Optimality Claim**: This fallback is NOT claimed to be accuracy-optimal or "methodologically superior." It is chosen solely as a defensive policy to avoid compiling and executing code in an unverified state.
- **Invariants**:
  - Exactly 0 router retries
  - Exactly 0 extra router generations
  - Worker still executes exactly once
  - Structured router failure metadata recorded cleanly

---

## 4. Router Inputs & Evidence Boundary

### 4.1 What the Router Sees
The router prompt receives the exact evidence bundle that V3 constructed:
1. **Original GAIA Question**: Complete text as supplied by the benchmark.
2. **Frozen Web Search Evidence**: Formatted snippet block from the single Tavily basic search (capped at 1,500 chars).
3. **Frozen Attachment Evidence**:
   - For text/table attachments: Extracted text or sheet structure from FileTool.
   - For native multimodal media (`.png`, `.jpg`, `.mp3`, `.pdf`): Dispatched as binary multimodal `types.Part` objects alongside the router prompt.
4. **Attachment Metadata**: Filename and extension (e.g. `Filename: calculation.xlsx`), accessible independently of FileTool extraction success.

### 4.2 What the Router Must NEVER See
- Ground-truth answers or validation annotations
- Prior benchmark correctness or historical V1/V2/V3 success labels
- Task-specific routing hints or heuristics (e.g., "always use Python for xlsx")
- Output from previous Python runs or worker responses
- Model confidence scores from earlier versions

### 4.3 Confound Assessment: Exposing Full Evidence to Router
Exposing full web and file evidence to the router is methodologically necessary:
- Determining whether a task requires Python computation depends fundamentally on whether the evidence contains structured tabular data, large numerical series, or complex equations versus purely descriptive text.
- If the router were blind to evidence, it would route based purely on question keywords, handicapping its ability to recognize data-heavy attachments.
- Evidence equivalence between V3 and V4 is preserved because both models receive the identical evidence payload.

---

## 5. Worker Contracts & Prompt Specifications

### 5.1 DIRECT Worker Specification
- **Prompt Version**: `router-direct-worker-v1`
- **Objective**: Synthesize a direct, concise answer from question and evidence without code execution.
- **Strict Injunctions**:
  - Forbidden from generating ` ```python ``` ` code blocks.
  - Forbidden from asking the user to run code.
  - Must format final answer on a single line starting with:
    ```text
    FINAL: <answer>
    ```
- **Deterministic Extraction**: Parsed via `extract_direct_answer(raw_text)` with `clean_answer()` normalization.

### 5.2 PYTHON Worker Specification
- **Prompt Version**: `router-python-worker-v1`
- **Objective**: Generate a single, self-contained Python script to compute the exact answer deterministically.
- **Strict Injunctions**:
  - Must output ONLY a single ` ```python ... ``` ` code block.
  - Forbidden from emitting explanatory text outside the block.
  - Must strictly adhere to the frozen V3 execution contract by ending with:
    ```python
    print(f"FINAL_ANSWER: {result}")
    ```
  - Informs the model that execution is single-shot with **NO retry, NO debugger, and NO multi-turn repair**.
  - Attachment files are placed in the current working directory under their original filename.
- **Deterministic Extraction**: Captured via `extract_python_final_answer(stdout)` from `PythonTool.execute()`.
- **Contract Integrity**: V4 intentionally preserves the exact `FINAL_ANSWER:` extraction contract without relaxation, ensuring direct comparability with V3.

---

## 6. Preservation of Frozen Tool Infrastructure & Python Semantics

V4 strictly reuses existing, validated tool implementations without semantic changes:

### 6.1 Strict Preservation of Frozen PythonTool Semantics
V4 preserves the frozen V3 Python execution environment exactly:
- **Subprocess Isolation**: Launched via `[sys.executable, "-I", "solution.py"]`.
- **Ephemeral Workspace**: Dedicated temporary directory (`tempfile.mkdtemp(prefix="gaia_v4_py_")`), deleted immediately upon task completion.
- **Attachment Read-Only**: Copied task attachments are marked read-only (`stat.S_IREAD`).
- **Sanitized Environment**: Subprocess inherits only non-sensitive system variables (`SYSTEMROOT`, `PATH`, `TMP`, etc.), omitting all API keys.
- **Resource Constraints**: Strict 15.0s timeout; stdout and stderr capped at 20,000 characters.
- **Static AST Security Policy**: Syntax inspection strictly blocks dangerous modules (`subprocess`, `socket`, `urllib`, `requests`, `aiohttp`, `importlib`, `ctypes`, `multiprocessing`, `threading`), dangerous OS calls, and path traversal.
- **Dependency Environment**: **No packages added or modified**. Adding `opencv-python`, `biopython`, or other libraries is strictly prohibited.
- **Extraction Contract Preservation**: The required `FINAL_ANSWER:` marker extraction contract is preserved unchanged.
- **Known V3 Marker Failure Pattern Unchanged**: The known failure pattern observed in V3 (where scripts exited cleanly with code 0 but omitted the required `FINAL_ANSWER:` marker) **must remain strictly unchanged for this experiment**. V4 tests whether explicit routing and worker prompt specialization alter this pattern; it does NOT alter the marker contract itself.

### 6.2 Frozen Tavily Search Invariants
- Maximum 1 search per task on original question (capped at 1,500 chars).
- Depth: `basic`, `max_results: 5`.
- Zero query rewriting, zero iterative search, zero search retry.

### 6.3 Frozen FileTool Invariants
- Deterministic extraction for 13 supported file extensions.
- Rejection/fallback for unsupported formats (`.zip`, `.pdb`, `.jsonld`, `.xls`).
- No OCR tools, no dynamic document renderers.

### 6.4 Model Configuration Invariants
- Model: `gemini-3.5-flash-lite`
- Thinking level: `medium`
- Max output tokens: `2048`
- Temperature: `None` (provider default sampling)
- Function calling: **Explicitly disabled (`mode="NONE"`)** for both router and worker generations.

---

## 7. Two-Generation Semantics & Proposed Invariants

### 7.1 Generation Attempt Semantics
To ensure metadata is deterministic and interpretable under provider errors:
- **Router Provider Failure**: If the router provider call times out or returns an error, this attempt still counts as one generation attempt (`router_generation_attempts = 1`, `router_generation_success = False`).
- **DIRECT Fallback Triggered**: The agent selects `router_decision = "DIRECT"` via fallback.
- **Worker Execution**: The worker generation attempt proceeds once (`worker_generation_attempts = 1`).
- **Total Generation Attempts**: In this scenario, `llm_generation_attempts == 2`, while `llm_generation_success_count == 1`.
- **Hard Fatal API Exception**: If an unrecoverable exception prevents the worker call from ever executing, the runner records `llm_generation_attempts = 1`, `llm_generation_success_count = 0` (or `1`). **The runner must NOT silently report `2` if only one provider generation attempt actually occurred.**

### 7.2 Invariant Specification Table
| Invariant | Value | Status & Verification Mechanism |
| :--- | :---: | :--- |
| `router_generation_attempts` | `1` | Enforced in agent; verified in runner |
| `worker_generation_attempts` | `1` | Enforced in agent; verified in runner |
| `llm_generation_count_target` | `2` | Design requirement pending implementation verification |
| `python_execution_count` | `in {0, 1}` | Enforced by execution branch; `0` on DIRECT, `<= 1` on PYTHON |
| `search_call_count` | `<= 1` | Managed by TavilySearchTool cache / single invocation |
| `router_retries` | `0` | No loop or exception retry around router call |
| `worker_retries` | `0` | No loop or exception retry around worker call |
| `python_retries` | `0` | No retry or self-correction turn on interpreter failure |
| `second_llm_synthesis` | `False` | Output extracted directly from Python stdout or worker text |
| `autonomous_tool_loop` | `False` | Hardcoded linear execution graph |

---

## 8. Experimental Confounds & Methodological Safeguards

### 8.1 Confound 1: Additional LLM Inference
- **Description**: V4 uses two Gemini generations where V3 used one. This introduces additional token consumption, inference latency, API variance, and an extra interpretation turn.
- **Safeguard & Reporting Rule**: V4 performance must be characterized explicitly as the effect of:
  > *An explicit two-stage capability routing architecture and its associated additional model inference*,
  rather than claiming a pure, cost-free algorithmic effect of routing logic alone.

### 8.2 Confound 2: Router Reasoning Leakage
- **Description**: If the router generated intermediate reasoning, problem breakdowns, or candidate plans and passed them to the worker, the worker would benefit from multi-turn Chain-of-Thought reasoning.
- **Safeguard**: The router prompt strictly forbids explanations (`ROUTE: <DIRECT|PYTHON>` only). Furthermore, the agent framework enforces an **information firewall**: the worker prompt receives ONLY the original question, web evidence, file evidence, and its own task instructions. The router output is NEVER passed to the worker.

### 8.3 Confound 3: Route-Specific Prompt Specialization
- **Description**: The DIRECT worker and PYTHON worker use specialized prompts (`router-direct-worker-v1` and `router-python-worker-v1`) that differ structurally from V3's unified `python-execution-v1` prompt.
- **Safeguard & Explicit Non-Separability**: Any observed performance change in V4 may reflect:
  1. Explicit capability selection
  2. Additional LLM inference
  3. Route-specific prompt specialization
  4. Changed exposure to provider stochasticity
  **These components cannot be cleanly separated by the primary V3→V4 comparison alone.** Prompts must be frozen prior to benchmark execution and never tuned based on GAIA task correctness.

### 8.4 Confound 4: Upstream Provider Stochasticity & Anomalies
- **Description**: As observed in V3, provider anomalies (`MALFORMED_FUNCTION_CALL`) accounted for 40.0% of regressions. Running V4 in a different provider environment or temporal window could bias results.
- **Safeguard**: V4 must be evaluated strictly against a **contemporaneous matched V3 control run** conducted side-by-side on the same hardware, API key tier, and operational time window.

---

## 9. Canonical Comparison & Evaluation Protocol

### 9.1 Matched V3 vs. V4 Protocol
The primary benchmark comparison is:
```text
V4 vs. contemporaneous matched V3 control
```
Historical frozen V3 results will be reported for provenance, but all comparative and transition conclusions must reference the contemporaneous matched run.

### 9.2 Level-by-Level Staging Plan
To ensure operational integrity and detect runtime anomalies early:
1. **Level 1 Execution**:
   - Run V4 Level 1 (53 tasks) -> Run matched V3 Level 1 (53 tasks).
   - Verify operational metrics (generation counts == 2, completion rate, latency, token budgets).
   - Do NOT inspect task accuracy to adjust prompts or routing!
2. **Level 2 Execution**:
   - Run V4 Level 2 (86 tasks) -> Run matched V3 Level 2 (86 tasks).
   - Verify operational validity.
3. **Level 3 Execution**:
   - Run V4 Level 3 (26 tasks) -> Run matched V3 Level 3 (26 tasks).
   - Verify full 165-task benchmark completion.

### 9.3 Methodological Note on Optional Secondary Controls
> **Methodological Note on Secondary Controls**:
> A future sham/two-call control (e.g., executing an inert preliminary LLM call before V3 single-shot generation, or a direct-answering two-call pipeline) could help isolate additional-inference overhead from routing behavior.
> **This secondary control is NOT included in the canonical V4 evaluation** to keep the benchmark scope manageable and focused. It is recorded here strictly as an experimental limitation and potential future research direction.

---

## 10. Required V4 Telemetry & Metadata Schema

Every V4 prediction record written to `predictions_level_{level}.jsonl` must capture:

### 10.1 Identification & Provenance
- `schema_version`: `3`
- `run_id`: UUID4 string
- `project_version`: `"v4"`
- `git_commit`, `git_branch`, `git_dirty`: String / bool
- `task_id`: String
- `level`: Integer (1, 2, 3)
- `attachment_required`: Boolean
- `file_name`: Optional[str]

### 10.2 Model & Prompt Configuration
- `model`: `"gemini-3.5-flash-lite"`
- `thinking_level`: `"medium"`
- `max_output_tokens`: `2048`
- `temperature`: `None`
- `prompt_version`: `"capability-router-v1"`
- `router_prompt_version`: `"capability-router-v1"`
- `worker_prompt_version`: `"router-direct-worker-v1"` or `"router-python-worker-v1"`

### 10.3 Router Telemetry
- `router_requested`: `True`
- `router_decision`: `"DIRECT"` | `"PYTHON"`
- `router_success`: Boolean
- `router_fallback`: Boolean
- `router_error_type`: Granular string (`"malformed_function_call_finish_reason"`, `"provider_timeout"`, `"provider_api_error"`, `"empty_provider_response"`, `"malformed_router_text"`, `"ambiguous_route_text"`, `"missing_route_marker"`, etc.)
- `router_latency_seconds`: Float
- `router_input_tokens`, `router_output_tokens`, `router_thinking_tokens`: Optional[int]

### 10.4 Worker Telemetry
- `worker_mode`: `"DIRECT"` | `"PYTHON"`
- `worker_success`: Boolean
- `worker_error_type`: Optional[str] (`"malformed_function_call_finish_reason"`, `"provider_timeout"`, `"provider_api_error"`, `"empty_worker_response"`, etc.)
- `worker_latency_seconds`: Float
- `worker_input_tokens`, `worker_output_tokens`, `worker_thinking_tokens`: Optional[int]

### 10.5 Generation Counts
- `router_generation_attempts`: `1`
- `router_generation_success`: Boolean
- `worker_generation_attempts`: `1` (or `0` on fatal router crash)
- `worker_generation_success`: Boolean
- `llm_generation_attempts`: Integer (normally `2`)
- `llm_generation_success_count`: Integer (`0`, `1`, or `2`)

### 10.6 Preserved Python Telemetry
- `python_requested`, `python_executed`, `python_execution_count`: Bool / int
- `python_success`, `python_timeout`, `python_exit_code`, `python_error_type`: Bool / int / str
- `python_latency_seconds`, `python_stdout_length`, `python_stderr_length`, `python_output_truncated`: Float / int / bool
- `python_fallback`: Boolean

### 10.7 Preserved Search & File Telemetry
- Full search metadata (12 fields) and file metadata (12 fields) inherited from V2/V3.

---

## 11. Aggregate Evaluation Metrics & Descriptive Subgroups

### 11.1 Benchmark-Level Metrics (in `summary_level_{level}.json`)
- **Overall Accuracy**: Total correct / total tasks.
- **Attachment & Non-Attachment Accuracy**.
- **Completion Rate**: `completion_success` rate across tasks.
- **Router Metrics**:
  - `router_direct_count`, `router_python_count`
  - `router_python_routing_rate`: `router_python_count / total_tasks`
  - `router_fallback_count`, `router_fallback_rate`
  - `router_failure_count`
  - `avg_router_latency`, `avg_router_tokens`
- **Worker Metrics**:
  - `avg_worker_latency`, `avg_worker_tokens`
  - `avg_total_llm_generations`: Should equal `2.0` for fully completed runs.
- **Python Execution Metrics**:
  - `python_execution_rate`: `python_executed_count / total_tasks`
  - `python_success_rate`: `python_success_count / python_executed_count`
  - `python_missing_marker_count`, `python_policy_rejection_count`, `python_dependency_failure_count`

### 11.2 Descriptive Subgroup Breakdown (Endogenous Routing Disclaimer)
Evaluation will report accuracy across discrete routing paths:
- Accuracy on `DIRECT`-routed tasks
- Accuracy on `PYTHON`-routed tasks
- Accuracy on tasks with successful Python execution vs. failed Python execution

> **CRITICAL METHODOLOGICAL WARNING**:
> Routing decisions are selected **endogenously** by the router based on perceived difficulty and task modality. Differences in accuracy between DIRECT and PYTHON subsets reflect selection bias and must NEVER be interpreted as causal proof of capability efficacy.

---

## 12. Matched Transition Analysis Plan

Post-benchmark analysis will generate `v3_v4_task_transitions.json` comparing contemporaneous matched V3 and V4 runs across all 165 tasks:

### 12.1 Transition Classes
- **Improvement** (V3 Fail → V4 Correct): Target capability win.
- **Regression** (V3 Correct → V4 Fail): Investigated for routing misclassification or execution regressions.
- **Stable Correct** (V3 Correct → V4 Correct): Preserved capability.
- **Stable Failure** (V3 Fail → V4 Fail): Persistent difficulty.

### 12.2 Stratification Dimensions
Every transition will be cross-tabulated by:
- Benchmark Level (1, 2, 3)
- Attachment requirement and file extension
- Router decision (`DIRECT` vs. `PYTHON` vs. `Fallback`)
- Python execution outcome (Success vs. Failure taxonomy)
- Upstream provider anomaly presence

### 12.3 Key Hypothesized Transitions to Track
- Tasks where V3 attempted Python and failed the extraction contract: did V4 route to DIRECT, or did dedicated PYTHON worker formatting resolve the marker omission?
- Tasks where V3 succeeded with Python: did V4 preserve Python routing and correct execution?
- Attachment-bearing tasks: did explicit routing reduce unnecessary Python executions on simple document lookup tasks?

---

## 13. Comprehensive V4 Failure Taxonomy Plan

A mutually exclusive, hierarchical failure classification prioritizing direct operational telemetry over subjective interpretation:

| Category | Description | Primary Operational Detection Rule |
| :--- | :--- | :--- |
| `router_provider_anomaly` | Router LLM failed with provider exception | `router_error_type in {"malformed_function_call_finish_reason", "provider_timeout", "provider_api_error"}` |
| `router_malformed_output` | Router output violated syntax contract | `router_error_type in {"missing_route_marker", "ambiguous_route_text", "malformed_router_text", "empty_provider_response"}` |
| `router_fallback_direct_wrong` | Router fell back to DIRECT and answer was incorrect | `router_fallback == True` and `is_correct == False` |
| `worker_provider_anomaly` | Worker LLM failed with provider exception | `worker_error_type in {"malformed_function_call_finish_reason", "provider_timeout", "provider_api_error"}` |
| `direct_incomplete_generation` | DIRECT worker truncated by token budget | `worker_mode == "DIRECT"` and `finish_reason == "MAX_TOKENS"` |
| `direct_reasoning_or_retrieval_failure` | DIRECT worker finished cleanly but answer incorrect | `worker_mode == "DIRECT"` and `completion_success == True` and `is_correct == False` |
| `python_policy_rejection` | Python script blocked by AST security validator | `worker_mode == "PYTHON"` and `python_error_type == "SecurityPolicyError"` |
| `python_dependency_failure` | Python script failed due to missing module | `worker_mode == "PYTHON"` and `python_error_type == "ModuleNotFoundError"` |
| `python_runtime_failure` | Python script crashed with runtime exception | `worker_mode == "PYTHON"` and `python_exit_code != 0` and error is not dependency |
| `python_missing_final_marker` | Python script exited cleanly but omitted marker | `worker_mode == "PYTHON"` and `python_error_type == "MissingFinalAnswerMarker"` |
| `python_timeout` | Python script exceeded 15.0s execution limit | `worker_mode == "PYTHON"` and `python_timeout == True` |
| `python_success_wrong_answer` | Python executed, printed marker, but answer wrong | `worker_mode == "PYTHON"` and `python_success == True` and `is_correct == False` |
| `formatting_failure` | Answer correct in reasoning text but failed exact normalization | Scorer failure where ground-truth substring is present in normalized text |
| `other` | Unclassified operational failure | Fallback when no category above matches |

Every classification record will include `confidence`: `"high"` (telemetry-grounded) vs `"low"` (heuristic).

---

## 14. File and Class Impact Map

| File / Component | Current Responsibility | Required V4 Change | Risk Level |
| :--- | :--- | :--- | :---: |
| `agent/agent.py` | Defines V0-V3 agents and `AgentResult` | Add `GAIARouterAgent`; extend `AgentResult` with router/worker telemetry fields | Medium |
| `agent/__init__.py` | Exports agent classes | Export `GAIARouterAgent` | Low |
| `prompts/router.py` (NEW) | Does not exist | Implement `build_router_prompt()`, `build_direct_worker_prompt()`, `build_python_worker_prompt()`, and version constants | Low |
| `prompts/__init__.py` | Exports prompt builders | Export new router prompt builders and version strings | Low |
| `evaluation/runner.py` | Executes task and assembles evaluation metadata dictionary | Add `project_version == "v4"` branch in `execute_task()`; extract router/worker fields; assert `llm_generation_attempts == 2` | Medium |
| `evaluation/run_level.py` | CLI level runner for V0-V3 | Add `v4` to version choices; instantiate `GAIARouterAgent(llm_client=llm)` | Low |
| `evaluation/run_one.py` | CLI single-task runner | Add `v4` support for single-question testing | Low |
| `evaluation/evaluate.py` | Calculates aggregate metrics and detailed JSONL | Unpack and aggregate V4 router metrics, worker latency/token metrics, and routing breakdown | Medium |
| `evaluation/metrics.py` | Official GAIA scorer | No changes required (scorer is immutable) | None |
| `tools/python_tool.py` | Single-shot Python executor | No changes allowed (frozen V3 implementation preserved) | None |
| `tools/file_tool.py` | Attachment extractor | No changes allowed (frozen V2 implementation preserved) | None |
| `tools/web_search.py` | Tavily search wrapper | No changes allowed (frozen V1 implementation preserved) | None |
| `tests/test_router_agent.py` (NEW) | Does not exist | Implement comprehensive unit test suite covering router parsing, fallback, generation counts, and invariants | Low |

---

## 15. Class and Inheritance Design Analysis

### 15.1 Detailed Evaluation of Inheritance Options

#### Option A: Deep Subclassing (`GAIARouterAgent(GAIAPythonAgent)`)
```text
GAIAAgent -> GAIAWebAgent -> GAIAFileAgent -> GAIAPythonAgent -> GAIARouterAgent
```
- **Hazard Analysis**: `GAIAPythonAgent.run()` encapsulates V3's single-generation prompt and implicit execution logic. If `GAIARouterAgent` subclasses `GAIAPythonAgent` and inadvertently calls `super().run()`, it would trigger the V3 execution path, resulting in an accidental extra LLM generation or conflicting tool execution.
- **Evaluation**: Unacceptable architectural coupling.

#### Option B (Recommended): Composition & Direct Sibling Subclassing (`GAIARouterAgent(GAIAFileAgent)`)
```text
GAIAAgent -> GAIAWebAgent -> GAIAFileAgent
                                 |
        +------------------------+------------------------+
        |                                                 |
GAIAPythonAgent (V3 Frozen)                      GAIARouterAgent (V4)
(implicit single-shot self-routing)              (explicit 2-stage routing architecture)
[has-a PythonTool]                               [has-a PythonTool]
```
- **Design Structure**:
  - `GAIARouterAgent` inherits directly from `GAIAFileAgent`, acquiring `self.search_tool` (Tavily) and `self.file_tool` (FileTool) without inheriting any V3 prompt generation logic.
  - `GAIARouterAgent` **composes** `PythonTool` as an internal attribute: `self.python_tool = PythonTool()`.
  - Reuses pure utility functions (`clean_answer`, `extract_python_code`, `extract_python_final_answer`, `extract_direct_answer`) from module scope without inheritance entanglement.
- **Evaluation**: Clean, robust, decoupled, and completely eliminates the risk of accidental superclass double-generation.

---

## 16. Prompt Versioning Specification

All V4 prompts must be versioned explicitly and tracked in public metadata:

1. **Router Prompt**:
   - Constant: `ROUTER_PROMPT_VERSION = "capability-router-v1"`
   - Role: Inspects question, web evidence, and file evidence; outputs strictly `ROUTE: DIRECT` or `ROUTE: PYTHON`.
2. **Direct Worker Prompt**:
   - Constant: `ROUTER_DIRECT_WORKER_PROMPT_VERSION = "router-direct-worker-v1"`
   - Role: Direct question-answering prompt with `FINAL: <answer>` extraction marker.
3. **Python Worker Prompt**:
   - Constant: `ROUTER_PYTHON_WORKER_PROMPT_VERSION = "router-python-worker-v1"`
   - Role: Code-generation prompt requiring `FINAL_ANSWER: <answer>` stdout output contract.
4. **Fallback Provenance**:
   - If the router fails, the agent dispatches to `router-direct-worker-v1` with `router_fallback = True`.
   - `fallback_prompt_version` in `AgentResult` records `"router-direct-worker-v1"`.

---

## 17. Pre-Implementation Test Plan

Before implementing V4 runtime code, 25 deterministic unit tests will be specified in `tests/test_router_agent.py`:

1. `test_router_parses_clean_direct`: Verifies `ROUTE: DIRECT` resolves to `DIRECT`.
2. `test_router_parses_clean_python`: Verifies `ROUTE: PYTHON` resolves to `PYTHON`.
3. `test_router_parses_case_and_whitespace`: Verifies `route : python \n` normalizes correctly.
4. `test_router_handles_conversational_wrapping`: Verifies unique route token embedded in text is extracted.
5. `test_router_malformed_empty_triggers_direct_fallback`: Verifies empty string triggers `DIRECT` fallback.
6. `test_router_malformed_missing_token_triggers_direct_fallback`: Verifies text without route marker triggers fallback.
7. `test_router_ambiguous_tokens_trigger_direct_fallback`: Verifies presence of both DIRECT and PYTHON triggers fallback.
8. `test_router_provider_anomaly_triggers_direct_fallback`: Verifies provider anomalies trigger fallback.
9. `test_router_generation_attempts_exactly_one`: Verifies router invokes LLM exactly once.
10. `test_worker_generation_attempts_exactly_one`: Verifies worker invokes LLM exactly once.
11. `test_total_generation_attempts_exactly_two`: Verifies `llm_generation_attempts == 2` for end-to-end task.
12. `test_direct_route_executes_zero_python`: Verifies PythonTool is NOT executed when routed to DIRECT.
13. `test_python_route_executes_at_most_one_python`: Verifies PythonTool is called at most once on PYTHON route.
14. `test_no_python_retry_on_execution_failure`: Verifies no retry turn occurs on Python crash.
15. `test_no_second_synthesis_call`: Verifies Python stdout is parsed deterministically without extra LLM turn.
16. `test_function_calling_disabled_for_both_generations`: Verifies `tools_mode == "NONE"` for router and worker.
17. `test_tavily_search_executed_at_most_once`: Verifies exactly one search call per task.
18. `test_file_tool_semantics_unchanged`: Verifies identical extraction across supported and unsupported types.
19. `test_attachment_basename_accessible_on_python_route`: Verifies filename available in workspace.
20. `test_unsupported_file_extension_accessible_to_python`: Verifies `.zip` or `.pdb` copied to workspace even when FileTool text extraction fails.
21. `test_python_marker_extraction_identical_to_v3`: Verifies `FINAL_ANSWER:` contract compatibility.
22. `test_runner_supports_v4_explicitly`: Verifies `execute_task` with `project_version="v4"`.
23. `test_run_level_cli_accepts_v4`: Verifies CLI arguments and dispatch for V4.
24. `test_public_artifacts_zero_privacy_exposure`: Verifies scan passes on mock V4 records.
25. `test_v0_v1_v2_v3_regressions_prevented`: Verifies all existing 191 unit tests remain intact.

---

## 18. Operational Smoke-Test Design

A dedicated operational pre-flight test using synthetic tasks (NOT GAIA benchmark tasks) to validate end-to-end plumbing before any canonical run:

### Synthetic Test Cases
1. **Direct Route Flow**:
   - Input: Simple arithmetic question.
   - Mocked Router: Returns `ROUTE: DIRECT`.
   - Mocked Worker: Returns `FINAL: 42`.
   - Verification: `router_decision == "DIRECT"`, `python_executed == False`, `llm_generation_attempts == 2`.
2. **Python Route Success Flow**:
   - Input: Matrix multiplication question.
   - Mocked Router: Returns `ROUTE: PYTHON`.
   - Mocked Worker: Returns valid Python script printing `FINAL_ANSWER: 120`.
   - Verification: `router_decision == "PYTHON"`, `python_executed == True`, `python_success == True`, `llm_generation_attempts == 2`.
3. **Router Malformed Fallback Flow**:
   - Input: Ambiguous query.
   - Mocked Router: Returns `I am thinking about this...`.
   - Mocked Worker: Receives DIRECT worker prompt; returns `FINAL: Paris`.
   - Verification: `router_fallback == True`, `router_error_type == "missing_route_marker"`, `python_executed == False`, `llm_generation_attempts == 2`.
4. **Python Execution Failure Flow**:
   - Input: Computational query.
   - Mocked Router: Returns `ROUTE: PYTHON`.
   - Mocked Worker: Returns script with syntax error.
   - Verification: `python_executed == True`, `python_success == False`, `python_fallback == True`, `llm_generation_attempts == 2`, zero retry calls.
5. **Synthetic Attachment Access**:
   - Synthetic `.xlsx` and synthetic `.zip` test cases validating workspace copying and basename derivation.

---

## 19. Privacy Audit & Benchmark Integrity Plan

V4 public evaluation records must undergo recursive scanning to guarantee complete data isolation:
- **Zero Prohibited Key Exposure**: Scan all JSON and JSONL artifacts for forbidden keys (`question`, `ground_truth`, `prediction`, `raw_response`, `prompt`, `python_code`, `code`, `stdout`, `stderr`, `search_results`, `api_key`).
- **Permitted Fields Only**: Task UUIDs, benchmark level, file extensions, routing decisions, structured error types, token counts, and wall-clock latencies.
- **Integrity Guarantee**: No benchmark files, questions, or ground-truth values will ever be checked into Git or stored in public summaries.

---

## 20. Unresolved Risks & Methodological Assessment

### 20.1 Identified Methodological Risks
1. **Two-Generation Latency and Cost Overhead**:
   - Adding an explicit routing generation doubles the LLM API calls per task. If routing accuracy is only marginally superior to V3's implicit routing, the latency and token overhead may outweigh the reliability gain.
2. **Compound Provider Anomaly Vulnerability**:
   - Because each task requires two consecutive Gemini API calls, the probability of encountering an upstream provider anomaly increases:
     $$\text{Pr}(\text{anomaly}) = 1 - (1 - p_1)(1 - p_2) \approx 2p$$
   - This risk is mitigated by our deterministic fallback policy (router anomalies fall back to DIRECT worker), but it remains an inherent operational factor.
3. **Router Misclassification Penalty**:
   - A false-negative router decision (`DIRECT` for a task requiring deep computation) denies the agent access to Python.
   - A false-positive router decision (`PYTHON` for a simple retrieval task) exposes the agent to interpreter syntax or marker failures.

### 20.2 Implementation Readiness Verdict
All architectural boundaries, mathematical invariants, tool interfaces, prompt specifications, and fallback policies have been defined with complete precision. No hidden multi-turn reasoning or tool-loop confounds exist.

**Conclusion**: The V4 capability router design is methodologically sound, strictly bounded, and ready for implementation review.
