# V5 Design Specification — One-Shot Post-Answer Verification

**Status**: DESIGN LOCKED / IMPLEMENTED / PRE-BENCHMARK AUDIT PENDING  
**Parent Baseline**: Frozen V4 (`v4-planner-router-final`)  
**Proposed Branch**: `v4-planner-router` (coexisting cleanly with frozen V4)  
**Version Label Shorthand**: `V5 = frozen V4 + one-shot post-answer verification/revision`  
**Full Experimental Characterization**: The controlled system-level effect of introducing an explicit one-shot post-answer verification and revision stage on top of the frozen V4 capability-routing pipeline, along with its associated verifier inference call, conservative verification prompting, and deterministic answer revision / non-destructive fallback enforcement.

---

## 1. Research Context & Problem Statement

### 1.1 Frozen V4 Context
The frozen V4 baseline evaluated an explicit two-stage capability router (`DIRECT` vs `PYTHON`) on the GAIA 2023 Validation set (165 tasks):
- **V4 Accuracy**: `52 / 165 = 31.52%` (Level 1: `52.83%`, Level 2: `24.42%`, Level 3: `11.54%`)
- **Contemporaneous Matched V3 Control**: `49 / 165 = 29.70%` (Level 1: `50.94%`, Level 2: `24.42%`, Level 3: `0.00%`)
- **Controlled Delta**: `+3 tasks` (`+1.82 pp`)
- **Completion Rate**: `82 / 165 = 49.70%` (vs Matched V3: `128 / 165 = 77.58%`)

Crucial findings from the audited V4 benchmark:
1. **Factored Capability Routing**: Factoring capability selection into an explicit router reduced wasteful and fragile Python attempts on non-computational tasks.
2. **Deterministic Route Enforcement**: Enforcing the selected route eliminated ambiguous execution states.
3. **Extraction & Format Errors**: A noticeable portion of completed candidate answers failed official GAIA scoring due to small formatting discrepancies, sign mismatches, precision truncation, or minor reading errors that could potentially be caught by a conservative post-answer sanity check.

### 1.2 Proposed V5 Experimental Characterization
In V5, an explicit **One-Shot Post-Answer Verification stage** is appended to the frozen V4 pipeline:
1. The frozen V4 pipeline generates a candidate answer via router selection, worker generation, and optional Python execution.
2. If the candidate answer is empty or missing, verification is **skipped entirely**; the verifier is never used to hallucinate an answer for an incomplete task.
3. If a candidate answer is present, a dedicated **Answer Verifier LLM call** audits the answer against question requirements and available evidence using a conservative verification prompt (`answer-verifier-v1`).
4. The verifier emits either `VERDICT: KEEP` or `VERDICT: REVISE` with `FINAL: <corrected answer>`.
5. If the verifier errors, times out, or produces malformed text, a **non-destructive fallback policy** preserves the pre-verification candidate answer.

**Critical Methodological Definition**:
V5 must NOT be described as isolating or estimating the pure causal effect of verification alone. V5 differs from V4 through a multi-faceted intervention bundle consisting of:
- An explicit post-answer verifier generation
- An additional LLM inference call per eligible task (maximum standard generations = 3: router=1, worker=1, verifier=1)
- Conservative verification prompting (`answer-verifier-v1`) with native function calling disabled (`mode="NONE"`)
- Deterministic verdict parsing and answer revision enforcement
- Changed exposure to provider failures, timeouts, and stochasticity

Therefore, the primary research comparison is defined as:
> **The controlled system-level effect of introducing an explicit one-shot post-answer verification and revision stage on top of the frozen V4 capability-routing pipeline, along with its associated verifier inference call, conservative verification prompting, and deterministic answer revision / non-destructive fallback enforcement.**

The shorthand `V5 = frozen V4 + one-shot post-answer verification/revision` serves strictly as a version label, not as a claim of single-variable isolation. All comparisons are conducted as a **controlled matched comparison** against contemporaneous V4 controls.

### 1.3 Pre-Registered Primary Scientific Claims
To prevent post-hoc overclaims, acceptable scientific descriptions are explicitly pre-registered:

- **Acceptable Claim**:
  > "V5 measures the system-level effect of adding an explicit one-shot post-answer verification stage on top of the frozen V4 capability-routing architecture under matched evaluation conditions."
- **Acceptable Claim**:
  > "Any observed performance difference may reflect verification accuracy, additional inference overhead, conservative revision thresholding, and altered provider-failure exposure."
- **Unacceptable Claim (Prohibited)**:
  > "V5 isolates the pure causal effect of verification."
- **Unacceptable Claim (Prohibited)**:
  > "The verifier fixes incorrect answers without cost."
- **Unacceptable Claim (Prohibited)**:
  > Claims treating post-hoc observational splits (e.g. comparing accuracy on tasks where verifier chose KEEP vs REVISE) as causal treatment effects.

### 1.4 Research Questions
- **Primary Research Question**:
  > *How does adding an explicit one-shot post-answer verification stage affect GAIA benchmark performance, completion, accuracy transitions (improvements vs regressions), latency, and cost relative to frozen V4?*
- **Secondary Research Question**:
  > *Does a conservative KEEP-biased verifier successfully correct superficial formatting/reasoning mistakes without inducing destructive regressions on already-correct candidate answers?*

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
| Prompt: router-direct-worker|   | Prompt: router-python-worker|
+-----------------------------+   +-----------------------------+
               |                                 |
               |                         [Extract Code]
               |                                 |
               |                                 v
               |                  +-----------------------------+
               |                  |      PythonTool (.run)      |
               |                  | (At most 1 local execution) |
               |                  +-----------------------------+
               |                                 |
               +----------------+----------------+
                                |
                                v
                    [Pre-Verification Candidate]
                                |
            +-------------------+-------------------+
            |                                       |
    (Candidate Empty)                       (Candidate Non-Empty)
            |                                       |
            v                                       v
    [Verifier Skipped]                     +-----------------------------+
    pre_ver = post_ver = ""                |    VERIFIER GEMINI CALL     |
    verifier_attempted = False             |       (Generation #3)       |
    final_answer = ""                      | Prompt: answer-verifier-v1  |
                                           | Tools: mode="NONE"          |
                                           +-----------------------------+
                                                           |
                                                           v
                                            [Deterministic Verdict Parser]
                                                           |
                                    +----------------------+----------------------+
                                    |                      |                      |
                              (Verdict: KEEP)       (Verdict: REVISE)      (Error/Fallback)
                                    |                      |                      |
                                    v                      v                      v
                             final = pre_ver        final = revised        final = pre_ver
                             revised = False        revised = True         fallback = True
```

---

## 3. Strict Execution Invariants

1. **Maximum Standard LLM Generations = 3**:
   - Router Generation: exactly 1 attempt
   - Worker Generation: exactly 1 attempt
   - Verifier Generation: at most 1 attempt (0 if candidate is empty, 1 if candidate is non-empty)
   - Total LLM generation attempts per task: `1 <= attempts <= 3`
   - Strictly no 4th generation, no retry, no repair loop, no verifier-of-verifier.
2. **Native Function Calling Disabled**:
   - `mode="NONE"` enforced across all three generation calls (Router, Worker, Verifier).
   - Tools are orchestrated locally and deterministically.
3. **Candidate Ineligibility Rule**:
   - If candidate answer is empty or whitespace: verifier is **never called** (`verifier_attempted = False`, `verifier_generation_attempts = 0`).
   - Verifier cannot be used to answer an unanswered task.
4. **Information Firewall**:
   - Verifier prompt receives ONLY:
     - Original question
     - Candidate answer (`pre_verification_answer`)
     - Already-retrieved web evidence
     - Already-processed file evidence
     - Attachment filename (if present)
   - Verifier prompt NEVER receives:
     - Benchmark ground truth
     - Scorer results
     - Raw router response or hidden reasoning
     - Raw worker response or hidden reasoning
     - Generated Python code
     - Python stdout / stderr
5. **Multimodal Attachment Handling**:
   - Native attachments (images, audio) reuse in-memory `FileResult.native_bytes`.
   - Zero disk re-reads.
   - Zero FileTool re-invocations.
6. **Non-Destructive Failure Policy**:
   - Any verifier provider exception (timeout, HTTP 500, quota error, malformed function call error) or parser error (empty response, missing verdict, ambiguous verdict, malformed text, missing/empty final answer on revise) preserves `post_verification_answer = pre_verification_answer` and sets `verifier_fallback = True`.
   - A non-empty candidate answer cannot be transformed into an empty answer by verification.
7. **Tool Call Invariants**:
   - Maximum Tavily searches: 1
   - Maximum FileTool executions: 1
   - Maximum Python executions: 1

---

## 4. Transition Taxonomy & Mathematical Verification

For every evaluated task, we compute both `pre_verification_correct` and `post_verification_correct` using the official `gaia_question_scorer`.

Tasks are partitioned into four mutually exclusive transition categories:
1. **Improvement**: `not pre_correct and post_correct` (verifier turned an incorrect candidate into a correct answer).
2. **Regression**: `pre_correct and not post_correct` (verifier corrupted an already-correct candidate).
3. **Stable Correct**: `pre_correct and post_correct` (answer remained correct).
4. **Stable Failure**: `not pre_correct and not post_correct` (answer remained incorrect).

### Exact Mathematical Identity
In every automated evaluation summary, the following mathematical identity is strictly verified:
$$\Delta_{\text{correct}} = \text{post\_correct} - \text{pre\_correct} = \text{improvements} - \text{regressions}$$

If this identity is violated by even 1 task, the evaluation pipeline aborts immediately with an assertion error.

---

## 5. Non-Causal Wording Rules

In accordance with rigorous scientific hygiene:
- The subgroups `KEEP`, `REVISE`, and `FALLBACK` represent **observational post-hoc strata**, NOT causal treatment arms.
- Wording such as *"the verifier caused 80% accuracy on revised tasks"* is prohibited.
- Accurate wording: *"Among the subset of tasks where the verifier emitted a REVISE verdict, post-verification accuracy was X%."*
- All comparative conclusions must be evaluated against the contemporaneous matched V4 control run under identical benchmark conditions.

