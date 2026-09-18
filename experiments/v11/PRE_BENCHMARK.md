# V11 — Formal Preregistration & Pre-Benchmark Protocol: Planner-Guided Adaptive Evidence Retrieval

**Status:** PROPOSED_PRE_IMPLEMENTATION  
**Document Version:** 1.0  
**Schema Version:** 9  
**Branch:** `v11-adaptive-evidence-retrieval`  
**Repository Parent Commit:** `0761b81330540cdc67fe2d662aef049bc87d9d8f`  
**Scientific Parent:** Frozen V10 (`v10-planner-executor`)  
**Canonical Parent Inference Commit:** `314d0aecd01a1679a96d85256044c01c8b6c30ce`  
**Canonical Parent Benchmark Score:** 84 / 165 (50.91%)  
**Evaluation Scope:** Full GAIA 2023 Validation Set (165 Tasks: 53 Level 1, 86 Level 2, 26 Level 3)  
**Model:** `gemini-3.5-flash-lite` (inherited from Frozen V7/V9/V10)  
**Date:** September 2026  

---

## 1. Primary Research Question

> *When Frozen V10's structured planner determines that the single frozen first-pass web search does not provide the evidence needed to execute its plan, can one bounded, planner-authored follow-up web search improve upstream candidate correctness without adding any LLM generation slots or changing Frozen V10's downstream safeguards?*

V11 isolates the effect of **adaptive evidence retrieval** at the upstream formulation boundary. It does not address Python code execution, reasoning errors on adequate evidence, or downstream repair conservatism.

---

## 2. Binding Hypotheses

### Primary Hypothesis
- **$H_1$ — Follow-Up Retrieval Benefit (Paired Upstream Metric):**  
  On the planner-triggered cohort ($N_{\text{triggered}}$ tasks where Planner v2 determines `EVIDENCE_STATUS: INSUFFICIENT`), the net candidate correctness delta under identical context and plan will be strictly positive:
  $$\Delta_{\text{followup}} = N_{\text{RETRIEVAL\_IMPROVEMENT}} - N_{\text{RETRIEVAL\_REGRESSION}} > 0$$
  *Non-Testability Clause:* If $N_{\text{triggered}} == 0$, $H_1$ is mathematically undefined (`NOT_TESTABLE`), and V11 cannot be promoted.

### Canonical Performance Gate
- **$H_2$ — Canonical End-to-End Benchmark Superiority:**  
  On the complete 165-task GAIA validation suite, the canonical V11 agent will strictly exceed the Frozen V10 historical reference ($84 / 165 = 50.91\%$):
  $$\text{V11 Correct Tasks} > 84 \iff \text{V11 Official Accuracy} > 50.91\%$$

### Secondary Diagnostic Hypotheses
- **$H_{3a}$ — Evidence-Risk Conditional Error Reduction:**  
  In post-hoc self-evaluation diagnostics, the conditional error rate for tasks assessed with `EVIDENCE` risk will strictly decrease compared to Frozen V10 ($32 / 36 = 88.89\%$):
  $$\text{V11 EVIDENCE Conditional Error Rate} < 88.89\%$$
- **$H_{3b}$ — Candidate Recovery Trigger Reduction:**  
  Because stronger evidence facilitates upstream task execution, the candidate recovery trigger rate will decrease below Frozen V10 ($51 / 165 = 30.91\%$):
  $$\text{V11 Recovery Trigger Rate} < 30.91\%$$
- **$H_{3c}$ — Reachability Preservation Floor:**  
  V11 downstream non-empty candidate reachability will maintain a high preservation floor:
  $$\text{V11 Post-Recovery Reachability} \ge 95.0\%$$
- **$H_{3d}$ — Planner v2 Contract Adherence:**  
  The deterministic line-oriented parser will achieve high parse reliability on Planner v2:
  $$\text{Planner v2 Parse Success Rate} \ge 95.0\%$$
- **$H_{3e}$ — Follow-Up Retrieval Operational Tracking:**  
  Document and report exact counts for follow-up search eligibility, attempts, successes, provider errors, and empty results. Provider errors do not constitute an automatic scientific failure unless widespread infrastructure collapse occurs.
- **$H_{3f}$ — Search Novelty Diagnostic:**  
  For triggered tasks, report the proportion of follow-up searches returning $\ge 1$ new URL not present in Search 1, along with the mean and median new URLs retrieved. This metric is descriptive only and non-binding.

---

## 3. Primary Evaluation Protocol: Triggered-Cohort Shared-Plan Paired Retrieval Ablation

The primary scientific evaluation is an isolated within-task paired ablation executed by `evaluation/run_v11_paired.py`:

```text
GAIA Question + Optional Attachment
     ↓
ONE Tavily Search 1 (Original Question)
     ↓
ONE File Context Preparation (if applicable)
     ↓
ONE Planner v2 Generation (`planner-v2-adaptive-evidence`)
     │
     ├── [EVIDENCE_STATUS: SUFFICIENT] → Record as Non-Triggered; bypass paired executor fork.
     │
     └── [EVIDENCE_STATUS: INSUFFICIENT & Valid Non-Duplicate Query]
              ↓
         Trigger Search 2 (Tavily, basic, max_results=5, N = 1)
              ↓
         Snapshot Frozen Shared State:
         - Same Question
         - Same File Context
         - Same Search 1 Evidence
         - Same Planner Output & Hash
         - Same Execution Plan & Hash
         - Same Model Configuration
              ↓
         FORK TO TWO PARALLEL UPSTREAM EXECUTOR BRANCHES
              │
              ├── Branch A (No Follow-Up Evidence):
              │   Question + Search 1 + File + Exact Plan
              │   ↓
              │   Frozen V10 Executor (N ≤ 1, Python ≤ 1)
              │   ↓
              │   Upstream Candidate A (`pre_recovery_candidate_A`)
              │
              └── Branch B (With Follow-Up Evidence):
                  Question + Search 1 + Search 2 + File + Exact Plan
                  ↓
                  Frozen V10 Executor (N ≤ 1, Python ≤ 1)
                  ↓
                  Upstream Candidate B (`pre_recovery_candidate_B`)
```

### Boundary Isolation Invariant
Both branches terminate strictly at the **pre-recovery candidate formulation boundary**. Neither Branch A nor Branch B executes Candidate Recovery, Answer Verifier, Self-Evaluator, or Targeted Repair. This isolates the pure effect of Search 2 evidence before any downstream intervention.

### Primary Transition Taxonomy
Evaluated post-hoc using the official GAIA leaderboard scorer:

| Transition Name | Branch A (No Search 2) | Branch B (With Search 2) | Interpretation |
| :--- | :---: | :---: | :--- |
| **`RETRIEVAL_IMPROVEMENT`** | Incorrect / Empty | Correct | Search 2 provided decisive factual evidence to solve the task. |
| **`RETRIEVAL_REGRESSION`** | Correct | Incorrect / Empty | Search 2 introduced distraction, noise, or ungrounded claims. |
| **`RETRIEVAL_STABLE_CORRECT`** | Correct | Correct | Task was already solvable without Search 2 evidence. |
| **`RETRIEVAL_STABLE_FAILURE`** | Incorrect / Empty | Incorrect / Empty | Neither branch solved the task; reasoning or evidence gap persists. |

### Methodological Status
The paired protocol controls question, initial retrieved search evidence, file context, planner output, operational plan, model parameters, and tool configurations. Residual stochasticity in Executor generation remains. This is an **intervention-oriented paired retrieval ablation**, not an assertion of absolute causal perfection.

---

## 4. Canonical Full-Benchmark Evaluation Protocol

Following the paired ablation, the full deployed V11 agent will be evaluated end-to-end across all **165 tasks** of the GAIA 2023 Validation Set:
- **Structural Coverage:** Exactly 165 / 165 unique tasks recorded.
- **Pipeline Completion:** All tasks must run through the end-to-end pipeline (Planner $\to$ [Search 2] $\to$ Executor $\to$ Recovery $\to$ Verifier $\to$ Self-Evaluator $\to$ Repair).
- **Benchmark Gate ($H_2$):** Correct tasks must exceed Frozen V10 canonical baseline ($> 84 / 165$).
- **Distinction from Primary:** The canonical run establishes overall project capability; the paired ablation establishes the isolated causal attribution of Search 2.

---

## 5. Secondary Matched Control Policy

A contemporaneous separate full-run control of Frozen V10 is **NOT required for promotion**.
- **Rationale:** The primary within-task paired ablation already provides rigorous, shared-context experimental evidence without run-to-run sampling divergence.
- Frozen V10 has an immutable, canonical reference baseline of $84 / 165 = 50.91\%$.
- An optional matched V10 control may be executed strictly for descriptive observational context, but will not be used as a binding promotion gate.

---

## 6. Binding Promotion Gates

Promotion of V11 as the project's new scientific baseline requires satisfying **ALL 13 binding promotion gates**:

```text
1. Primary Triggered-Cohort Delta_followup > 0
2. Canonical V11 Correct Tasks > 84 / 165 (> 50.91%)
3. Total Web Searches <= 2 per deployed task
4. Search 2 Calls <= 1 per deployed task
5. Search 2 occurs ONLY after a valid INSUFFICIENT planner decision
6. Planner fallback NEVER triggers Search 2
7. File Processing <= 1 per deployed task
8. Python Executions <= 1 per deployed task
9. Upstream LLM Generation Slots == 2 (Slot 1: Planner, Slot 2: Executor)
10. Non-Recovery Path Logical Generations <= 5
11. Candidate-Recovery Path Logical Generations <= 6
12. Frozen V10 Downstream Pipeline preserved verbatim
13. Canonical Operational Validity confirmed (165 tasks, zero request failures)
```

No additional criteria or post-hoc threshold modifications are permitted.

---

## 7. Operational Validity & Neutral Outcome Definitions

### Neutral Outcome
If $\Delta_{\text{followup}} \le 0$ or Canonical Correct $\le 84$, the scientific verdict is:
```text
NEUTRAL / NOT_SUPPORTED_AS_AN_IMPROVEMENT
```
V11 will be archived as a completed experiment and will **not** be promoted as the baseline for V12.

### Operational Invalidity Conditions
A benchmark run is declared `INVALID` if any of the following occur:
- Incomplete validation split ($< 165$ tasks evaluated).
- Ground-truth reference leakage or scorer execution at agent runtime.
- Any violation of search or generation budget invariants.
- Runtime or prompt modifications introduced after pre-benchmark audit lock.
- Widespread provider infrastructure failure or API collapse ($> 10\%$ unhandled task failures).

### Isolated Search 2 Provider Failure Policy
An individual Search 2 failure (e.g., HTTP 429 or timeout) must fall back cleanly to Search 1 evidence and complete the task. Isolated search failures are recorded in telemetry and do **not** invalidate the run.

---

## 8. Ground-Truth Scorer Firewall

At runtime, neither the agent, the planner, the executor, nor the paired ablation harness may access:
- Ground-truth reference answers.
- Evaluation split ground-truth datasets.
- Task correctness indicators.
- Scorer logic or transition categories.

All evaluation scoring must take place strictly **post-hoc** using the official GAIA scoring module.

---

## 9. Deterministic Smoke Scenarios Matrix (28 Scenarios)

Before executing GAIA benchmarks, the V11 implementation must pass **28 deterministic zero-network unit scenarios**:

### Group 1: Planner v2 Contract & Grammar (Scenarios 1–8)
1. **Valid SUFFICIENT + NONE:** Parse succeeds; `EVIDENCE_STATUS == "SUFFICIENT"`, `FOLLOWUP_QUERY == "NONE"`.
2. **Valid INSUFFICIENT + Query:** Parse succeeds; `EVIDENCE_STATUS == "INSUFFICIENT"`, `FOLLOWUP_QUERY` is preserved.
3. **Invalid Evidence Status:** Text with `EVIDENCE_STATUS: PARTIAL` is rejected by parser.
4. **SUFFICIENT with Non-NONE Query:** Text with `EVIDENCE_STATUS: SUFFICIENT` and `FOLLOWUP_QUERY: "search query"` is rejected.
5. **INSUFFICIENT with NONE Query:** Text with `EVIDENCE_STATUS: INSUFFICIENT` and `FOLLOWUP_QUERY: NONE` is rejected.
6. **Missing FOLLOWUP_QUERY:** Output omitting `FOLLOWUP_QUERY:` marker is rejected.
7. **Parser Fallback Contract:** Parser failure cleanly returns the deterministic fallback plan with `SUFFICIENT` and `NONE`.
8. **Planner Failure Safety Invariant:** Planner exception or parser failure **never** triggers Search 2.

### Group 2: Follow-Up Search Control & Fallbacks (Scenarios 9–14)
9. **Valid Trigger Execution:** Valid `INSUFFICIENT` planner decision triggers exactly one Search 2 call.
10. **Sufficient Search Bypass:** `SUFFICIENT` planner decision executes 0 Search 2 calls.
11. **Duplicate Query Skip:** If follow-up query matches Search 1 query after normalization, Search 2 is skipped and logged.
12. **Query Normalization & Truncation:** Whitespace is stripped/collapsed; queries exceeding 1,500 characters are truncated.
13. **Search 2 Provider Failure Fallback:** Simulated Tavily HTTP error cleanly falls back to Search 1 evidence without crash.
14. **Search 2 Empty Results Fallback:** Simulated empty snippet list cleanly falls back to Search 1 evidence.

### Group 3: Resource & Tool Budgets (Scenarios 15–20)
15. **Non-Triggered Search Budget:** Tasks without follow-up search execute exactly 1 search call.
16. **Triggered Search Budget:** Tasks with follow-up search execute at most 2 search calls.
17. **Search 3 Impossibility:** Under no code path can a third search call be initiated.
18. **File Processing Invariant:** File processing remains capped at $\le 1$ per task.
19. **Python Execution Invariant:** Python tool execution remains capped at $\le 1$ per deployed branch.
20. **Upstream Slot Invariant:** Total upstream LLM generation slots strictly equal 2 (Planner + Executor).

### Group 4: Downstream Safeguards & Generation Caps (Scenarios 21–24)
21. **Non-Recovery Generation Cap:** Non-recovery path executes $\le 5$ logical generations.
22. **Candidate-Recovery Generation Cap:** Candidate-recovery path executes $\le 6$ logical generations.
23. **Recovery Bypass on Non-Empty Candidate:** Non-empty candidate passes through recovery with 100.0% preservation.
24. **Frozen Downstream Pipeline Integrity:** Sequence of Recovery $\to$ Verifier $\to$ Self-Eval $\to$ Repair is preserved verbatim.

### Group 5: Primary Paired Ablation Harness (Scenarios 25–28)
25. **Identical Context & Plan Invariant:** Branch A and Branch B receive identical context and plan hashes.
26. **Single Search 2 Execution:** In the paired harness, Search 2 is executed exactly once and shared with Branch B.
27. **Zero Runtime Ground Truth:** Paired harness contains no references to reference answers.
28. **Post-Hoc Transition Computation:** Transition matrix cells are assigned strictly after runtime candidate generation.

---

## 10. Scientific Limitations & Risk Controls

1. **Information Horizon:** If critical facts are omitted from public web indexes, Search 2 cannot resolve the failure.
2. **Planner Overconfidence / Starvation:** If Planner v2 erroneously declares `SUFFICIENT`, the agent remains starved.
3. **No Code Repair:** Python syntax and package issues ($H_{3e}$) remain unaddressed by V11.
4. **Generalization Safeguard:** No specific query heuristics, entity regexes, or task-specific prompting may be derived from GAIA ground-truth answers.

