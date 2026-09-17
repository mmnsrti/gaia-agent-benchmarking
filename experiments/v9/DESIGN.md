# V9 — Upstream Candidate Recovery: Experimental Design Document

**Status**: PROPOSED_PRE_BENCHMARK  
**Parent Version**: Frozen V7 (`v7-targeted-repair`)  
**Proposed Experimental Version**: V9  
**Schema Version**: 7  
**Branch**: `v9-upstream-candidate-recovery`  
**Date**: September 2026  

---

## 1. Executive Summary & Version Definition

Version 9 (V9) introduces **Upstream Candidate Recovery** into the GAIA agent benchmarking framework.

Formally:
```text
V9 = Frozen V7 + at most one bounded text-only candidate-recovery generation for explicitly eligible no-candidate upstream failures
```

V9 directly addresses the primary empirical bottleneck discovered in V7 and V8 benchmarks: **upstream candidate starvation**. In the canonical V8 benchmark:
- **83 / 165 tasks (50.3%)** produced a non-empty candidate answer.
- **82 / 165 tasks (49.7%)** experienced upstream failure and produced no candidate answer (`""`), rendering half of the benchmark structurally unreachable by downstream verification (V5), self-evaluation (V6), or targeted repair (V7).

V9 provides a selective, bounded recovery opportunity exclusively for tasks where upstream generation failed to produce a candidate answer due to an eligible semantic or execution failure. If the Frozen V7 upstream worker already produces a non-empty candidate, V9 **strictly does not intervene** (`eligible = False`), guaranteeing 100.0% verbatim answer preservation on non-triggered tasks.

---

## 2. Scientific Baseline vs. Transport Infrastructure Layer

To ensure methodological rigor, V9 strictly decouples transport-level infrastructure hardening from scientific capability increments:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       SCIENTIFIC AGENT PIPELINE                             │
│  Frozen V7 (Router → Worker → V5 Verifier → V6 Self-Eval → V7 Repair)       │
│  + V9 Bounded Upstream Candidate Recovery (Scientific Intervention)         │
├─────────────────────────────────────────────────────────────────────────────┤
│                    TRANSPORT & INFRASTRUCTURE LAYER                         │
│  LLMClient Multi-Key Credential Failover (Gemini API key rotation)          │
│  TavilySearchTool Multi-Key Credential Failover (Tavily API key rotation)   │
│  Automatic Transient Error Backoff (HTTP 429 / RESOURCE_EXHAUSTED)          │
└─────────────────────────────────────────────────────────────────────────────┘
```

1. **Transport Layer (Operational Infrastructure)**:
   - Automated failover across multiple API keys in `agent/llm.py` (`discover_gemini_api_keys`) and `tools/web_search.py` (`discover_tavily_api_keys`).
   - Handles network timeouts, credential expiration, quota exhaustion, and transport retries.
   - **NOT** classified as a scientific capability increment.
   - Does **NOT** increment logical LLM generation counters.
2. **Scientific Layer (V9 Intervention)**:
   - Exactly one bounded, text-only generation to recover a candidate answer when upstream worker execution semantically failed.
   - Consumes only existing runtime evidence.
   - Increments logical LLM generation count by at most 1.

---

## 3. Primary Research Question & Secondary Questions

### Primary Research Question
> *When the Frozen V7 upstream pipeline fails to produce a non-empty candidate answer due to an eligible generation or execution failure, can one bounded, text-only recovery generation restore candidate reachability and increase final GAIA benchmark correctness without altering tasks that already produced an upstream candidate?*

### Secondary Research Questions
1. **Candidate Reachability Delta**: What percentage of starved tasks ($49.7\%$ in V8) can be converted into valid candidate answers?
2. **Recovered Candidate Accuracy**: When a starved task is recovered into a candidate answer, what is the accuracy of that candidate?
3. **Failure-Class Differential**: Which specific upstream failure classes (e.g., `EMPTY_RESPONSE`, `FUNCTION_CALL_ONLY`, `PYTHON_EXECUTION_FAILURE`, `PYTHON_OUTPUT_MISSING_MARKER`) benefit most from candidate recovery?
4. **Downstream Safeguard Interaction**: How do downstream V5 verifier, V6 self-evaluator, and V7 targeted repair interact with recovered candidate answers?
5. **Non-Triggered Answer Invariant**: Is the non-triggered answer preservation rate strictly $100.0\%$ (zero regressions on tasks that already produced a candidate)?
6. **Net Within-Run Correctness Delta**: Does V9 achieve a strictly positive net change ($\Delta = \text{improvements} - \text{regressions} > 0$) within the same task execution?
7. **Resource & Latency Overhead**: What token and latency costs are introduced by the candidate recovery stage?

---

## 4. Core Hypothesis

Pre-registered as an empirical hypothesis (NOT an assumed conclusion):
> *Upstream candidate starvation accounts for approximately half of all GAIA task failures. A single bounded recovery generation that re-examines already-collected web and file evidence with a focused answer-extraction contract can recover a non-trivial fraction of starved tasks into correct answers, while strictly preserving all existing answers on tasks where upstream worker generation succeeded.*

A finding of zero or negative net correctness improvement is an entirely valid, scientifically informative result that would prove that upstream candidate failures cannot be resolved without active re-retrieval or code re-execution.

---

## 5. Non-Goals & Strict Prohibitions

V9 strictly isolates candidate recovery. The following mechanisms are **prohibited**:
- **NO Active Verification**: No V8-style dynamic evidence re-verification.
- **NO New Web Searches**: Zero new Tavily queries or network fetches.
- **NO Additional Python Execution**: Zero sandbox runs or code executions during recovery.
- **NO File Re-reading**: Zero file re-opening, re-parsing, or multimodal re-ingestion.
- **NO Multi-Agent Systems**: No LangGraph, CrewAI, Autogen, or multi-agent debate.
- **NO Iterative Loops**: No reflection loops, re-try loops, or iterative prompt modification.
- **NO Multiple Recovery Attempts**: Exactly $\le 1$ recovery generation attempt per task.
- **NO Semantic Retries**: No retrying of failed recovery attempts.
- **NO Search Query Rewriting**: No multi-hop search reformulation.
- **NO Model Architecture Changes**: Model remains Gemini 2.5 Flash Lite (`gemini-2.5-flash-lite`), consistent with Frozen V7.

---

## 6. Architectural Options & Selected Design

### Architectural Alternatives

Two structural placements were evaluated:

```text
DESIGN A (Selected — Upstream Worker Recovery):
GAIA Question + Attachment
     ↓
Router (DIRECT vs PYTHON)
     ↓
Worker Execution (Direct LLM or Python)
     │
     ├── Candidate Non-Empty ───┐
     │                          │
     └── Candidate Empty        │
            ↓                   │
       V9 Recovery              │
            ↓                   │
     Recovered Candidate        │
            │                   │
            ▼                   ▼
     V5 Conservative Verifier (KEEP / REVISE)
            ↓
     V6 Read-Only Self-Evaluator (PASS / SUSPECT)
            ↓
     V7 Targeted Repair (Triggered if SUSPECT)
            ↓
     Final Answer

─────────────────────────────────────────────────────────────

DESIGN B (Rejected — End-of-Pipeline Bypass):
GAIA Question + Attachment
     ↓
Frozen V7 Pipeline (Worker → V5 Verifier → V6 Evaluator → V7 Repair)
     │
     ├── Final Answer Non-Empty ───> Final Answer
     │
     └── Final Answer Empty
            ↓
       V9 Recovery
            ↓
       Direct Final Answer (Bypasses V5, V6, V7)
```

### Justification for Design A (Upstream Worker Recovery)

Design A is chosen as the canonical architecture for V9 for four essential reasons:
1. **Symmetric Quality Gates**: Recovered candidates are newly synthesized hypotheses. Subjecting them to V5 verification and V6/V7 targeted repair ensures they are scrutinized under the exact same safeguards as normal candidates, rather than bypassing quality control.
2. **True Root-Cause Repair**: The empirical bottleneck is *candidate starvation* at the worker boundary. Intervening at the worker boundary restores the missing candidate so the remainder of the established agent pipeline functions as designed.
3. **Avoidance of Dual Pipelines**: Design B creates an asymmetric architecture where some final answers undergo verification/repair while others do not, confounding scientific analysis of whether gains stem from recovery or from skipping verification.
4. **Preservation of Downstream Semantics**: In Frozen V7, empty candidates bypass V5, V6, and V7 because `pre_verification_answer` and `pre_repair_answer` are empty. By restoring the candidate before V5, V5, V6, and V7 naturally activate when appropriate.

---

## 7. Execution Flow & State Machine (Design A)

```text
Input: Question, Optional File Attachment
  │
  ├─ 1. Upstream Evidence Gathering (Frozen V7)
  │    ├─ Search: ≤ 1 Tavily query on original question
  │    └─ File: ≤ 1 Local deterministic extraction
  │
  ├─ 2. Capability Routing (Frozen V7)
  │    └─ LLM Router selects DIRECT vs PYTHON
  │
  ├─ 3. Worker Execution (Frozen V7)
  │    ├─ DIRECT: LLM Worker generates candidate text
  │    └─ PYTHON: LLM generates script → PythonTool executes → extracts stdout
  │
  ├─ 4. Upstream Candidate Evaluation & V9 Recovery Gate
  │    │
  │    ├─ Candidate Non-Empty:
  │    │    ├─ candidate_recovery_eligible = False
  │    │    ├─ candidate_recovery_triggered = False
  │    │    ├─ pre_recovery_candidate = candidate
  │    │    └─ post_recovery_candidate = candidate (100% verbatim)
  │    │
  │    └─ Candidate Empty (""):
  │         ├─ Classify Upstream Failure (Failure Taxonomy)
  │         │
  │         ├─ Ineligible Failure (e.g. Provider Collapse):
  │         │    ├─ candidate_recovery_eligible = False
  │         │    └─ post_recovery_candidate = ""
  │         │
  │         └─ Eligible Failure (e.g. EMPTY_RESPONSE, FUNCTION_CALL_ONLY, etc.):
  │              ├─ candidate_recovery_eligible = True
  │              ├─ candidate_recovery_triggered = True
  │              ├─ Execute ONE Bounded Recovery Generation (candidate-recovery-v1)
  │              │    ├─ Success & Valid Parse ("FINAL: <ans>")
  │              │    │    └─ post_recovery_candidate = <ans>
  │              │    └─ Failure, Timeout, or Malformed Output
  │              │         └─ post_recovery_candidate = "" (Non-destructive)
  │
  ├─ 5. V5 Conservative Verifier (Frozen V5)
  │    ├─ If post_recovery_candidate is empty: Bypass V5
  │    └─ If post_recovery_candidate is non-empty: Evaluate KEEP vs REVISE
  │
  ├─ 6. V6 Self-Evaluator (Frozen V6)
  │    ├─ If post-verifier answer is empty: Bypass V6
  │    └─ If post-verifier answer is non-empty: Evaluate PASS vs SUSPECT
  │
  ├─ 7. V7 Targeted Repair (Frozen V7)
  │    ├─ If answer is empty or PASS: Bypass V7
  │    └─ If answer is non-empty and valid SUSPECT: Evaluate KEEP vs REPLACE
  │
  └─ 8. Final Answer Emission
```

---

## 8. Intervention Boundary & Variable Naming

To ensure absolute clarity across telemetry, logging, and evaluation, the following boundary variables are established:

| Variable Name | Type | Definition |
| :--- | :---: | :--- |
| `pre_recovery_candidate` | `str` | The exact candidate answer string produced by the Frozen V7 upstream worker before V9 intervention (empty string `""` if worker failed). |
| `post_recovery_candidate` | `str` | The candidate answer string after V9 candidate recovery evaluation (matches `pre_recovery_candidate` if ineligible or unchanged; contains parsed recovery if successfully recovered). |
| `pre_recovery_answer` | `str` | Alias for `pre_recovery_candidate` representing pipeline answer state prior to recovery. |
| `post_recovery_answer` | `str` | Pipeline answer state immediately following recovery intervention. |
| `final_answer` | `str` | The ultimate answer emitted after traversal of V5 verifier, V6 self-evaluator, and V7 targeted repair. |

### Verbatim Preservation Invariant
```python
if not candidate_recovery_triggered:
    assert post_recovery_candidate == pre_recovery_candidate
```

---

## 9. Deterministic Failure Taxonomy

Upstream failure classification is derived deterministically from existing runtime telemetry (`LLMResponse`, `PythonResult`, worker return values). No subjective LLM judgments are used.

### Eligible Upstream Failure Classes

| Failure Class | Trigger Rule | Description |
| :--- | :--- | :--- |
| `FUNCTION_CALL_ONLY` | `has_function_call_part == True and has_text_part == False` OR `worker_finish_reason == "MALFORMED_FUNCTION_CALL"` with no final text | Model attempted an unconfigured function call or provider emitted malformed function call part without final answer text. |
| `THOUGHT_ONLY` | `"thought" in response_part_types and has_text_part == False` | Model completed internal thinking/reasoning parts but generated no text part. |
| `EMPTY_RESPONSE` | `(not has_text_part or not raw_text.strip()) and worker_error_type in (None, "empty_worker_response")` | Model returned clean finish status (`STOP`) but text content was completely empty or whitespace. |
| `PYTHON_EXECUTION_FAILURE` | `worker_mode == "PYTHON" and python_executed == True and python_success == False and not candidate_extracted` | Python script crashed (syntax error, runtime exception, non-zero exit code, timeout) and direct text fallback was empty. |
| `PYTHON_OUTPUT_MISSING_MARKER` | `worker_mode == "PYTHON" and python_executed == True and python_success == True and extracted_ans is None and not candidate_extracted` | Python script ran successfully (exit 0) but stdout lacked `FINAL_ANSWER:` marker and direct fallback was empty. |
| `PYTHON_CODE_EXTRACTION_FAILURE` | `worker_mode == "PYTHON" and python_requested == False and not candidate_extracted` | Router chose `PYTHON`, but worker emitted text with no valid markdown code block (` ```python `) and direct fallback was empty. |
| `DIRECT_EXTRACTION_FAILURE` | `worker_mode == "DIRECT" and raw_text.strip() != "" and candidate_answer == ""` | Direct worker generated text, but regex parsing and cleaning extracted an empty string. |

### Excluded (Non-Eligible) Categories

| Category | Reason for Exclusion |
| :--- | :--- |
| `EXISTING_CANDIDATE` | `bool(pre_recovery_candidate and pre_recovery_candidate.strip()) == True`. Task succeeded upstream; V9 must not intervene. |
| `PROVIDER_COLLAPSE` | All Gemini API keys failed with quota exhaustion (HTTP 429), authentication error, or connection termination. Handled by transport layer or triggers operational run invalidation / quarantine. |
| `ROUTER_FATAL_COLLAPSE` | System-level crash before router initialization. |

---

## 10. Formal Eligibility Function

The eligibility function is strictly boolean, pure, and deterministic:

```python
def is_candidate_recovery_eligible(
    pre_recovery_candidate: str,
    worker_error_type: Optional[str],
    failure_class: Optional[str],
    provider_collapsed: bool,
) -> bool:
    """Determines whether a task is eligible for V9 candidate recovery."""
    # Rule 1: Must NOT have an existing candidate answer
    if pre_recovery_candidate and pre_recovery_candidate.strip():
        return False

    # Rule 2: Provider infrastructure must NOT have collapsed
    if provider_collapsed:
        return False

    # Rule 3: Upstream failure class must be an eligible recoverable class
    ELIGIBLE_CLASSES = {
        "FUNCTION_CALL_ONLY",
        "THOUGHT_ONLY",
        "EMPTY_RESPONSE",
        "PYTHON_EXECUTION_FAILURE",
        "PYTHON_OUTPUT_MISSING_MARKER",
        "PYTHON_CODE_EXTRACTION_FAILURE",
        "DIRECT_EXTRACTION_FAILURE",
    }
    return failure_class in ELIGIBLE_CLASSES
```

---

## 11. Information Firewall & Allowed Recovery Inputs

The recovery model receives **strictly sanitized runtime context** already gathered upstream. It operates under an airtight information firewall:

### Allowed Inputs
1. **Original Question**: The exact user question.
2. **Existing Web Evidence Block**: Bounded text (up to 1,500 characters) extracted by the upstream search tool.
3. **Existing File Evidence Block**: Bounded text extracted by the upstream file tool (or attachment filename/mime-type summary).
4. **Router Decision**: Capability selected by router (`DIRECT` vs `PYTHON`).
5. **Sanitized Failure Summary**: The deterministic failure class (e.g. `PYTHON_OUTPUT_MISSING_MARKER`) and a compact description of why the worker failed.
6. **Execution Output Snippet (Sanitized)**: For Python execution failures or missing marker cases, the tail of stdout/stderr (bounded to 500 characters), stripped of environment variables or paths.

### Forbidden Inputs (Strict Firewall)
- **NO Ground Truth**: Reference answers or labels.
- **NO Scorer Feedback**: Scorer functions, evaluation outcomes, or grading logic.
- **NO Hidden Reasoning**: Model chain-of-thought, private scratchpads, or unparsed thinking tokens.
- **NO Tool Access**: Function calling definitions, schema definitions, or tool bindings.
- **NO Interactive Context**: Previous conversational turns or system prompt internals.

---

## 12. Recovery Prompt Contract (`candidate-recovery-v1`)

The recovery prompt is formulated to perform exactly one task: synthesize a definitive final candidate answer from existing evidence.

### Prompt Specification
- **Prompt Version**: `candidate-recovery-v1`
- **System Objective**: Extract and state the single concise final answer based on the provided evidence.
- **Strict Instruction**:
  - Do NOT provide conversational filler, explanation, or caveats.
  - Do NOT suggest running code or performing searches.
  - State the final answer on a single line prefixed by `FINAL: `.

---

## 13. Strict Output Schema & Parser Error Taxonomy

### Output Schema
The recovery model must emit output conforming to:
```text
FINAL: <candidate_answer>
```

- Exactly one line containing the prefix `FINAL: ` followed by the non-empty candidate answer.
- No surrounding markdown code blocks (```` ``` ````).
- No multiline text.

### Parser Error Taxonomy
If the raw output deviates from the schema, `parse_candidate_recovery_result` marks the parse as invalid and assigns a deterministic error code:

| Error Code | Description |
| :--- | :--- |
| `empty_recovery_response` | Raw model text was empty or whitespace. |
| `markdown_code_fence` | Model returned markdown code blocks (```` ``` ````). |
| `missing_final_marker` | Output lacked the required `FINAL: ` prefix. |
| `empty_final_value` | Text after `FINAL: ` was whitespace or empty. |
| `multiline_candidate` | Model emitted additional lines of text after the answer. |
| `provider_timeout` | Recovery API call exceeded deadline. |
| `provider_api_error` | Non-timeout API exception from provider. |
| `malformed_function_call` | Model output was flagged as a malformed function call. |

---

## 14. Non-Destructive Failure-Safe Policy

Candidate recovery is strictly non-destructive:
```text
If recovery generation throws, times out, or emits invalid output:
    post_recovery_candidate = ""
    candidate_recovery_success = False
    Downstream V5, V6, V7 safely bypass (as for any empty candidate)
    Final Answer = ""
```

- Zero speculative guessing.
- Zero placeholder substitution (no `"UNKNOWN"`, `"N/A"`, or `"None"`).
- A failed recovery task remains cleanly recorded as an upstream candidate starvation failure without corrupting pipeline execution.

---

## 15. Generation, Tool, and Resource Budgets

### Logical Generation Budget
V9 enforces a strict ceiling on logical LLM generation attempts:

| Stage | Normal Tasks | Starved Tasks (Recovered) |
| :--- | :---: | :---: |
| Router | 1 | 1 |
| Worker | 1 | 1 |
| **V9 Candidate Recovery** | **0** | **1** |
| V5 Verifier | 1 | 1 |
| V6 Self-Evaluator | 1 | 1 |
| V7 Targeted Repair | 1 | 1 |
| **Total Standard Cap** | **$\le 5$** | **$\le 6$** |

- Runtime assertion: `assert llm_generation_attempts <= 6, "V9 exceeds six-generation cap"`
- Non-triggered tasks: `assert llm_generation_attempts <= 5, "Non-triggered V9 exceeds five-generation cap"`

### Tool & Loop Budget
- Web Searches: $\le 1$ (upstream only; **0** in recovery)
- File Extractions: $\le 1$ (upstream only; **0** in recovery)
- Python Executions: $\le 1$ (upstream only; **0** in recovery)
- Tools Mode during Recovery: `"NONE"` (text-only)
- Semantic Retries: **0**
- Recursive Loops: **0**

---

## 16. Telemetry Schema Specification (Schema Version 7)

All task records produced in V9 will record full candidate recovery telemetry alongside inherited Frozen V7 fields:

```json
{
  "schema_version": 7,
  "project_version": "v9",
  "candidate_recovery_eligible": true,
  "candidate_recovery_triggered": true,
  "candidate_recovery_failure_class": "PYTHON_OUTPUT_MISSING_MARKER",
  "candidate_recovery_attempted": true,
  "candidate_recovery_success": true,
  "candidate_recovery_parse_success": true,
  "pre_recovery_candidate": "",
  "post_recovery_candidate": "42",
  "candidate_recovery_candidate_changed": true,
  "candidate_recovery_finish_reason": "STOP",
  "candidate_recovery_response_part_types": ["text"],
  "candidate_recovery_has_text_part": true,
  "candidate_recovery_has_function_call_part": false,
  "candidate_recovery_error_type": null,
  "candidate_recovery_error_message": null,
  "candidate_recovery_logical_generation_count": 1,
  "candidate_recovery_latency_seconds": 1.45,
  "candidate_recovery_input_tokens": 820,
  "candidate_recovery_output_tokens": 12,
  "candidate_recovery_thinking_tokens": 0,
  "candidate_recovery_total_tokens": 832,
  "candidate_recovery_prompt_version": "candidate-recovery-v1"
}
```

*Public Safety Note: Prompts and raw recovery text are excluded from public-safe benchmark files to protect against evaluation leakage.*

---

## 17. Core Invariants & Safety Guarantees

1. **Non-Triggered Answer Invariant**:
   For any task where `candidate_recovery_triggered == False`:
   $$\text{final\_answer}_{\text{V9}} \equiv \text{final\_answer}_{\text{Frozen V7}}$$
2. **Failure Non-Destruction Invariant**:
   If recovery is triggered but fails:
   $$\text{post\_recovery\_candidate} == ""$$
3. **Tool Isolation Invariant**:
   During recovery execution:
   $$\Delta \text{search\_count} = 0, \quad \Delta \text{python\_count} = 0, \quad \Delta \text{file\_count} = 0$$
4. **Information Firewall Invariant**:
   Zero ground-truth or scorer data passed to recovery prompts.
5. **Generation Cap Invariant**:
   $$\text{llm\_generation\_attempts} \le 6 \quad \text{for all tasks}$$

---

## 18. Threats to Validity

1. **Hallucination in Recovered Answers**: In tasks where upstream code crashed because the required calculation was difficult, the recovery model might synthesize a confident hallucination rather than a correct answer.
2. **Downstream Safeguard Distortion**: If recovered answers are weak, they could trigger V6 `SUSPECT` and V7 `REPAIR`, consuming tokens without producing correct answers.
3. **Evidence Truncation**: Reusing only existing web evidence (truncated to 1,500 characters) may fail if the answer required information not captured in initial snippets.
4. **Provider Quota Variance**: Multi-key rotation prevents catastrophic failure, but provider latency or tier differences could introduce execution variance.

