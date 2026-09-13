# V7 — SUSPECT-Triggered Targeted Repair

**Status:** FROZEN<br>
**Branch:** `v7-targeted-repair`<br>
**Parent Baseline:** Frozen V6 (`v6-self-evaluation-agent`)<br>
**Freeze Verdict:** FROZEN_WITH_DOCUMENTED_LIMITATIONS<br>
**Date:** September 2026

---

## 1. Research Definition & Capability Boundary

```text
V7 = Frozen V6 + one bounded text-only targeted repair generation triggered exclusively by valid SUSPECT
```

### Research Question
> *Can one bounded targeted repair generation, triggered only by a valid V6 SUSPECT assessment, correct more erroneous answers than it harms correct answers, without additional tools, new evidence retrieval, or retries?*

### What V7 Does
- Receives an already-finalized V6 candidate answer and diagnostic assessment.
- Activates targeted repair if and only if the self-evaluation assessment is a valid `SUSPECT` on a non-empty candidate answer.
- Operates strictly on existing evidence and compact status context.
- Selects between `ACTION: KEEP` (retain original candidate verbatim) and `ACTION: REPLACE` (substitute with a revised answer).
- Preserves the original pre-repair answer identically upon any repair parser failure, timeout, or exception.

### What V7 Does NOT Do
- Does **NOT** perform new web searches (`search = false`).
- Does **NOT** execute new Python code (`python = false`).
- Does **NOT** reread or extract files (`file_reread = false`).
- Does **NOT** use any tools or function calling (`mode = "NONE"`).
- Does **NOT** retry failed repair generations (`provider_retries = 0`).
- Does **NOT** execute post-repair verification (`post_repair_verification = false`).
- Does **NOT** execute post-repair self-evaluation (`post_repair_self_evaluation = false`).
- Does **NOT** access ground-truth reference labels or official scorer internals at runtime.
- Does **NOT** repair empty candidate answers or unflagged (`PASS`) candidates.

---

## 2. Execution Flow & Architecture

```text
GAIA Question + Optional Attachment File
     ↓
ONE Tavily Search (Original Question as Query, Capped at 1,500 Chars, N ≤ 1)
     ↓
FileTool (Deterministic local extraction inherited from frozen V2–V6, N ≤ 1)
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
     │
     ├── [Empty Candidate / Assessment != SUSPECT / Assessment == PASS]
     │        ↓
     │   Targeted Repair Bypassed (0 repair LLM calls)
     │        ↓
     │   Final Answer = pre_repair_answer
     │
     └── [Candidate Present AND Assessment == SUSPECT]
              ↓
         Stage 5: One-Shot Targeted Repair Generation (`targeted-repair-v1`, mode="NONE", N ≤ 1)
         (Inputs: Question, Existing Evidence, Pre-Repair Answer, Risk Type, Reasoning)
              ↓
         Deterministic Action Parser
              ├── [ACTION: KEEP] → Post-Repair Answer = Pre-Repair Answer
              ├── [ACTION: REPLACE] → Post-Repair Answer = Repaired Answer
              └── [PARSER FAILURE / ERROR] → Fallback: Pre-Repair Answer Preserved
              ↓
         Final Answer Emitted to Scorer
```

---

## 3. Strict Frozen Invariants

The V7 architecture strictly enforces the following invariants:
- **Trigger Guard**: Repair is attempted if and only if `self_eval_assessment == "SUSPECT"` on a non-empty candidate answer. Zero `PASS` tasks and zero empty-candidate tasks attempted repair.
- **Budget Boundedness**: At most **1** repair generation attempt per task ($N \in \{0, 1\}$). Maximum total LLM generation attempts capped at **5** across the entire pipeline ($\le 4$ upstream + $\le 1$ repair).
- **Tool Isolation**: The repair stage is strictly text-only (`tools_mode = "NONE"`). Exactly 0 search queries, 0 Python executions, and 0 file operations were executed during repair.
- **Deterministic Fallback Safety**: On any repair failure or unparseable response, the pre-repair candidate answer is preserved identically (`repair_answer_changed = False`).
- **Ground-Truth Firewall**: The repair agent operates with zero knowledge of reference answers or scorer outputs. All scoring is conducted strictly post-hoc.

---

## 4. Canonical Benchmark Results (GAIA 2023 Validation Set, 165 Tasks)

### Within-Run Pre/Post Repair Effect

Because V7 logs both `pre_repair_answer` / `pre_repair_correct` and `post_repair_answer` / `post_repair_correct` within the exact same execution trace, the observed repair-stage effect in this benchmark run is measured with zero cross-run sampling variance:

| Metric | Level 1 (N=53) | Level 2 (N=86) | Level 3 (N=26) | Overall (N=165) |
| :--- | :---: | :---: | :---: | :---: |
| **Pre-Repair Correct** | 22 (41.51%) | 22 (25.58%) | 2 (7.69%) | **46 (27.88%)** |
| **Post-Repair Correct** | 22 (41.51%) | 22 (25.58%) | 2 (7.69%) | **46 (27.88%)** |
| **Net Repair Delta** | **0 (0.00 pp)** | **0 (0.00 pp)** | **0 (0.00 pp)** | **0 tasks (0.00 pp)** |
| Completed Tasks | 34 (64.15%) | 38 (44.19%) | 8 (30.77%) | **80 (48.48%)** |
| Improvements ($0 \rightarrow 1$) | 0 | 0 | 0 | **0** |
| Regressions ($1 \rightarrow 0$) | 0 | 0 | 0 | **0** |
| Stable Correct ($1 \rightarrow 1$) | 1 | 2 | 1 | **4** |
| Stable Failure ($0 \rightarrow 0$) | 4 | 5 | 6 | **15** |
| Not Triggered | 48 | 79 | 19 | **146** |
| **Correction Rate** | 0.00% (0/4) | 0.00% (0/5) | 0.00% (0/6) | **0.00% (0/15)** |
| **Triggered-Answer Harm Rate** | 0.00% (0/1) | 0.00% (0/2) | 0.00% (0/1) | **0.00% (0/4)** |

> **Within-Run Finding**: In this V7 benchmark run, the bounded targeted repair stage produced zero wrong-to-correct transitions and zero correct-to-wrong transitions, for a net within-run change of 0 correct tasks.

---

## 5. Canonical Repair Actions & Forensic Case Studies

Across all 165 GAIA tasks, exactly 19 tasks triggered targeted repair:

| Metric | Overall Count | Breakdown / Interpretation |
| :--- | :---: | :--- |
| **Repair Eligible** | 19 | Non-empty candidate answers receiving a valid `SUSPECT` evaluation |
| **Repair Attempted** | 19 | Exactly 1 attempt per triggered task (zero retries) |
| **Valid Actions** | 18 | Successfully parsed actions (`KEEP` or `REPLACE`) |
| **Failed Actions** | 1 | Schema parse failure (fallback preserved candidate) |
| **KEEP Actions** | 16 (84.21%) | Model chose to retain existing answer |
| **REPLACE Actions** | 2 (10.53%) | Model substituted answer (both in Level 3) |
| **Answers Changed** | 2 (10.53%) | Tasks where the final emitted answer differed from candidate |

### The Two REPLACE Outcomes
Both actual replacement operations occurred in Level 3 and resulted in `STABLE_FAILURE`:
1. **Task `ebbc1f13-d24d-40df-9068-adcf735b4240` (L3, `EVIDENCE` risk, Conf: 1.0)**:
   - *Pre-repair candidate*: `'El Pais'` (incorrect)
   - *Post-repair answer*: `'The Country'` (incorrect)
   - *Outcome*: Model substituted the English translation for the Spanish newspaper title, but neither matched the ground-truth benchmark requirement.
2. **Task `c3a79cfe-8206-451f-aca8-3fec8ebe51d3` (L3, `FORMAT` risk, Conf: 1.0)**:
   - *Pre-repair candidate*: Verbose explanatory paragraph listing stations (incorrect)
   - *Post-repair answer*: `'8'` (incorrect)
   - *Outcome*: Model resolved the format defect by extracting an integer, but the underlying station count remained factually incorrect.

### The One Failed Repair
- **Task `c8b7e059-c60d-472e-ad64-3b04ae1166dc` (L2, `EXECUTION` risk, Conf: 0.8)**:
  - Error type: `malformed_repair_text` (unstructured response omitting required headers).
  - *Safety result*: Pre-repair answer (`'31'`) preserved verbatim; `repair_answer_changed = False`. Not counted as `KEEP`.

### Harm Safety Context
Among the four initially-correct answers that were flagged `SUSPECT`, no regression was observed in this run ($0 / 4 = 0.00\%$). All four were protected by `KEEP` behavior. However, this safety observation is bounded by its small denominator ($N = 4$), with only two total `REPLACE` actions occurring across the benchmark.

---

## 6. Diagnostic Performance Inside V7 Run (Anchored to Pre-Repair Ground Truth)

Diagnostic metrics of the upstream self-evaluator strictly evaluated against **pre-repair ground truth**:

| Diagnostic Metric | Canonical V7 Value | Context / Meaning |
| :--- | :---: | :--- |
| **Eligible Candidates** | **78** (47.27%) | Tasks where a non-empty candidate answer reached self-evaluation |
| **Diagnostic Coverage** | **100.0%** (78 / 78) | All eligible candidates evaluated (78 / 165 is candidate availability) |
| **True Positives (TP)** | **15** | Erroneous pre-repair candidates flagged as `SUSPECT` |
| **False Positives (FP)** | **4** | Correct pre-repair candidates mistakenly flagged as `SUSPECT` |
| **True Negatives (TN)** | **42** | Correct pre-repair candidates correctly passed (`PASS`) |
| **False Negatives (FN)** | **17** | Erroneous pre-repair candidates missed by evaluator (`PASS`) |
| **Precision** | **78.95%** (15 / 19) | Reliability of the `SUSPECT` trigger |
| **Recall (Eligible)** | **46.88%** (15 / 32) | Fraction of candidate-bearing errors caught |
| **F1 Score** | **0.5882** | Balanced diagnostic score on eligible candidates |
| **Specificity** | **91.30%** (42 / 46) | Preservation of correct candidate answers |
| **False Alarm Rate (FAR)** | **8.70%** (4 / 46) | Low rate of false suspicion on correct answers |
| **Missed Error Rate (MER)** | **53.12%** (17 / 32) | Fraction of candidate-bearing errors unflagged |
| **Brier Score** | **0.2581** | Mean squared error of probabilistic error predictions |

---

## 7. Candidate Starvation: The Dominant Architectural Bottleneck

| Reach Metric | Count / Fraction | Percentage |
| :--- | :---: | :---: |
| Total Benchmark Tasks | 165 | 100.0% |
| Total Pre-Repair System Errors | 119 | 72.12% |
| **No-Candidate Tasks (Candidate Starved)** | **87** | **52.73% of tasks** |
| **Starved Errors (Inaccessible to Repair)** | **87 / 119** | **73.11% of all system errors** |
| Reachable Errors (Candidate-Bearing) | 32 / 119 | 26.89% of all system errors |
| Repair-Triggered Erroneous Answers (TP) | 15 / 119 | 12.61% of all system errors |
| **Opportunity Coverage (All System Errors)** | **15 / 119** | **12.61%** |
| **Opportunity Coverage (Reachable Errors)** | **15 / 32** | **46.88%** |
| **End-to-End Corrected Fraction** | **0 / 119** | **0.00%** |

Candidate starvation remains the dominant end-to-end limitation: **73.11%** of all failures occurred upstream before an answer could be formulated, rendering them completely unreachable by downstream repair.

---

## 8. Evaluator-Assigned Diagnostic Risk Types

Aggregate distribution of evaluator-assigned risk labels across all 19 `SUSPECT` triggers:

| Evaluator-Assigned Risk Category | Triggers | KEEP | REPLACE | Failed | Stable Correct | Stable Failure |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **EVIDENCE** | **15 (78.95%)** | 14 | 1 | 0 | 4 | 11 |
| **REASONING** | **2 (10.53%)** | 2 | 0 | 0 | 0 | 2 |
| **EXECUTION** | **1 (5.26%)** | 0 | 0 | 1 | 0 | 1 |
| **FORMAT** | **1 (5.26%)** | 0 | 1 | 0 | 0 | 1 |
| **CALCULATION** | **0 (0.00%)** | 0 | 0 | 0 | 0 | 0 |
| **UNKNOWN** | **0 (0.00%)** | 0 | 0 | 0 | 0 | 0 |

> **Evidence-Limitation Context**: Most SUSPECT triggers were evaluator-assigned EVIDENCE risks, while V7 was limited to reconsidering already-available evidence. The V7 repair stage was unable to acquire new evidence because active retrieval and tools were intentionally prohibited. This motivates studying bounded active verification in a future version.

---

## 9. Contemporaneous Matched Frozen V6 Observational Comparison

A contemporaneous matched frozen V6 control run was conducted in parallel with V7:

| Benchmark Level | Matched V6 Correct | V7 Post-Repair Correct | Cross-Run Difference |
| :---: | :---: | :---: | :---: |
| **Level 1** | 24 / 53 (45.28%) | 22 / 53 (41.51%) | -2 tasks (-3.77 pp) |
| **Level 2** | 25 / 86 (29.07%) | 22 / 86 (25.58%) | -3 tasks (-3.49 pp) |
| **Level 3** | 3 / 26 (11.54%) | 2 / 26 (7.69%) | -1 task (-3.85 pp) |
| **Overall** | **52 / 165 (31.52%)** | **46 / 165 (27.88%)** | **-6 tasks (-3.64 pp)** |

- **Matched V6 Completed**: 85 / 165 (51.52%) vs. V7 Completed: 80 / 165 (48.48%).
- **Cross-Run 2x2 Contingency Matrix**:
  - Both Correct: 36 tasks
  - Both Wrong: 103 tasks
  - Matched V6 Wrong $\rightarrow$ V7 Correct: 10 tasks
  - Matched V6 Correct $\rightarrow$ V7 Wrong: 16 tasks
  - Check: $36 + 103 + 10 + 16 = 165$ tasks.

> **Methodological Attribution**: The observed -6 task (-3.64 pp) cross-run difference is strictly **observational and non-causal**. Within the V7 run itself, the direct causal delta of targeted repair was identically **0 tasks (0.00 pp)**. The cross-run variation reflects upstream LLM sampling stochasticity, capability routing choices, and provider completion behavior across separate runs.

---

## 10. Provider Incident Provenance & Recovery

All provider incidents encountered during the campaign are preserved with full historical provenance:
1. **Pre-Benchmark Tavily Health Gate**: Before benchmark launch, Tavily quota exhaustion triggered health-gate failure; Canonical Level 1 was not launched until quota refreshed, ensuring no canonical evidence was polluted.
2. **Invalid Matched V6 Level 1 Run** (`experiments/v7_matched_v6_invalid_l1_provider_collapse/`): Google Gemini free-tier daily quota exhaustion (429 RESOURCE_EXHAUSTED) caused 39 completion failures. Quarantined and cleanly re-executed upon quota reset.
3. **Invalid Matched V6 Level 2 Run** (`experiments/v7_matched_v6_invalid_l2_provider_collapse/`): Gemini service account deletion (401 UNAUTHENTICATED) caused 73 consecutive router fallbacks. Quarantined and cleanly re-executed after the user provided an active credential.
4. **Canonical Replacement Selection Rule**: In accordance with preregistered benchmark rules, the first operationally healthy run was accepted regardless of benchmark score.

---

## 11. Source Provenance & Behavioral Invariance

- **Smoke-Tested Behavioral Source Baseline**: Git commit `8c0036001cc07408f45e2f6ec3c2ca5e73dc3c46`.
- **Benchmark Execution Commit**: `246dc650cecab023ddd32be2da757c49cca2a31a`.
- **Audit & Finalization Commit**: `647c51b7feeb5ae57b6d136932fe4eeadcfdfd59`.
- **Source Verification**: A complete git diff analysis confirmed that commits following `8c00360` introduced strictly benchmark summaries, artifact metadata, invalid-run provenance, analysis/audit scripts, and documentation. Zero behavioral changes were made to `agent/`, `prompts/`, `tools/`, repair runtime, self-evaluator, router, worker, or verifier.
- **Git State (`git_dirty`)**: Benchmark summaries record `git_dirty = true` because append-only prediction JSONL logs and local evaluation artifacts were actively generated in the working tree during execution.
- **Status**: `BEHAVIORALLY_IDENTICAL_SOURCE_CONFIRMED`.

---

## 12. Canonical Artifact Manifests (SHA-256 Checksums)

All canonical artifacts parse cleanly with zero schema errors or duplicate task IDs across all levels.

### Canonical V7 Files (`experiments/v7/`)
| Artifact File | SHA-256 Checksum | Size (Bytes) | Verification Status |
| :--- | :--- | :---: | :---: |
| `predictions_level_1.jsonl` | `075cab93a74b191de23489696f3b1ca347e694f9dbf317f21b83744e464c3146` | 2,349,607 | Verified (53/53) |
| `predictions_level_2.jsonl` | `6181f9b9fa36e20af1a38db7bd9e78101dc37df9a006343922743ec7cd0b3878` | 3,456,861 | Verified (86/86) |
| `predictions_level_3.jsonl` | `cb38ce40cb05e83d561acd77247dd3d8c157ed771208c1e4e4484bc02a583c39` | 1,061,643 | Verified (26/26) |
| `detailed_eval_level_1.jsonl` | `6d6f4143d44b82cb6c5fe7959d0b389b791b25f271ab93523d189f1c3d864443` | 557,750 | Verified (53/53) |
| `detailed_eval_level_2.jsonl` | `dbebd86ad6cd45f38b37754f141ee82cf331e63d7d388fa9f56fe7ee301e904c` | 884,930 | Verified (86/86) |
| `detailed_eval_level_3.jsonl` | `46f05429834503abdc553a1350377866a53749244f601ee68fe5255d943e6fbf` | 271,768 | Verified (26/26) |
| `summary_level_1.json` | `8477a46ed5fb58d82b1c9365b23491cdf3c688be2fe636d7ffb2a0bd88484b1f` | 7,654 | Verified |
| `summary_level_2.json` | `66117e9d8ce0b9ee2b670af83342ca9355a35ec3b6e99b92fc152fc2fb3c65c1` | 7,576 | Verified |
| `summary_level_3.json` | `9d36d5f9e1c0f90736b58c95de1ae7a91075449e9f57654b2b7c64f05dd112cd` | 7,370 | Verified |

### Contemporaneous Matched V6 Control Files (`experiments/v7_matched_v6/`)
| Artifact File | SHA-256 Checksum | Size (Bytes) | Verification Status |
| :--- | :--- | :---: | :---: |
| `predictions_level_1.jsonl` | `53c1f19e8c0dcfd69e021cdc3e0b8521a3c648172e0b460d8f773c166b93d9fd` | 2,279,726 | Verified (53/53) |
| `predictions_level_2.jsonl` | `e3789501e9a170a0b57ce119b6d3b8b5a87385449a60c1289d6cf746c7e7e644` | 3,369,634 | Verified (86/86) |
| `predictions_level_3.jsonl` | `66b0da7362245185b7dcc450c7813ac87e19056e8c212ffc49108457edc7e6c3` | 1,013,118 | Verified (26/26) |
| `detailed_eval_level_1.jsonl` | `b7068ad12b10257e21dbab2497763c368c65de9a4232ca19fa0493ac7bee8619` | 550,539 | Verified (53/53) |
| `detailed_eval_level_2.jsonl` | `ba409255415ae7204812b815d3a7ff57b7a681af7db269efc5bbfc4b873c7735` | 868,735 | Verified (86/86) |
| `detailed_eval_level_3.jsonl` | `9e175105857805fcb9d59059a35d583290f243740f1106cb20e0dd6003c8f028` | 260,864 | Verified (26/26) |
| `summary_level_1.json` | `6edbed7515962336e80be9a5c6ac020ee2af8697537d8739ccc7fbc7442b208d` | 6,554 | Verified |
| `summary_level_2.json` | `f77ec487a61543f9db095e3e7ae4defb176903d39621dd4c6a82378998e6d6b7` | 6,539 | Verified |
| `summary_level_3.json` | `4f2b5030f3d402515034b088657c061a429f74b3acddbc1a96867cc90fe31c61` | 6,293 | Verified |

> **Public Artifact Policy**: In accordance with `.gitignore`, raw `predictions_*.jsonl` files are local canonical artifacts. Summary JSON files and `ARTIFACT_MANIFEST.sha256` files are tracked in Git.

---

## 13. Scientific Limitations & Handoff to V8

### Scientific Limitations
1. **Ineffectiveness of Text-Only Reconsideration**: In this benchmark run, reconsidering already-available evidence without tools or new retrieval produced zero improvements across 15 erroneous SUSPECT candidates.
2. **Small Harm Safety Denominator**: While zero regressions were observed across the four initially-correct candidates, the replacement operation only executed twice across the entire benchmark, limiting broader generalization about replacement safety.
3. **Candidate Starvation Bottleneck**: Over 73% of all system errors were unreachable by repair because the agent failed to generate a candidate answer.

### V8 Experimental Increment Handoff
- **Scope**: Keep the next experimental increment narrow: **V8 — Bounded Active Verification**.
- **Definition**:
  ```text
  V8 = Frozen V7 + one bounded active verification capability
  ```
- **Research Question**: *When the passive evaluator marks an answer SUSPECT, does acquiring one targeted piece of new evidence or performing one targeted computation improve correction compared with text-only reconsideration?*
- **Candidate Starvation Demarcation**: Candidate starvation must **NOT** be simultaneously redesigned in V8. Addressing candidate starvation requires pipeline interventions that represent a distinct architectural capability, preserved as a separate future research direction.

---

## 14. Freeze Verdict

```text
V7 FREEZE VERDICT: FROZEN_WITH_DOCUMENTED_LIMITATIONS
```

V7 is frozen as the immutable research baseline for SUSPECT-triggered targeted repair. Future work must not alter V7 results, runtime code, prompts, model configs, or evaluations. Any active verification experimentation belongs to V8+.
