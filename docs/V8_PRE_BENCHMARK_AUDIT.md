# V8 Pre-Benchmark Audit Report

**Date:** September 14, 2026  
**Auditor:** Automated Benchmark Integrity Suite / Antigravity Agent  
**Target Version:** `V8 — Bounded Active Evidence Verification`  
**Parent Baseline:** `V7 — SUSPECT-Triggered Targeted Repair` (Frozen)  
**Verdict:** `READY_FOR_CONTROLLED_SMOKE`

---

## Executive Summary

This pre-benchmark audit validates the architectural design, runtime implementation, information firewall, failure safety, telemetry serialization, within-run scoring metrics, and test coverage for **V8 (Bounded Active Evidence Verification)** prior to conducting controlled smoke validation and canonical benchmarking on GAIA.

V8 introduces exactly **one bounded capability increment** on top of the frozen V7 baseline:
$$\text{V8} = \text{Frozen V7} + \text{One Bounded Active Evidence-Verification Opportunity}$$

The audit confirms that all core invariants, non-destructive safety mechanisms, search contracts, usable evidence gates, information firewalls, diagnostic anchoring guarantees, and test suites are intact and verified.

---

## Preregistered Primary Research Question

> *When Frozen V7 reaches a non-empty answer whose upstream V6 diagnostic is a valid `SUSPECT` with `RISK_TYPE: EVIDENCE`, does one additional bounded web retrieval followed by one bounded evidence-based adjudication correct more erroneous answers than it harms correct answers?*

---

## Audit Checklist & Verification Matrix

| Audit Dimension | Requirement | Status | Evidence / Invariant |
| :--- | :--- | :---: | :--- |
| **Parent Baseline Integrity** | V7 code, prompts, and frozen artifacts unmodified | **PASS** | `experiments/v7/FROZEN.md`, configs, summaries intact |
| **Capability Scope** | Single isolated capability increment | **PASS** | Only bounded active evidence verification added |
| **Trigger Eligibility** | Triggered only by `SUSPECT` + `EVIDENCE` risk + non-empty V7 final answer | **PASS** | Bypassed on `PASS`, non-`EVIDENCE` (e.g. `REASONING`), invalid diagnostic, or empty answer |
| **Search Contract** | At most 1 bounded search; deterministic query; max 5 results; 1500-char query limit | **PASS** | Verified in unit tests and `prompts/active_evidence_verification.py` |
| **Usable Evidence Gate** | Skip adjudication if search fails or yields 0 usable results | **PASS** | 0 LLM adjudication calls without usable evidence; preserves V7 answer |
| **Tool Isolation** | 0 Python calls, 0 file rereads in V8 | **PASS** | `tools_mode = "NONE"`, verified in unit tests |
| **Budget Invariants** | Total searches $\le 2$, Total standard LLM generations $\le 6$ | **PASS** | Upstream $\le 1$ search, V8 $\le 1$; upstream $\le 5$ gen, V8 $\le 1$ |
| **Failure Safety** | Strictly non-destructive on any search, API, or parser error | **PASS** | Always falls back to `pre_active_verification_answer` verbatim (`action = None`) |
| **Information Firewall** | Zero access to ground truth or scorer at runtime | **PASS** | `build_active_evidence_verification_prompt` parameter audit |
| **Diagnostic Anchoring** | Upstream V6 diagnostic metrics anchored to pre-repair answer | **PASS** | Evaluated against `pre_repair_correct` / `pre_self_evaluation_correct` |
| **Intervention Taxonomy** | Within-run pre/post evaluation with 5 transitions | **PASS** | `IMPROVEMENT`, `REGRESSION`, `STABLE_CORRECT`, `STABLE_FAILURE`, `NOT_TRIGGERED` |
| **Public Privacy** | No prompts or raw responses in public records | **PASS** | `active_verification_prompt` and `raw_response` omitted; `schema_version = 7` |
| **Unit Test Coverage** | Dedicated tests + regression suite passing | **PASS** | 21/21 V8 tests pass; 349/349 full suite pass |

---

## Detailed Audit Findings

### 1. Parent Baseline (V7) Integrity
- The parent baseline `V7` remains completely frozen and immutable.
- All canonical V7 artifacts in `experiments/v7/` (`FROZEN.md`, `config.json`, `detailed_eval_level_*.jsonl`, `summary_level_*.json`, `predictions_level_*.jsonl`, `MANIFEST.invariants.json`) have been preserved without modification.
- `GAIAActiveEvidenceVerificationAgent` cleanly subclasses `GAIATargetedRepairAgent`, calling `super().run(question, file_path)` to execute the complete frozen V7 pipeline (routing $\rightarrow$ worker execution $\rightarrow$ V5 verification $\rightarrow$ V6 self-evaluation $\rightarrow$ V7 targeted repair) before entering active verification logic.
- Version dispatch in `evaluation/runner.py` and `evaluation/run_level.py` places `isinstance(agent, GAIAActiveEvidenceVerificationAgent)` strictly before `isinstance(agent, GAIATargetedRepairAgent)` to prevent subclass masking.

### 2. Single Capability Increment & Trigger Guard
- The sole increment in V8 is a bounded active evidence verification opportunity.
- **Eligibility Conditions:**
  1. Frozen V7 final answer (`pre_active_verification_answer`) is non-empty and non-whitespace.
  2. Upstream self-evaluator completed successfully (`self_eval_success == True`).
  3. Upstream self-evaluator assessment is strictly `SUSPECT` (`self_eval_assessment == "SUSPECT"`).
  4. Upstream self-evaluator risk type is strictly `EVIDENCE` (`self_eval_risk_type == "EVIDENCE"`).
- If self-evaluation is `PASS`, invalid, associated with a non-`EVIDENCE` risk (e.g. `REASONING`, `CALCULATION`, `FORMAT`, `EXECUTION`), or if the candidate answer is empty, active verification is completely bypassed:
  - `active_verification_eligible = False`
  - `active_verification_triggered = False`
  - `active_verification_search_attempted = False`
  - `active_verification_adjudication_attempted = False`
  - `active_verification_generation_attempts = 0`
  - Answer preserved verbatim (`post_active_verification_answer = pre_active_verification_answer`).

### 3. Active Search Contract & Usable Evidence Gate
- **Deterministic Search Query Generation:**
  - Function signature:
    ```python
    def build_active_evidence_query(question: str, current_answer: str) -> str:
        return (
            f"{question.strip()}\n\n"
            f"Candidate answer to independently verify:\n"
            f"{current_answer.strip()}"
        )
    ```
  - V8 deterministically constructs the active verification query by concatenating the original question with the current Frozen V7 final answer (`pre_active_verification_answer`) under the fixed `"Candidate answer to independently verify:"` label.
  - No LLM or heuristic query rewriting is performed. Zero entity extraction, keyword filtering, stop-word removal, predicate extraction, or artificial keyword appending.
- **Search Execution & Truncation:**
  - At most 1 search execution (`max_results=5`).
  - The active verification query is deterministically truncated to the first 1,500 characters by the existing `TavilySearchTool` before provider submission (`provider_query = cleaned_query[:1500]`).
  - Zero search retries (`max_retries=0`).
- **Usable Evidence Gate:**
  - If search encounters an exception, provider timeout, or yields 0 search results:
    - `active_verification_search_usable = False`
    - Adjudication LLM call is **skipped entirely** (`active_verification_adjudication_attempted = False`, `active_verification_generation_attempts = 0`).
    - The agent immediately preserves the Frozen V7 final answer (`pre_active_verification_answer`) verbatim.
    - Automatic failure preservation is **not** a `KEEP` action (`active_verification_action = None`).

### 4. Adjudication Prompt, Information Firewall & Strict Schema
- `build_active_evidence_verification_prompt` accepts only:
  - Original question
  - Candidate answer (marked `CURRENT ANSWER (MARKED SUSPECT)`)
  - Upstream diagnostic metadata (`ASSESSMENT: SUSPECT`, `RISK_TYPE: EVIDENCE`, `CONFIDENCE`)
  - Prior evidence summary (upstream search query + summary)
  - Existing file context and attachment filename
  - Newly retrieved active verification evidence (snippets + URLs)
  - Compact deterministic execution summary
- **Firewall Guarantee:** Ground truth, reference answers, scorer functions, internal worker CoT reasoning, Python code, and scratchpad traces are strictly excluded.
- **Strict Output Schema:**
  - Option A (Confirm / Keep - exactly 1 line):
    ```text
    VERIFICATION_ACTION: KEEP
    ```
  - Option B (Correct / Replace - exactly 2 lines):
    ```text
    VERIFICATION_ACTION: REPLACE
    FINAL: <replacement answer>
    ```
- `parse_active_evidence_verification_result` strictly rejects:
  - Markdown code fences (```` ``` ````)
  - Multiline replacements
  - Replacements identical to `pre_active_verification_answer` (`replace_same_answer`)
  - Missing or empty `FINAL:` line under `REPLACE`
  - Extraneous text or unapproved action verbs

### 5. Non-Destructive Failure Safety
- If active verification encounters:
  - Active search failure / 0 results (`active_search_error`, `zero_search_results`)
  - Provider timeout (`provider_timeout`)
  - Provider API error (`provider_api_error`)
  - Provider finish reason anomalies (`malformed_function_call_finish_reason`, `unexpected_finish_reason`)
  - Schema/parser failure (`empty_verification_response`, `markdown_code_fence`, `malformed_verification_text`, `replace_same_answer`, etc.)
- The agent immediately falls back to `pre_active_verification_answer` (Frozen V7 answer):
  $$\text{post\_active\_verification\_answer} = \text{pre\_active\_verification\_answer}$$
  $$\text{final\_answer} = \text{pre\_active\_verification\_answer}$$
  $$\text{active\_verification\_answer\_changed} = \text{False}$$
- Automatic fallback preservation is strictly recorded with `active_verification_action = None`. `KEEP` is only recorded when the model successfully emits a valid `VERIFICATION_ACTION: KEEP` response.
- An active verification failure can never produce an empty answer, crash execution, or corrupt a valid V7 answer.

### 6. Resource Budgets & Invariants
- **Search Budget:**
  - Upstream searches: $\le 1$
  - V8 active search: $\le 1$
  - Total cumulative searches: $\le 2$
- **Generation Budget:**
  - Router: $\le 1$
  - Worker: $\le 1$
  - Verifier (V5): $\le 1$
  - Self-Evaluator (V6): $\le 1$
  - Targeted Repair (V7): $\le 1$
  - Active Verification Adjudication (V8): $\le 1$
  - Total cumulative standard LLM generations: $\le 6$ (enforced by runtime assertion)
- **Tool Isolation:**
  - Python calls during V8: 0
  - File rereads during V8: 0

### 7. Scorer Firewall & Diagnostic Anchoring
- Ground-truth evaluation occurs strictly post-hoc in `evaluation/evaluate.py`.
- **Upstream Diagnostic Anchoring:**
  - The upstream V6 evaluator diagnostic remains anchored to the answer that V6 actually evaluated (`pre_repair_answer` / `pre_repair_correct` or fallback `pre_self_evaluation_correct`).
  - V6 True Positives, False Positives, Precision, Recall, and F1 are **not** anchored to `pre_active_verification_correct` or generic `pre_verification_correct`.
- **Within-Run Intervention Transitions:**
  - V8 intervention transitions are measured separately by comparing `pre_active_verification_correct` and `post_active_verification_correct`:
    - `IMPROVEMENT` ($0 \rightarrow 1$): `pre_active_verification_correct == False` and `post_active_verification_correct == True`
    - `REGRESSION` ($1 \rightarrow 0$): `pre_active_verification_correct == True` and `post_active_verification_correct == False`
    - `STABLE_CORRECT` ($1 \rightarrow 1$): `pre_active_verification_correct == True` and `post_active_verification_correct == True`
    - `STABLE_FAILURE` ($0 \rightarrow 0$): `pre_active_verification_correct == False` and `post_active_verification_correct == False`
    - `NOT_TRIGGERED`: Verification not triggered (ineligible or bypassed)

### 8. Scientific Attribution & Observational Matched Control
- **Primary within-run intervention measurement**: The primary V8 stage-effect measurement compares the Frozen V7 final answer (`pre_active_verification_answer`) with the V8 final answer (`post_active_verification_answer`) inside the exact same execution trace.
- **Matched Frozen V7 Control**: A separately executed matched Frozen V7 control run is observational and non-causal. Useful for monitoring provider stability and global completion behavior, but explicitly labeled non-causal.

### 9. Public Serialization & Privacy
- Public predictions JSONL records:
  - Serialized under `schema_version = 7`.
  - Comprehensive safe telemetry: `pre_active_verification_answer`, `post_active_verification_answer`, `active_verification_eligible`, `active_verification_triggered`, `active_verification_search_attempted`, `active_verification_search_success`, `active_verification_query`, `active_verification_search_result_count`, `active_verification_usable_evidence`, `active_verification_adjudication_attempted`, `active_verification_generation_success`, `active_verification_action`, `active_verification_answer_changed`, `active_verification_error_type`, `active_verification_finish_reason`, tokens, and latencies.
  - **Strictly Omitted:** `active_verification_prompt` and `active_verification_raw_response`.

### 10. Test Suite Validation
- Dedicated V8 unit tests (`tests/test_v8_active_evidence_verification.py`):
  - 21 focused unit tests covering prompt generation, deterministic query formation, strict parser compliance, eligibility guards (PASS bypass, REASONING risk bypass, empty answer bypass), usable evidence enforcement, non-destructive fallbacks, budget limits ($\le 6$ generations, $\le 2$ searches), diagnostic anchoring, within-run transition taxonomy, and serialization.
- **Full Repository Suite:** 349 / 349 tests passing with 0 errors and 0 failures.

---

## Controlled Smoke Validation Protocol (Next Phase)

Prior to launching any canonical benchmark:
1. Execute a controlled smoke validation on the first 6 fixed GAIA tasks across Levels 1-3.
2. Verify:
   - Proper extraction of `schema_version = 7` in prediction artifacts.
   - Exact triggering on `SUSPECT` + `EVIDENCE`.
   - Complete bypass on `PASS` or non-`EVIDENCE`.
   - Adjudication skip when search returns no usable evidence.
   - Public privacy compliance (prompts and raw responses omitted).
   - Zero-harm preservation of V7 answers upon parser or API errors.

---

## Audit Verdict

```text
FINAL VERDICT: READY_FOR_CONTROLLED_SMOKE
```

V8 is fully designed, implemented, instrumented, verified, and ready for smoke testing. No full GAIA benchmark or freeze action has been taken.
