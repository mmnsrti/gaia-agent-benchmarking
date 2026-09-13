# V8 — Bounded Active Evidence Verification: Experimental Design Document

**Status**: PROPOSED / PRE-BENCHMARK  
**Parent Version**: Frozen V7 (`v7-targeted-repair-agent`)  
**Proposed Experimental Version**: V8  
**Schema Version**: 7  

---

## 1. Frozen Parent Baseline (V7)

V8 directly inherits the frozen V7 baseline:
```text
V7 = frozen V6 + one bounded text-only targeted repair generation triggered only by valid SUSPECT
```

In frozen V7:
- Upstream pipeline executes initial Tavily search ($\le 1$), file extraction ($\le 1$), capability routing (`DIRECT` vs `PYTHON`), route-specific single-shot worker execution, candidate eligibility check, conservative verification (`KEEP` vs `REVISE`), read-only self-evaluation (`PASS` vs `SUSPECT`, `RISK_TYPE`, `CONFIDENCE`), and optional one-shot text-only repair.
- The V7 repair stage operates strictly on existing evidence without tool access, new search queries, Python executions, or retries.
- All upstream V0–V7 behavior, prompts, configurations, and benchmark artifacts remain strictly immutable.

---

## 2. Research Motivation

The canonical V7 benchmark across 165 GAIA validation tasks established:
```text
Total GAIA validation tasks: 165
Pre-repair correct: 46 / 165 (27.88%)
Post-repair correct: 46 / 165 (27.88%)
V7 repair improvements: 0
V7 repair regressions: 0
Net repair delta: 0
Valid SUSPECT triggers: 19
Evaluator-assigned EVIDENCE risks: 15 / 19 (78.95%)
```

In V7, the repair agent was intentionally prohibited from retrieving new evidence. Across the 19 triggered tasks, 15 (78.95%) were labeled by the upstream evaluator as suffering specifically from an `EVIDENCE` risk.

V8 tests whether providing one bounded active retrieval opportunity helps when the upstream evaluator diagnoses an `EVIDENCE` defect.

> [!NOTE]
> `RISK_TYPE: EVIDENCE` is an evaluator-assigned diagnostic label, not ground-truth causal attribution. V8 does not assume or assert that lack of evidence caused V7 failures; it experimentally tests whether targeted retrieval changes outcomes.

---

## 3. Primary & Secondary Research Questions

### Primary Research Question
> *When Frozen V7 reaches a non-empty answer whose upstream V6 diagnostic is a valid `SUSPECT` with `RISK_TYPE: EVIDENCE`, does one additional bounded web retrieval followed by one bounded evidence-based adjudication correct more erroneous answers than it harms correct answers?*

### Secondary Research Question
> *Does newly retrieved evidence change the correction rate relative to Frozen V7's same-evidence text-only repair baseline?*

---

## 4. Single Added Capability & Non-Goals

V8 introduces exactly **one** new capability:
> **One bounded active evidence-verification opportunity (at most 1 additional Tavily web search followed by at most 1 bounded adjudication generation), triggered strictly by a valid `SUSPECT` evaluation with `RISK_TYPE: EVIDENCE` on a non-empty Frozen V7 answer.**

### Explicit Non-Goals & Prohibitions
To preserve single-variable experimental discipline, V8 strictly prohibits:
- **Python verification**: forbidden (no Python tool calls, no calculation verifiers).
- **Tool chooser / Router**: forbidden (no dynamic routing between search and Python).
- **Verification planner**: forbidden (no query planning LLM generation).
- **Adaptive search / Multi-hop**: forbidden (no secondary searches, no search loops).
- **Search retries**: forbidden (0 provider retries on search).
- **Adjudication retries**: forbidden (0 provider retries on adjudication).
- **File reread / Re-extraction**: forbidden (no file operations in V8).
- **Candidate starvation recovery**: forbidden (empty V7 answers bypass V8).
- **Post-verification self-eval / repair**: forbidden (no recursive loops).
- **Multi-agent frameworks**: forbidden (no LangGraph, smolagents, CrewAI).
- **Confidence filtering**: forbidden (`confidence_threshold = null`).

---

## 5. Architecture & Execution Flow

```text
Frozen V7 Pipeline
      ↓
V7 Final Answer
      ↓
Read existing upstream V6 diagnostic
      ↓
Eligibility Guard
      │
      ├── empty answer
      │       ↓
      │     BYPASS (0 search, 0 LLM calls)
      │
      ├── invalid/no self-evaluation (self_eval_success is False)
      │       ↓
      │     BYPASS (0 search, 0 LLM calls)
      │
      ├── PASS assessment
      │       ↓
      │     BYPASS (0 search, 0 LLM calls)
      │
      ├── SUSPECT but RISK_TYPE != EVIDENCE (e.g., REASONING, FORMAT, EXECUTION, CALCULATION)
      │       ↓
      │     BYPASS (0 search, 0 LLM calls)
      │
      └── valid SUSPECT + RISK_TYPE == EVIDENCE + non-empty V7 answer
              ↓
      Deterministic Verification Query Generation (pure string helper)
              ↓
      ONE additional targeted Tavily search (search_depth="basic", max_results=5, N ≤ 1)
              ↓
       ┌──────┴───────────────────────────┐
       │                                  │
 search failure                     usable evidence
 or zero results               (success=True, count > 0)
       │                                  │
       │                                  ↓
       │                   ONE bounded V8 adjudication generation
       │                   (`active-evidence-verification-v1`, mode="NONE", N ≤ 1)
       │                                  │
       │                            ┌─────┴─────┐
       │                            │           │
       │                       KEEP (1 line)  REPLACE (2 lines)
       │                            │           │
       │                            │     new final answer
       │                            │           │
       │       [PARSER FAILURE] ────┤           │
       │       (Fallback: preserve) │           │
       │                            │           │
       └────────────────────────────┴─────┬─────┘
                                          ↓
                                     V8 Final Answer
```

---

## 6. Eligibility Contract

Active evidence verification is eligible if and only if ALL conditions are met:
```python
bool(v7_final_answer and v7_final_answer.strip())
and v7_result.self_eval_success is True
and v7_result.self_eval_assessment == "SUSPECT"
and v7_result.self_eval_risk_type == "EVIDENCE"
```

- **Upstream Diagnostic Source**: Strictly reuses the structured V6 diagnostic fields already recorded on `v7_result`.
- **No Free-Form Inference**: Never infers risk from text or reasoning logs.
- **No Confidence Thresholding**: `confidence_threshold = null`. All valid `SUSPECT + EVIDENCE` candidates are eligible regardless of confidence score.
- **Ineligible Behavior**: If ineligible, active verification is bypassed; 0 searches and 0 LLM calls are made; `pre_active_verification_answer` is preserved verbatim.

---

## 7. Active Verification Query Contract

To avoid adding an extra LLM generation, V8 uses a deterministic, pure Python query construction helper:
```python
def build_active_evidence_query(question: str, current_answer: str) -> str:
    return (
        f"{question.strip()}\n\n"
        f"Candidate answer to independently verify:\n"
        f"{current_answer.strip()}"
    )
```

- **Query Truncation**: Reuses the standard `TavilySearchTool` contract which deterministically truncates queries exceeding 1,500 characters to `cleaned_query[:1500]`.
- **No LLM Planner**: Zero LLM generations for query formulation.
- **No Search Loops**: Exactly 1 search executed.

---

## 8. Search Budget & Failure Policy

- **Upstream Search**: $\le 1$ Tavily search (inherited from V1–V7).
- **V8 Search**: $\le 1$ Tavily search.
- **Total Global Search Budget**: $\le 2$ Tavily searches per task.
- **Usable Evidence Definition**:
  ```python
  usable_evidence = (search_result.success is True) and (len(search_result.results) > 0)
  ```
- **Search Failure Policy**:
  If the search fails (provider exception, timeout, quota error, network failure) OR returns zero results:
  - Adjudication generation is **NOT** executed.
  - Final answer remains `pre_active_verification_answer` verbatim.
  - Failure is recorded under `active_verification_search_error_type`.
  - Prevents falling back to same-evidence reconsideration.

---

## 9. Adjudication Stage & Strict Output Schema

### Prompt Version
`active-evidence-verification-v1`

### Allowed Adjudication Inputs (Strict Firewall)
The adjudicator receives ONLY:
1. Original question
2. Current Frozen V7 final answer
3. Existing original web evidence (from upstream search)
4. Existing extracted file context (from upstream file extraction)
5. Newly retrieved active verification evidence
6. Structured upstream V6 diagnostic (`ASSESSMENT: SUSPECT`, `RISK_TYPE: EVIDENCE`, `CONFIDENCE`)
7. Compact deterministic execution summary

It does **NOT** receive:
- Ground-truth reference answers or scorer outputs
- Correctness labels
- Hidden chain-of-thought or worker reasoning
- Generated Python source code or Python stdout/stderr
- Raw V5 verifier, V6 evaluator, or V7 repair responses

### Output Schema
The adjudicator must emit strictly one of two formats:

1. **KEEP** (exactly 1 line):
   ```text
   VERIFICATION_ACTION: KEEP
   ```
2. **REPLACE** (exactly 2 lines):
   ```text
   VERIFICATION_ACTION: REPLACE
   FINAL: <non-empty one-line answer>
   ```

### Strict Parser Rules
- Matching is case-insensitive for `VERIFICATION_ACTION`.
- Result status is one of `VALID_KEEP`, `VALID_REPLACE`, or `INVALID`.
- Rejected as `INVALID`:
  - Empty response
  - Markdown formatting or code fences (` ``` `)
  - Extra prose before or after schema
  - Unexpected or duplicate fields
  - Missing `VERIFICATION_ACTION`
  - Unknown action
  - `KEEP` accompanied by `FINAL`
  - `REPLACE` missing `FINAL`
  - Empty or whitespace-only `FINAL`
  - Multiline `FINAL` answer
  - Same-answer replacement (`FINAL == current_answer`)

---

## 10. Failure Preservation Invariant

On **ANY** V8 failure:
```text
post_active_verification_answer = pre_active_verification_answer
final_answer = pre_active_verification_answer
active_verification_answer_changed = False
```

Failures covered:
- Search provider exception, HTTP error, timeout
- Search returning 0 results
- Adjudication provider exception, timeout, rate limit
- Unexpected finish reason (`MALFORMED_FUNCTION_CALL`, `MAX_TOKENS`, etc.)
- Unexpected provider response type
- Parser rejection (syntax error, extra prose, missing fields, duplicate fields, same-answer replacement)

---

## 11. Budget Invariants

- **Total Standard LLM Generations**: $\le 6$ (Router $\le 1$ + Worker $\le 1$ + Verifier $\le 1$ + Self-Evaluator $\le 1$ + Repair $\le 1$ + Adjudication $\le 1$).
- **Total Tavily Searches**: $\le 2$ (Upstream $\le 1$ + Active Verification $\le 1$).
- **Total Python Executions**: $\le 1$ (Upstream $\le 1$, V8 active verification $= 0$).
- **Total File Tool Executions**: $\le 1$ (Upstream $\le 1$, V8 active verification reread $= 0$).
- **Retries**: $0$ across all providers.

---

## 12. Primary Outcome & Funnel Metrics

### Within-Run Causal Measurement
Because V8 logs both `pre_active_verification_answer` and `post_active_verification_answer` within the exact same execution trace:
```text
IMPROVEMENT:      pre_correct == False and post_correct == True
REGRESSION:       pre_correct == True and post_correct == False
STABLE_CORRECT:   pre_correct == True and post_correct == True
STABLE_FAILURE:   pre_correct == False and post_correct == False
NOT_TRIGGERED:    active_verification_triggered == False
```

- **Net Active Verification Delta**:
  $$\Delta_{\text{active}} = \text{improvements} - \text{regressions}$$
- **Correction Rate**:
  $$\text{Correction Rate} = \frac{\text{improvements}}{\text{initially wrong eligible tasks}}$$
- **Harm Rate**:
  $$\text{Harm Rate} = \frac{\text{regressions}}{\text{initially correct eligible tasks}}$$

### Funnel Metrics
- Total benchmark tasks
- Non-empty V7 answers
- Valid `SUSPECT` candidates
- `SUSPECT + EVIDENCE` candidates
- Active verification eligible
- Searches attempted
- Searches successful
- Searches returning usable evidence
- Adjudications attempted
- Valid `KEEP` actions
- Valid `REPLACE` actions
- Invalid adjudications
- Answers changed
- Usable evidence rate: $\frac{\text{usable searches}}{\text{searches attempted}}$
- Adjudication coverage: $\frac{\text{valid adjudications}}{\text{usable searches}}$
- Change rate: $\frac{\text{answers changed}}{\text{valid adjudications}}$

### Causal vs Observational Distinction
- **Primary Causal Effect**: Within-run pre-vs-post active verification comparison ($V7_{\text{final}} \rightarrow V8_{\text{final}}$). Zero cross-run sampling variance.
- **Matched V7 Run**: Observational only. Useful for monitoring provider stability and global completion behavior, but explicitly labeled non-causal.

