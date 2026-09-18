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

V9 provides a selective, bounded recovery opportunity exclusively for tasks where upstream generation failed to produce a candidate answer due to an eligible semantic or execution failure. If the Frozen V7 upstream worker already produces a non-empty candidate, V9 **strictly does not intervene** (`eligible = False`), guaranteeing 100.0% verbatim candidate preservation at the recovery boundary.

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

### Model Configuration Source of Truth
Consistent with `experiments/v7/config.json`, the scientific model for V9 is:
```text
Model: gemini-3.5-flash-lite
thinking_level: medium
max_output_tokens: 2048
temperature: null
```
V9 preserves this exact model configuration. V9 is **not** a model-comparison experiment.

---

## 3. Primary Research Question & Secondary Questions

### Primary Research Question
> *When the Frozen V7 upstream pipeline fails to produce a non-empty candidate answer due to an eligible generation or execution failure, can one bounded, text-only recovery generation restore candidate reachability and increase final GAIA benchmark correctness without altering tasks that already produced an upstream candidate?*

### Secondary Research Questions
1. **Candidate Reachability Delta**: What fraction of starved tasks ($49.7\%$ in V8) can be converted into valid candidate answers?
2. **Recovered Candidate Accuracy**: When a starved task is recovered into a candidate answer, what is the accuracy of that candidate?
3. **Failure-Class Differential**: Which specific upstream failure classes (e.g., `PYTHON_OUTPUT_MISSING_MARKER`, `MALFORMED_FUNCTION_CALL`, `EMPTY_RESPONSE`) benefit most from candidate recovery?
4. **Downstream Safeguard Interaction**: How do downstream V5 verifier, V6 self-evaluator, and V7 targeted repair interact with recovered candidate answers (preservation, revision, damage, rescue)?
5. **Recovery-Boundary Preservation**: Is the non-triggered recovery-boundary preservation rate strictly $100.0\%$ (zero mutations on tasks that already produced a candidate)?
6. **Within-Run Intervention Delta**: What is the net task delta ($\Delta = \text{improvements} - \text{regressions}$) measured via the within-run paired intervention measurement?
7. **Resource & Latency Overhead**: What token and latency costs are introduced by the candidate recovery stage?

---

## 4. Core Hypothesis

Pre-registered as an empirical hypothesis (NOT an assumed conclusion):
> *Upstream candidate starvation accounts for approximately half of all GAIA task failures. A single bounded recovery generation that re-examines already-collected web and file evidence with a focused answer-extraction contract can recover a non-trivial fraction of starved tasks into correct answers, while strictly preserving all existing candidate answers on tasks where upstream worker generation succeeded.*

A finding of zero or negative net correctness improvement is an entirely valid, scientifically informative result that would document that upstream candidate failures cannot be resolved without active re-retrieval or code re-execution.

---

## 5. Non-Goals & Strict Prohibitions

V9 strictly isolates candidate recovery. The following mechanisms are **prohibited**:
- **NO Active Verification**: No V8-style dynamic evidence re-verification.
- **NO New Web Searches**: Zero new Tavily queries or network fetches (`additional searches = 0`).
- **NO Additional Python Execution**: Zero sandbox runs or code executions during recovery (`additional Python = 0`).
- **NO File Re-reading**: Zero file re-opening, re-parsing, or multimodal re-ingestion (`additional file reads = 0`).
- **NO Multi-Agent Systems**: No LangGraph, CrewAI, Autogen, or multi-agent debate.
- **NO Iterative Loops**: No reflection loops, re-try loops, or iterative prompt modification.
- **NO Multiple Recovery Attempts**: Exactly $\le 1$ recovery generation attempt per task.
- **NO Semantic Retries**: No retrying of failed recovery attempts (`semantic retries = 0`).
- **NO Search Query Rewriting**: No multi-hop search reformulation.
- **NO Model Architecture Changes**: Model remains Gemini 3.5 Flash Lite (`gemini-3.5-flash-lite`), identical to Frozen V7.

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
  │    ├─ Search: ≤ 1 Tavily query on original question (query length ≤ 1500 chars)
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
  │    │    ├─ pre_recovery_candidate = worker candidate
  │    │    └─ post_recovery_candidate = pre_recovery_candidate (100% verbatim)
  │    │
  │    └─ Candidate Empty (""):
  │         ├─ pre_recovery_candidate = ""
  │         ├─ Deterministic Failure Classification (Precedence Order)
  │         │
  │         ├─ Ineligible (e.g. Provider Error / Unknown):
  │         │    ├─ candidate_recovery_eligible = False
  │         │    └─ post_recovery_candidate = ""
  │         │
  │         └─ Eligible Failure (e.g. PYTHON_OUTPUT_MISSING_MARKER, etc.):
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

## 8. Intervention Boundary & Explicit Variable Naming

To prevent confusion between recovery outputs and downstream verifier/repair transformations, the runtime establishes three distinct variable layers:

| Variable Name | Stage | Definition |
| :--- | :---: | :--- |
| `pre_recovery_candidate` | Worker Output | The candidate string generated by the Frozen V7 upstream worker before V9 intervention (empty string `""` on worker failure). |
| `post_recovery_candidate` | V9 Boundary | The candidate string immediately following V9 candidate recovery evaluation (matches `pre_recovery_candidate` if ineligible or unchanged; contains parsed recovery answer if successfully recovered). |
| `final_answer` | Pipeline Output | The ultimate answer emitted after full traversal of V5 verifier, V6 self-evaluator, and V7 targeted repair. |

### Recovery-Boundary Preservation Invariant
```python
if candidate_recovery_triggered is False:
    assert post_recovery_candidate == pre_recovery_candidate
```

---

## 9. Deterministic Failure Taxonomy & Classification Precedence

Upstream failures are classified using a **single, mutually exclusive, strictly ordered classifier** based on observable post-worker runtime state in `agent/agent.py`.

### Classification Precedence Order

Every task that produces an empty candidate (`pre_recovery_candidate == ""`) is evaluated through the following priority order, receiving **at most one** failure classification:

```text
1. PROVIDER_ERROR (INELIGIBLE)
   worker_error_type in {"provider_timeout", "provider_api_error"}
   OR router_error_type in {"provider_timeout", "provider_api_error"}

2. PYTHON_OUTPUT_MISSING_MARKER (ELIGIBLE)
   worker_mode == "PYTHON"
   AND python_executed is True
   AND python_result is not None
   AND python_result.error_type == "MissingFinalAnswerMarker"
   AND pre_recovery_candidate == ""

3. PYTHON_EXECUTION_FAILURE (ELIGIBLE)
   worker_mode == "PYTHON"
   AND python_executed is True
   AND python_result is not None
   AND python_result.success is False
   AND python_result.error_type != "MissingFinalAnswerMarker"
   AND pre_recovery_candidate == ""

4. PYTHON_CODE_EXTRACTION_FAILURE (ELIGIBLE)
   worker_mode == "PYTHON"
   AND python_requested is False
   AND pre_recovery_candidate == ""

5. MALFORMED_FUNCTION_CALL (ELIGIBLE)
   (worker_error_type == "malformed_function_call_finish_reason"
    OR (worker_llm_resp is not None and getattr(worker_llm_resp, "finish_reason", None) == "MALFORMED_FUNCTION_CALL"))
   AND pre_recovery_candidate == ""

6. FUNCTION_CALL_ONLY (ELIGIBLE)
   has_function_call_part is True
   AND has_text_part is False
   AND worker_error_type != "malformed_function_call_finish_reason"
   AND pre_recovery_candidate == ""

7. THOUGHT_ONLY (ELIGIBLE)
   "thought" in response_part_types
   AND has_text_part is False
   AND has_function_call_part is False
   AND pre_recovery_candidate == ""

8. DIRECT_EXTRACTION_FAILURE (ELIGIBLE)
   worker_mode == "DIRECT"
   AND worker_raw_response is not None
   AND worker_raw_response.strip() != ""
   AND pre_recovery_candidate == ""

9. EMPTY_RESPONSE (ELIGIBLE - LAST RESORT SEMANTIC CLASS)
   pre_recovery_candidate == ""
   AND worker_error_type in (None, "empty_worker_response")
   AND (not worker_raw_response or not worker_raw_response.strip())
   (Evaluated strictly after steps 1–8 have been excluded)

10. UNKNOWN_NO_CANDIDATE (INELIGIBLE)
    pre_recovery_candidate == "" and none of the above specific rules matched.
```

### Mutual Exclusivity Invariant
```python
assert failure_class is None or isinstance(failure_class, str)
# Exactly one failure classification per task; never multiple simultaneous classes.
```

### Detailed Taxonomy Table

| Failure Class | Eligibility | Rule / Telemetry State | Description |
| :--- | :---: | :--- | :--- |
| `PROVIDER_ERROR` | **Ineligible** | `worker_error_type in {"provider_timeout", "provider_api_error"}` | Transport/API failure. Multi-key failover exhausted. Non-recoverable scientifically. |
| `PYTHON_OUTPUT_MISSING_MARKER` | **Eligible** | `worker_mode == "PYTHON" and python_executed and python_result.error_type == "MissingFinalAnswerMarker" and pre_recovery_candidate == ""` | Python executed (exit 0) but stdout lacked `FINAL_ANSWER:` marker and direct fallback was empty. |
| `PYTHON_EXECUTION_FAILURE` | **Eligible** | `worker_mode == "PYTHON" and python_executed and not python_result.success and python_result.error_type != "MissingFinalAnswerMarker" and pre_recovery_candidate == ""` | Python script threw an exception, syntax error, or non-zero exit code, and direct fallback was empty. |
| `PYTHON_CODE_EXTRACTION_FAILURE` | **Eligible** | `worker_mode == "PYTHON" and not python_requested and pre_recovery_candidate == ""` | Router chose `PYTHON`, but worker emitted no valid ` ```python ` block and direct fallback was empty. |
| `MALFORMED_FUNCTION_CALL` | **Eligible** | `worker_error_type == "malformed_function_call_finish_reason"` or finish reason is `MALFORMED_FUNCTION_CALL` | Model attempted a malformed function call structure without extractable answer text. |
| `FUNCTION_CALL_ONLY` | **Eligible** | `has_function_call_part and not has_text_part and worker_error_type != "malformed_function_call_finish_reason"` | Model emitted valid function call part but zero text parts. |
| `THOUGHT_ONLY` | **Eligible** | `"thought" in response_part_types and not has_text_part and not has_function_call_part` | Model completed reasoning parts but generated zero text answer. |
| `DIRECT_EXTRACTION_FAILURE` | **Eligible** | `worker_mode == "DIRECT" and raw_text.strip() != "" and pre_recovery_candidate == ""` | Direct worker produced text, but regex extraction/cleaning yielded empty string. |
| `EMPTY_RESPONSE` | **Eligible** | All above excluded, text is empty/whitespace, and no provider error. | Last-resort semantic empty output from model. |

---

## 10. Formal Eligibility Function

The eligibility function is pure, deterministic, and rejects provider infrastructure failures:

```python
def is_candidate_recovery_eligible(
    pre_recovery_candidate: str,
    worker_error_type: Optional[str],
    failure_class: Optional[str],
) -> bool:
    """Determines whether a task is eligible for V9 candidate recovery."""
    # Rule 1: Non-empty candidate is strictly ineligible (100% preservation)
    if pre_recovery_candidate and pre_recovery_candidate.strip():
        return False

    # Rule 2: Upstream provider / infrastructure errors are strictly ineligible
    if worker_error_type in {"provider_timeout", "provider_api_error"}:
        return False

    # Rule 3: Must match an eligible recoverable class
    ELIGIBLE_CLASSES = {
        "PYTHON_OUTPUT_MISSING_MARKER",
        "PYTHON_EXECUTION_FAILURE",
        "PYTHON_CODE_EXTRACTION_FAILURE",
        "MALFORMED_FUNCTION_CALL",
        "FUNCTION_CALL_ONLY",
        "THOUGHT_ONLY",
        "DIRECT_EXTRACTION_FAILURE",
        "EMPTY_RESPONSE",
    }
    return failure_class in ELIGIBLE_CLASSES
```

---

## 11. Information Firewall & Recovery Inputs

The recovery model receives strictly sanitized runtime context already gathered upstream. It operates under an airtight information firewall:

### Allowed Inputs
1. **Original Question**: The exact user question.
2. **Existing Web Evidence Block**: The already-retrieved, already-formatted web evidence block produced upstream by Tavily (the identical evidence block normally supplied to the downstream verifier). No additional search is performed. The 1,500-character limit applies to the Tavily search query, not automatically to the returned evidence block.
3. **Existing Textual File Context**: Already-extracted text from the upstream file tool (`file_result.text_content`). If the attachment was handled only as native multimodal input and no reusable textual extraction exists, V9 recovery receives only the existing textual metadata/placeholder (`file_name`, mime-type description). No attachment reread or secondary native multimodal ingestion occurs (`additional file reads = 0`).
4. **Router Decision**: Capability selected by router (`DIRECT` vs `PYTHON`).
5. **Sanitized Failure Classification**: The deterministic failure class (e.g. `PYTHON_OUTPUT_MISSING_MARKER`).
6. **Sanitized Execution Output Snippet**: For Python failures or missing marker cases, the tail of stdout/stderr (bounded to 500 characters), stripped of environment paths or private variables.

### Forbidden Inputs (Strict Firewall)
- **NO Ground Truth**: Reference answers or labels.
- **NO Scorer Feedback**: Scorer functions, evaluation outcomes, or grading logic.
- **NO Hidden Reasoning**: Model chain-of-thought, private scratchpads, or unparsed thinking tokens.
- **NO Tool Access**: Function calling definitions, schema definitions, or tool bindings.
- **NO Interactive Context**: Previous conversational turns or system prompt internals.

---

## 12. Recovery Prompt Contract (`candidate-recovery-v1`)

The recovery prompt has one exclusive purpose: synthesize a definitive final candidate answer from existing evidence.

### Prompt Specification
- **Prompt Version**: `candidate-recovery-v1`
- **System Objective**: Extract and emit the single concise final answer based on the provided evidence.
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
    final_answer = ""
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

All task records produced in V9 record full candidate recovery telemetry alongside inherited Frozen V7 fields:

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

1. **Recovery-Boundary Preservation Invariant**:
   For any task where `candidate_recovery_triggered == False`:
   $$\text{post\_recovery\_candidate} \equiv \text{pre\_recovery\_candidate}$$
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
3. **Evidence Incompleteness**: Reusing only existing web evidence without new searches may fail if the answer required information not captured in initial snippets.
4. **Provider Quota Variance**: Multi-key rotation prevents catastrophic failure, but provider latency or tier differences could introduce execution variance.
