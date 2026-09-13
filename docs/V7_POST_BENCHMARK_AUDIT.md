# V7 Post-Benchmark Audit: SUSPECT-Triggered Targeted Repair

**Status:** POST-BENCHMARK AUDITED (Freeze Candidate)<br>
**POST-BENCHMARK AUDIT:** PASSED<br>
**FREEZE READINESS:** READY_TO_FREEZE_WITH_DOCUMENTED_LIMITATIONS<br>
**Evaluation Scope:** GAIA 2023 Validation Set (165 Tasks: 53 Level 1, 86 Level 2, 26 Level 3)<br>
**Parent Baseline:** Frozen V6 Self-Evaluation / Failure Detection<br>
**Branch:** `v7-targeted-repair`<br>
**Date:** September 2026

---

## 1. Experimental Definition & Hypotheses

Version 7 (V7) investigates bounded post-evaluation targeted repair within the GAIA agent benchmarking framework. V7 is formally defined as:

$$\text{V7} = \text{Frozen V6} + \text{one bounded text-only repair generation triggered exclusively by valid SUSPECT}$$

The primary scientific research question is:
> *Can one bounded targeted repair generation, triggered only by a valid V6 SUSPECT assessment, correct more erroneous answers than it harms correct answers, without additional tools, new evidence retrieval, or retries?*

### Formal Hypotheses
1. **Hypothesis 1 (Effectiveness / Correction):** A single targeted generation prompting the model with self-evaluation risk diagnostics and existing evidence can revise erroneous answers into correct ones, yielding $\text{Improvements} > 0$.
2. **Hypothesis 2 (Harm Avoidance / Conservative Retention):** The repair prompt's instruction to `KEEP` the existing answer unless existing evidence definitively supports a revision will prevent degradation of already-correct answers ($\text{Harm Rate} \approx 0\%$).
3. **Hypothesis 3 (Selective Activation):** Conditioning repair strictly on non-empty candidate answers receiving a valid `SUSPECT` verdict avoids unnecessary invocations on `PASS` answers or upstream failures.
4. **Hypothesis 4 (Bounded Overhead):** Targeted repair introduces negligible latency and token overhead when bounded to a single generation attempt with zero additional tool calls.

---

## 2. Benchmark Protocol & Environmental Integrity

The canonical evaluation was conducted on the full GAIA 2023 Validation set (165 tasks across Levels 1, 2, and 3):
- **Model**: `gemini-3.5-flash-lite` (temperature=None, thinking_level="medium", max_output_tokens=2048).
- **Search Provider**: Tavily Search API (`tavily-python` v0.5.1), max results=5, search depth="advanced".
- **Execution Environment**: Windows NT, Python 3.13.2, isolated sub-process runner with 5.0-second inter-task delay.
- **Evaluation Scorer**: Official GAIA leaderboard evaluator (`gaia_question_scorer`), applied strictly post-hoc.
- **Contemporaneous Matched Control**: A parallel run of frozen V6 was executed under identical software dependencies, API endpoints, and model configurations across all 165 tasks.

---

## 3. Source Provenance & Behavioral Invariance

The source code integrity across the benchmark execution was verified against the git commit history on branch `v7-targeted-repair`:
- **Pre-Benchmark Smoke Commit**: `8c0036001cc07408f45e2f6ec3c2ca5e73dc3c46` (validated via 6-task controlled smoke).
- **Execution Intermediate Commit**: `246dc650cecab023ddd32be2da757c49cca2a31a`.
- **Artifact Finalization Commit**: `647c51b7feeb5ae57b6d136932fe4eeadcfdfd59`.

A complete git diff audit between `8c00360` and `HEAD` confirms that **zero** modifications were made to:
- Agent runtime logic (`agent/runner.py`, `agent/targeted_repair.py`, `agent/self_evaluator.py`, `agent/verification.py`).
- System prompts (`prompts/targeted_repair_prompts.py`, `prompts/self_evaluator_prompts.py`).
- Tool configurations or execution sandboxes.
- Parser grammar, decision thresholds, or repair eligibility logic.

All code differences between smoke and canonical benchmark completion consisted strictly of benchmark artifact generation, telemetry analysis utilities, and test scripts.  
**Verdict:** `BEHAVIORALLY_IDENTICAL_SOURCE_CONFIRMED`.

---

## 4. Provider Incident History & Disaster Recovery

During the execution of the contemporaneous matched frozen V6 control runs, two external provider failure events occurred:

### Incident 1: Matched V6 Level 1 Provider Quota Exhaustion
- **Failure Mode**: Google Gemini API free-tier request limit (`429 RESOURCE_EXHAUSTED: Daily request limit of 500 reached`).
- **Impact**: Matched V6 Level 1 halted after 27 tasks.
- **Mitigation & Quarantine**: The incomplete execution was immediately halted and quarantined under `experiments/v7_matched_v6_invalid_l1_provider_collapse/`.
- **Recovery**: Once daily quota was reset, Matched V6 Level 1 was cleanly executed from task 1 through 53 without interruptions.

### Incident 2: Matched V6 Level 2 Service Account Invalidation
- **Failure Mode**: Google Gemini API authentication failure (`401 UNAUTHENTICATED: The bound service account is deleted or disabled`).
- **Impact**: Matched V6 Level 2 suffered an operational collapse at task 22, triggering 73 consecutive router fallbacks.
- **Mitigation & Quarantine**: The invalid run was immediately quarantined under `experiments/v7_matched_v6_invalid_l2_provider_collapse/`.
- **Recovery**: The user provided an active replacement API credential. Both provider endpoints (Gemini LLM and Tavily Search) were verified via live sanity checks. Matched V6 Level 2 was then cleanly re-executed in full across all 86 tasks.

### Canonical Run Protection
Neither incident affected the Canonical V7 runs (Levels 1, 2, and 3 were executed to completion with zero provider auth/quota errors). All healthy canonical runs were preserved intact. In accordance with preregistered benchmark rules, the first operationally healthy run was accepted regardless of benchmark score.

---

## 5. Quarantined Runs Inspection & Forensic Demarcation

The two quarantined historical runs remain preserved for full transparency:

| Quarantined Run | Tasks Walked | Completed | Correct | Router Fallbacks | Provider Errors | Root Cause |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `invalid_l1_provider_collapse` | 53 | 14 (26.4%) | 11 (20.8%) | 39 | 39 | 429 Quota Exhaustion |
| `invalid_l2_provider_collapse` | 86 | 13 (15.1%) | 10 (11.6%) | 73 | 73 | 401 Deleted Service Account |

Both quarantined directories are permanently excluded from benchmark scoring and analysis manifests.

---

## 6. Within-Run Repair Transitions & Observed Repair-Stage Effect

Because V7 logs `pre_repair_answer` / `pre_repair_correct` and `post_repair_answer` / `post_repair_correct` within each individual task execution, the observed repair-stage intervention effect in this benchmark run is measured with zero cross-run sampling variance:

$$\Delta_{\text{repair}} = \text{Improvements} - \text{Regressions}$$

### Within-Run Repair Results (GAIA Validation Set, 165 Tasks)

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
| **Triggered Harm Rate** | 0.00% (0/1) | 0.00% (0/2) | 0.00% (0/1) | **0.00% (0/4)** |

### Within-Run Findings
- **Zero Net Accuracy Change**: In this V7 benchmark run, the bounded targeted repair stage produced zero wrong-to-correct transitions and zero correct-to-wrong transitions, for a net within-run change of 0 correct tasks.
- **Harm Avoidance in This Run**: Among the four initially-correct answers that were flagged `SUSPECT`, no regression was observed. All four were protected by `KEEP` behavior.
- **Zero Correction Observed**: On the 15 tasks where an incorrect answer was correctly flagged as `SUSPECT`, the repair model produced zero improvements.

---

## 7. Detailed Breakdown of Repair Actions (KEEP vs. REPLACE vs. Failed)

Across all 165 GAIA tasks, exactly 19 tasks met the trigger condition (`repair_eligible == True` and `self_eval_assessment == "SUSPECT"`):

| Level | Triggered | Attempted | Valid Actions | KEEP | REPLACE | Failed (Fallback) | Answer Changed |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 5 | 5 | 5 | 5 | 0 | 0 | 0 |
| **Level 2** | 7 | 7 | 6 | 6 | 0 | 1 | 0 |
| **Level 3** | 7 | 7 | 7 | 5 | 2 | 0 | 2 |
| **Total** | **19** | **19** | **18** | **16** | **2** | **1** | **2** |

### Proportional Action Distribution
- **KEEP**: 16 / 19 (84.21%)
- **REPLACE**: 2 / 19 (10.53%)
- **Failed**: 1 / 19 (5.26%)
- **Answers Changed**: 2 / 19 (10.53%)

The high `KEEP` rate (84.2%) reflects the conservative design of `targeted-repair-v1`, which explicitly instructs the agent:
> *"If the existing evidence does not contain clear, unambiguous facts to support an alternative answer, you MUST choose KEEP."*

Among the four initially-correct answers that were flagged `SUSPECT`, no regression was observed ($0 / 4 = 0.00\%$), as all four were protected by `KEEP` behavior. However, this safety result cannot be broadly generalized because only two actual `REPLACE` operations occurred across the entire benchmark.

---

## 8. Deep Dive into the Two REPLACE Tasks

Only two tasks underwent actual answer replacement during the entire benchmark. Both occurred in Level 3, and both resulted in `STABLE_FAILURE`:

### Case 1: Task `ebbc1f13-d24d-40df-9068-adcf735b4240` (Level 3)
- **Question**: Requires identifying the original Spanish newspaper publication name for an archival article.
- **Self-Evaluation**: `ASSESSMENT: SUSPECT`, `RISK_TYPE: EVIDENCE`, `CONFIDENCE: 1.0`.
- **Pre-Repair Answer**: `'El Pais'`
- **Repair Action**: `REPLACE`
- **Post-Repair Answer**: `'The Country'`
- **Outcome**: Pre-repair = Incorrect, Post-repair = Incorrect $\rightarrow$ `STABLE_FAILURE`.
- **Qualitative Behavioral Description**: The model replaced the Spanish title with its English translation (*"The Country"*), but neither was the exact ground-truth publication citation required by GAIA.

### Case 2: Task `c3a79cfe-8206-451f-aca8-3fec8ebe51d3` (Level 3)
- **Question**: Multi-hop reasoning task requiring counting specific train stations matching criteria.
- **Self-Evaluation**: `ASSESSMENT: SUSPECT`, `RISK_TYPE: FORMAT`, `CONFIDENCE: 1.0`.
- **Pre-Repair Answer**: Verbose explanatory paragraph detailing candidate stations and route notes.
- **Repair Action**: `REPLACE`
- **Post-Repair Answer**: `'8'`
- **Outcome**: Pre-repair = Incorrect, Post-repair = Incorrect $\rightarrow$ `STABLE_FAILURE`.
- **Qualitative Behavioral Description**: The self-evaluator assigned a `FORMAT` risk (the upstream agent outputted an essay rather than a single number). The repair model followed the format instruction and extracted a single integer (`'8'`), resolving the format defect. However, the upstream station counting logic had omitted intermediate transfers, so the numerical answer remained factually incorrect.

---

## 9. Forensic Audit of the One Repair Failure

Across all 19 attempted repairs, exactly one generation failure occurred:

### Task `c8b7e059-c60d-472e-ad64-3b04ae1166dc` (Level 2)
- **Self-Evaluation**: `ASSESSMENT: SUSPECT`, `RISK_TYPE: EXECUTION`, `CONFIDENCE: 0.8`.
- **Pre-Repair Answer**: `'31'`
- **Repair Outcome**: `repair_success = False`, `repair_error_type = "malformed_repair_text"`.
- **Root Cause**: The model generated an unformatted thought sequence omitting the required `ACTION: KEEP|REPLACE` and `REPAIRED_ANSWER:` header structure.
- **Fallback Verification**:
  - `post_repair_answer` was set identically to `pre_repair_answer` (`'31'`).
  - `repair_answer_changed` was set to `False`.
  - Causal transition recorded as `STABLE_FAILURE`.
  - Not counted as `KEEP`.
- **System Invariant Confirmed**: Zero crashes, zero blanked answers, zero data corruption upon repair generation failure.

---

## 10. Diagnostic Accuracy & Calibration (Anchored to Pre-Repair Correctness)

To evaluate the self-evaluator's true diagnostic capability without circularity, performance is evaluated against **pre-repair ground truth correctness**:

| Diagnostic Metric | Value | Formula / Definition |
| :--- | :---: | :--- |
| **Eligible Candidates** | **78** (47.27%) | Non-empty candidate answers reaching self-evaluation |
| **Diagnostic Coverage** | **100.0%** (78 / 78) | Valid evaluations on eligible candidates (78 / 165 is candidate availability) |
| **True Positives (TP)** | **15** | Erroneous pre-repair answers flagged as `SUSPECT` |
| **False Positives (FP)** | **4** | Correct pre-repair answers mistakenly flagged as `SUSPECT` |
| **True Negatives (TN)** | **42** | Correct pre-repair answers correctly passed (`PASS`) |
| **False Negatives (FN)** | **17** | Erroneous pre-repair answers missed by evaluator (`PASS`) |
| **Precision** | **78.95%** | $15 / (15 + 4)$ |
| **Recall (Eligible)** | **46.88%** | $15 / (15 + 17)$ |
| **F1 Score** | **0.5882** | $2 \cdot \frac{P \cdot R}{P + R}$ |
| **Specificity** | **91.30%** | $42 / (42 + 4)$ |
| **False Alarm Rate (FAR)** | **8.70%** | $4 / (42 + 4)$ |
| **Missed Error Rate (MER)** | **53.12%** | $17 / (17 + 15)$ |
| **Brier Score** | **0.2581** | Mean squared error of probabilistic error predictions |

### Forensic Analysis of the 4 False Positives
The self-evaluator flagged 4 correct answers as `SUSPECT`:
1. **L1 `75ee5c34-d074-4b52-b8ba-0a78ae32bcad`**: Evaluator-assigned Risk `EVIDENCE`, Conf 0.95. Repair Action: `KEEP` $\rightarrow$ Correctness preserved.
2. **L2 `366e2f2b-8632-4ef2-81eb-bc3877489217`**: Evaluator-assigned Risk `EVIDENCE`, Conf 0.95. Repair Action: `KEEP` $\rightarrow$ Correctness preserved.
3. **L2 `5ce3d596-fdd2-4b72-a16a-f32a5ec2ec50`**: Evaluator-assigned Risk `EVIDENCE`, Conf 0.90. Repair Action: `KEEP` $\rightarrow$ Correctness preserved.
4. **L3 `b80eefb3-1f1f-4bb2-b673-c6be368a52cf`**: Evaluator-assigned Risk `EVIDENCE`, Conf 0.90. Repair Action: `KEEP` $\rightarrow$ Correctness preserved.

Because the repair stage chose `KEEP` in all 4 false positive cases, no regressions occurred.

---

## 11. Risk-Type Distribution & Conditional Repair Performance

Self-evaluation assigns a specific risk category to each `SUSPECT` diagnosis. Breakdown of outcomes across assigned risk types:

| Evaluator-Assigned Risk Category | Triggers | KEEP | REPLACE | Failed | Stable Correct | Stable Failure | Improvements | Regressions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **EVIDENCE** | **15 (78.95%)** | 14 | 1 | 0 | 4 | 11 | 0 | 0 |
| **REASONING** | **2 (10.53%)** | 2 | 0 | 0 | 0 | 2 | 0 | 0 |
| **EXECUTION** | **1 (5.26%)** | 0 | 0 | 1 | 0 | 1 | 0 | 0 |
| **FORMAT** | **1 (5.26%)** | 0 | 1 | 0 | 0 | 1 | 0 | 0 |
| **CALCULATION** | **0 (0.00%)** | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **UNKNOWN** | **0 (0.00%)** | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **Total** | **19** | **16** | **2** | **1** | **4** | **15** | **0** | **0** |

> **Evidence-Limitation Context**: Most SUSPECT triggers were evaluator-assigned EVIDENCE risks, while V7 was limited to reconsidering already-available evidence. The V7 repair stage was unable to acquire new evidence because active retrieval and tools were intentionally prohibited. This motivates studying bounded active verification in a future version.

---

## 12. Candidate Starvation & System Error Reach

The reach of downstream targeted repair is strictly bounded by the agent's ability to produce a non-empty candidate answer upstream:

| System Error Reach Metric | Count / Fraction | Percentage |
| :--- | :---: | :---: |
| Total Benchmark Tasks | 165 | 100.0% |
| Total Pre-Repair System Errors | 119 | 72.12% |
| **No-Candidate Tasks (Candidate Starved)** | **87** | **52.73% of tasks** |
| **Starved Errors (Inaccessible to Repair)** | **87 / 119** | **73.11% of all system errors** |
| Reachable Errors (Candidate-Bearing) | 32 / 119 | 26.89% of all system errors |
| Erroneous Candidates Triggered (TP) | 15 / 119 | 12.61% of all system errors |
| **Opportunity Coverage (All System Errors)** | **15 / 119** | **12.61%** |
| **Opportunity Coverage (Reachable Errors)** | **15 / 32** | **46.88%** |
| **End-to-End Corrected Fraction** | **0 / 119** | **0.00%** |

Candidate starvation remains the dominant architectural limitation: **73.11%** of all failures occurred upstream before an answer could be formulated, rendering them completely unreachable by downstream repair.

---

## 13. Matched Frozen V6 Observational Comparison

A contemporaneous matched frozen V6 control run was conducted in parallel with V7:

| Level | Matched V6 Accuracy | Canonical V7 Post-Repair Accuracy | Cross-Run Difference |
| :---: | :---: | :---: | :---: |
| **Level 1** | 45.28% (24 / 53) | 41.51% (22 / 53) | -3.77 pp (-2 tasks) |
| **Level 2** | 29.07% (25 / 86) | 25.58% (22 / 86) | -3.49 pp (-3 tasks) |
| **Level 3** | 11.54% (3 / 26) | 7.69% (2 / 26) | -3.85 pp (-1 task) |
| **Overall** | **31.52% (52 / 165)** | **27.88% (46 / 165)** | **-3.64 pp (-6 tasks)** |

- **Cross-Run 2x2 Contingency Matrix**:
  - Both Correct: 36 tasks
  - Both Wrong: 103 tasks
  - Matched V6 Wrong $\rightarrow$ V7 Correct: 10 tasks
  - Matched V6 Correct $\rightarrow$ V7 Wrong: 16 tasks
  - Check: $36 + 103 + 10 + 16 = 165$ tasks.

> **Methodological Attribution**: The observed -6 task (-3.64 pp) cross-run difference is strictly **observational and non-causal**. Within the V7 run itself, the within-run repair delta was identically **0 tasks (0.00 pp)**. The cross-run variation reflects upstream LLM sampling stochasticity, capability routing choices, and provider completion behavior across separate runs.

---

## 14. Cost & Latency Telemetry of Targeted Repair

Targeted repair was invoked on 19 tasks. Telemetry metrics across all repair invocations:

| Telemetry Metric | Latency (Seconds) | Input Tokens | Output Tokens | Thinking Tokens | Total Tokens |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Mean** | **4.86 s** | **2,310.8** | **6.5** | **815.7** | **3,047.2** |
| **Median** | **2.28 s** | 2,245.0 | 5.0 | 792.0 | 3,012.0 |
| **Min** | 0.60 s | 1,840.0 | 1.0 | 120.0 | 1,961.0 |
| **Max** | 16.28 s | 2,950.0 | 24.0 | 1,480.0 | 4,210.0 |
| **Benchmark Total** | 92.34 s | 43,905 | 123 | 15,498 | **57,896** |

The targeted repair stage is computationally bounded, adding an average of ~4.9 seconds and ~3,000 tokens per triggered task, totaling less than 58k tokens across the entire 165-task GAIA benchmark.

---

## 15. Artifact Integrity & SHA-256 Checksums

All canonical artifacts in `experiments/v7/` and `experiments/v7_matched_v6/` are verified against SHA-256 manifests:

### Canonical V7 Artifacts (`experiments/v7/`)
| Artifact File | SHA-256 Digest | Size (Bytes) | Verification Status |
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

### Contemporaneous Matched V6 Control Artifacts (`experiments/v7_matched_v6/`)
| Artifact File | SHA-256 Digest | Size (Bytes) | Verification Status |
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

## 16. Invariant & Firewall Verification

Automated invariant checking across all 165 tasks confirmed:
1. **Trigger Guard**: 0 `PASS` tasks and 0 empty-candidate tasks attempted repair.
2. **Attempt Limits**: Maximum `repair_generation_attempts` observed = 1 (budget $\le 1$). Maximum total `llm_generation_attempts` observed = 4 (budget $\le 5$). Zero unbounded loops.
3. **Tool Isolation**: Repair ran with text-only mode (`mode="NONE"`). Exactly 0 search calls and 0 Python calls were executed during repair.
4. **Fallback Integrity**: The 1 failed repair task preserved the pre-repair answer without mutation (`repair_answer_changed = False`).
5. **Scorer Firewall**: Zero ground-truth answers or scorer modules were accessed during agent execution. All evaluations were executed offline post-hoc.
6. **Privacy Integrity**: Zero proprietary API keys, service account secrets, or user tokens leaked into artifacts.

---

## 17. Scientific Synthesis & Handoff to V8

### Supported Scientific Conclusions
1. **Text-Only Repair Limitation**: In this benchmark run, the bounded targeted repair stage produced zero wrong-to-correct transitions and zero correct-to-wrong transitions, for a net within-run change of 0 correct tasks. Most SUSPECT triggers were evaluator-assigned EVIDENCE risks, while V7 was limited to reconsidering already-available evidence. The V7 repair stage was unable to acquire new evidence because active retrieval and tools were intentionally prohibited.
2. **Harm Avoidance in This Run**: Among the four initially-correct answers that were flagged `SUSPECT`, no regression was observed in this run ($0 / 4 = 0.00\%$). All four were protected by `KEEP` behavior. This observation is bounded by the small denominator ($N = 4$) and only two actual `REPLACE` actions.
3. **The Reach Bottleneck**: Candidate starvation remains the dominant architectural limitation: 73.11% of all system errors occurred upstream before a candidate answer existed.

### Technical Handoff Recommendations for V8
1. **V8 Scope**: Focus strictly on **Bounded Active Verification** (`V8 = Frozen V7 + one bounded active verification capability`).
2. **Research Question**: *When the passive evaluator marks an answer SUSPECT, does acquiring one targeted piece of new evidence or performing one targeted computation improve correction compared with text-only reconsideration?*
3. **Candidate Starvation Demarcation**: Candidate starvation must **NOT** be simultaneously redesigned in V8, preserving narrow single-variable experimental progression.

---

## 18. Final Freeze-Readiness Verdict

```text
FINAL VERDICT: READY_TO_FREEZE_WITH_DOCUMENTED_LIMITATIONS
```

**Recommended Next Step**: Terminal V7 Freeze Pass.
