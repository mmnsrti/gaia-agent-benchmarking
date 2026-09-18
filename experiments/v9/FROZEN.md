# V9 — Upstream Candidate Recovery

**Status:** FROZEN
**Branch:** `v9-upstream-candidate-recovery`
**Scientific Parent:** Frozen V7 (`v7-targeted-repair`)
**Freeze Verdict:** `FROZEN_AND_PROMOTED_AS_V10_BASELINE`
**Canonical Inference Commit:** `6369f427c4479073a6ca06531bdfd43e47cd613f`
**Canonical Results Commit:** `0a411ec313e151fdfc67c546f5f1eda9a02dc9d7`
**Freeze Source Head:** `e007939651129a734c6a2c5d2b5dad5796a1156a`
**Model:** `gemini-3.5-flash-lite` (temperature=None, thinking_level="medium", max_output_tokens=2048)
**Evaluation Scope:** Full GAIA 2023 Validation Set (165 Tasks: 53 Level 1, 86 Level 2, 26 Level 3)
**Date:** September 2026

---

## 1. Research Definition & Capability Boundary

Version 9 (V9) investigates **Upstream Candidate Recovery** to resolve the central structural bottleneck identified in GAIA agent benchmarking: **candidate starvation**.

$$\text{V9} = \text{Frozen V7} + \text{one bounded text-only candidate-recovery generation for preregistered eligible no-candidate failure classes}$$

### Primary Research Question
> *When Frozen V7 fails to produce a non-empty upstream candidate due to an eligible generation or execution failure, can one bounded, text-only candidate recovery generation operating strictly on existing runtime evidence recover a valid candidate and produce a strictly positive net correctness gain ($\Delta = \text{improvements} - \text{regressions} > 0$) within the same task executions?*

### What V9 Does
- Inspects the upstream worker output at the candidate formulation boundary (`pre_recovery_candidate`).
- If the upstream candidate is non-empty, V9 **bypasses recovery entirely**, strictly preserving the candidate answer with $100.0\%$ fidelity.
- If the upstream candidate is empty (`""`), V9 evaluates whether the worker failure matches a deterministic, preregistered eligible failure class.
- For eligible failures, V9 executes at most **one bounded text-only recovery generation** (`candidate-recovery-v1`, `mode="NONE"`) prompting the model to extract or synthesize a final answer using strictly already-gathered runtime evidence.
- Parses the recovery output adhering strictly to the contract (`FINAL: <answer>`).
- If recovery succeeds, passes `post_recovery_candidate` downstream to the frozen V5 verifier, V6 self-evaluator, and V7 targeted repair pipeline.
- If recovery fails, times out, or produces malformed text, V9 cleanly falls back to `""`, allowing downstream stages to safely bypass without runtime exception.

### Allowed Recovery Inputs
The V9 recovery generation prompt receives strictly:
- Original task question
- Existing web-search evidence (gathered prior to router dispatch)
- Existing extracted file context / attachment metadata
- Raw worker response / output (including stdout/stderr or unformatted text from worker trace)
- Deterministic failure classification reason

### What V9 Does NOT Do
- Does **NOT** execute new web searches (`candidate_recovery_searches_added = 0`).
- Does **NOT** execute new Python code (`candidate_recovery_python_runs_added = 0`).
- Does **NOT** reread or re-extract attachment files.
- Does **NOT** use any tools or function calling during recovery (`mode = "NONE"`).
- Does **NOT** retry failed recovery generations (`recovery_generation_attempts \le 1`).
- Does **NOT** access ground-truth answers or official scorer modules during execution.
- Does **NOT** intervene on tasks where an upstream candidate was already produced.

---

## 2. Architecture & Execution Flow

```text
GAIA Question + Optional Attachment File
     ↓
ONE Tavily Search (Original Question as Query, Capped at 1,500 Chars, N ≤ 1)
     ↓
FileTool (Deterministic local extraction inherited from frozen V2–V8, N ≤ 1)
     ↓
Stage 1: Frozen Router Generation (`capability-router-v1`, mode="NONE", N ≤ 1)
     ↓
Stage 2: Route-Specific Worker Execution (`DIRECT` or `PYTHON`, N ≤ 1)
     ↓
Candidate Extraction Boundary (`pre_recovery_candidate`)
     │
     ├── [Upstream Candidate Non-Empty]
     │        ↓
     │   RECOVERY BYPASSED (Zero recovery LLM calls)
     │   post_recovery_candidate = pre_recovery_candidate (100.0% Preservation Invariant)
     │        ↓
     │   Proceed to Downstream Pipeline
     │
     └── [Upstream Candidate Empty `""`]
              ↓
         Deterministic Failure Taxonomy Classification (10 Mutually Exclusive Classes)
              │
              ├── [Ineligible Class: PROVIDER_ERROR / UNKNOWN_NO_CANDIDATE]
              │        ↓
              │   RECOVERY INELIGIBLE (Zero recovery LLM calls)
              │   post_recovery_candidate = ""
              │        ↓
              │   Downstream Safeguards Safely Bypass → Final Answer = ""
              │
              └── [Eligible Class: e.g. PYTHON_CODE_EXTRACTION_FAILURE, etc.]
                       ↓
                   Stage 2b: One-Shot Bounded Candidate Recovery (`candidate-recovery-v1`, mode="NONE", N ≤ 1)
                   (Inputs: Question, Web Evidence, File Context, Raw Worker Output, Failure Reason)
                       ↓
                   Deterministic Recovery Parser (`FINAL: <answer>`)
                       ├── [Parse Success] → post_recovery_candidate = Parsed Answer
                       └── [Parse Failure / Timeout] → post_recovery_candidate = "" (Clean Fallback)
                            ↓
Stage 3: Frozen One-Shot Verifier Generation (`answer-verifier-v1`, mode="NONE", N ≤ 1)
     ↓
Stage 4: Frozen Read-Only Self-Evaluator Generation (`self-evaluator-v1`, mode="NONE", N ≤ 1)
     ↓
Stage 5: Frozen Targeted Repair Generation (`targeted-repair-v1`, mode="NONE", N ≤ 1, if SUSPECT)
     ↓
Final Benchmark Answer
```

---

## 3. Deterministic Eligible Failure Taxonomy

V9 establishes a mutually exclusive, deterministic 10-class failure classifier evaluated prior to recovery invocation:

| # | Taxonomy Class | Recovery Eligibility | Trigger Condition |
| :-: | :--- | :---: | :--- |
| 1 | `PYTHON_OUTPUT_MISSING_MARKER` | **Eligible** | Python script executed (exit code 0), but stdout omitted `FINAL_ANSWER:`. |
| 2 | `PYTHON_EXECUTION_FAILURE` | **Eligible** | Python subprocess exited with non-zero code or uncaught exception. |
| 3 | `PYTHON_CODE_EXTRACTION_FAILURE` | **Eligible** | Python worker model emitted text without valid executable code blocks. |
| 4 | `MALFORMED_FUNCTION_CALL` | **Eligible** | Provider flagged response with finish reason `MALFORMED_FUNCTION_CALL`. |
| 5 | `FUNCTION_CALL_ONLY` | **Eligible** | Response contained function call parts but lacked final text part. |
| 6 | `THOUGHT_ONLY` | **Eligible** | Response contained model reasoning/thought parts without final text part. |
| 7 | `DIRECT_EXTRACTION_FAILURE` | **Eligible** | Direct worker generated text but lacked required `FINAL_ANSWER:` marker. |
| 8 | `EMPTY_RESPONSE` | **Eligible** | Last-resort fallback when model returned completely empty response text. |
| 9 | `PROVIDER_ERROR` | **Ineligible** | Transport/API failure (HTTP 429, timeout, network error). Bypassed. |
| 10 | `UNKNOWN_NO_CANDIDATE` | **Ineligible** | Ambiguous unclassified failure state. Bypassed. |

---

## 4. Canonical Benchmark Failure-Class Results

Breakdown of candidate recovery performance across the 10 failure classes on the GAIA 2023 Validation set (165 tasks):

| Failure Taxonomy Class | Observed | Eligible | Triggered | Succeeded | Cand Correct | Final Correct | Recovery Accuracy |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `PYTHON_CODE_EXTRACTION_FAILURE` | 80 | 80 | 80 | 75 | 21 | 22 | 28.00% (21/75) |
| `PYTHON_EXECUTION_FAILURE` | 6 | 6 | 6 | 6 | 4 | 5 | 66.67% (4/6) |
| `PYTHON_OUTPUT_MISSING_MARKER` | 3 | 3 | 3 | 3 | 1 | 1 | 33.33% (1/3) |
| `MALFORMED_FUNCTION_CALL` | 1 | 1 | 1 | 0 | 0 | 0 | N/A |
| `FUNCTION_CALL_ONLY` | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| `THOUGHT_ONLY` | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| `DIRECT_EXTRACTION_FAILURE` | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| `EMPTY_RESPONSE` | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| `PROVIDER_ERROR` | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| `UNKNOWN_NO_CANDIDATE` | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| *Non-Triggered (Upstream Candidate Present)* | 75 | 0 | 0 | 0 | N/A | 45 | N/A |
| **Total Benchmark** | **165** | **90** | **90** | **84** | **26** | **73** | **30.95% (26/84)** |

*Note on Recovery Accuracy*: For `MALFORMED_FUNCTION_CALL`, 0 recoveries succeeded out of 1 attempt; accuracy is mathematically undefined ($0/0$) and reported as `N/A`.

---

## 5. Strict Frozen Invariants

Across all 165 benchmark task traces, the following strict invariants were verified with zero violations:

1. **Generation Budget Cap**:
   - Triggered tasks: maximum observed logical generations = **6** (budget bound $\le 6$).
   - Non-triggered tasks: maximum observed logical generations = **5** (budget bound $\le 5$).
   - Generation violations across 165 tasks: **0**.
2. **Strict Tool Isolation**:
   - Candidate recovery added search calls: **0**.
   - Candidate recovery added Python executions: **0**.
   - Candidate recovery added file reads: **0**.
   - Maximum searches per task: **1**.
   - Maximum Python executions per task: **1**.
3. **Core Safety Invariant (Non-Triggered Preservation Rate)**:
   - Non-triggered tasks: **75 / 75** preserved identically at the recovery boundary (`post_recovery_candidate == pre_recovery_candidate`).
   - Boundary Preservation Rate: **100.00%**.
4. **Deterministic Fallback Integrity**:
   - The 6 failed recovery attempts preserved `post_recovery_candidate = ""` without raising exceptions or producing unhandled crashes.
5. **Transport vs. Scientific Separation**:
   - Multi-key API key rotation in `agent/llm.py` and `tools/web_search.py` is operational transport failover infrastructure, completely separated from scientific generation budgets. Zero semantic retries were permitted.
6. **Scorer Firewall**:
   - Ground-truth reference answers and the official GAIA scorer were completely inaccessible to the agent at runtime. All evaluations were executed strictly post-hoc.

---

## 6. Canonical Benchmark Headline Results

Evaluated on the full GAIA 2023 Validation Set (165 tasks across Levels 1, 2, and 3):

| Level | Tasks | Completed Tasks | Completion Rate | Correct Tasks | Accuracy | Request Failures |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 53 | 52 | 98.11% | 33 | **62.26%** | 0 |
| **Level 2** | 86 | 85 | 98.84% | 34 | **39.53%** | 0 |
| **Level 3** | 26 | 26 | 100.00% | 6 | **23.08%** | 0 |
| **Overall** | **165** | **163** | **98.79%** | **73** | **44.24%** | **0** |

- **Structural Benchmark Coverage**: **165 / 165 official task IDs (100.0% structurally recorded)**, 165 unique IDs, 0 duplicates.
- **Pipeline Completion Metric**: **163 / 165 tasks (98.79%)** completed without parse fallback.

---

## 7. Primary Scientific Measurement: Within-Run Paired Intervention

In accordance with Section 3 and Section 27 of `experiments/v9/PRE_BENCHMARK.md`, the primary scientific evaluation of V9 is the **within-run paired intervention measurement**:
- Non-triggered tasks (75 tasks): Frozen V7 within-run state = `final_answer` (preserved identically at recovery boundary).
- Triggered tasks (90 tasks): Without recovery, Frozen V7 produced an empty upstream candidate, causing downstream stages to bypass; baseline state = `""` (evaluated as incorrect).

### Paired Within-Run Transition Matrix (165 Tasks)

| Transition Name | Definition | Level 1 (N=53) | Level 2 (N=86) | Level 3 (N=26) | Overall (N=165) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **`IMPROVEMENT` ($0 \to 1$)** | Baseline wrong $\to$ V9 final correct | 11 | 14 | 3 | **28 (16.97%)** |
| **`REGRESSION` ($1 \to 0$)** | Baseline correct $\to$ V9 final wrong | 0 | 0 | 0 | **0 (0.00%)** |
| **`STABLE_CORRECT` ($1 \to 1$)** | Baseline correct $\to$ V9 final correct | 22 | 20 | 3 | **45 (27.27%)** |
| **`STABLE_FAILURE` ($0 \to 0$)** | Baseline wrong $\to$ V9 final wrong | 20 | 52 | 20 | **92 (55.76%)** |
| **Total** | | **53** | **86** | **26** | **165 (100.0%)** |

$$\Delta_{\text{within-run}} = \text{Improvements} - \text{Regressions} = 28 - 0 = \mathbf{+28 \text{ tasks}}$$
$$\Delta_{\text{pp}} = \frac{+28}{165} \times 100 = \mathbf{+16.97 \text{ percentage points}}$$

- **Pre-Intervention Baseline Correct**: 45 / 165 (27.27%)
- **Post-Intervention V9 Final Correct**: 73 / 165 (44.24%)
- **Level 1 Net Gain**: $+11$ tasks ($41.51\% \to 62.26\%$, $+20.75$ pp)
- **Level 2 Net Gain**: $+14$ tasks ($23.26\% \to 39.53\%$, $+16.28$ pp)
- **Level 3 Net Gain**: $+3$ tasks ($11.54\% \to 23.08\%$, $+11.54$ pp)

> [!NOTE]
> **Methodological Note on Within-Run Measurement**:
> The within-run paired intervention measurement avoids the separate-run sampling divergence that affects the matched V7 comparison and is the preregistered primary decision metric. It should not be described as a perfect causal estimate or as eliminating all sources of uncertainty.

---

## 8. Candidate Reachability Expansion

- **Pre-Recovery Non-Empty Candidates**: 75 / 165 (45.45%)
- **Post-Recovery Non-Empty Candidates**: 159 / 165 (96.36%)
- **Net Reachability Expansion**: **+84 tasks (+50.91 percentage points)**
- **Triggered Recoveries**: 90 / 165 (54.55%)
- **Successful Recovery Parses**: 84 / 90 (**93.33%**)
- **Clean Recovery Failures**: 6 / 90 (6.67%)
- **Recovered Candidate Accuracy (Official Scorer)**: **26 / 84 (30.95%)**

---

## 9. Downstream Safeguard Interactions (Recovered Cohort, N=84)

Once recovered, candidates entered the downstream pipeline: V5 verifier $\to$ V6 self-evaluator $\to$ V7 targeted repair.

| Transition Metric | Count | Fraction | Architectural Impact |
| :--- | :---: | :---: | :--- |
| **`RECOVERY_CORRECT_FINAL_CORRECT`** | **25** | **29.76%** | Downstream safeguards preserved the correct recovered candidate. |
| **`RECOVERY_CORRECT_FINAL_WRONG`** | **1** | **1.19%** | Downstream verifier altered a correct candidate (L2 `4d51c4bf...`). |
| **`RECOVERY_WRONG_FINAL_CORRECT`** | **3** | **3.57%** | Downstream safeguards (V5/V7) rescued an imperfect recovered candidate. |
| **`RECOVERY_WRONG_FINAL_WRONG`** | **55** | **65.48%** | Recovered candidate was incorrect and remained incorrect throughout pipeline. |
| **Total Recovered Cohort** | **84** | **100.00%** | Full closure of recovered cohort. |

- Net downstream modification on recovered cohort: $+3$ rescues vs $-1$ harm = **$+2$ tasks**.
- Combined with the 45 baseline correct non-triggered tasks: $45 + 28 = \mathbf{73 \text{ final correct tasks}}$.

---

## 10. Contemporaneous Matched Frozen V7 Control Comparison

A matched control run of Frozen V7 was executed contemporaneously from the exact same inference commit (`6369f427c4479073a6ca06531bdfd43e47cd613f`):

| Level | Matched V7 Accuracy | Canonical V9 Accuracy | Observational Delta |
| :---: | :---: | :---: | :---: |
| **Level 1** | 25 / 53 (47.17%) | 33 / 53 (62.26%) | +8 tasks (+15.09 pp) |
| **Level 2** | 23 / 86 (26.74%) | 34 / 86 (39.53%) | +11 tasks (+12.79 pp) |
| **Level 3** | 3 / 26 (11.54%) | 6 / 26 (23.08%) | +3 tasks (+11.54 pp) |
| **Overall** | **51 / 165 (30.91%)** | **73 / 165 (44.24%)** | **+22 tasks (+13.33 pp)** |

### Cross-Run 2x2 Contingency Matrix (165 Tasks)

| Contingency Cell | Task Count | Percentage | Interpretation |
| :--- | :---: | :---: | :--- |
| **Both Correct** | 43 | 26.06% | Robustly solved across both runs |
| **Both Wrong** | 84 | 50.91% | Difficult tasks unaddressed by either run |
| **Matched V7 Wrong $\to$ V9 Correct** | 30 | 18.18% | Solved in V9 run |
| **Matched V7 Correct $\to$ V9 Wrong** | 8 | 4.85% | Stochastic divergence in upstream sampling |
| **Total** | **165** | **100.00%** | Full contingency closure |

> [!IMPORTANT]
> **Methodological Status**:
> The matched Frozen V7 comparison is based on a separate stochastic execution and therefore remains strictly **secondary, observational, and non-causal**. Run-to-run sampling variance in routing and search formulation causes separate executions to diverge. The primary basis for promotion is the within-run paired intervention measurement (+28 tasks, +16.97 pp).

---

## 11. Scientific Limitations

1. **Recovery Precision (30.95%)**:
   While recovery successfully emitted candidates for 84 tasks, only 26 were directly correct. Most recovered candidates (58 / 84) were incorrect, indicating that candidate recovery primarily creates an answer candidate rather than resolving underlying reasoning or evidence deficiencies.
2. **Dominance of Python Extraction Brittleness**:
   80 of the 90 triggered recoveries (88.89%) stemmed from `PYTHON_CODE_EXTRACTION_FAILURE`, where Gemini Flash-Lite emitted non-fenced python code. Part of V9's measured gain represents compensation for upstream worker formatting brittleness.
3. **Downstream Safeguard Harm Risk**:
   In 1 case (L2 `4d51c4bf...`), an accurate recovered candidate was degraded to an incorrect answer by the downstream V5 verifier. Downstream safeguards are not perfectly conservative on recovered candidates.
4. **Residual Starvation (6 Tasks)**:
   Candidate recovery failed on 6 tasks (4 unexpected finish reasons, 1 missing marker, 1 malformed call), leaving them starved.
5. **Matched-Control Stochasticity**:
   Separate-run cross comparisons diverge upstream due to LLM sampling stochasticity, reinforcing the necessity of within-run paired intervention designs.

---

## 12. Final Freeze Verdict

```text
================================================================================
V9 FREEZE VERDICT:        FROZEN_AND_PROMOTED_AS_V10_BASELINE
RESEARCH VERDICT:         SUPPORTED_AS_AN_IMPROVEMENT
PROMOTION RECOMMENDATION: PROMOTE_V9_AS_V10_BASELINE
================================================================================
```

### Rationale
V9 has met every preregistered promotion condition established in `experiments/v9/PRE_BENCHMARK.md`:
1. Within-run net correctness delta $> 0$ (+28 tasks, +16.97 pp) — **PASS**.
2. Non-triggered boundary preservation rate $== 100.0\%$ (75 / 75) — **PASS**.
3. Zero added recovery tools (0 searches, 0 Python runs, 0 file reads) — **PASS**.
4. Generation budgets respected (maximum 6 logical generations) — **PASS**.
5. Operational validity confirmed (165 / 165 tasks structurally completed, zero collapse) — **PASS**.

Version 9 is formally frozen and promoted as the scientific parent baseline for Version 10. Future iterations must not alter V9 runtime code, prompts, canonical benchmark artifacts, or frozen scientific conclusions.

---

## 13. V10 Scientific Baseline Handoff

```text
Scientific Parent for V10: Frozen V9 (v9-upstream-candidate-recovery)
Inference Baseline Commit: 6369f427c4479073a6ca06531bdfd43e47cd613f
```

- Any future V10 experiment must begin from **Frozen V9** behavior and introduce a separately preregistered, bounded intervention.
- The V10 research question, capability intervention, and preregistration are **NOT** defined in this document and must be established in a dedicated preregistration phase.
- Baseline regression against Frozen V9 requires preserving the candidate recovery stage and its 100.0% non-triggered preservation invariant.
