# V11 — Final Pre-Benchmark Audit

**Status:** `READY_FOR_CANONICAL_BENCHMARK`  
**Branch:** `v11-adaptive-evidence-retrieval`  
**Scientific Parent:** `Frozen V10`  
**Preregistration Commit:** `59f6944ff92f94e6ef2122bb98a0079d021d411b`  
**Canonical Inference Candidate:** `02b368b030e2c86c2e534d6012149f819e8d136a`  
**Evaluation Schema:** `9`  
**Frozen V10 Reference:** `84 / 165 = 50.91%`  

---

## 1. Executive Summary & Canonical Inference Lock

This document establishes the final independent scientific audit of **V11 — Planner-Guided Adaptive Evidence Retrieval** prior to formal benchmark execution on the GAIA benchmark.

### Canonical Inference Lock
```text
V11 CANONICAL INFERENCE CANDIDATE:
02b368b030e2c86c2e534d6012149f819e8d136a
```

> [!IMPORTANT]
> Any runtime, prompt, tool, evaluation harness, parser, or test-relevant behavioral change after commit `02b368b030e2c86c2e534d6012149f819e8d136a` invalidates this audit and requires a new pre-benchmark audit. Documentation-only audit commits do not change the canonical inference candidate.

---

## 2. Provenance Audit & History Verification

The complete commit lineage on branch `v11-adaptive-evidence-retrieval` above Frozen V10 (`0761b81330540cdc67fe2d662aef049bc87d9d8f`) has been audited:

```text
02b368b fix: finalize V11 pre-benchmark invariants
dcada60 Revert "feat: enhance V11 adaptive evidence retrieval with follow-up search capabilities and query normalization"
e699737 feat: enhance V11 adaptive evidence retrieval with follow-up search capabilities and query normalization
338d89f fix: harden V11 paired retrieval invariants
29e7ac5 feat: implement V11 adaptive evidence retrieval
59f6944 docs: clarify V11 paired retrieval methodology
6b3ef04 fix: standardize formatting in V11 documentation for improved clarity
aa870ef docs: preregister V11 adaptive evidence retrieval
```

### Accidental Additive Commit & Explicit Revert Provenance Note
The accidental additive commit `e699737c02b5edd8c77f8825e4eb17c91c8284e5` remains visible in Git history for complete historical transparency and audit trail provenance. It was explicitly reverted by `dcada6089d0c2734315bfcbd5e9fc28bd39fa14c` prior to the canonical inference candidate.
Verification of content equivalence:
```powershell
git diff 338d89fa75f00bbb2b6c06477082cf3184262d18 dcada6089d0c2734315bfcbd5e9fc28bd39fa14c --stat
```
**Result:** 0 files changed, 0 insertions, 0 deletions (content-identical to `338d89f`). History was not rewritten.

---

## 3. Preregistration & Frozen V10 Immutability

### Preregistration Artifact Immutability
Compared against the final preregistration methodology commit `59f6944ff92f94e6ef2122bb98a0079d021d411b`:
```powershell
git diff 59f6944ff92f94e6ef2122bb98a0079d021d411b HEAD -- `
  experiments/v11/DESIGN.md `
  experiments/v11/PRE_BENCHMARK.md `
  experiments/v11/config.json `
  experiments/v11/README.md `
  docs/V11_PRE_IMPLEMENTATION_AUDIT.md
```
**Result:** 0 differences (empty diff). All historical metadata, schemas, and preregistration files remain strictly immutable.

### Frozen V10 Immutability
Compared against the merge of Frozen V10 into main `0761b81330540cdc67fe2d662aef049bc87d9d8f`:
```powershell
git diff 0761b81330540cdc67fe2d662aef049bc87d9d8f HEAD -- experiments/v10
```
**Result:** 0 differences (empty diff).  
Freeze status in `experiments/v10/FROZEN.md` explicitly confirmed: `FROZEN_AND_PROMOTED_AS_V11_BASELINE`.

---

## 4. Single Scientific Intervention & Architecture

The V11 architectural intervention is strictly isolated to upstream evidence acquisition:
```text
Search 1
   ↓
File Context
   ↓
Planner v2 (evaluates evidence sufficiency; generates plan + optional follow-up query)
   ↓
optional Search 2 (executed at most once iff follow-up eligible)
   ↓
Plan-Guided Executor (Frozen V10 prompt templates)
   ↓
Frozen V9 Candidate Recovery
   ↓
Frozen V5 Verifier
   ↓
Frozen V6 Self-Evaluator
   ↓
Frozen V7 Targeted Repair
   ↓
Final Answer
```

**Negative Architectural Assertions Verified:**
- Zero Search 3.
- Zero replanning LLM generations.
- Zero retrieval loops.
- Zero Python retries.
- Zero repair retries.
- Zero extra verifier or self-evaluation calls.
- Zero post-repair verification.

---

## 5. V11 Type & Version Precedence

### Type Hierarchy
- `GAIAAdaptiveEvidenceAgent` inherits from `GAIAPlannerExecutorAgent` (Frozen V10).
- Class flags:
  ```python
  _is_v11: bool = True
  _is_v10: bool = True
  _is_v9: bool = False
  ```

### Detection Precedence in Evaluation Runners
In `evaluation/runner.py`, `evaluation/run_level.py`, and `evaluation/run_one.py`:
- `is_v11 = (project_version == "v11") or isinstance(agent, GAIAAdaptiveEvidenceAgent)`
- `is_v10 = ((project_version == "v10") or isinstance(agent, GAIAPlannerExecutorAgent)) and not is_v11`
- `is_v9 = ((project_version == "v9") or isinstance(agent, GAIAUpstreamCandidateRecoveryAgent)) and not is_v10 and not is_v11`
- Precedence is strictly: **V11 before V10 before V9**.

### Schema Versions
- V11 resolves to `schema_version = 9`.
- V10 resolves to `schema_version = 8`.
- V9 resolves to `schema_version = 7`.

---

## 6. Planner v2 Grammar & Safe Fallback Contract

- **Prompt Version:** `planner-v2-adaptive-evidence` in `prompts/adaptive_planner.py`.
- **Grammar Specification:**
  ```text
  MODE: <DIRECT | PYTHON>
  OBJECTIVE: <sentence>
  EVIDENCE_STATUS: <SUFFICIENT | INSUFFICIENT>
  EVIDENCE_NEEDED: <description>
  FOLLOWUP_QUERY: <NONE | targeted query>
  PLAN:
  1. <step 1>
  ...
  ANSWER_TYPE: <type>
  ```
- **Strict Parsing:**
  - If `EVIDENCE_STATUS == SUFFICIENT`, `FOLLOWUP_QUERY` must be `NONE`.
  - If `EVIDENCE_STATUS == INSUFFICIENT`, `FOLLOWUP_QUERY` must NOT be `NONE` or empty.
  - Plan steps must be 1 to 5 consecutively numbered steps.
- **Safe Fallback (`build_adaptive_fallback_plan`):**
  - Fallback produces `MODE: DIRECT`, `EVIDENCE_STATUS: SUFFICIENT`, `FOLLOWUP_QUERY: NONE`.
  - **Inviolable Invariant:** Planner fallback can never trigger Search 2.
  - Zero second planner generation.

---

## 7. Query Normalization & Anti-Selection-Bias Eligibility

### Normalization Contract (`normalize_followup_query`)
- Strips leading and trailing whitespace.
- Collapses internal whitespace sequences (`\s+`) to single space `' '`.
- Deterministically truncates to `<= 1500` characters.
- Preserves wrapping quotes for search operator syntax.
- Preserves casing (no `lower()`, no `casefold()`).
- No punctuation stripping or semantic alteration.

### Duplicate Detection
- Compares `norm_followup_query == norm_search1_query` using exact string equality.

### Cohort Eligibility (`followup_eligible`)
- `planner_requested_followup = bool(parse_success and plan_spec.evidence_status == "INSUFFICIENT")`
- `followup_eligible = bool(planner_requested_followup and followup_query_valid and not followup_query_duplicate)`
- **Anti-Selection-Bias Invariant:** Evaluated prior to Search 2 execution. Cohort eligibility is completely independent of:
  - Search 2 HTTP success/failure
  - Search 2 result count
  - New URL count
  - Candidate correctness

---

## 8. Search 2 Contract & Outcome Mutual Exclusion

- **Search Tool Budget:**
  - Search 1 <= 1
  - Search 2 <= 1 (executed only if `followup_eligible == True`)
  - Total Searches <= 2
- **Tavily Configuration:**
  - `search_depth = "basic"`
  - `max_results = 5`
  - `include_answer = False`
  - `include_raw_content = False`
  - `include_images = False`
  - `auto_parameters = False`
- **Zero Semantic Retries / Zero Search 3:**
  - Tavily key rotation handles credential failover only at the HTTP client level; does not constitute a new semantic search call.
- **Strict Mutual Exclusion:**
  - Exactly 3 mutually exclusive operational outcomes:
    1. **Usable Results:** `second_search_success = True`, `second_search_empty_results = False`, `result_count > 0`
    2. **Empty Results:** `second_search_success = False`, `second_search_empty_results = True`, `result_count == 0`
    3. **Provider Failure:** `second_search_success = False`, `second_search_empty_results = False`
  - Enforced by explicit assertion:
    ```python
    assert not (second_search_success and second_search_empty_results)
    ```

---

## 9. Canonical Retrieval Categories

Every canonical task is classified into exactly one of six mutually exclusive categories:
1. `SUFFICIENT_NON_TRIGGERED`
2. `INSUFFICIENT_DUPLICATE_QUERY`
3. `FOLLOWUP_ELIGIBLE_SEARCH2_SUCCESS`
4. `FOLLOWUP_ELIGIBLE_SEARCH2_PROVIDER_FAILURE`
5. `FOLLOWUP_ELIGIBLE_SEARCH2_EMPTY_RESULTS`
6. `PLANNER_FALLBACK`

---

## 10. Evidence Augmentation Contract & SHA-256 Hashing

In `_build_v11_executor_evidence`:
- Search 2 augments Search 1; it never replaces Search 1.
- Without usable Search 2:
  ```text
  === PRIMARY WEB SEARCH EVIDENCE ===
  <Search 1 Evidence>
  ```
- With usable Search 2:
  ```text
  === PRIMARY WEB SEARCH EVIDENCE ===
  <Search 1 Evidence>

  === FOLLOW-UP WEB SEARCH EVIDENCE ===
  <Search 2 Evidence>
  ```
- The exact string passed to the Executor is hashed in `combined_search_evidence_hash`.

---

## 11. Executor Preservation & Shared Execution Helper

- Prompts `prompts/executor.py` (`executor-direct-v1`, `executor-python-v1`) are 100% byte-identical to Frozen V10 (`314d0aecd01a1679a96d85256044c01c8b6c30ce`).
- Canonical V11 agent and paired ablation runner (Branch A and Branch B) call the single shared helper `_execute_v11_executor_from_plan`. No duplicate executor implementation exists.

---

## 12. Frozen Downstream AST Equivalence Audit

Programmatic comparison of AST structures against Frozen V10 (`314d0aecd01a1679a96d85256044c01c8b6c30ce`):
- `GAIAUpstreamCandidateRecoveryAgent`: **100% AST Identity**
- `GAIAVerificationAgent`: **100% AST Identity**
- `GAIASelfEvaluationAgent`: **100% AST Identity**
- `GAIATargetedRepairAgent`: **100% AST Identity**
  - Verified 0 references to `_is_v11` inside `GAIATargetedRepairAgent`.
  - Verified exactly 2 `max_v7_gens` assignments (`6 if getattr(self, "_is_v9", False) else 5` and `6 if (getattr(self, "_is_v9", False) or getattr(self, "_is_v10", False)) else 5`).
- Prompt files `candidate_recovery.py`, `verification.py`, `self_evaluation.py`, `targeted_repair.py`: **0 byte diff** against Frozen V10.

---

## 13. Frozen Tool Audit

Source files compared against Frozen V10 (`314d0aecd01a1679a96d85256044c01c8b6c30ce`):
- `tools/web_search.py`: **0 byte diff**
- `tools/file_tool.py`: **0 byte diff**
- `tools/python_tool.py`: **0 byte diff**

---

## 14. Generation Accounting & Tool Budgets

- Upstream LLM generation slots: strictly 2 (Planner v2 + Executor).
- Search 2 executes as a tool call (0 LLM generations).
- Downstream generation caps:
  - Candidate recovery: <= 1 generation
  - Verifier: <= 1 generation
  - Self-evaluator: <= 1 generation
  - Targeted repair: <= 1 generation
  - Total deployed generation cap:
    - Non-recovery path: <= 5 generations
    - Recovery-triggered path: <= 6 generations
- Tool call caps:
  - Search 1 <= 1
  - Search 2 <= 1
  - Total Searches <= 2
  - File Tool <= 1
  - Python Tool <= 1 (Branch A <= 1, Branch B <= 1 in paired harness)

---

## 15. Paired Retrieval Ablation Invariants

### Primary Paired Cohort & Sidecar Enrollment Ledger
In `evaluation/run_v11_paired.py`:
- Primary raw output file (`paired_retrieval_raw.jsonl`) contains **ONLY** follow-up eligible tasks (`followup_eligible == True`).
- Enrollment ledger (`paired_retrieval_raw.enrollment.jsonl`) records all scanned tasks with complete diagnostics.
- Non-eligible tasks never contaminate the primary raw ablation file.

### Crash-Safe Resume Cross-Artifact Validation
`validate_paired_resume_artifacts(raw_file, enrollment_file) -> set[str]` enforces:
1. Both files must exist if one exists (fails closed on orphan artifact).
2. No duplicate `task_id` in raw file or enrollment ledger.
3. Every record in raw file must have `followup_eligible == True`.
4. Every eligible record in ledger must have `paired_record_written == True` and exist in raw file.
5. Every raw record must have a matching eligible entry in the ledger with `paired_record_written == True`.
6. Non-eligible records in ledger must have `paired_record_written == False` and must NOT exist in raw file.
Any discrepancy raises `RuntimeError` immediately before any LLM or search call is executed.

### Write Order Inversion
- Raw record is written and flushed **first**.
- Enrollment ledger entry is written and flushed **second** with `paired_record_written = followup_eligible`.
- For non-eligible tasks, only the enrollment ledger entry is written.

### Shared Context & Execution Plan Hashing
- Both branches receive identical:
  - `shared_primary_search_hash`
  - `shared_file_hash`
  - `shared_plan_hash`
- `shared_plan_hash` is computed exclusively over execution fields (`mode`, `objective`, `evidence_needed`, `plan_steps`, `answer_type`) via `hash_canonical_execution_plan(plan_spec)`, completely ignoring retrieval control flags (`evidence_status`, `followup_query`, `is_fallback`, `validation_error`).

### Search 2 Single-Shot Execution
- Search 2 is executed **at most once total per paired task** (not once per branch).
- Results are provided to Branch B; Branch A receives Search 1 evidence only.

### Pre-Recovery Candidate Boundary
- Both branches terminate immediately after Executor candidate generation (`candidate_without_followup` and `candidate_with_followup`).
- Zero downstream stages (Candidate Recovery, Verifier, Self-Evaluator, Targeted Repair) execute inside the paired harness.

### Ground-Truth Firewall
- Verified by source inspection and unit test `test_scenario_27_zero_runtime_ground_truth`:
- `evaluation/run_v11_paired.py` contains zero references to ground truth, reference answers, correctness, scorers, or transition classifications.

### Official Post-Hoc Scorer & Metrics
- `evaluation/evaluate_v11_paired.py` evaluates candidate pairs using official `gaia_question_scorer`.
- Transition categories:
  - `RETRIEVAL_IMPROVEMENT`
  - `RETRIEVAL_REGRESSION`
  - `RETRIEVAL_STABLE_CORRECT`
  - `RETRIEVAL_STABLE_FAILURE`
- Primary Metric:
  $$\Delta_{\text{followup}} = N(\text{RETRIEVAL\_IMPROVEMENT}) - N(\text{RETRIEVAL\_REGRESSION})$$

### Zero-Cohort Contract & Provider-Failure Retention
- If primary raw file is empty, evaluator gracefully reports `cohort_size = 0`, $\Delta_{\text{followup}} = 0$, and `scientific_verdict = "NOT_TESTABLE"`.
- If Search 2 fails (provider failure or 0 results), eligible tasks are **retained** in the primary cohort with fallback to Search 1 evidence.

### Search Novelty Diagnostic
- Denominator: `second_search_attempted`.
- Provider failures and empty results count as 0 new URLs.
- Reports attempted count, count with new URLs, proportion, mean new URLs, median new URLs.

---

## 16. Static Source Hygiene

Source hygiene verification via AST parsing:
- Duplicate module-level function definitions: **0**
- Duplicate classes: **0**
- Adjacent duplicate assignments: **0**
- Duplicate dictionary keys: **0**
- Dead superseded V11 implementations: **0**
- Specific single-definition checks in `evaluation/run_v11_paired.py`:
  - `hash_shared_plan`: **1**
  - `run_paired_ablation`: **1**
  - `execute_plan_branch`: **1**
  - `validate_paired_resume_artifacts`: **1**

---

## 17. Test Suite Audit Results

| Suite | Command | Tests Run | Failures | Errors | Status |
|---|---|---|---|---|---|
| **V11 Suite** | `python -m unittest tests.test_v11_adaptive_evidence -v` | **47** | 0 | 0 | **PASS** |
| **Smoke Scenarios** | Included in V11 suite (Scenarios 1–28) | **28** | 0 | 0 | **PASS** |
| **Hardening Tests** | Included in V11 suite (Hardening 1–16) | **19** | 0 | 0 | **PASS** |
| **Frozen Regression** | `test_v10`, `test_v9`, `test_v7`, `test_v6`, `test_verifier`, `test_router` | **197** | 0 | 0 | **PASS** |
| **Multi-Key Infrastructure** | `test_llm`, `test_web_search` | **47** | 0 | 0 | **PASS** |
| **Full Repository** | `python -m unittest discover -s tests -p "test_*.py"` | **457** | 0 | 0 | **PASS** |
| **Bytecode Compilation** | `python -m compileall agent prompts tools evaluation tests` | All modules | 0 | 0 | **PASS** |
| **Whitespace / Diff Check** | `git diff --check` | Clean | 0 | 0 | **PASS** |

### Post-Test Audit Diff Lock
- `git status --porcelain`: Empty (working tree clean).
- HEAD verified: `02b368b030e2c86c2e534d6012149f819e8d136a`.

---

## 18. Canonical Execution Plan

The formal evaluation sequence must be executed in the following order:

### Phase A: Primary Follow-Up-Eligible Paired Retrieval Ablation
Must run with `--no_resume` to ensure a clean artifact baseline:
```powershell
python -m evaluation.run_v11_paired --no_resume
```

### Phase B: Post-Hoc Paired Scoring
```powershell
python -m evaluation.evaluate_v11_paired `
  --input_file experiments/v11/paired_retrieval_raw.jsonl `
  --summary_output experiments/v11/paired_summary.json `
  --detailed_output experiments/v11/paired_detailed.jsonl
```

### Phase C: Canonical V11 Level 1 Benchmark
```powershell
python -m evaluation.run_level --level 1 --version v11 --enforce-task-count
```

### Phase D: Canonical V11 Level 2 Benchmark
```powershell
python -m evaluation.run_level --level 2 --version v11 --enforce-task-count
```

### Phase E: Canonical V11 Level 3 Benchmark
```powershell
python -m evaluation.run_level --level 3 --version v11 --enforce-task-count
```

### Phase F: Official Scoring & Overall Summary
Generated automatically by the evaluation runner or summarized via the standard post-benchmark pipeline.

---

## 19. Canonical Artifact Plan & Provenance Requirements

### Expected Scientific Artifacts
- Primary Paired Ablation:
  - `experiments/v11/paired_retrieval_raw.jsonl`
  - `experiments/v11/paired_retrieval_raw.enrollment.jsonl`
  - `experiments/v11/paired_summary.json`
  - `experiments/v11/paired_detailed.jsonl`
- Canonical End-to-End Benchmark:
  - `experiments/v11/predictions_level_1.jsonl`
  - `experiments/v11/predictions_level_2.jsonl`
  - `experiments/v11/predictions_level_3.jsonl`
  - `experiments/v11/detailed_eval_level_1.jsonl`
  - `experiments/v11/detailed_eval_level_2.jsonl`
  - `experiments/v11/detailed_eval_level_3.jsonl`
  - `experiments/v11/summary_level_1.json`
  - `experiments/v11/summary_level_2.json`
  - `experiments/v11/summary_level_3.json`
  - `experiments/v11/overall_summary.json`

### Post-Benchmark Provenance Requirements
The post-benchmark report must document:
- Canonical inference commit: `02b368b030e2c86c2e534d6012149f819e8d136a`
- Audit commit
- SHA-256 hashes of all generated JSON and JSONL artifacts
- Complete task execution counts (53 Level 1, 86 Level 2, 26 Level 3 = 165 total)
- Zero code modifications between audit lock and benchmark completion

---

## 20. Methodological Caveats & Terminology

- **Terminology:** This investigation utilizes an **intervention-oriented paired estimate** within a **follow-up-eligible shared-plan paired retrieval ablation** measuring the **paired net difference** ($\Delta_{\text{followup}}$).
- **Stochasticity Acknowledgment:** While upstream context acquisition, file bytes, and structured planning are strictly identical across branches, Plan-Guided Executor generations operate under LLM non-determinism (temperature > 0 or model inference variance). Therefore, $\Delta_{\text{followup}}$ represents an intervention-oriented estimate rather than an isolated deterministic causal proof.

---

## 21. Binding Promotion Gates and Secondary Diagnostics

### Binding Promotion Gates

Promotion of V11 as the project's new scientific baseline requires satisfying **ALL** binding promotion gates listed below:

| Gate / Invariant | Metric | Requirement | Classification |
|---|---|---|---|
| **H1 (Primary Paired Gate)** | $\Delta_{\text{followup}}$ | $> 0$ ($N_{\text{RETRIEVAL\_IMPROVEMENT}} - N_{\text{RETRIEVAL\_REGRESSION}} > 0$) | Binding Promotion Gate |
| **H1 Feasibility Gate** | Follow-up Eligible Cohort Size | $N > 0$ (if $N = 0 \Rightarrow \text{NOT\_TESTABLE} \Rightarrow \text{cannot promote}$) | Binding Promotion Gate |
| **H2 (Canonical Accuracy Gate)** | Overall Benchmark Accuracy | $> 84 / 165$ ($> 50.91\%$) | Binding Promotion Gate |
| **Search Total Budget** | Web searches per deployed task | $\le 2$ | Binding Budget Invariant |
| **Search 2 Budget** | Second search calls per deployed task | $\le 1$ | Binding Budget Invariant |
| **Search 2 Eligibility Invariant** | Follow-up search invocation condition | Search 2 occurs ONLY after valid follow-up eligibility (`INSUFFICIENT` + valid non-duplicate query) | Binding Operational Invariant |
| **Planner Fallback Invariant** | Fallback plan search triggering | Planner fallback never triggers Search 2 (cleanly returns `SUFFICIENT` + `NONE`) | Binding Safety Invariant |
| **File Processing Budget** | File extractions per deployed task | $\le 1$ | Binding Budget Invariant |
| **Python Execution Budget** | Python executions per deployed task | $\le 1$ | Binding Budget Invariant |
| **Upstream LLM Slots** | Upstream generation calls | $== 2$ (Slot 1: Planner, Slot 2: Executor) | Binding Architectural Invariant |
| **Non-Recovery Generations** | Logical generation calls on nominal path | $\le 5$ | Binding Budget Invariant |
| **Recovery Generations** | Logical generation calls on recovery path | $\le 6$ | Binding Budget Invariant |
| **Downstream Integrity** | Downstream pipeline preservation | Frozen V10 pipeline (Recovery $\to$ Verifier $\to$ Self-Eval $\to$ Repair) preserved verbatim | Binding Architectural Invariant |
| **Operational Validity** | Complete run execution | Confirmed under preregistered invalidity definition (165 tasks evaluated, zero runtime scorer leakage, $\le 10\%$ unhandled infrastructure failures) | Binding Validity Invariant |

### Non-Binding Secondary Diagnostics (H3a–H3f)

The following metrics are evaluated and reported post-hoc to characterize the mechanism and behavior of adaptive evidence retrieval. They are strictly **Non-Binding Secondary Diagnostics / Secondary Hypotheses** and are **NOT** promotion gates.

| Diagnostic Hypothesis | Metric | Preregistered Direction / Benchmark | Classification |
|---|---|---|---|
| **H3a** | EVIDENCE Conditional Error Rate | $< 88.89\%$ (Frozen V10 reference: $32 / 36 = 88.89\%$) | Secondary Diagnostic Hypothesis (NOT a promotion gate) |
| **H3b** | Candidate Recovery Trigger Rate | $< 30.91\%$ (Frozen V10 reference: $51 / 165 = 30.91\%$) | Secondary Diagnostic Hypothesis (NOT a promotion gate) |
| **H3c** | Post-Recovery Reachability Floor | $\ge 95.0\%$ | Secondary Diagnostic Hypothesis (NOT a promotion gate) |
| **H3d** | Planner-v2 Parse Success Rate | $\ge 95.0\%$ | Secondary Diagnostic Hypothesis (NOT a promotion gate) |
| **H3e** | Follow-Up Retrieval Operational Tracking | Complete reporting across all 6 mutually exclusive categories | Descriptive Diagnostic (NOT a promotion gate) |
| **H3f** | Search Novelty Diagnostics | Proportion $\ge 1$ new URL, mean/median new URLs (attempted denominator) | Descriptive Diagnostic (NOT a promotion gate) |

### Decision Rules and Outcome Definitions

- **Governance Decision Rule:** Failure to meet H3a, H3b, H3c, or H3d does not by itself block V11 promotion. These hypotheses are secondary diagnostics and must be reported regardless of outcome. Promotion is governed only by the preregistered binding gates listed above.
- **Neutral Outcome Definition:** If $\Delta_{\text{followup}} \le 0$ or Canonical Correct $\le 84 / 165$, the scientific verdict is `NEUTRAL / NOT_SUPPORTED_AS_AN_IMPROVEMENT`. V11 will not be promoted as the project baseline. Secondary diagnostic success cannot override failure of H1 or H2, and secondary diagnostic failure cannot independently invalidate a V11 that passes all binding gates.
- **Operational Invalidity Definition:** A benchmark run is declared `INVALID` if and only if any preregistered invalidity condition occurs: incomplete validation split ($< 165$ tasks), ground-truth reference leakage or scorer execution at agent runtime, violation of search/generation budget invariants, post-audit runtime/prompt modifications, or widespread provider infrastructure collapse ($> 10\%$ unhandled task failures). Isolated bounded Search 2 provider failures (HTTP 429, timeout, empty results) fall back cleanly to Search 1 evidence and do **not** invalidate the run.

---

## 22. Audit Verdict

```text
================================================================================
V11 PRE-BENCHMARK AUDIT VERDICT: READY_FOR_CANONICAL_BENCHMARK
CANONICAL INFERENCE COMMIT:      02b368b030e2c86c2e534d6012149f819e8d136a
SCIENTIFIC PARENT:               FROZEN V10
SCHEMA:                          9
RUNTIME LOCKED:                  YES
================================================================================
```

