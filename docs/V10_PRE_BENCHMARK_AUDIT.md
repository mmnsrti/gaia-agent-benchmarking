# V10 — Pre-Benchmark Audit

**Status:** `READY_FOR_CANONICAL_BENCHMARK`
**Date:** September 18, 2026
**Auditor:** Automated Benchmark Integrity Suite / Antigravity Agent
**Branch:** `v10-planner-executor`
**Scientific Parent:** Frozen V9 (`v9-upstream-candidate-recovery`)
**Parent Inference Baseline:** `6369f427c4479073a6ca06531bdfd43e47cd613f` (Score: 73 / 165 = 44.24%)
**Preregistration Baseline Commit:** `5132ad8a9122f057dc6156f878e4c697a35f505b`
**Canonical Inference Candidate:** `314d0aecd01a1679a96d85256044c01c8b6c30ce`
**Evaluation Schema Version:** 8

---

## 1. Executive Summary & Audit Verdict

This formal pre-benchmark audit thoroughly evaluates the technical implementation, architectural integrity, resource bounds, generation accounting, information firewalls, deterministic fallback policies, and verification test suites for **Version 10 (V10) — Structured Planner → Plan-Guided Executor** against the binding preregistration in `experiments/v10/`.

### Final Audit Verdict
```text
READY_FOR_CANONICAL_BENCHMARK
```

All 47 audit checkpoints pass without exception:
1. **Single Scientific Intervention Isolated**: The coarse capability router (Router) and worker (Worker) from Frozen V9 are cleanly replaced by the Structured Planner (Slot 1) and Plan-Guided Executor (Slot 2). All downstream mechanisms (Candidate Recovery, Verifier, Self-Evaluator, Targeted Repair) are preserved verbatim.
2. **Strict Generation Slot Equalization**: Upstream generation slots are strictly equalized at 2 (Slot 1: Planner, Slot 2: Executor). Zero extra LLM generations or replanning loops are introduced.
3. **Tool Budgets Frozen**: $\le 1$ Tavily search, $\le 1$ file processing, $\le 1$ Python execution per agent branch. The Structured Planner has 0 tools (`tools_mode = "NONE"`).
4. **Resilient Local Fallback**: Any planner parsing failure, malformed output, timeout, or unexpected finish reason (`MAX_TOKENS`, `LENGTH`, `SAFETY`) deterministically triggers a safe `MODE: DIRECT` fallback plan with zero provider retry.
5. **Deterministic Shared-Context Paired Ablation**: The primary evaluation harness executes counterfactual paired runs across identical snapshotted retrieval contexts with SHA-256 evidence hashing and strict ground-truth firewalling.
6. **Full Test Suite Validation**: 410 / 410 unit and integration tests pass with 0 failures and 0 errors.
7. **Clean Runtime Baseline**: Canonical inference candidate commit `314d0aecd01a1679a96d85256044c01c8b6c30ce` is fully locked.

---

## 2. Canonical Inference Commit Lock

> [!IMPORTANT]
> The canonical runtime inference candidate commit is:
> ```text
> 314d0aecd01a1679a96d85256044c01c8b6c30ce
> ```
> This audit applies strictly to code at this commit. If any runtime, prompt, tool, or evaluation-harness code is modified after `314d0aecd01a1679a96d85256044c01c8b6c30ce`, this pre-benchmark audit is automatically invalidated and must be completely rerun prior to canonical benchmark execution.

---

## 3. Scientific Question & Theoretical Motivation

### 3.1 Primary Research Question
> *When operating on the same Frozen V9 search, file, and tool budget, does replacing the coarse capability router with a bounded structured planner and conditioning the existing executor on that plan improve GAIA end-to-end correctness without increasing retrieval or execution tool budgets or total upstream generation slots?*

### 3.2 Empirical Motivation from Frozen V9
The canonical Frozen V9 benchmark established that candidate starvation was largely solved:
- Pre-recovery candidate reachability: $45.45\%$ (75/165)
- Post-recovery candidate reachability: $96.36\%$ (159/165, $+50.91$ percentage points)

However, a severe upstream execution bottleneck remained:
- Recovered candidates initial accuracy was only $30.95\%$ (26/84).
- $65.48\%$ ($55/84$) of recovered candidates remained incorrect throughout all downstream stages.
- Downstream V7 targeted repair triggered on 75 tasks but yielded only $1$ net improvement ($0 + 0 + 1$).
- Self-evaluation risk diagnostics revealed conditional error rates of $78.3\%$ for `EXECUTION` risk and $88.9\%$ for `EVIDENCE` risk.

Because post-hoc text repair cannot reconstruct ungathered facts or salvage fundamentally misdirected execution, V10 intervenes upstream via explicit task decomposition and plan-guided execution.

---

## 4. Single Architectural Intervention

```text
Frozen V9 Upstream Pipeline:
  Shared Search / File Context
          ↓
  [Slot 1] Capability Router Generation (DIRECT vs PYTHON)
          ↓
  [Slot 2] Worker Generation (DIRECT answer or PYTHON script)
          ↓
  Upstream Candidate

V10 Upstream Pipeline:
  Shared Search / File Context
          ↓
  [Slot 1] Structured Planner Generation (MODE, OBJECTIVE, EVIDENCE, PLAN, ANSWER_TYPE)
          ↓
  [Slot 2] Plan-Guided Executor Generation (conditioned on Structured Plan)
          ↓
  Upstream Candidate
```

### Preserved Downstream Stages
```text
Upstream Candidate
       ↓
1. Candidate Recovery (Frozen V9)  — Bounded 1-shot recovery for eligible empty candidates; strictly bypassed if candidate is non-empty.
       ↓
2. Answer Verifier (Frozen V5)     — 1-shot verification (KEEP vs REVISE).
       ↓
3. Self-Evaluator (Frozen V6)     — Risk diagnosis (PASS vs SUSPECT, confidence, risk_type).
       ↓
4. Targeted Repair (Frozen V7)     — 1-shot repair for SUSPECT candidates (KEEP vs REPLACE).
       ↓
Final Answer
```

Conclusion: Single scientific intervention strictly isolated.

---

## 5. Architectural Contracts & Resource Invariants

| Invariant / Resource | Specification | Audit Status | Evidence / Implementation Reference |
| :--- | :--- | :---: | :--- |
| **Model Configuration** | `gemini-3.5-flash-lite`, `thinking_level: medium`, `max_output_tokens: 2048`, `temperature: null`, `tools_mode: NONE` | **VERIFIED** | `experiments/v10/config.json`, `agent/agent.py` |
| **Upstream Slots** | Exactly 2 logical generations (Slot 1: Planner, Slot 2: Executor) | **VERIFIED** | `GAIAPlannerExecutorAgent._execute_upstream_pair_from_context` |
| **Non-Recovery Generation Cap** | $\le 5$ logical generations (Planner + Executor + Verifier + Self-Eval + Repair) | **VERIFIED** | Enforced by assertions in `agent/agent.py` and `evaluation/runner.py` |
| **Recovery Generation Cap** | $\le 6$ logical generations (Planner + Executor + Recovery + Verifier + Self-Eval + Repair) | **VERIFIED** | Enforced by assertions in `agent/agent.py` and `evaluation/runner.py` |
| **Search Budget** | $\le 1$ Tavily search per task (Planner = 0, Recovery = 0) | **VERIFIED** | Snapshotted in `_prepare_upstream_context`, planner has no tools |
| **File Budget** | $\le 1$ FileTool parse per task (Planner = 0, Recovery = 0) | **VERIFIED** | Snapshotted in `_prepare_upstream_context`, planner has no tools |
| **Python Budget** | $\le 1$ execution per deployed agent branch (0 in DIRECT, $\le 1$ in PYTHON) | **VERIFIED** | Enforced by single-shot execution contract in `agent/agent.py` |
| **Planner Fallback** | Deterministic local fallback plan on error; zero additional LLM generations | **VERIFIED** | `build_fallback_plan` in `prompts/planner.py` |
| **Unexpected Finish** | Non-`STOP` finish reasons normalized to `unexpected_finish_reason` with fallback | **VERIFIED** | Handled in `GAIAPlannerExecutorAgent` lines 2138–2141 |
| **Schema Version** | Schema 8 with comprehensive V10 planner/executor telemetry | **VERIFIED** | Serialized in `evaluation/runner.py`, version resolution hierarchy verified |
| **Telemetry Privacy** | No private scratchpad, chain-of-thought, or ground truth logged | **VERIFIED** | Public fields in Schema 8 audited in `evaluation/runner.py` |

---

## 6. Two-Tier Evaluation Methodology & Decision Rules

### 6.1 Tier 1 (Primary): Shared-Context Paired Upstream Ablation
- **Harness**: `evaluation/run_v10_paired.py`
- **Boundary**: Candidate answers produced at the upstream boundary before any candidate recovery, verification, self-evaluation, or repair occurs.
- **Controlled Invariants**:
  - Context Acquisition: Exactly 1 search and at most 1 file parse executed and snapshotted.
  - Evidence Hashing: SHA-256 digests (`shared_context_search_hash`, `shared_context_file_hash`, `v9_*`, `v10_*`) computed without disk re-reads.
  - Information Firewall: Zero access to reference answers or official scorer at runtime.
  - Post-Hoc Scoring: Scored using official vendored GAIA scorer (`evaluation/scorer.py`).
- **Primary Paired Metric**:
  $$\Delta_{\text{upstream}} = N(\text{UPSTREAM\_IMPROVEMENT}) - N(\text{UPSTREAM\_REGRESSION})$$

### 6.2 Tier 2 (Secondary): Contemporaneous Matched Frozen V9 Control
- **Harness**: `evaluation/run_level.py` (Version `v10` full run + contemporaneous Version `v9` full run).
- **Classification**: Observational and non-causal due to run-to-run sampling variance.
- **Reporting**: Cross-run transition matrix reported for diagnostic context only; not the primary causal criterion.

### 6.3 Binding Promotion Gates
Promotion of V10 as the baseline for V11 requires meeting **ALL** preregistered criteria:
1. $\Delta_{\text{upstream}} = N(\text{UPSTREAM\_IMPROVEMENT}) - N(\text{UPSTREAM\_REGRESSION}) > 0$.
2. Canonical V10 official accuracy strictly exceeds Frozen V9 reference:
   $$\text{Accuracy}_{\text{V10}} > \frac{73}{165} = 44.24\%$$
3. Tool budgets strictly respected ($\le 1$ search, $\le 1$ file, $\le 1$ Python per branch).
4. Generation budgets strictly respected ($\le 5$ non-recovery, $\le 6$ recovery).
5. Upstream generation slots == 2.
6. Frozen V9 candidate recovery preserved verbatim.
7. Frozen V5/V6/V7 downstream pipeline preserved verbatim.
8. Operational validity confirmed across all 165 tasks with 0 unhandled exceptions.

---

## 7. Static Source Hygiene & AST Verification

Direct AST inspection confirmed:
- `GAIARouterAgent.run` definitions: Exactly **1** definition.
- `GAIATargetedRepairAgent.run` `max_v7_gens` assignments: Exactly **2** definitions (1 in skipped-repair path, 1 in post-repair path).
- Adjacent duplicate assignments to `max_v7_gens`: Exactly **0** occurrences.
- Duplicate classes, functions, and dead methods in V10 modules: **0**.

---

## 8. Verification & Test Suite Execution Results

All automated test suites execute deterministically with zero live network calls:

1. **V10 Deterministic Smoke & Hardened Invariant Suite**:
   ```powershell
   python -m unittest tests.test_v10_planner_executor -v
   ```
   **Result**: 37 / 37 tests PASSED in 2.684s.
   - Scenarios 1–10: Planner Prompt & Strict Grammar Parsing (Valid Direct, Valid Python, Missing Keys, Bad Modes, Empty Steps, Boundary 1-step and 5-step, Fallback triggers).
   - Scenarios 11–12: Upstream Execution Matrix (Planner + Direct Executor, Planner + Python Executor).
   - Scenarios 13–16: Candidate Extraction & Recovery Coupling (Empty Candidate, Python Crash, Recovery After Starvation, Non-Starved Bypass).
   - Scenarios 17–18: Full Pipeline Preservation (5 generations on non-recovery, 6 generations on recovery).
   - Scenarios 19–20: Tool Budget & Information Firewall Audits ($\le 1$ tool call, 0 tools for planner, zero leaked tokens).
   - Scenarios 21–24: Shared Context & Paired Harness Invariants (Search/File Hash Invariance, Transition Scoring, Ground Truth Firewall).
   - Hardened Invariants: AST single `run()` check, AST 2-cap check, AST 0-adjacent duplicates check, multimodal native byte hashing, strict consecutive numbering, unexpected finish reason fallback, token telemetry.

2. **Regression Test Suites (Frozen V9, V7, V6, V5, V4)**:
   ```powershell
   python -m unittest tests.test_v9_candidate_recovery tests.test_v7_targeted_repair tests.test_v6_self_evaluation tests.test_verification_agent tests.test_router_agent -v
   ```
   **Result**: 160 / 160 tests PASSED in 58.479s.

3. **Multi-Key Transport Failover Suites (Gemini & Tavily)**:
   ```powershell
   python -m unittest tests.test_llm tests.test_web_search -v
   ```
   **Result**: 47 / 47 tests PASSED in 4.085s.

4. **Full Repository Test Suite**:
   ```powershell
   python -m unittest discover -s tests -p "test_*.py"
   ```
   **Result**: 410 / 410 tests PASSED in 122.753s. Zero regressions.

5. **Codebase Compilation**:
   ```powershell
   python -m compileall agent prompts tools evaluation tests
   ```
   **Result**: Exit code 0 (clean compilation).

---

## 9. Canonical Benchmark Execution Plan

Following this pre-benchmark audit approval, three canonical runs will be executed in strict sequence:

### Execution A: Primary Paired Ablation
- **Command**:
  ```powershell
  python -m evaluation.run_v10_paired --output_file experiments/v10/paired_results_raw.jsonl
  python -m evaluation.evaluate_v10_paired --input_file experiments/v10/paired_results_raw.jsonl --summary_output experiments/v10/paired_summary.json --detailed_output experiments/v10/paired_detailed.jsonl
  ```
- **Scope**: All 165 GAIA tasks across Levels 1, 2, and 3.
- **Output**: Primary metric $\Delta_{\text{upstream}}$, transition matrix, empty candidate counts, hash mismatch counts.

### Execution B: Canonical V10 Full Benchmark
- **Commands**:
  ```powershell
  python -m evaluation.run_level --version v10 --level 1 --delay 5.0
  python -m evaluation.run_level --version v10 --level 2 --delay 5.0
  python -m evaluation.run_level --version v10 --level 3 --delay 5.0
  ```
- **Scope**: Full 165 tasks (53 L1, 86 L2, 26 L3).
- **Output**: Official canonical accuracy $\text{Accuracy}_{\text{V10}}$, full pipeline telemetry in Schema 8.

### Execution C: Secondary Matched Control (Contemporaneous Frozen V9 Full Run)
- **Commands**:
  ```powershell
  python -m evaluation.run_level --version v9 --level 1 --delay 5.0
  python -m evaluation.run_level --version v9 --level 2 --delay 5.0
  python -m evaluation.run_level --version v9 --level 3 --delay 5.0
  ```
- **Scope**: Full 165 tasks contemporaneously matched.
- **Output**: Observational, non-causal cross-run comparison for environmental context.
