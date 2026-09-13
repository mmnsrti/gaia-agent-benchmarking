# V7 — SUSPECT-Triggered Targeted Repair: Experimental Design Document

**Status**: PROPOSED_PRE_BENCHMARK  
**Parent Version**: Frozen V6 (`v6-self-evaluation-agent`)  
**Proposed Experimental Version**: V7  
**Schema Version**: 6  

---

## 1. Frozen Parent Baseline (V6)

V7 directly inherits the frozen V6 baseline:
```text
V6 = frozen V5 + one bounded read-only post-answer self-evaluation generation
```

In frozen V6:
- The upstream pipeline executes search ($\le 1$), file extraction ($\le 1$), capability routing (`DIRECT` vs `PYTHON`), single-shot execution, candidate eligibility check, and conservative post-answer verification (`KEEP`/`REVISE`).
- The self-evaluator performs exactly one read-only text generation assessing answer reliability (`PASS` vs `SUSPECT`, `RISK_TYPE`, `CONFIDENCE`).
- V6 strictly preserves answer immutability (`self_eval_answer_unchanged == True`), with zero tool access, zero Python, zero search, zero retries, and zero ground-truth leakage.

All V6 properties remain strictly unchanged up to and including the diagnostic stage.

---

## 2. Single Added Capability

V7 introduces exactly **one** new capability:
> **One bounded text-only targeted repair generation, triggered exclusively by a valid V6 `SUSPECT` assessment.**

Formal definition:
```text
V7 = frozen V6 + one bounded targeted repair generation triggered only by valid SUSPECT
```

---

## 3. Primary Research Question & Secondary Questions

### Primary Research Question
> *Can one bounded targeted repair generation, triggered only by a valid V6 `SUSPECT` assessment, correct more erroneous answers than it harms correct answers, without additional tools, new evidence retrieval, or retries?*

### Secondary Research Questions
1. **Correction Rate**: How often does targeted repair convert an incorrect answer to a correct answer?
2. **Harm Rate**: How often does targeted repair damage an answer that was already correct (e.g., false-positive `SUSPECT` cases)?
3. **Conservative Protection**: Does `KEEP` effectively protect false-positive `SUSPECT` cases from damage?
4. **Risk-Type Correlation**: Does the evaluator-assigned risk type correlate with repair outcome?
5. **Net Within-Run Effect**: What is the net task delta ($\Delta = \text{improvements} - \text{regressions}$) within the exact same run?
6. **Candidate Starvation**: What fraction of the benchmark error space remains unreachable because no candidate answer was generated upstream?
7. **Operational Cost**: What latency and token overhead does the repair stage add?
8. **Pre-vs-Post Accuracy**: Does targeted repair improve post-repair system accuracy relative to the pre-repair state in the same run?

---

## 4. Core Hypothesis

Pre-registered as a hypothesis (NOT an expected result):
> *Because V6 `SUSPECT` exhibited relatively high observed precision (88.89%) in the frozen V6 benchmark, a single targeted repair generation restricted to `SUSPECT` answers may produce more `wrong → correct` transitions than `correct → wrong` regressions.*

Negative or zero net effect is an entirely valid scientific outcome.

---

## 5. Non-Goals & Strict Prohibitions

V7 strictly prohibits:
- New web searches or Tavily calls during repair
- New Python executions or sandbox invocations during repair
- New file-tool reads or attachment processing during repair
- Active/tool-assisted verification
- Query rewriting or multi-hop retrieval
- Additional router calls or dynamic planning
- Multi-agent frameworks (LangGraph, smolagents, CrewAI, etc.)
- Reflection loops or iterative repair
- Multiple repair generation attempts
- Post-repair verification or post-repair self-evaluation
- Repair retries under any error or exception
- Confidence threshold filtering on triggers
- Majority voting or answer ensembling

---

## 6. Architecture & Execution Flow

```text
GAIA Question + Optional Attachment File
     ↓
Frozen Upstream Pipeline (V5/V6):
  - Search (≤ 1 Tavily query on original question)
  - File extraction (≤ 1 deterministic local extraction)
  - Capability Router (LLM selects DIRECT vs PYTHON)
  - Execution Worker (Direct LLM or single-shot local Python)
  - Candidate Answer Guard (Empty answer check)
  - Conservative Verifier (KEEP vs REVISE)
     ↓
V5 Final Answer
     ↓
Frozen V6 Read-Only Self-Evaluator
     │
     ├── Empty candidate answer
     │      ↓
     │   Self-Eval bypass
     │   Repair bypass
     │      ↓
     │   V7 final answer = unchanged empty answer
     │
     ├── Self-Eval failure / invalid schema
     │      ↓
     │   Repair bypass
     │      ↓
     │   V7 final answer = unchanged V6 answer
     │
     ├── VALID PASS
     │      ↓
     │   Repair bypass
     │      ↓
     │   V7 final answer = unchanged V6 answer
     │
     └── VALID SUSPECT
            ↓
       ONE bounded targeted repair generation (Gemini 3.5 Flash Lite)
            ↓
       Strict repair parser
            │
            ├── VALID KEEP
            │     ↓
            │   Preserve original pre-repair answer
            │
            ├── VALID REPLACE
            │     ↓
            │   Adopt parsed replacement answer
            │
            └── Provider error / Parser rejection
                  ↓
                Preserve original pre-repair answer
```

No stage after repair may inspect, verify, or alter the answer.

---

## 7. Repair Eligibility & Trigger Semantics

Repair eligibility is defined deterministically:
```python
repair_eligible = (
    bool(pre_repair_answer and pre_repair_answer.strip())
    and self_eval_success is True
    and self_eval_assessment == "SUSPECT"
)
```

### Deterministic Routing Rules:
| Condition | Repair Status | Action | Final Answer |
| :--- | :---: | :---: | :--- |
| Empty / whitespace answer | NOT eligible | Bypass | Unchanged empty answer |
| Self-eval bypass | NOT eligible | Bypass | Unchanged V6 answer |
| Self-eval provider failure | NOT eligible | Bypass | Unchanged V6 answer |
| Self-eval parser invalid | NOT eligible | Bypass | Unchanged V6 answer |
| Self-eval assessment: `PASS` | NOT eligible | Bypass | Unchanged V6 answer |
| Self-eval assessment: `VALID SUSPECT` | **Eligible** | Trigger Repair | Evaluated by repairer |

Every `VALID SUSPECT` triggers repair regardless of confidence score, risk type, benchmark level, route, or attachment presence.

---

## 8. Why No Confidence Threshold

V7 explicitly rejects confidence-based trigger gating (e.g. `if assessment == "SUSPECT" and confidence >= 0.85:`).
- Using confidence cutoffs tuned on V6 benchmark results would represent post-hoc overfitting to frozen empirical evidence.
- The V6 confidence score is recorded as telemetry and supplied as diagnostic context to the repair prompt, but it does **not** decide repair eligibility.
- This preserves unbiased evaluation across the entire `SUSPECT` population.

---

## 9. Repairer Inputs (Information Firewall)

The repair model receives **only** already-existing runtime material:
1. Original GAIA question
2. Existing web search evidence block (from upstream search)
3. Existing extracted file context & filename (from upstream file tool)
4. Current V6 final answer (`pre_repair_answer`)
5. Structured V6 assessment (`SUSPECT`)
6. Structured V6 risk type (`EVIDENCE`, `REASONING`, `CALCULATION`, `FORMAT`, `EXECUTION`, `UNKNOWN`)
7. Structured V6 confidence score (0.00 to 1.00)
8. Compact deterministic execution summary

---

## 10. Forbidden Inputs (Strict Firewall)

The repair stage must **never** receive:
- Benchmark ground-truth or reference answers
- Official scorer outcomes or correctness flags
- Scorer logic or grading internals
- Raw router prompts or raw worker reasoning
- Generated Python code or Python stdout/stderr
- Raw V5 verifier prompts or raw responses
- Raw V6 self-evaluator prompts or raw responses
- New web search results or fresh network fetches
- New file reads or re-parsed attachment bytes

---

## 11. Strict Repair Output Schema

The repair model must emit strictly formatted output.

### KEEP Action (Exactly 1 line)
```text
REPAIR_ACTION: KEEP
```
- No second line.
- No `FINAL:` line.
- No commentary or prose.

### REPLACE Action (Exactly 2 lines)
```text
REPAIR_ACTION: REPLACE
FINAL: <non-empty one-line exact answer>
```
- Exactly two lines.
- `FINAL:` must contain a non-empty, single-line replacement answer.
- If `FINAL:` matches the original answer, it is rejected as semantically inconsistent (`replace_same_answer`).

### Formatting Rules:
- Case-insensitive field matching for `REPAIR_ACTION` (e.g. `KEEP`, `keep`, `REPLACE`, `replace`).
- No markdown formatting or code fences (````).
- No extraneous fields, explanations, or multiple replacement lines.
- Malformed outputs are never normalized into valid actions.

---

## 12. Strict Repair Parser & Error Taxonomy

Parse result data structure:
```python
@dataclass(frozen=True)
class TargetedRepairParseResult:
    status: str  # "VALID_KEEP", "VALID_REPLACE", "INVALID"
    action: Optional[str] = None  # "KEEP", "REPLACE"
    final_answer: Optional[str] = None
    error_type: Optional[str] = None
```

### Parser Error Taxonomy:
- `empty_repair_response`: Raw model text was empty or whitespace.
- `markdown_code_fence`: Output contained code block backticks (````).
- `unexpected_repair_content`: Output line count was not 1 (for KEEP) or 2 (for REPLACE).
- `malformed_repair_text`: Line failed strict `FIELD: VALUE` syntax.
- `unexpected_repair_field`: Unknown field name encountered.
- `duplicate_repair_field`: Field specified multiple times.
- `missing_repair_field`: Required field omitted.
- `unknown_repair_action`: Action was not `KEEP` or `REPLACE`.
- `keep_with_final`: `KEEP` erroneously provided a `FINAL:` line.
- `replace_missing_final`: `REPLACE` lacked a `FINAL:` line.
- `replace_empty_final`: `FINAL:` value was empty.
- `replace_same_answer`: `FINAL:` value was identical to pre-repair answer.
- `multiline_replacement`: Replacement contained newline characters.

### Provider Failure Categories:
- `provider_timeout`: Request exceeded deadline.
- `provider_api_error`: Non-timeout API exception.
- `malformed_function_call_finish_reason`: Provider finished with `MALFORMED_FUNCTION_CALL`.
- `unexpected_finish_reason`: Finish reason was not `STOP`.
- `unexpected_provider_response_type`: Response was not a valid string or `LLMResponse`.

---

## 13. Failure Policy & Non-Destructive Safety

Targeted repair is strictly **non-destructive**:
- On any parser failure, provider exception, timeout, or malformed response:
  $$\text{post\_repair\_answer} = \text{pre\_repair\_answer}$$
  $$\text{final\_answer} = \text{pre\_repair\_answer}$$
- Zero retries are permitted (`max_retries=0`).
- The agent safely falls back to the original answer, ensuring repair failure never causes an empty answer or runtime crash.

---

## 14. Generation & Tool Budgets

### Generation Budget
- Router: $\le 1$
- Worker: $\le 1$
- Verifier: $\le 1$
- Self-Evaluator: $\le 1$
- Targeted Repair: $\le 1$
- **Total Standard LLM Generations**: $\le 5$
- Runtime assertion: `assert llm_generation_attempts <= 5`

### Tool Budget
- Tavily Search: $\le 1$ (upstream only; 0 in repair)
- File Extraction: $\le 1$ (upstream only; 0 in repair)
- Python Execution: $\le 1$ (upstream only; 0 in repair)
- Function Calling: `tools_mode = "NONE"` (0 in repair)

---

## 15. Scorer Firewall

Runtime execution has zero access to ground-truth answers or official scorer functions.
All correctness evaluation and transition classification occur exclusively post-hoc in `evaluation/evaluate.py`.

---

## 16. Within-Run Pre/Post Evaluation Design

The official scorer evaluates **both** answers post-hoc for every task:
1. `pre_repair_answer` $\rightarrow$ `pre_repair_correct`
2. `post_repair_answer` $\rightarrow$ `post_repair_correct`

### Within-Run Repair Transition Taxonomy:
| Transition | Pre-Repair Correctness | Post-Repair Correctness | Repair Triggered? | Meaning |
| :--- | :---: | :---: | :---: | :--- |
| **IMPROVEMENT** | False | True | Yes | Repair corrected an erroneous answer |
| **REGRESSION** | True | False | Yes | Repair damaged a correct answer |
| **STABLE_CORRECT** | True | True | Yes | Answer remained correct (e.g. valid KEEP) |
| **STABLE_FAILURE** | False | False | Yes | Answer remained incorrect |
| **NOT_TRIGGERED** | N/A | N/A | No | Repair was not triggered (PASS or ineligible) |

---

## 17. Primary Within-Run Repair Metrics

From `evaluation/targeted_repair_metrics.py`:
- `repair_eligible_count`
- `repair_triggered_count`
- `repair_attempted_count`
- `repair_valid_count`
- `repair_failure_count`
- `repair_valid_output_rate` = $\frac{\text{valid}}{\text{attempted}}$
- `repair_keep_count`
- `repair_replace_count`
- `repair_changed_count`
- `repair_improvement_count` ($0 \rightarrow 1$)
- `repair_regression_count` ($1 \rightarrow 0$)
- `repair_stable_correct_count` ($1 \rightarrow 1$)
- `repair_stable_failure_count` ($0 \rightarrow 0$)
- `repair_net_correct_delta` = $\text{improvements} - \text{regressions}$
- `pre_repair_accuracy` vs `post_repair_accuracy`
- `repair_accuracy_delta_pp` = $\text{post\_acc} - \text{pre\_acc}$
- `repair_correction_rate` = $\frac{\text{improvements}}{\text{improvements} + \text{stable\_failures}}$
- `repair_harm_rate` = $\frac{\text{regressions}}{\text{regressions} + \text{stable\_correct}}$

---

## 18. V6 Diagnostic Anchoring Invariant

> [!IMPORTANT]
> **CRITICAL SCIENTIFIC REQUIREMENT**:  
> V6 Self-Evaluation diagnostic metrics (TP, FP, TN, FN, Precision, Recall, F1, Specificity, Brier) must be evaluated against **`pre_repair_correct`**, NOT `post_repair_correct`.
> 
> If diagnostic metrics were scored against repaired correctness, a successful repair would convert a genuine True Positive into an apparent False Positive, distorting the diagnostic evaluation.

---

## 19. Contemporaneous Matched V6 Protocol

For the future V7 benchmark:
- Namespace: `experiments/v7_matched_v6/`
- Tasks: Identical 165 GAIA Validation tasks
- Configuration: Identical Gemini 3.5 Flash Lite settings (`temperature=null`, `max_output_tokens=2048`, `thinking_level=medium`)
- Inter-task delay: Exactly **5.0 seconds** for both runs
- Analysis role: Secondary, observational cross-run comparison (within-run pre/post scoring is primary).

---

## 20. Candidate Starvation Limitation

V7 does not solve candidate starvation:
- 73.17% of errors in V6 occurred because no non-empty candidate answer reached the evaluation stage.
- Empty candidate answers bypass self-evaluation and bypass repair.
- Therefore, V7 repair reach is bounded to the $\approx 27\%$ of errors that produce an inspectable candidate answer.

---

## 21. Causal Wording Rules

- **Permitted**: "In this V7 run, targeted repair produced $X$ improvements and $Y$ regressions, yielding an observed net within-run change of $Z$ tasks."
- **Prohibited**: "V7 causes a $Z$-point improvement on GAIA" (cross-run variation remains observational).

---

## 22. Boundary Between V7 and Future Versions

| Version | Mechanism | Scope |
| :--- | :--- | :--- |
| **V5** | One-shot conservative verifier before finalization | Candidate $\rightarrow$ `KEEP`/`REVISE` $\rightarrow$ final answer |
| **V6** | Read-only post-answer self-evaluator | Final answer $\rightarrow$ `PASS`/`SUSPECT` $\rightarrow$ diagnostic signal |
| **V7** | Targeted text-only repair from existing evidence | `SUSPECT` answer $\rightarrow$ `KEEP`/`REPLACE` $\rightarrow$ repaired answer |
| **V8+** | Active tool-grounded verification / re-execution | Dynamic tool calls, re-search, Python re-execution, graph loops |

Active tool verification, new searches, and Python re-execution belong exclusively to future versions and must never enter V7.

