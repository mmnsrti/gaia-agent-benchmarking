# V10 — Structured Planner → Plan-Guided Executor: Technical Design Document

**Status**: `PROPOSED_PRE_IMPLEMENTATION`  
**Parent Version**: Frozen V9 (`v9-upstream-candidate-recovery`)  
**Target Experimental Version**: V10  
**Schema Version**: 8  
**Branch**: `v10-planner-executor`  
**Baseline Main Commit**: `7e6f35bd27c83c23072e27a337d52e157d5904cd`  
**Date**: September 2026  

---

## 1. Executive Summary & Version Definition

Version 10 (V10) introduces **Structured Planning and Plan-Guided Execution** into the upstream stage of the GAIA agent benchmarking framework.

Formally:
```text
V10 = Frozen V9 with coarse Capability Router replaced by Structured Planner
      and Worker replaced by Plan-Guided Executor
```

V10 addresses the primary residual failure mode established in the canonical Frozen V9 benchmark: **upstream execution, reasoning, and evidence utilization deficiencies**.

In Frozen V9:
- Upstream candidate reachability was largely solved, rising from $45.45\%$ ($75/165$) to $96.36\%$ ($159/165$) via candidate recovery.
- However, over $65\%$ ($55/84$) of recovered candidates remained incorrect throughout the entire downstream pipeline.
- Downstream V7 targeted repair triggered across 75 tasks but yielded only $1$ net improvement ($0 + 0 + 1$).
- Diagnostic risk evaluations revealed high conditional error rates for execution ($78.3\%$) and evidence ($88.9\%$) failures.

Because post-hoc text-only repair cannot reconstruct omitted evidence or salvage a fundamentally misdirected approach, V10 intervenes earlier: replacing the coarse capability router (which made only a binary `DIRECT` vs `PYTHON` decision) with a **Structured Planner** that decomposes the objective, specifies required evidence, outlines sequential execution steps, and fixes the target answer format.

---

## 2. Scientific Baseline vs. Transport Infrastructure Layer

In accordance with GAIA benchmarking standards, V10 strictly decouples operational infrastructure from the scientific agent pipeline:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       SCIENTIFIC AGENT PIPELINE                             │
│  V10 Upstream: Structured Planner (Slot 1) → Plan-Guided Executor (Slot 2)  │
│  Frozen V9 Candidate Recovery (at most 1 recovery for starved tasks)        │
│  Frozen V5 Verifier → Frozen V6 Self-Evaluator → Frozen V7 Targeted Repair  │
├─────────────────────────────────────────────────────────────────────────────┤
│                    TRANSPORT & INFRASTRUCTURE LAYER                         │
│  LLMClient Multi-Key Credential Failover (Gemini API key pool)              │
│  TavilySearchTool Multi-Key Credential Failover (Tavily API key pool)       │
│  Automatic Transient Error Backoff (HTTP 429 / RESOURCE_EXHAUSTED)          │
└─────────────────────────────────────────────────────────────────────────────┘
```

1. **Transport Layer (Operational Infrastructure)**:
   - Multi-key API failover (`discover_gemini_api_keys`, `discover_tavily_api_keys`).
   - Rate limit backoffs and network timeout recovery.
   - Non-scientific; does NOT increment logical generation counters.
2. **Scientific Layer (V10 Intervention)**:
   - Replaces `Router → Worker` upstream pair with `Structured Planner → Plan-Guided Executor`.
   - Strictly preserves downstream candidate recovery (V9), verification (V5), self-evaluation (V6), and repair (V7).

### Model Configuration Source of Truth
Consistent with `experiments/v7/config.json` and `experiments/v9/config.json`, the scientific model configuration is strictly preserved:
```text
Model: gemini-3.5-flash-lite
thinking_level: medium
max_output_tokens: 2048
temperature: null (provider default)
tools_mode: NONE
function_calling_enabled: false
```
V10 is **not** a model-comparison experiment.

---

## 3. Empirical Motivation from Canonical V9 Benchmark Data

The design of V10 is anchored in quantitative empirical findings from the Frozen V9 canonical benchmark (165 tasks):

### 3.1 Reachability Is No Longer the Dominant Bottleneck
- **Pre-Recovery Candidate Reachability**: $75 / 165 = 45.45\%$
- **Post-Recovery Candidate Reachability**: $159 / 165 = 96.36\%$
- **Net Reachability Gain**: $+84 \text{ tasks } (+50.91 \text{ pp})$
- **Recovery Success Rate**: $84 / 90 = 93.33\%$

Upstream candidate starvation was the primary bottleneck in V7 and V8, but V9 successfully unlocked candidate reachability.

### 3.2 Recovered Candidate Quality Bottleneck
- **Recovered Candidate Initial Accuracy**: Only $26 / 84 = 30.95\%$
- **Downstream Transitions on Recovered Candidates**:
  - `RECOVERY_CORRECT_FINAL_CORRECT`: $25 / 84$ ($29.76\%$)
  - `RECOVERY_CORRECT_FINAL_WRONG`: $1 / 84$ ($1.19\%$)
  - `RECOVERY_WRONG_FINAL_CORRECT`: $3 / 84$ ($3.57\%$)
  - `RECOVERY_WRONG_FINAL_WRONG`: $55 / 84$ ($65.48\%$)

Nearly two-thirds of recovered candidates were incorrect upon generation and remained incorrect downstream.

### 3.3 Limitations of Downstream Post-Hoc Repair
- **V7 Repair Triggers Across Benchmark**: $14 \text{ (L1)} + 41 \text{ (L2)} + 20 \text{ (L3)} = 75 \text{ tasks}$
- **V7 Repair Net Improvements**: $0 \text{ (L1)} + 0 \text{ (L2)} + 1 \text{ (L3)} = 1 \text{ net task}$

When a model generates an erroneous upstream candidate due to misunderstanding the question, ignoring key evidence, or choosing an inappropriate calculation method, post-hoc text-only repair almost never succeeds in fixing the error.

### 3.4 Canonical Diagnostic Risk Signals
Aggregated V9 self-evaluation risk diagnostics across all 165 tasks show:

| Risk Category | Assessed Tasks ($N$) | Incorrect | Correct | Conditional Error Rate |
| :--- | :---: | :---: | :---: | :---: |
| **`CALCULATION`** | 1 | 1 | 0 | **100.0%** |
| **`REASONING`** | 1 | 1 | 0 | **100.0%** |
| **`EVIDENCE`** | 27 | 24 | 3 | **88.9%** |
| **`EXECUTION`** | 46 | 36 | 10 | **78.3%** |
| **`NONE`** | 81 | 24 | 57 | **29.6%** |

Together, `EXECUTION` and `EVIDENCE` account for 73 of the 75 identified non-`NONE` risk assessments, with error rates near $80\text{--}90\%$. This demonstrates that the agent fails primarily because it either misinterprets the retrieved evidence or executes an unsound calculation procedure. Intervening upstream via structured planning directly targets both of these root causes.

---

## 4. Upstream Slot Replacement & Strict Ablation Guarantee

A critical architectural requirement for V10 is that **no additional LLM generation slots are introduced**:

```text
Frozen V9 Upstream Pipeline (2 generations):
  1. Router Generation  (determines DIRECT vs PYTHON)
  2. Worker Generation  (executes DIRECT or generates PYTHON)

V10 Upstream Pipeline (2 generations):
  1. Planner Generation (decomposes task, determines MODE, OBJECTIVE, EVIDENCE, PLAN, ANSWER_TYPE)
  2. Executor Generation (executes plan via DIRECT reasoning or plan-guided PYTHON script)
```

### Ablation Properties
1. **Generations Equalized**: Both V9 and V10 allocate exactly **2 upstream generation slots**.
2. **Compute Confounder Eliminated**: Any observed performance difference between V9 and V10 cannot be dismissed as merely giving the agent "more thinking steps" or "extra generation calls".
3. **Budget Invariant Preserved**: Total logical generations remain strictly bounded:
   - Non-recovery path: $\le 5$ generations
   - Recovery path: $\le 6$ generations

---

## 5. Structured Planner Contract & Deterministic Grammar

The Structured Planner replaces the coarse router. It receives the question, web search evidence, and file context, and produces a structured, actionable plan.

### 5.1 Input Context to Planner
- `question`: The original GAIA task question.
- `search_evidence`: Summary or snippet of web search results (if search was triggered).
- `file_context`: Extracted text or metadata from attached file (if file was attached).
- System instruction strictly enforcing:
  - Do NOT solve the problem or emit the final answer.
  - Do NOT execute code or call tools.
  - Output ONLY the structured plan block.

### 5.2 Deterministic Output Grammar
The planner prompt (`planner-v1`) mandates the following line-oriented grammar:

```text
MODE: <DIRECT | PYTHON>
OBJECTIVE: <single concise sentence stating what must be computed or found>
EVIDENCE_NEEDED: <specific facts, variables, or data elements required from search/file>
PLAN:
1. <actionable step 1>
2. <actionable step 2>
...
ANSWER_TYPE: <number | name | date | list | phrase | short text>
```

### 5.3 Semantic Rules & Constraints
1. **`MODE`**: Must be either `DIRECT` or `PYTHON`.
   - `DIRECT`: For factual extraction, textual reasoning, or straightforward lookup where existing evidence is sufficient.
   - `PYTHON`: For complex arithmetic, string manipulation, date math, multi-step calculations, or large data aggregation.
2. **`OBJECTIVE`**: Exactly 1 line defining the target output clearly.
3. **`EVIDENCE_NEEDED`**: Exactly 1 line identifying the relevant pieces of provided evidence.
4. **`PLAN`**: 1 to 5 numbered steps ($1 \le N \le 5$). Steps must be operational and concrete, not abstract ("think carefully" is disallowed).
5. **`ANSWER_TYPE`**: Target output data format expected by GAIA question (e.g. integer, float with 2 decimals, comma-separated list, single surname).
6. **No Chain-of-Thought or Hidden Reasoning Exposure**: The plan must contain only declarative planning fields. No private reasoning traces or scratchpads are exposed or logged.
7. **Tool Isolation**: The planner has zero tools (`tools_mode = "NONE"`). It cannot execute searches, run Python, or re-read files.
8. **Information Firewall**: The planner has zero access to ground-truth answers, evaluation split metadata, or official scorer logic.

---

## 6. Plan-Guided Executor Contract

The Plan-Guided Executor replaces the upstream worker. It receives the task context conditioned on the structured plan.

### 6.1 Executor Input Conditioning
- `question`: Original task question.
- `search_evidence`: Search results snippet.
- `file_context`: File text / summary.
- `plan_context`: The structured plan fields (`MODE`, `OBJECTIVE`, `EVIDENCE_NEEDED`, `PLAN`, `ANSWER_TYPE`).

### 6.2 Behavior Under `MODE: DIRECT`
- Prompt version: `executor-direct-v1`.
- The model directly executes the sequential plan over the provided evidence.
- It produces the standard candidate answer contract:
  ```text
  FINAL: <candidate answer>
  ```
- Parser extracts candidate answer using existing robust multi-pattern parsing.

### 6.3 Behavior Under `MODE: PYTHON`
- Prompt version: `executor-python-v1`.
- The model writes a clean, bounded Python script that implements the steps in `PLAN`.
- The script must be enclosed in standard ```python ... ``` fences.
- When executed, the script must print the answer to stdout using:
  ```text
  FINAL_ANSWER: <candidate answer>
  ```
- Python runtime constraints:
  - Max executions per task: $\le 1$
  - Timeout: 15.0 seconds
  - Disallowed modules: `multiprocessing`, `ctypes`

---

## 7. Deterministic Planner Fallback Policy

To ensure high robustness without violating generation budgets, V10 defines a pure local fallback policy when planner output cannot be parsed:

### 7.1 Failure Trigger Conditions
- Provider timeout or API error during planner call.
- Model response is empty, truncated, or whitespace-only.
- Missing required keys (`MODE:`, `OBJECTIVE:`, `PLAN:`, `ANSWER_TYPE:`).
- Unsupported mode (anything other than `DIRECT` or `PYTHON`).
- Plan contains 0 steps or exceeds maximum steps.

### 7.2 Deterministic Default Plan
If any failure condition occurs, the agent does **NOT** call an extra LLM generation to re-route or re-plan. Instead, it deterministically constructs the following safe fallback plan:

```python
FALLBACK_PLAN = {
    "mode": "DIRECT",
    "objective": "Answer the question directly using available evidence.",
    "evidence_needed": "Existing web search or file context.",
    "plan": ["1. Extract the direct answer from the available evidence."],
    "answer_type": "short text",
    "is_fallback": True,
    "error_type": error_type,
}
```

### 7.3 Generation Budget Accounting
- The failed planner call is counted as 1 attempt (`planner_attempted = True`, `planner_success = False`).
- The fallback plan is passed to the executor as `MODE: DIRECT`.
- Total upstream generations remain strictly **2** (1 attempted planner + 1 executor).
- Zero additional API calls are incurred.

---

## 8. Preserved Downstream Stages (Frozen V9)

All downstream stages from Frozen V9 are preserved verbatim:

```text
[Executor Output]
       │
       ▼
1. Candidate Recovery (Frozen V9)
   - Triggers ONLY if candidate is empty ("") AND failure is eligible.
   - If candidate is non-empty, strictly bypasses (100% boundary preservation).
   - Generates at most 1 bounded text-only recovery.
       │
       ▼
2. V5 Answer Verifier (Frozen V5)
   - Prompt: answer-verifier-v1
   - Decides: KEEP vs REVISE (1 generation).
       │
       ▼
3. V6 Self-Evaluator (Frozen V6)
   - Prompt: self-evaluator-v1
   - Emits: PASS vs SUSPECT, confidence score, and risk_type.
       │
       ▼
4. V7 Targeted Repair (Frozen V7)
   - Prompt: targeted-repair-v1
   - Triggers ONLY if assessment is SUSPECT.
   - Decides: KEEP vs REPLACE (1 generation).
       │
       ▼
  [Final Answer]
```

---

## 9. Tool Budgets & Safety Invariants

| Resource / Action | Frozen V9 Limit | V10 Limit | Scientific Rationale |
| :--- | :---: | :---: | :--- |
| **Web Searches** | $\le 1$ | $\le 1$ | Frozen tool budget. Planner has 0 searches. |
| **File Processing** | $\le 1$ | $\le 1$ | Frozen tool budget. Planner has 0 file reads. |
| **Python Executions** | $\le 1$ | $\le 1$ | Frozen tool budget. Planner has 0 executions. |
| **Planner Generations** | N/A (Router = 1) | 1 | Replaces Router slot. |
| **Executor Generations** | N/A (Worker = 1) | 1 | Replaces Worker slot. |
| **Upstream Generations** | 2 | 2 | Zero added upstream generations. |
| **Recovery Generations** | $\le 1$ | $\le 1$ | Empty candidate only. |
| **Verifier Generations** | $\le 1$ | $\le 1$ | Candidate present only. |
| **Self-Eval Generations**| $\le 1$ | $\le 1$ | Candidate present only. |
| **Repair Generations**   | $\le 1$ | $\le 1$ | SUSPECT only. |
| **Non-Recovery Max Gen** | $\le 5$ | $\le 5$ | Strictly equalized. |
| **Recovery Max Gen**     | $\le 6$ | $\le 6$ | Strictly equalized. |
| **Information Firewall** | Strict | Strict | Zero access to labels/scorer. |

---

## 10. Telemetry Schema (Schema Version 8)

To support forensic post-benchmark analysis and regression auditing, V10 introduces Schema Version 8.

### New Telemetry Fields
```json
{
  "schema_version": 8,
  "planner_prompt_version": "planner-v1",
  "planner_attempted": true,
  "planner_success": true,
  "planner_parse_success": true,
  "planner_fallback_used": false,
  "planner_mode": "PYTHON",
  "planner_objective": "Compute total revenue from CSV file",
  "planner_evidence_needed": "Revenue column values from attached spreadsheet",
  "plan_step_count": 3,
  "plan_steps": [
    "1. Read CSV and parse header",
    "2. Filter rows matching criteria",
    "3. Sum revenue and format as integer"
  ],
  "plan_answer_type": "integer",
  "planner_error_type": null,
  "planner_input_tokens": 850,
  "planner_output_tokens": 120,
  "planner_thinking_tokens": 210,
  "planner_latency_seconds": 2.15,
  "executor_mode": "PYTHON",
  "executor_plan_used": true,
  "executor_success": true,
  "executor_prompt_version": "executor-python-v1",
  "executor_generation_attempts": 1,
  "executor_input_tokens": 1050,
  "executor_output_tokens": 340,
  "executor_thinking_tokens": 420,
  "executor_latency_seconds": 3.42
}
```

### Privacy & Serialization Safeguards
- No hidden chain-of-thought or raw reasoning tokens are logged or serialized.
- Raw system prompts are excluded from output JSONL lines.
- Only structured, parsed planning keys and telemetry token counts are stored.

