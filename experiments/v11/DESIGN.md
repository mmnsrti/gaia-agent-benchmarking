# V11 — Architectural Specification: Planner-Guided Adaptive Evidence Retrieval

**Status:** PROPOSED_PRE_IMPLEMENTATION
**Document Version:** 1.0
**Schema Version:** 9
**Branch:** `v11-adaptive-evidence-retrieval`
**Repository Parent Commit:** `0761b81330540cdc67fe2d662aef049bc87d9d8f`
**Scientific Parent:** Frozen V10 (`v10-planner-executor`)
**Canonical Parent Inference Commit:** `314d0aecd01a1679a96d85256044c01c8b6c30ce`
**Canonical Parent Benchmark Score:** 84 / 165 (50.91%)
**Date:** September 2026

---

## 1. Motivation & Empirical Diagnostics from Frozen V10

Version 10 (V10) introduced **Structured Planning and Plan-Guided Execution**, replacing the coarse capability router with an equalized structured planner slot. On identical context snapshots, V10 achieved a strictly positive primary paired delta ($\Delta_{\text{upstream}} = +8$) and raised canonical benchmark accuracy to $84 / 165 = 50.91\%$ (+11 tasks over Frozen V9).

However, deep diagnostic analysis of Frozen V10 telemetry revealed a stark, unaddressed empirical bottleneck:
1. **Evidence-Insufficiency Resistance:**
   In Frozen V10 self-evaluation risk diagnostics, tasks assessed with `EVIDENCE` risk exhibited an **$88.89\%$ (32 / 36)** error rate. This error rate was essentially identical to Frozen V9 ($88.9\%$).
2. **Single-Search Rigidity:**
   Frozen V2 through V10 strictly enforced at most one initial web search formulated by using the raw user question verbatim. In complex information-seeking tasks requiring entity disambiguation, secondary attributes, or date-filtered verification, the initial query often returned general or irrelevant search snippets.
3. **Downstream Repair Impotence on Starved Evidence:**
   Post-hoc Targeted Repair produced only $+1$ net improvement across the entire 165-task benchmark ($16 \text{ KEEP} / 0 \text{ REPLACE}$ on Level 1; $32 \text{ KEEP} / 2 \text{ REPLACE}$ on Level 2; $14 \text{ KEEP} / 2 \text{ REPLACE}$ on Level 3). When the underlying execution trace lacks the critical factual predicate, text-only reflection cannot repair the answer.

Version 11 (V11) targets **ONLY** this evidence-insufficiency bottleneck by equipping the structured planner with the capability to assess evidence sufficiency and optionally request **at most ONE targeted follow-up web search**.

---

## 2. Research Definition & Capability Boundary

### Primary Research Question
> *When Frozen V10's structured planner determines that the single frozen first-pass web search does not provide the evidence needed to execute its plan, can one bounded, planner-authored follow-up web search improve upstream candidate correctness without adding any LLM generation slots or changing Frozen V10's downstream safeguards?*

### Formal V11 Definition
$$\text{V11} = \text{Frozen V10} + \text{at most ONE planner-triggered targeted follow-up web search}$$

### What V11 Does
- Preserves the single first-pass Tavily web search (`Search 1`) using the original question.
- Preserves single-pass local deterministic file processing (`FileTool`).
- Upgrades the structured planner prompt to `planner-v2-adaptive-evidence`.
- In its single upstream planning generation, Planner v2 evaluates the combined initial context and emits a structured contract containing `EVIDENCE_STATUS` (`SUFFICIENT` vs `INSUFFICIENT`) and `FOLLOWUP_QUERY` (`NONE` vs targeted query string).
- If `EVIDENCE_STATUS == SUFFICIENT`, follow-up search is bypassed, maintaining exactly 1 search call.
- If `EVIDENCE_STATUS == INSUFFICIENT` and the query is valid and non-duplicate, executes **at most ONE targeted follow-up web search** (`Search 2`).
- Augments the search evidence passed to the Executor with labeled primary and follow-up sections.
- Forwards the execution plan to the Plan-Guided Executor (`DIRECT` or `PYTHON`).
- Passes the resulting candidate answer to the unchanged Frozen V10 downstream pipeline (Recovery $\to$ Verifier $\to$ Self-Evaluator $\to$ Targeted Repair).

### What V11 Does NOT Do
- Does **NOT** add an extra LLM planning generation (upstream slots remain strictly 2).
- Does **NOT** introduce an iterative search loop or autonomous tool loop ($N_{\text{searches}} \le 2$).
- Does **NOT** implement multi-agent search or browser agents.
- Does **NOT** alter the Executor prompts (`executor-direct-v1`, `executor-python-v1`) beyond evidence labeling.
- Does **NOT** add Python retries, code repair, or second Python runs ($N_{\text{python}} \le 1$).
- Does **NOT** alter downstream safeguards (Candidate Recovery, Verifier, Self-Evaluator, Targeted Repair).
- Does **NOT** rewrite the user question prior to Search 1.

---

## 3. Architecture & Execution Flow

```text
GAIA Question + Optional Attachment File
     ↓
ONE Tavily Search 1 (Original Question as Query, Capped at 1,500 Chars, N ≤ 1)
     ↓
ONE File Context Preparation if applicable (N ≤ 1)
     ↓
Stage 1: Structured Planner v2 (`planner-v2-adaptive-evidence`, mode="NONE", N ≤ 1)
     │
     ├── [EVIDENCE_STATUS: SUFFICIENT & FOLLOWUP_QUERY: NONE]
     │        ↓
     │   SEARCH 2 BYPASSED (second_search_triggered = False)
     │   Total Searches = 1
     │        ↓
     │   Proceed directly to Stage 2 Executor
     │
     └── [EVIDENCE_STATUS: INSUFFICIENT & Valid Non-Duplicate FOLLOWUP_QUERY]
              ↓
         SEARCH 2 TRIGGERED (second_search_triggered = True)
              ↓
         Deterministic Query Normalizer (Strip, collapse whitespace, cap at 1500 chars)
              │
              ├── [Duplicate of Search 1 Query] → Skip Search 2 (second_search_skipped_duplicate = True)
              │                                   Total Searches = 1
              │
              └── [Distinct Targeted Query]
                       ↓
                   Non-LLM Search 2 (Tavily, basic, max_results=5, N ≤ 1)
                       ├── [Search 2 Succeeded] → Augment evidence: Primary + Follow-Up
                       └── [Search 2 Failed/Empty] → Fallback to Search 1 evidence (clean fallback)
                            ↓
Stage 2: Plan-Guided Executor (`executor-direct-v1` or `executor-python-v1`, N ≤ 1)
     ↓
Candidate Formulation Boundary (`pre_recovery_candidate`)
     │
     ├── [Upstream Candidate Non-Empty] → post_recovery_candidate = pre_recovery_candidate (Preserved 100%)
     └── [Upstream Candidate Empty `""`] → Stage 2b: Frozen V9 Candidate Recovery (N ≤ 1, when eligible)
              ↓
Stage 3: Frozen V5 Answer Verifier (`answer-verifier-v1`, mode="NONE", N ≤ 1)
     ↓
Stage 4: Frozen V6 Self-Evaluator (`self-evaluator-v1`, mode="NONE", N ≤ 1)
     ↓
Stage 5: Frozen V7 Targeted Repair (`targeted-repair-v1`, mode="NONE", N ≤ 1, if SUSPECT)
     ↓
Final Benchmark Answer
```

---

## 4. Upstream Generation Slots & Compute Equivalence

A central invariant of V11 is that **Search 2 is a deterministic retrieval action, not an additional LLM generation**.

| Stage | Component | LLM Generation Slot | Tool Call |
| :--- | :--- | :---: | :---: |
| Initial Retrieval | Tavily Search 1 | 0 | 1 |
| Initial Context | FileTool | 0 | $\le 1$ |
| Upstream Slot 1 | Structured Planner v2 | **1** | 0 |
| Adaptive Retrieval | Targeted Search 2 (Optional) | **0** | $\le 1$ |
| Upstream Slot 2 | Plan-Guided Executor | **1** | $\le 1$ (Python only) |
| **Total Upstream** | | **2** | **Searches $\le 2$, File $\le 1$, Python $\le 1$** |

### Frozen Logical Generation Caps
- **Non-Recovery Path:** Maximum **5** logical generations:
  $\text{Planner v2 (1)} + \text{Executor (1)} + \text{Verifier (1)} + \text{Self-Eval (1)} + \text{Repair (1)} = \mathbf{5}$
- **Candidate-Recovery Path:** Maximum **6** logical generations:
  $\text{Planner v2 (1)} + \text{Executor (1)} + \text{Recovery (1)} + \text{Verifier (1)} + \text{Self-Eval (1)} + \text{Repair (1)} = \mathbf{6}$

---

## 5. First-Pass Web Search (Frozen Search 1)

Search 1 is strictly preserved from Frozen V2–V10 without modification:
- **Provider:** Tavily (`tavily-python`)
- **Query Formulation:** Original GAIA question verbatim (no rewriting, no LLM query expansion)
- **Search Depth:** `basic`
- **Max Results:** 5
- **Include Answer:** `False`
- **Include Raw Content:** `False`
- **Include Images:** `False`
- **Auto Parameters:** `False`
- **Query Length Cap:** 1,500 characters
- **Execution Cap:** $\le 1$ per task

---

## 6. Planner v2 Structured Contract & Grammar

### Prompt Version
`planner-v2-adaptive-evidence`

### Line-Oriented Deterministic Grammar
The planner output must adhere strictly to the following 7-block format:
```text
MODE: <DIRECT | PYTHON>
OBJECTIVE: <one concise sentence defining the task objective>
EVIDENCE_STATUS: <SUFFICIENT | INSUFFICIENT>
EVIDENCE_NEEDED: <one concise line describing critical evidence>
FOLLOWUP_QUERY: <NONE | specific search query>
PLAN:
1. <concise operational step>
2. <concise operational step>
...
ANSWER_TYPE: <number | name | list | date | short text>
```

### Grammar Rules & Semantics
1. `MODE`: Must be exactly `DIRECT` or `PYTHON`.
2. `OBJECTIVE`: Exactly one single line specifying the goal.
3. `EVIDENCE_STATUS`:
   - `SUFFICIENT`: The provided Search 1 results and/or file context appear adequate to answer the question.
   - `INSUFFICIENT`: A specific factual or evidentiary gap remains that can reasonably be addressed with one additional targeted search.
4. `EVIDENCE_NEEDED`: Exactly one single line describing the primary evidence sought.
5. `FOLLOWUP_QUERY`:
   - If `EVIDENCE_STATUS: SUFFICIENT`, `FOLLOWUP_QUERY` **MUST** be exactly `NONE`.
   - If `EVIDENCE_STATUS: INSUFFICIENT`, `FOLLOWUP_QUERY` **MUST** be a non-empty, focused search query targeting the missing fact. It must **NOT** be `NONE` and must **NOT** merely repeat the user question.
6. `PLAN`: Step list numbered `1.` to `N.` ($1 \le N \le 5$). Steps must be consecutive integers starting at 1.
7. `ANSWER_TYPE`: Concise classification of expected answer format.

### Prohibited Behaviors
Planner v2 prompt explicitly prohibits:
- Emitting the final task answer.
- Generating executable Python code.
- Invoking tools or function calling (`mode="NONE"`).
- Emitting conversational preamble, pleasantries, or closing text.
- Using hidden thought or scratchpad blocks outside the contract.

---

## 7. Strict Deterministic Parser & Fallback Specification

### Rejection Conditions
The parser deterministically rejects the planner output if any of the following occur:
1. Missing or unparseable `MODE:` marker.
2. `MODE` value not in `{"DIRECT", "PYTHON"}`.
3. Missing `OBJECTIVE:` line or empty objective.
4. Missing or unparseable `EVIDENCE_STATUS:` marker.
5. `EVIDENCE_STATUS` value not in `{"SUFFICIENT", "INSUFFICIENT"}`.
6. Missing `EVIDENCE_NEEDED:` line or empty evidence description.
7. Missing `FOLLOWUP_QUERY:` marker.
8. `EVIDENCE_STATUS: SUFFICIENT` but `FOLLOWUP_QUERY` is not `NONE`.
9. `EVIDENCE_STATUS: INSUFFICIENT` but `FOLLOWUP_QUERY` is `NONE` or empty string.
10. Missing `PLAN:` block or 0 numbered steps.
11. More than 5 numbered steps in `PLAN:`.
12. Non-consecutive or non-integer step numbering (e.g., 1, 3, 4).
13. Missing `ANSWER_TYPE:` line or empty answer type.

### Rejection Handling: Zero LLM Retry
In keeping with Frozen V10 principles:
- **No LLM Retry:** No second planner generation is ever attempted.
- **No Fuzzy Repair:** The parser does not use regex guessing or heuristic string patching.

### Deterministic Local Fallback Plan
On parser failure, timeout, or unexpected exception, the agent immediately applies the following deterministic fallback plan:
```text
MODE: DIRECT
OBJECTIVE: Answer the question directly using available evidence.
EVIDENCE_STATUS: SUFFICIENT
EVIDENCE_NEEDED: Existing web search or file context.
FOLLOWUP_QUERY: NONE
PLAN:
1. Extract the direct answer from the available evidence.
ANSWER_TYPE: short text
```

### Critical Safety Invariant: Fallback Never Searches
$$\text{Parser Failure} \implies \text{EVIDENCE\_STATUS} = \text{SUFFICIENT} \land \text{FOLLOWUP\_QUERY} = \text{NONE} \implies \text{Search 2 Prohibited}$$
Under no circumstances may a malformed planner output or parser fallback trigger an additional web search call.

---

## 8. Follow-Up Query Processing & Control Invariants

### Normalization Pipeline
When `EVIDENCE_STATUS: INSUFFICIENT` and a non-empty `FOLLOWUP_QUERY` is emitted:
1. Strip leading and trailing whitespace.
2. Collapse internal repeated whitespace (tabs, newlines, multiple spaces) to a single space.
3. If length exceeds 1,500 characters, deterministically truncate to exactly 1,500 characters and record `second_search_query_truncated = True`.

### Duplicate Query Protection
Before dispatching Search 2:
1. Normalize the Search 1 query (original question) and the candidate Search 2 query using identical normalization.
2. If `normalized(Search 2) == normalized(Search 1)`:
   - **Skip Search 2 entirely.**
   - Record `second_search_skipped_duplicate_query = True`.
   - Record `second_search_triggered = True`, but `second_search_attempted = False`.
   - Total search count remains **1**.

### Search 2 Provider Configuration
When executed:
- **Provider:** Tavily (`tavily-python`)
- **Query:** Normalized follow-up query
- **Search Depth:** `basic`
- **Max Results:** 5
- **Include Answer:** `False`
- **Include Raw Content:** `False`
- **Include Images:** `False`
- **Auto Parameters:** `False`
- **Budget:** Exactly $\le 1$ call per task. No third search is structurally possible.

### Search 2 Failure & Timeout Policy
If Search 2 fails (HTTP 429, timeout, network exception, empty snippet list):
- Record failure telemetry (`second_search_error_type`, `second_search_error_message`).
- Do **NOT** retry semantically.
- Do **NOT** replan or invoke a recovery LLM.
- Do **NOT** invoke a fallback search provider.
- Proceed cleanly to the Executor using only Search 1 evidence, file context, and the parsed plan.

---

## 9. Evidence Augmentation & Executor Formatting

### Semantic Drift Minimization Invariant
To prevent semantic drift and ensure that V11 gains stem strictly from evidence augmentation rather than executor behavioral shifts:
1. **Executor Plan Conditioning:** The Executor receives only the operational fields from the plan:
   - `MODE`
   - `OBJECTIVE`
   - `EVIDENCE_NEEDED`
   - `PLAN`
   - `ANSWER_TYPE`
2. **Retrieval-Control Exclusion:** The retrieval-control fields (`EVIDENCE_STATUS`, `FOLLOWUP_QUERY`) **MUST NOT** be passed to the Executor prompt as operational instructions.
3. **Prompt Preservation:** Prompts `executor-direct-v1` and `executor-python-v1` remain conceptually identical to Frozen V10.

### Evidence Block Structure
When Search 2 is executed and succeeds, the evidence presented to the Executor is formatted as:
```text
=== PRIMARY WEB SEARCH EVIDENCE ===
[Results from Search 1]

=== FOLLOW-UP WEB SEARCH EVIDENCE ===
[Results from Search 2]
```
When Search 2 is bypassed, skipped, or fails:
```text
=== PRIMARY WEB SEARCH EVIDENCE ===
[Results from Search 1]
```
File context remains completely untouched and is formatted identically to Frozen V10.

---

## 10. Preserved Frozen Downstream Stages

The downstream pipeline is inherited verbatim from Frozen V10 (and its predecessors):
1. **Candidate Recovery (Frozen V9):**
   If the upstream Executor fails to emit a candidate (`""`), deterministic failure classification evaluates eligibility. For eligible classes, one bounded text-only recovery generation is attempted. Non-triggered tasks maintain 100.0% boundary candidate preservation.
2. **Answer Verifier (Frozen V5):**
   One-shot text-only verifier evaluating `KEEP` vs `REVISE` on non-empty candidates.
3. **Self-Evaluator (Frozen V6):**
   Read-only diagnostic classification (`PASS` vs `SUSPECT`, with risk type taxonomy).
4. **Targeted Repair (Frozen V7):**
   Conditional one-shot repair triggered only on `SUSPECT` verdicts (`KEEP` vs `REPLACE`).

Zero downstream prompt or code modifications are permitted in V11.

---

## 11. Resource Budgets & Invariants

Across every deployed V11 task, the following strict invariants are mathematically enforced:

| Resource Constraint | Non-Triggered Task | Triggered Task (Search 2) | Hard Maximum |
| :--- | :---: | :---: | :---: |
| **Web Searches** | 1 | 2 | **2** |
| **File Processing** | $\le 1$ | $\le 1$ | **1** |
| **Python Executions** | $\le 1$ | $\le 1$ | **1** |
| **Planner Generations** | 1 | 1 | **1** |
| **Search 2 LLM Generations** | 0 | 0 | **0** |
| **Executor Generations** | 1 | 1 | **1** |
| **Candidate Recovery Generations** | $\le 1$ | $\le 1$ | **1** |
| **Verifier Generations** | $\le 1$ | $\le 1$ | **1** |
| **Self-Evaluator Generations** | $\le 1$ | $\le 1$ | **1** |
| **Targeted Repair Generations** | $\le 1$ | $\le 1$ | **1** |
| **Logical Generations (Non-Recovery)** | $\le 5$ | $\le 5$ | **5** |
| **Logical Generations (Recovery Path)** | $\le 6$ | $\le 6$ | **6** |

---

## 12. Telemetry Schema (Version 9)

V11 establishes `schema_version = 9`. All task summary and detailed prediction records must include the following deterministic fields:

### New Retrieval & Cohort Fields
- `planner_evidence_status`: `"SUFFICIENT"` | `"INSUFFICIENT"` | `null`
- `planner_followup_query`: string | `null`
- `planner_requested_followup`: boolean (`planner_parse_success AND evidence_status == "INSUFFICIENT"`)
- `followup_query_valid`: boolean (syntax non-empty and valid)
- `followup_query_duplicate`: boolean (normalized query matches Search 1)
- `followup_eligible`: boolean (`planner_requested_followup AND followup_query_valid AND NOT followup_query_duplicate`)
- `second_search_triggered`: boolean
- `second_search_attempted`: boolean
- `second_search_success`: boolean
- `second_search_empty_results`: boolean
- `second_search_skipped_duplicate_query`: boolean
- `second_search_query`: string | `null`
- `second_search_provider_query`: string | `null`
- `second_search_query_truncated`: boolean
- `second_search_latency_seconds`: float | `null`
- `second_search_result_count`: integer | `null`
- `second_search_error_type`: string | `null`
- `second_search_error_message`: string | `null`
- `primary_search_call_count`: integer (1)
- `second_search_call_count`: integer (0 or 1)
- `total_search_call_count`: integer (1 or 2)

### Cryptographic Hashes (Public-Safe)
- `primary_search_evidence_hash`: SHA-256 of Search 1 output
- `followup_search_evidence_hash`: SHA-256 of Search 2 output (or `null`)
- `combined_search_evidence_hash`: SHA-256 of total search context passed to Executor

### Public-Safe Privacy Rules
Telemetry records must never include:
- Ground truth answers or references.
- Runtime correctness scores or official scorer outputs.
- Hidden provider reasoning parts or model scratchpads.

---

## 13. Primary Evaluation Architecture: Follow-Up-Eligible Paired Retrieval Ablation

The primary evaluation protocol (`followup_eligible_shared_plan_paired_retrieval_ablation`) evaluates the isolated evidence intervention under strict context and plan control:
- **Cohort Definition:** Restricted strictly to tasks where `followup_eligible == True`.
- **Pre-Intervention Determination:** Cohort membership is locked before Search 2 execution. Tasks are never conditioned on Search 2 success, non-empty results, new URLs, or correctness.
- **Provider Failure Handling:** If Search 2 suffers a provider failure or returns empty results, Branch B receives the clean fallback (Search 1 evidence only). The task **remains** in the paired cohort, typically resulting in `RETRIEVAL_STABLE_CORRECT` or `RETRIEVAL_STABLE_FAILURE`.
- **Excluded Cases:** Tasks with `EVIDENCE_STATUS: SUFFICIENT`, duplicate queries, or planner fallbacks are excluded from the paired cohort.
- **Methodological Characterization:** This protocol provides an intervention-oriented paired comparison under identical context and plan. It is **not a perfect causal estimate** and is **not fully causal**, as residual generation stochasticity in the Executor remains. Preferred terminology is *shared-plan paired retrieval ablation*, *paired intervention-oriented estimate*, and *paired net difference*.

---

## 14. Class Hierarchy & Subclass Detection Architecture

### Class Architecture
The V11 runtime class will inherit directly from Frozen V10:
```python
class GAIAAdaptiveEvidenceAgent(GAIAPlannerExecutorAgent):
    """V11 Agent: Planner-Guided Adaptive Evidence Retrieval."""
    pass
```

### Subclass Detection Requirement
Because `issubclass(GAIAAdaptiveEvidenceAgent, GAIAPlannerExecutorAgent)` evaluates to `True`, dispatchers in evaluation runners (`runner.py`, `run_level.py`, `run_one.py`, `run_v11_paired.py`) must inspect `v11` **before** inspecting `v10`:
```python
# Required dispatch sequence:
if version == "v11":
    agent = GAIAAdaptiveEvidenceAgent(...)
elif version == "v10":
    agent = GAIAPlannerExecutorAgent(...)
```
Reversing this order is an architectural defect that would cause V11 to execute as V10.

---

## 15. Course Alignment & Theoretical Motivation

### Background: Hugging Face Agents Course
The *Hugging Face Agents Course* identifies single-step retrieval as a fundamental architectural bottleneck of traditional Retrieval-Augmented Generation (RAG). Specifically:
- **Query Formulation Brittleness:** Raw user questions frequently fail to match indexing semantics in vector databases or web search indexes.
- **Agentic Retrieval:** Moving from static RAG to agentic RAG involves multi-step search, query reformulation, and plan-guided information gathering.

### Bounded Engineering Scope
While theoretical agentic RAG often advocates unbounded multi-hop search loops or autonomous web navigation, V11 purposefully enforces a **strictly bounded one-follow-up design**:
$$\text{Max Searches} = 2, \quad \text{Max Upstream LLM Generations} = 2$$
This guarantees predictable latency, compute equivalence, and rigorous experimental attribution without entering divergent autonomous search loops.

---

## 16. Known Scientific Limitations

1. **Retrieval-Specific Intervention:**
   V11 addresses only evidence availability. It does not repair flawed mathematical reasoning, incorrect Python syntax ($H_{3e}$ failure in V10), or downstream repair conservatism.
2. **Planner Trigger Accuracy Risk:**
   Because Planner v2 itself decides whether evidence is `SUFFICIENT` or `INSUFFICIENT`, the agent is vulnerable to:
   - *False Sufficiency:* Incorrectly declaring sufficient evidence and starving the Executor.
   - *False Insufficiency:* Unnecessarily triggering Search 2 on already-sufficient contexts, risking query distraction or noise.
3. **Search Provider Coverage:**
   If missing information is behind paywalls, in non-indexed databases, or requires complex multi-hop clicks, a single basic Tavily follow-up search will remain ineffective.

