# V8 — Bounded Active Evidence Verification

**Status:** FROZEN<br>
**Branch:** `v8-active-evidence-verification`<br>
**Parent Baseline:** Frozen V7 (`v7-targeted-repair`)<br>
**Freeze Verdict:** FROZEN_WITH_DOCUMENTED_NEGATIVE_RESULT<br>
**Date:** September 2026

---

## 1. Research Definition & Capability Boundary

```text
V8 = Frozen V7 + exactly one bounded active web evidence verification opportunity for valid SUSPECT + EVIDENCE candidates
```

### Research Question
> *When Frozen V7 reaches a non-empty answer whose upstream V6 diagnostic is a valid SUSPECT with RISK_TYPE: EVIDENCE, does one additional bounded web retrieval followed by one bounded evidence-based adjudication correct more erroneous answers than it harms correct answers?*

### What V8 Does
- Fully executes the frozen upstream V7 pipeline (`Question → Search → FileTool → Router → Worker → V5 Verifier → V6 Evaluator → V7 Targeted Repair`).
- Inspects the resulting Frozen V7 candidate answer (`pre_active_verification_answer`) and upstream diagnostic signals.
- Activates active evidence verification if and only if:
  1. The Frozen V7 final answer is non-empty and non-whitespace.
  2. The upstream V6 self-evaluator succeeded (`self_eval_success == True`).
  3. The upstream assessment is `SUSPECT`.
  4. The diagnosed risk type is `EVIDENCE`.
- Deterministically formulates an active verification search query by appending the candidate answer to the question:
  ```text
  <question>

  Candidate answer to independently verify:
  <candidate_answer>
  ```
- Submits at most one search to Tavily (`max_results=5`, capped at 1,500 characters, zero retries).
- If usable evidence is retrieved, invokes an active evidence adjudicator with an explicit information firewall:
  - Valid outputs:
    - Exactly 1 line:
      ```text
      VERIFICATION_ACTION: KEEP
      ```
    - Exactly 2 lines:
      ```text
      VERIFICATION_ACTION: REPLACE
      FINAL: <replacement answer>
      ```
- Reverts safely to `pre_active_verification_answer` upon zero search results, search timeout, provider API failure, schema violation, or empty replacement.

### What V8 Does NOT Do
- Does **NOT** activate on empty candidate answers or unflagged (`PASS`) candidates.
- Does **NOT** activate on non-`EVIDENCE` risks (e.g. `REASONING`, `CALCULATION`, `FORMAT`, `EXECUTION`).
- Does **NOT** rewrite queries using an LLM or multi-turn query planner.
- Does **NOT** perform multi-hop web retrieval (`active_searches <= 1`).
- Does **NOT** execute Python code (`v8_python = 0`).
- Does **NOT** reread or re-extract attachment files (`v8_file_reread = 0`).
- Does **NOT** use tool loops, iterative reflection, or native function calling (`mode = "NONE"`).
- Does **NOT** attempt candidate starvation recovery.

---

## 2. Execution Flow & Architecture

```text
GAIA Question + Optional Attachment File
     ↓
ONE Tavily Search (Original Question as Query, Capped at 1,500 Chars, N ≤ 1)
     ↓
FileTool (Deterministic local extraction inherited from frozen V2–V7, N ≤ 1)
     ↓
Stage 1: Frozen Router Generation (`capability-router-v1`, mode="NONE", N ≤ 1)
     ↓
Stage 2: Route-Specific Worker Dispatch (`router-direct-worker-v1` or `router-python-worker-v1`, N ≤ 1)
     ↓
Candidate Answer Extraction (`pre_verification_answer`)
     ↓
Stage 3: Frozen One-Shot Verifier Generation (`answer-verifier-v1`, mode="NONE", N ≤ 1)
     ↓
Post-Verification Candidate Answer (`pre_repair_answer`)
     ↓
Stage 4: Frozen Read-Only Self-Evaluator Generation (`self-evaluator-v1`, mode="NONE", N ≤ 1)
     ↓
Stage 5: Frozen SUSPECT-Triggered Targeted Repair (`targeted-repair-v1`, mode="NONE", N ≤ 1)
     ↓
Frozen V7 Final Answer (`pre_active_verification_answer`)
     │
     ├── [Empty Candidate / Assessment != SUSPECT / Risk != EVIDENCE]
     │        ↓
     │   Active Verification Bypassed (0 search, 0 LLM calls)
     │        ↓
     │   Final Answer = pre_active_verification_answer
     │
     └── [Candidate Present AND Assessment == SUSPECT AND Risk == EVIDENCE]
              ↓
         Deterministic Query Formulation:
         "<question>\n\nCandidate answer to independently verify:\n<candidate_answer>"
              ↓
         Stage 6a: One Bounded Tavily Search (N ≤ 1, max_results=5, timeout=15s)
              │
              ├── [Search Failed / Timeout / 0 Results]
              │        ↓
              │   Adjudication Skipped (0 LLM calls)
              │   Final Answer = pre_active_verification_answer (Preserved verbatim)
              │
              └── [Usable Evidence Retrieved]
                       ↓
                  Stage 6b: One Bounded Adjudication Generation (`active-evidence-verification-v1`, N ≤ 1)
                  (Inputs: Question, Candidate Answer, Diagnostic Signal, Evidence, Context, Attachment)
                       ↓
                  Strict Parser (`parse_active_evidence_verification_result`)
                       ├── [VERIFICATION_ACTION: KEEP] → Final Answer = pre_active_verification_answer
                       ├── [VERIFICATION_ACTION: REPLACE\nFINAL: <ans>] → Final Answer = <replacement>
                       └── [Malformed / Timeout / Exception] → Final Answer = pre_active_verification_answer
```

---

## 3. Strict Frozen Invariants

1. **Sequential Execution Order**: Frozen V7 executes to completion before V8 begins.
2. **Trigger Gate**: Requires non-empty candidate, `self_eval_success == True`, `self_eval_assessment == "SUSPECT"`, and `self_eval_risk_type == "EVIDENCE"`.
3. **Bounded Active Retrieval**: At most 1 external web search per task (`active_verification_search_attempted <= 1`).
4. **Bounded Active Adjudication**: At most 1 logical LLM generation per task (`active_verification_adjudication_attempted <= 1`).
5. **Total Search Budget**: At most 2 search calls across the entire task lifetime (`search_call_count <= 2`).
6. **Total LLM Generation Budget**: At most 6 logical standard LLM generations per task (`llm_generation_attempts <= 6`).
7. **No Auxiliary Capabilities**: Exactly 0 Python calls and 0 file rereads during active verification.
8. **Non-Destructive Failure Preservation**: Any search failure, empty result set, adjudication provider failure, or parser rejection preserves `pre_active_verification_answer` identically.
9. **Boundary Demarcation**: Candidate boundaries remain `pre_active_verification_answer` and `post_active_verification_answer`.

---

## 4. Canonical Benchmark Results

Canonical evaluation on the complete official GAIA 2023 Validation dataset (165 tasks):

| Level | Total Tasks | Completed Tasks | Correct Tasks | Accuracy |
| :--- | :---: | :---: | :---: | :---: |
| **Level 1** | 53 | 34 (64.1%) | 20 | **37.74%** |
| **Level 2** | 86 | 44 (51.2%) | 25 | **29.07%** |
| **Level 3** | 26 | 9 (34.6%) | 3 | **11.54%** |
| **Overall Total** | **165** | **87 (52.7%)** | **48** | **29.09%** |

---

## 5. Primary Within-Run Intervention Result

The primary scientific measurement of V8 evaluates within-run transitions comparing the candidate answer entering active verification with the final answer inside the exact same execution trace:

| Metric | Level 1 (53) | Level 2 (86) | Level 3 (26) | Overall Total (165) |
| :--- | :---: | :---: | :---: | :---: |
| **Pre-Active Correct** | 20 / 53 (37.74%) | 25 / 86 (29.07%) | 4 / 26 (15.38%) | **49 / 165 (29.70%)** |
| **Post-Active Correct** | 20 / 53 (37.74%) | 25 / 86 (29.07%) | 3 / 26 (11.54%) | **48 / 165 (29.09%)** |
| **Improvements ($0 \rightarrow 1$)** | 0 | 0 | 0 | **0** |
| **Regressions ($1 \rightarrow 0$)** | 0 | 0 | 1 | **1** |
| **Stable Correct ($1 \rightarrow 1$)** | 0 | 1 | 0 | **1** |
| **Stable Failure ($0 \rightarrow 0$)** | 6 | 5 | 2 | **13** |
| **Triggered Interventions** | 6 | 6 | 3 | **15** |
| **Not Triggered (Bypassed)** | 47 | 80 | 23 | **150** |
| **Net Active Verification Delta** | **+0** | **+0** | **-1** | **-1 task (-0.61 pp)** |
| **Correction Rate** | 0.0% | 0.0% | 0.0% | **0.0%** |
| **Harm Rate** | 0.0% | 0.0% | 100.0% | **50.0%** |

### Arithmetic Invariants
- $\text{Triggered} = 0 + 1 + 1 + 13 = 15$.
- $\text{Post-Active Correct (48)} - \text{Pre-Active Correct (49)} = 0 - 1 = -1$.

---

## 6. Trigger / Retrieval / Adjudication Funnel

| Funnel Stage | Count | % of Total (165) | Conversion Rate |
| :--- | :---: | :---: | :---: |
| **Total Tasks** | 165 | 100.0% | — |
| **Non-Empty Frozen V7 Answers** | 83 | 50.3% | 50.3% |
| **Self-Eval Evaluated** | 83 | 50.3% | 100.0% |
| **Flagged `SUSPECT`** | 18 | 10.9% | 21.7% of evaluated |
| **`SUSPECT` with `EVIDENCE` Risk** | 15 | 9.1% | 83.3% of suspects |
| **Active Verification Eligible** | 15 | 9.1% | 100.0% |
| **Active Verification Triggered** | 15 | 9.1% | 100.0% |
| **Active Search Attempted** | 15 | 9.1% | 100.0% |
| **Active Search Usable** | 14 | 8.5% | 93.3% of searches |
| **Adjudications Attempted** | 14 | 8.5% | 100.0% of usable |
| **Valid Adjudications** | 14 | 8.5% | 100.0% |
| **Action `KEEP`** | 13 | 7.9% | 92.9% of adjudications |
| **Action `REPLACE`** | 1 | 0.6% | 7.1% of adjudications |
| **Answers Changed** | 1 | 0.6% | 7.1% of adjudications |

---

## 7. Single Regression Forensic Case

In Level 3, Task `00d579ea-0889-4fd9-a771-2c8d79835c8d`:
- **Question**: *"Assuming scientists in the famous youtube video The Thinking Machine (Artificial Intelligence) 1961 MIT..."*
- **Ground Truth**: `"Claude Shannon"`
- **Candidate Answer entering V8**: `"Claude Shannon"` (Correct)
- **Upstream Diagnostic**: V6 self-evaluator flagged the candidate as `SUSPECT` with `EVIDENCE` risk.
- **Active Search**: Formulated query retrieved text discussing multiple MIT participants in the 1961 documentary, prominently featuring both Claude Shannon and Jerome Wiesner.
- **Adjudication**: The adjudicator emitted `VERIFICATION_ACTION: REPLACE` with `FINAL: Jerome Wiesner`.
- **Outcome**: Converted a correct candidate into an incorrect answer ($1 \rightarrow 0$), producing the single regression observed across the benchmark.

---

## 8. V6 Diagnostic Metrics

Anchored strictly to `pre_repair_correct` (the exact candidate evaluated by V6):

| Metric | Value |
| :--- | :---: |
| **Evaluated Candidates ($N$)** | 83 |
| **True Positives (SUSPECT & Incorrect)** | 15 |
| **False Positives (SUSPECT & Correct)** | 3 |
| **False Negatives (PASS & Incorrect)** | 18 |
| **True Negatives (PASS & Correct)** | 47 |
| **Precision** | **83.33%** |
| **Recall** | **45.45%** |
| **F1 Score** | **58.82%** |

---

## 9. Candidate Starvation & Upstream Reachability

- **Reachable Candidates**: 83 / 165 tasks (50.3%).
- **Candidate Starvation**: 82 / 165 tasks (49.7%) failed to produce any candidate answer from upstream worker/router stages due to model `MALFORMED_FUNCTION_CALL` or empty responses.
- **Structural Bottleneck**: Because V8 is a post-answer verification stage, tasks lacking candidate answers are structurally unreachable. Candidate starvation is an upstream generation bottleneck that cannot be solved by post-answer verification and must be addressed in a separate upstream capability version.

---

## 10. Matched Frozen V7 Observational Comparison

| Split / Level | Canonical V8 Accuracy | Matched Frozen V7 Accuracy | Observational Delta |
| :--- | :---: | :---: | :---: |
| **Level 1** | 20 / 53 (37.74%) | 21 / 53 (39.62%) | -1 task (-1.88 pp) |
| **Level 2** | 25 / 86 (29.07%) | 21 / 86 (24.42%) | +4 tasks (+4.65 pp) |
| **Level 3** | 3 / 26 (11.54%) | 3 / 26 (11.54%) | +0 tasks (+0.00 pp) |
| **Overall** | **48 / 165 (29.09%)** | **45 / 165 (27.27%)** | **+3 tasks (+1.82 pp)** |

> **Methodological Classification**: In accordance with preregistered protocol, the cross-run difference (+1.82 pp) is strictly **observational and non-causal** due to stochastic LLM sampling variance across separate runs. The primary within-run intervention effect of V8 was **-1 task (-0.61 pp)**.

---

## 11. Provider Incidents & Quarantined Runs

1. **Quarantined Collapsed Runs**:
   - `experiments/v8_invalid_l2_provider_collapse/`
   - `experiments/v8_invalid_l3_provider_collapse/`
   - `experiments/v8_matched_v7_invalid_l2_provider_collapse/`
   - `experiments/v8_matched_v7_invalid_l3_provider_collapse/`
   - `experiments/quarantine/v8_matched_v7_invalid_l2_pre_rerun_predictions.jsonl`
2. **Infrastructure Remediation**:
   - Implemented process-wide automatic multi-key discovery and rotation upon 429 quota exhaustion.
   - Added conservative provider collapse guards in `evaluation/run_level.py` ensuring that any provider collapse halts execution without logging partial invalid records.
3. **Canonical Replacement Selection Rule**:
   - All invalid runs were excluded based on infrastructure/provider invalidity, never benchmark score. The first operationally healthy run was accepted as canonical.

---

## 12. Source / Execution Provenance

- **Canonical V8 L1 Commit**: `39d216200de831e39cccc610a31f190ac6171a83` (`git_dirty=False`)
- **Canonical V8 L2 Commit**: `39d216200de831e39cccc610a31f190ac6171a83` (`git_dirty=False`)
- **Canonical V8 L3 Commit**: `d0c770aa8976b5043228762257c27b179ac5aafe` (`git_dirty=False`)
- **Matched V7 L1 Commit**: `39d216200de831e39cccc610a31f190ac6171a83` (`git_dirty=False`)
- **Matched V7 L2 Commit**: `8ae57c21762cfc91f6cc22e73550294dde41429f`
- **Matched V7 L3 Commit**: `d0c770aa8976b5043228762257c27b179ac5aafe` (`git_dirty=False`)
- **Initial Freeze Commit**: `467a3a16ad3d8fb217f2ba4a706852bb33f9586a`
  - Subsequent documentation-only cleanup commits do not alter the frozen runtime, benchmark artifacts, or scientific result.

---

## 13. Canonical Artifact Integrity

All 165 task IDs are unique and identical across V8 and Matched V7. Zero corrupted records. All local artifacts are hashed in `experiments/v8/ARTIFACT_MANIFEST.sha256` and `experiments/v8_matched_v7/ARTIFACT_MANIFEST.sha256`.

---

## 14. Scientific Limitations

1. **Adjudication Conservatism**: The adjudicator chose `KEEP` in 92.9% of usable evidence cases, resulting in zero corrections on incorrect candidates.
2. **Evidence Ambiguity Risk**: Single-turn web search on complex GAIA tasks often retrieves competing entities, which can mislead the adjudicator into replacing correct candidates.
3. **Upstream Starvation Ceiling**: Nearly half of all benchmark tasks failed prior to verification, severely restricting the addressable error space.

---

## 15. Research Conclusion

Bounded active evidence verification did not produce a positive within-run intervention effect on the GAIA benchmark under this experimental configuration. Across 15 triggered interventions, it yielded 0 improvements, 1 regression, and a net change of -1 task (-0.61 pp).

---

## 16. Freeze Verdict & Governance

```text
Research Verdict:
REJECTED_AS_AN_IMPROVEMENT

Freeze Verdict:
FROZEN_WITH_DOCUMENTED_NEGATIVE_RESULT

Promotion Verdict:
DO_NOT_PROMOTE

Successor Baseline:
Frozen V7
```

### Rule of Immutability
V8 is frozen as an immutable negative research result. The following are permanently frozen under V8:
- V8 architecture and trigger rule
- V8 deterministic query formulation
- V8 active evidence verification prompt and parser
- V8 generation and search budgets
- Canonical predictions, evaluations, summaries, and manifests

Future experimentation must not modify V8. Any subsequent capability exploration belongs to V9+.

---

## 17. Handoff to Future Work

Because V8 demonstrated a negative within-run intervention effect, **V8 is NOT promoted** as the baseline architecture for successor experiments.

The recommended parent architecture for the next experiment is:

```text
Frozen V7 (v7-targeted-repair)
```

The primary bottleneck identified across V4–V8 is **candidate starvation** (49.7% empty responses from upstream router/worker failures). Future research should target upstream candidate generation and recovery rather than additional post-answer verification.

---

## Immutable Freeze Manifest

```text
Version:
v8

Research label:
bounded active evidence verification

Parent:
Frozen V7

Canonical final accuracy:
48 / 165
29.09%

Pre-active correct:
49 / 165

Post-active correct:
48 / 165

Triggered:
15

Improvements:
0

Regressions:
1

Net within-run intervention delta:
-1 task
-0.61 pp

Matched Frozen V7:
45 / 165
27.27%
observational / non-causal

Research verdict:
REJECTED_AS_AN_IMPROVEMENT

Freeze Verdict:
FROZEN_WITH_DOCUMENTED_NEGATIVE_RESULT

Promotion:
NO

Successor baseline:
Frozen V7

Dataset:
GAIA 2023 Validation
165 tasks

Official scorer:
9f133d71362e77b3539f1514f31b9c101a545fec

Status:
FROZEN
```

