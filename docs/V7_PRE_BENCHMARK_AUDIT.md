# V7 Pre-Benchmark Audit Report

**Date:** September 13, 2026  
**Auditor:** Automated Benchmark Integrity Suite / Antigravity Agent  
**Target Version:** `V7 — SUSPECT-Triggered Targeted Repair`  
**Parent Baseline:** `V6 — Self-Evaluation / Failure Detection` (Frozen)  
**Verdict:** `READY_FOR_CONTROLLED_SMOKE`

---

## Executive Summary

This pre-benchmark audit validates the architectural design, runtime implementation, information firewall, failure safety, telemetry serialization, within-run scoring metrics, and test coverage for **V7 (SUSPECT-Triggered Targeted Repair)** prior to conducting controlled smoke tests and canonical benchmarking on the GAIA benchmark.

V7 introduces exactly **one bounded capability increment** on top of the frozen V6 baseline:
$$\text{V7} = \text{Frozen V6} + \text{One-Shot SUSPECT-Triggered Text-Only Targeted Repair}$$

The audit confirms that all core invariants, non-destructive safety mechanisms, information firewalls, diagnostic anchoring guarantees, and test suites are intact and verified.

---

## Audit Checklist & Verification Matrix

| Audit Dimension | Requirement | Status | Evidence / Invariant |
| :--- | :--- | :---: | :--- |
| **Parent Baseline Integrity** | V6 code, prompts, and frozen artifacts unmodified | **PASS** | `experiments/v6/FROZEN.md`, configs, summaries intact |
| **Capability Scope** | Single isolated capability increment | **PASS** | Only post-answer targeted repair added |
| **Trigger Eligibility** | Triggered only by valid `SUSPECT` on non-empty answer | **PASS** | Bypass on `PASS`, invalid self-eval, or empty answer |
| **Tool Isolation** | 0 search, 0 python, 0 file rereads in repair | **PASS** | `tools_mode = "NONE"`, verified in unit tests |
| **Generation Cap** | Strict $\le 5$ generation limit on all paths | **PASS** | `assert llm_generation_attempts <= 5` in `agent.py` |
| **Failure Safety** | Strictly non-destructive on any error | **PASS** | Always falls back to `pre_repair_answer` |
| **Information Firewall** | Zero access to ground truth or scorer at runtime | **PASS** | `build_targeted_repair_prompt` parameter audit |
| **Diagnostic Anchoring** | V6 self-eval metrics anchored to pre-repair answer | **PASS** | Scored against `pre_repair_correct` in `evaluate.py` |
| **Transition Taxonomy** | Within-run pre/post evaluation with 5 transitions | **PASS** | `IMPROVEMENT`, `REGRESSION`, `STABLE_CORRECT`, etc. |
| **Public Privacy** | No prompts or raw responses in public records | **PASS** | `repair_prompt` and `raw_response` omitted; schema v6 |
| **Unit Test Coverage** | Dedicated tests + regression suite passing | **PASS** | 23/23 V7 tests pass; 0 regressions |

---

## Detailed Audit Findings

### 1. Parent Baseline (V6) Integrity
- The parent baseline `V6` remains completely frozen and immutable.
- All canonical V6 artifacts in `experiments/v6/` (`FROZEN.md`, `config.json`, `detailed_eval_level_*.jsonl`, `summary_level_*.json`, `predictions_level_*.jsonl`) have been preserved without modification.
- `GAIATargetedRepairAgent` cleanly subclasses `GAIASelfEvaluationAgent`, calling `super().run(question, file_path)` to execute the complete frozen V6 pipeline (routing $\rightarrow$ worker execution $\rightarrow$ V5 verification $\rightarrow$ V6 self-evaluation) before entering repair logic.
- Version dispatch in `evaluation/runner.py` places `isinstance(agent, GAIATargetedRepairAgent)` strictly before `isinstance(agent, GAIASelfEvaluationAgent)` to prevent subclass masking.

### 2. Single Capability Increment & Tool Policy
- The sole increment in V7 is a single, bounded text-only generation to repair answers assessed as `SUSPECT`.
- **Eligibility Conditions:**
  1. `pre_repair_answer` is non-empty and non-whitespace.
  2. V6 self-evaluator completed successfully (`self_eval_success == True`).
  3. V6 self-evaluator assessment is strictly `SUSPECT` (`self_eval_assessment == "SUSPECT"`).
- If self-evaluation is `PASS`, invalid, or if the answer is empty, repair is completely bypassed (`repair_eligible=False`, `repair_triggered=False`, `repair_attempted=False`, `repair_generation_attempts=0`).
- **Tool Isolation:**
  - Repair prompt is text-only (`attachment_parts=None`).
  - Search tool calls during repair = 0.
  - Python tool calls during repair = 0.
  - File reading calls during repair = 0.
  - LLM max retries = 0 (`max_retries=0`).
- **Generation Budget Invariant:**
  - Router: $\le 1$
  - Worker: $\le 1$
  - Verifier: $\le 1$
  - Self-Evaluator: $\le 1$
  - Targeted Repair: $\le 1$
  - Standard total generations cap: $\le 5$ enforced by runtime assertion.

### 3. Information Firewall & Strict Schema
- `build_targeted_repair_prompt` accepts only:
  - Original question
  - Pre-repair answer (marked `CURRENT ANSWER (MARKED SUSPECT)`)
  - Upstream V6 diagnostic signal (`ASSESSMENT: SUSPECT`, `RISK_TYPE`, `CONFIDENCE`)
  - Deterministic compact execution summary (route, search success, attachment info)
  - Existing web and file evidence already gathered upstream
- **Firewall Guarantee:** Ground truth, reference answers, scorer functions, raw worker internal reasoning, generated Python code, and Python stdout/stderr are strictly excluded.
- **Strict Output Schema:**
  - Option A:
    ```text
    REPAIR_ACTION: KEEP
    ```
  - Option B:
    ```text
    REPAIR_ACTION: REPLACE
    FINAL: <replacement answer>
    ```
- `parse_targeted_repair_result` strictly rejects:
  - Markdown code fences (```` ``` ````)
  - Multiline replacements
  - Replacements matching the pre-repair answer (`replace_same_answer`)
  - Missing or empty `FINAL:` line under `REPLACE`
  - Extraneous text, explanations, or multiple fields

### 4. Non-Destructive Failure Safety
- If the repair generation encounters:
  - Provider timeout (`provider_timeout`)
  - Provider API error (`provider_api_error`)
  - Provider finish reason anomalies (`malformed_function_call_finish_reason`, `unexpected_finish_reason`)
  - Schema/parser failure (`empty_repair_response`, `markdown_code_fence`, `malformed_repair_text`, `replace_same_answer`, etc.)
- The agent immediately falls back to `pre_repair_answer`:
  $$\text{post\_repair\_answer} = \text{pre\_repair\_answer}$$
  $$\text{final\_answer} = \text{pre\_repair\_answer}$$
  $$\text{repair\_answer\_changed} = \text{False}$$
- A repair failure can never produce an empty answer or crash the execution loop.

### 5. Scorer Firewall & Diagnostic Anchoring
- Ground-truth evaluation occurs strictly post-hoc in `evaluation/evaluate.py`.
- **Within-Run Repair Transition Taxonomy:**
  - `IMPROVEMENT` ($0 \rightarrow 1$): Pre-repair wrong, post-repair correct.
  - `REGRESSION` ($1 \rightarrow 0$): Pre-repair correct, post-repair wrong (harm).
  - `STABLE_CORRECT` ($1 \rightarrow 1$): Pre-repair correct, post-repair correct.
  - `STABLE_FAILURE` ($0 \rightarrow 0$): Pre-repair wrong, post-repair wrong.
  - `NOT_TRIGGERED`: Repair not triggered (PASS or ineligible).
- **Critical Diagnostic Anchoring Invariant:**
  - Self-evaluation occurs chronologically *before* repair.
  - In V7 evaluation summaries, V6 True Positives, False Positives, Precision, Recall, and F1 are calculated against `pre_repair_correct`, **NOT** `post_repair_correct`.
  - This prevents an effective repair from artificially turning a True Positive failure detection into an apparent False Positive.

### 6. Public Serialization & Privacy
- Public predictions JSONL records:
  - Updated to `schema_version = 6`.
  - Include safe telemetry: `pre_repair_answer`, `post_repair_answer`, `repair_eligible`, `repair_triggered`, `repair_attempted`, `repair_success`, `repair_action`, `repair_answer_changed`, `repair_error_type`, `repair_finish_reason`, tokens, and latencies.
  - **Strictly Omit:** `repair_prompt` and `repair_raw_response`.

### 7. Unit Test Suite Validation
- Dedicated unit tests in `tests/test_v7_targeted_repair.py`:
  - `TestV7TargetedRepairParser` (4 tests: valid KEEP, valid REPLACE, schema rejections, same-answer rejections)
  - `TestV7PromptBuilderAndFirewall` (2 tests: permitted context, scorer firewall)
  - `TestV7RuntimeAndTriggerLogic` (5 tests: PASS bypass, empty answer bypass, invalid self-eval bypass, valid SUSPECT KEEP, valid SUSPECT REPLACE)
  - `TestV7FailureSafety` (4 tests: timeout fallback, malformed function call fallback, parser error fallback, redundant replace fallback)
  - `TestV7ToolIsolationAndBoundedness` (2 tests: zero extra tools during repair, generation cap $\le 5$)
  - `TestV7VersionDispatchAndSubclassResolution` (2 tests: subclass resolution order, v6 parent isolation)
  - `TestV7DiagnosticAnchoring` (1 test: diagnostic metrics anchored to pre-repair correctness)
  - `TestV7WithinRunRepairMetrics` (2 tests: transition and rate calculations, zero-denominator safety)
  - `TestV7HarmAndConservativeKeep` (1 test: utility of conservative KEEP under false alarm)
- **Total V7 Unit Tests:** 23 passing.
- **Repository Full Test Suite:** All existing regression tests passing.

---

## Controlled Smoke Test Protocol (Next Phase)

Prior to launching any canonical benchmark run:
1. Run a single-task controlled smoke test with `--limit 1` on Level 1:
   ```bash
   python -m evaluation.run_level --version v7 --level 1 --limit 1
   ```
2. Verify that:
   - Prediction artifact has `schema_version == 6`.
   - `project_version == "v7"`.
   - Repair telemetry fields are populated correctly.
   - Private fields (`repair_prompt`, `repair_raw_response`) are absent.
   - Summary file `experiments/v7/summary_level_1.json` is generated.

---

## Audit Verdict

```text
FINAL VERDICT: READY_FOR_CONTROLLED_SMOKE
```

V7 is fully designed, implemented, instrumented, verified, and ready for smoke testing. No full GAIA benchmark or freeze action has been taken.

