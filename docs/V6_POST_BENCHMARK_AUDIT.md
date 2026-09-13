# V6 Post-Benchmark Audit: Self-Evaluation and Failure Detection

**Status:** AUDITED / READY TO FREEZE WITH DOCUMENTED LIMITATIONS  
**POST-BENCHMARK AUDIT:** PASSED  
**FREEZE READINESS:** READY_TO_FREEZE_WITH_DOCUMENTED_LIMITATIONS  
**Evaluation Scope:** GAIA 2023 Validation Set (165 Tasks: 53 Level 1, 86 Level 2, 26 Level 3)  
**Parent Baseline:** Frozen V5 One-Shot Post-Answer Verification  
**Branch:** `v6-self-evaluation-agent`  
**Date:** September 2026  

---

## 1. Experiment Definition

Version 6 (V6) investigates bounded post-answer self-evaluation within the GAIA agent benchmarking framework. V6 is formally defined as:

$$\text{V6} = \text{Frozen V5} + \text{one bounded read-only post-answer self-evaluation generation}$$

The primary scientific research question is:
> *Can a bounded self-evaluator reliably detect when the agent's non-empty final answer is likely incorrect, without modifying the answer or using additional tools?*

The self-evaluator is strictly observational and diagnostic. It receives the task question, existing search/file evidence, compact execution metadata, and the frozen V5 final answer, emitting a structured output adhering to `self-evaluator-v1`:
```text
ASSESSMENT: PASS|SUSPECT
RISK_TYPE: NONE|EVIDENCE|REASONING|CALCULATION|FORMAT|EXECUTION|UNKNOWN
CONFIDENCE: 0.00–1.00
```
In this diagnostic evaluation, the error class is defined as the positive class:
- `SUSPECT`: Predicts that the candidate answer is incorrect (positive detection).
- `PASS`: Predicts that the candidate answer is correct (negative detection).

---

## 2. Frozen Parent Baseline

The parent baseline for V6 is **Frozen V5** (`experiments/v5/`), which fixed the architecture:
$$\text{V5} = \text{Frozen V4} + \text{one-shot conservative post-answer verification/revision}$$
Upstream components—including Tavily web search ($N \le 1$), deterministic file extraction ($N \le 1$), capability router (`DIRECT` vs `PYTHON`), route-specific workers, candidate eligibility guards, and the one-shot conservative verifier (`KEEP`/`REVISE`)—are completely preserved.

---

## 3. Single New Capability

The sole new capability evaluated in V6 is a single, bounded, text-only model generation that evaluates the reliability of the agent's final answer.
- **Read-Only**: V6 introduces no repair loop, no retry mechanism, no answer substitution, and no candidate suppression. The final answer emitted by V5 is returned verbatim.
- **Tool Isolation**: The evaluator runs with text-only context, disabling native function calling (`mode="NONE"`), with zero search calls and zero Python execution.
- **Budget Boundedness**: The generation attempt budget is capped at $\le 1$ for the self-evaluator, and total task generations are capped at $\le 4$.

---

## 4. Benchmark Protocol

The canonical evaluation was conducted on the full GAIA 2023 Validation set (165 tasks across Levels 1, 2, and 3):
- **Model**: `gemini-3.5-flash-lite` (temperature=None, thinking_level="medium", max_output_tokens=2048).
- **Inter-Task Delay**: 5.0 seconds between consecutive tasks.
- **Scorer**: Official GAIA evaluator (`gaia_question_scorer`), applied post-hoc.
- **Contemporaneous Matched Control**: A parallel run of frozen V5 was executed under identical environment conditions, software dependencies, and model settings.

---

## 5. Canonical Artifacts & Integrity Manifest

Canonical artifacts for V6 and the matched V5 control are stored in `experiments/`:

### Canonical V6 Files (`experiments/v6/`)
| File Name | SHA-256 Checksum | Size (Bytes) | Description |
| :--- | :--- | :---: | :--- |
| `detailed_eval_level_1.jsonl` | `ed9a9a89985eb3b4fca95cbf03fd87abd1109139e933c7d8ced7777afe0fc940` | 548,406 | All 53 Level 1 evaluation records |
| `detailed_eval_level_2.jsonl` | `0d691c98504f0bf08844b9adb124f50f627059764b62b2e436123b2f0c027898` | 864,634 | All 86 Level 2 evaluation records |
| `detailed_eval_level_3.jsonl` | `54770378a541584b84f854edb21b22630bff5d7cde1fa95f90e9b0248255e4d5` | 260,175 | All 26 Level 3 evaluation records |
| `predictions_level_1.jsonl` | `b7cec9d1c5ef31418282d207b5066e5f8e81d65b50b2fff2af88b92139cdbb1e` | 2,247,983 | Full runtime predictions for Level 1 |
| `predictions_level_2.jsonl` | `7ea2fd941b1d22759dff9d105f3e5b925b4bfffa7448da51c207666ecceccf9d` | 3,307,217 | Full runtime predictions for Level 2 |
| `predictions_level_3.jsonl` | `c799033d6f5ce95a7e3baedf94d29aa43e1e5f9d717da79f362b48b1704a4200` | 980,501 | Full runtime predictions for Level 3 (recovery replication) |
| `summary_level_1.json` | `33cd2088b9e07011f7d84ea5a23a74cd93034f68e8c55a33fed0f2d96a23a065` | 6,539 | Level 1 aggregate summary |
| `summary_level_2.json` | `9d2365ba559254e1edbd0f2053d373c734928dd2d434b7394640622314e8b555` | 6,459 | Level 2 aggregate summary |
| `summary_level_3.json` | `c48aa99fefc3cd19436246bf2c68bf3d52b14b1b1637040d89048a718d4532a0` | 6,256 | Level 3 aggregate summary |
| `config.proposed.json` | `990f3ed20fa908eb54cf62d586d135bb5d0f21921c9cc28300742c60993d04ca` | 5,651 | Evaluated configuration spec |
| `DESIGN.md` | `0cf1708a13e4da4d03dc9b1c06d0b40974c928ba689ae0fcfa002f3dc291bf58` | 5,238 | V6 specification & architecture |

### Contemporaneous Matched V5 Files (`experiments/v6_matched_v5/`)
| File Name | SHA-256 Checksum | Size (Bytes) |
| :--- | :--- | :---: |
| `detailed_eval_level_1.jsonl` | `37d65ca059b9b4157c4e737908a14c2dffa41ac7e6bd7b5133a11304889dacfd` | 526,553 |
| `detailed_eval_level_2.jsonl` | `322a2a4d00b3b90474ab54bd7694416d793ae700f1b672dcf1edc5a32ac08f70` | 799,716 |
| `detailed_eval_level_3.jsonl` | `9c6862e7c6080b7412e7d80349500cd5133dbedd771139cf716443e36584d6ff` | 257,784 |
| `predictions_level_1.jsonl` | `fe37a3de77d7948b1348651b53916cd708b03709a0977115ed5c33d0446b7b51` | 2,291,472 |
| `predictions_level_2.jsonl` | `677bc4d6f962cfa4a6d5331df803c28ac1f1920264796bc6afe3a58e984b2485` | 3,221,568 |
| `predictions_level_3.jsonl` | `9b6ca1e68746c8d627027ae78631b9ca55618fe6467fb30022a6ceec0433bece` | 1,045,290 |
| `summary_level_1.json` | `01a7fa83ea10ec2d00208730e1ad2cfac3ab29f960bde979f093285ccefd6d50` | 4,853 |
| `summary_level_2.json` | `f4bcad0580e92d3a16758201cde535677495839c6dd6a885417f0913a3f24b24` | 4,878 |
| `summary_level_3.json` | `15f87bcff68206cbecc53426ab7c7018b99fb46d67067cba6d0dc6ac75ce8c81` | 4,589 |

All JSON/JSONL artifacts parse cleanly with zero schema errors or duplicate task IDs across all levels. All prediction and evaluation record counts match the expected GAIA dataset split totals (53 Level 1, 86 Level 2, 26 Level 3 = 165 total tasks).

---

## 6. Canonical Answer Performance

Canonical task accuracy across GAIA validation levels:

| Evaluation Level | Total Tasks | V6 Correct | V6 Accuracy | V6 Completed | V6 Completion Rate |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 53 | 23 | 43.40% | 35 | 66.04% |
| **Level 2** | 86 | 18 | 20.93% | 35 | 40.70% |
| **Level 3** | 26 | 1 | 3.85% | 6 | 23.08% |
| **Overall** | **165** | **42** | **25.45%** | **76** | **46.06%** |

---

## 7. Matched V5 Performance & Comparison

Contemporaneous matched frozen V5 control run:

| Evaluation Level | Matched V5 Correct | Matched V5 Accuracy | Matched V5 Completed | Matched V5 Completion Rate |
| :--- | :---: | :---: | :---: | :---: |
| **Level 1** | 25 / 53 | 47.17% | 32 / 53 | 60.38% |
| **Level 2** | 20 / 86 | 23.26% | 33 / 86 | 38.37% |
| **Level 3** | 2 / 26 | 7.69% | 8 / 26 | 30.77% |
| **Overall** | **47 / 165** | **28.48%** | **73 / 165** | **44.24%** |

Observed Cross-Run Difference ($V6 - \text{Matched } V5$):
- **Accuracy Delta**:
  - **Level 1**: -2 tasks (-3.77 pp; 23 vs 25)
  - **Level 2**: -2 tasks (-2.33 pp; 18 vs 20)
  - **Level 3**: -1 task (-3.85 pp; 1 vs 2)
  - **Overall**: **-5 tasks (-3.03 pp; 42 vs 47)**
- **Completion Delta**:
  - **Level 1**: +3 tasks (+5.66 pp; 35 vs 32)
  - **Level 2**: +2 tasks (+2.33 pp; 35 vs 33)
  - **Level 3**: -2 tasks (-7.69 pp; 6 vs 8)
  - **Overall**: **+3 tasks (+1.82 pp; 76 vs 73)**

> [!NOTE]
> **Completed Count Reconciliation & Provenance of Historical References**:  
> In an earlier draft summary, Matched V5 completed counts were erroneously transcribed as 41 (L1), 37 (L2), and 6 (L3) totaling 84 (50.91%). Detailed investigation of canonical run records confirmed that the true completed counts (`completion_success == True`) in Level 1 and Level 2 are 32 and 33. Following the Level 3 recovery replication, Level 3 completed tasks stand at 6 for V6 and 8 for Matched V5, yielding canonical totals of 76 / 165 (46.06%) for V6 and 73 / 165 (44.24%) for Matched V5 (+3 tasks / +1.82 pp delta).

---

## 8. Cross-Run Comparability Caveat (Observational, Non-Causal)

> [!IMPORTANT]
> The observed cross-run delta of -5 tasks (-3.03 pp) is strictly **observational and non-causal**.

Because `self_eval_answer_unchanged == True` across all 165 tasks (Section 20), the self-evaluator had zero write access to candidate answers. The observed delta reflects run-to-run stochasticity in upstream LLM sampling, capability routing, tool execution, and provider completion behavior:
- **Both Correct**: 29 tasks
- **Both Wrong**: 105 tasks
- **V5 Wrong $\rightarrow$ V6 Correct** (Stochastic improvement): 13 tasks
- **V5 Correct $\rightarrow$ V6 Wrong** (Stochastic regression): 18 tasks
- **Net Difference**: $13 - 18 = -5$ tasks

This delta must never be reported as "accuracy damage caused by self-evaluation."

---

## 9. Diagnostic Confusion Matrices

Across all 75 eligible non-empty final answers, the evaluator emitted valid assessments for all 75 tasks (0 invalid, 0 failed):

### By Benchmark Level
| Level | Eligible | Valid | TP | FP | TN | FN |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 35 | 35 | 6 | 0 | 23 | 6 |
| **Level 2** | 34 | 34 | 5 | 2 | 16 | 11 |
| **Level 3** | 6 | 6 | 5 | 0 | 1 | 0 |
| **Overall** | **75** | **75** | **16** | **2** | **40** | **17** |

---

## 10. Overall Diagnostic Metrics

Evaluating error detection ($Y = 1$ if incorrect, $Y = 0$ if correct):

| Metric | Level 1 | Level 2 | Level 3 | Overall | Formula / Definition |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Diagnostic Coverage** | 100.0% | 100.0% | 100.0% | **100.0%** | $\text{Valid} / \text{Eligible}$ ($75 / 75$) |
| **Precision** | 100.0% | 71.43% | 100.0% | **88.89%** | $TP / (TP + FP) = 16 / 18$ |
| **Recall (Eligible)** | 50.00% | 31.25% | 100.0% | **48.48%** | $TP / (TP + FN) = 16 / 33$ |
| **F1 Score** | 0.6667 | 0.4348 | 1.0000 | **0.6274** | $2 \cdot P \cdot R / (P + R)$ |
| **Specificity** | 100.0% | 88.89% | 100.0% | **95.24%** | $TN / (TN + FP) = 40 / 42$ |
| **False Alarm Rate (FAR)** | 0.00% | 11.11% | 0.00% | **4.76%** | $FP / (TN + FP) = 2 / 42$ |
| **Missed Error Rate (MER)** | 50.00% | 68.75% | 0.00% | **51.52%** | $FN / (TP + FN) = 17 / 33$ |
| **PASS Group Correctness (NPV)** | 79.31% | 59.26% | 100.0% | **70.18%** | $TN / (TN + FN) = 40 / 57$ |
| **SUSPECT Group Error Rate** | 100.0% | 71.43% | 100.0% | **88.89%** | $TP / (TP + FP) = 16 / 18$ |
| **Brier Diagnostic Score** | 0.1739 | 0.3555 | 0.0059 | **0.2428** | Mean squared error of predicted error prob |

---

## 11. Diagnostic Coverage

Diagnostic coverage was **100.0%** (75 / 75 eligible tasks).
- Parser failure count: **0**
- Malformed schema count: **0**
- Timeout / exception count during self-evaluation: **0**
- Unparseable confidence count: **0**

Every eligible non-empty answer received a syntactically and semantically valid diagnostic label.

---

## 12. Candidate-Starvation Analysis

A critical architectural finding of V6 is candidate starvation:

```mermaid
flowchart TD
    Total["Total Tasks (165)"]
    Total --> Eligible["Eligible Answers (75 / 45.5%)"]
    Total --> Ineligible["Ineligible Candidates (90 / 54.5%)"]
    
    Eligible --> EC["Correct Answers (42)"]
    Eligible --> EW["Incorrect Answers (33)"]
    
    EW --> TP["Flagged SUSPECT: TP (16)"]
    EW --> FN["Missed as PASS: FN (17)"]
    
    EC --> TN["Correctly PASS: TN (40)"]
    EC --> FP["False Alarm: FP (2)"]
    
    Ineligible --> Starved["Starved Upstream Failures (90)"]
    
    style Starved fill:#ffcccc,stroke:#cc0000
    style TP fill:#ccffcc,stroke:#00cc00
    style FN fill:#fff0cc,stroke:#ff9900
    style FP fill:#ffe6e6,stroke:#ff6666
```

### Breakdown of System Errors
- **Total System Correct**: 42 tasks (25.45%)
- **Total System Errors**: 123 tasks (74.55%)
- **Upstream / Starvation Errors**: 90 tasks (73.17% of all system errors)
- **Reachable Errors**: 33 tasks (26.83% of all system errors)
- **Actually Flagged Errors (TP)**: 16 tasks (13.01% of all system errors)

> [!WARNING]
> While the self-evaluator achieved a diagnostic recall of **48.48%** on eligible answers, its **end-to-end failure detection rate across the entire benchmark was only 13.01%** (16 / 123).
> **73.17% of all benchmark failures occurred before the self-evaluator had an answer to evaluate.**

---

## 13. Risk-Type Analysis

All 75 valid assessments strictly adhered to schema-assessment consistency rules:
- `PASS` $\rightarrow$ `RISK_TYPE: NONE` (57 tasks)
- `SUSPECT` $\rightarrow$ non-`NONE` risk type (18 tasks)

### Empirical Risk Distribution & Efficacy
| Assigned Risk Type | Count | Actual Correct | Actual Incorrect | True Positives | False Positives | Empirical Error Rate | Mean Conf | Median Conf |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **NONE** (`PASS`) | 57 | 40 | 17 | 0 | 0 | 29.82% | 0.9939 | 1.0000 |
| **EVIDENCE** (`SUSPECT`) | 12 | 2 | 10 | 10 | 2 | 83.33% | 0.9042 | 0.9000 |
| **EXECUTION** (`SUSPECT`) | 4 | 0 | 4 | 4 | 0 | 100.0% | 1.0000 | 1.0000 |
| **FORMAT** (`SUSPECT`) | 1 | 0 | 1 | 1 | 0 | 100.0% | 0.8500 | 0.8500 |
| **REASONING** (`SUSPECT`) | 1 | 0 | 1 | 1 | 0 | 100.0% | 0.9900 | 0.9900 |
| **CALCULATION** | 0 | — | — | — | — | — | — | — |
| **UNKNOWN** | 0 | — | — | — | — | — | — | — |

*Note: Risk types represent the evaluator's diagnostic classification, not ground-truth causal attribution. Two defined categories (`CALCULATION`, `UNKNOWN`) did not appear in this run.*

---

## 14. Confidence and Calibration Analysis

Each assessment was mapped to a predicted error probability:
$$P(\text{error}) = \begin{cases} \text{confidence} & \text{if assessment is SUSPECT} \\ 1.0 - \text{confidence} & \text{if assessment is PASS} \end{cases}$$

- **Overall Brier Diagnostic Score**: **0.2428** (L1: 0.1739, L2: 0.3555, L3: 0.0059).
- **Mean Error Probability for Correct Answers** ($n=42$): **0.0440**
- **Mean Error Probability for Incorrect Answers** ($n=33$): **0.4603**

### Confidence by Diagnostic Outcome
| Outcome Category | Count | Mean Confidence | Median Confidence | Min Confidence | Max Confidence |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **True Positives (TP)** | 16 | 0.9369 | 0.9500 | 0.8000 | 1.0000 |
| **False Positives (FP)** | 2 | 0.8500 | 0.9000 | 0.8000 | 0.9000 |
| **True Negatives (TN)** | 40 | 0.9963 | 1.0000 | 0.9500 | 1.0000 |
| **False Negatives (FN)** | 17 | 0.9882 | 1.0000 | 0.9000 | 1.0000 |

### Calibration Bins
| Probability Bin | Count | Mean Pred Error Prob | Observed Error Rate | Interpretation |
| :---: | :---: | :---: | :---: | :--- |
| **[0.0, 0.2)** | 57 | 0.0061 | 29.82% (17 / 57) | Under-calibrated due to 17 false negatives ($P \le 0.10$) |
| **[0.2, 0.4)** | 0 | — | — | Empty |
| **[0.4, 0.6)** | 0 | — | — | Empty |
| **[0.6, 0.8)** | 0 | — | — | Empty |
| **[0.8, 1.0]** | 18 | 0.9272 | 88.89% (16 / 18) | Well-calibrated high-confidence SUSPECT alerts |

> [!NOTE]
> The primary calibration failure stems from false negatives: the model emits `PASS` with high confidence (mean 0.988) on 17 erroneous answers, yielding a 29.82% error rate in the lowest predicted-error bucket.

---

## 15. Attachment vs Non-Attachment Diagnostics

| Slice | Tasks | Accuracy | Eligible | TP | FP | TN | FN | Precision | Recall | F1 | Specificity | Starvation Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Attachment** | 38 | 15.79% (6) | 7 | 0 | 1 | 5 | 1 | 0.00% | 0.00% | Undefined | 83.33% | **81.58%** (31/38) |
| **Non-Attachment** | 127 | 28.35% (36) | 68 | 16 | 1 | 35 | 16 | 94.12% | 50.00% | 0.6531 | 97.22% | **46.46%** (59/127) |

On attachment tasks, severe candidate starvation (81.58%) left only 7 eligible answers. The evaluator produced 0 true positives, 1 false positive, 5 true negatives, and 1 false negative.

---

## 16. DIRECT vs PYTHON Diagnostic Analysis

| Track | Tasks | Accuracy | Eligible | TP | FP | TN | FN | Precision | Recall | F1 | Specificity | Starvation Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **DIRECT** | 66 | 50.00% (33) | 64 | 16 | 2 | 31 | 15 | 88.89% | 51.61% | 0.6530 | 93.94% | **3.03%** (2/66) |
| **PYTHON** | 99 | 9.09% (9) | 11 | 0 | 0 | 9 | 2 | Undefined | 0.00% | Undefined | 100.0% | **88.89%** (88/99) |

### PYTHON Route Breakdown
- **Executed ($n=18$)**: 11 eligible answers, 9 correct, 2 incorrect. Evaluator issued `PASS` on all 11 (TP=0, FP=0, TN=9, FN=2).
- **Not Executed ($n=81$)**: 0 eligible answers (81 / 81 starvation errors caused by fallback/syntax/policy rejections).
- **Correlation with Execution Risk**: All 4 `EXECUTION` risk diagnoses occurred on the `DIRECT` track, where workers leaked reasoning text or formatting into the final answer. None occurred on successfully executed Python tasks.

---

## 17. Representative Task-Level Case Studies

### A. False Positives (Evaluator flagged SUSPECT, but answer was CORRECT; $n=2$)
1. **Task `ad37a656-079a-49f9-a493-7b739c9167d1`** (Level 2, DIRECT):
   - Pred: `'18'` | GT: `'18'` | Conf: `0.90` | Risk: `EVIDENCE`
   - Mechanism: The agent retrieved the correct member count '18', but the self-evaluator expressed skepticism about whether the web search results were complete, issuing a false alarm.
2. **Task `366e2f2b-8632-4ef2-81eb-bc3877489217`** (Level 2, DIRECT):
   - Pred: `'4'` | GT: `'4'` | Conf: `0.80` | Risk: `EVIDENCE`
   - Mechanism: The agent calculated the count '4', but the self-evaluator questioned the evidence sufficiency.

### B. High-Confidence False Negatives (Evaluator flagged PASS, but answer was WRONG; $n=17$)
1. **Task `e8cb5b03-41e0-4086-99e5-f6806cd97211`** (Level 2, PYTHON):
   - Pred: `'short rib'` | GT: `'shrimp'` | Conf: `1.00` | Risk: `NONE`
   - Mechanism: Python script executed cleanly and produced 'short rib'. The evaluator saw successful code execution and uncritically validated the output.
2. **Task `05407167-39ec-4d3a-a234-73a9120c325d`** (Level 2, DIRECT):
   - Pred: `'Replace All'` | GT: `'Format Document'` | Conf: `1.00` | Risk: `NONE`
   - Mechanism: Factual error regarding VS Code keyboard shortcuts. Evaluator shared the worker's misconception.
3. **Task `08cae58d-4084-4616-b6dd-dd6534e4825b`** (Level 2, DIRECT):
   - Pred: `'1983'` | GT: `'2018'` | Conf: `1.00` | Risk: `NONE`
   - Mechanism: Retrieved publication date was incorrect; evaluator failed to cross-check chronology.

### C. True Positives (Evaluator flagged SUSPECT and answer was WRONG; $n=16$)
1. **Evidence Risk ($n=10$)**:
   - `305ac316-eef6-4446-960a-92d80d542f82` (Level 1, DIRECT, Conf 1.0): Pred `'Wojtek'`, GT `'Wojciech'`. Evaluator recognized diminutive vs formal naming mismatch.
   - `3f57289b-8c60-48be-bd80-01f8099ca449` (Level 1, DIRECT, Conf 1.0): Pred `'525'`, GT `'519'`. Evaluator spotted numerical ambiguity in search snippets.
   - `8131e2c0-0083-4265-9ce7-78c2d568425d` (Level 3, DIRECT, Conf 0.90): Pred `'101.4, 98.5'`, GT `'98.5'`. Evaluator identified ambiguity in performance comparison figures.
   - `ad2b4d70-9314-4fe6-bfbe-894a45f6055f` (Level 3, DIRECT, Conf 0.95): Pred `'infinity'`, GT `'1000000000000'`. Evaluator identified invalid numerical string.
   - `0512426f-4d28-49f0-be77-06d05daec096` (Level 3, DIRECT, Conf 0.85): Pred `'250 million'`, GT `'65 million'`. Evaluator flagged discrepancy in extinction timeline dates.
2. **Execution Risk ($n=4$)**:
   - `7673d772-ef80-4f0f-a602-1bf4485c9b43` (Level 1, DIRECT): Pred `'" format.'`, GT `'inference'`. Evaluator detected worker truncation.
   - `3627a8be-a77f-41bb-b807-7e1bd4c0ebdf` (Level 2, DIRECT): Leaked internal reasoning block.
   - `e2d69698-bc99-4e85-9880-67eaccd66e6c` (Level 2, DIRECT): Leaked unformatted scratchpad text.
   - `ebbc1f13-d24d-40df-9068-adcf735b4240` (Level 3, DIRECT, Conf 1.0): Leaked internal conjecture instead of single word.
3. **Format Risk ($n=1$)**:
   - `dc22a632-937f-4e6a-b72f-ba0ff3f5ff97` (Level 1, DIRECT, Conf 0.85): Pred `'Roadfood'`, GT full title. Evaluator caught informal title abbreviation.
4. **Reasoning Risk ($n=1$)**:
   - `9e1fc53b-46ff-49a1-9d05-9e6faac34cc5` (Level 3, DIRECT, Conf 0.99): Pred `'Druid, Hunter, Mage, Paladin, Priest'`, GT `'Death Knight, Druid, Mage, Paladin, Priest'`. Evaluator caught class composition deduction error.

---

## 18. V5 Verifier Behavior Inside V6

Inside the V6 run, the upstream V5 verifier performed as follows:
- **Eligible Tasks**: 75
- **KEEP Decisions**: 74 (98.67%)
- **REVISE Decisions**: 1 (1.33%)
- **Transitions**:
  - **Improvement ($0 \rightarrow 1$)**: 1 task (`c714ab3a-da30-4603-bacd-d008800188b9`, Level 1, revised `'0'` $\rightarrow$ `'100'`, correct=True, self-eval issued `PASS`, conf=1.0)
  - **Regression ($1 \rightarrow 0$)**: 0 tasks
  - **Stable Correct**: 41 tasks
  - **Stable Failure**: 123 tasks

The V5 verifier acted as an **editor** (KEEP/REVISE). In contrast, the V6 self-evaluator acted purely as an **inspector** (PASS/SUSPECT) and never altered answers.

---

## 19. V6 Self-Evaluator Behavior

The self-evaluator operated downstream of V5 verification:
- Evaluated candidates: 75
- Output `PASS`: 57 (76.00%)
- Output `SUSPECT`: 18 (24.00%)
- Runtime exceptions / provider failures: 0
- Self-evaluator retries: 0

---

## 20. Answer Immutability Audit

Answer immutability was verified across all 165 tasks:
- `self_eval_answer_unchanged == True` for all 165 tasks (**0 violations**).
- Pre-self-eval answer equals final answer string verbatim (**0 mismatches**).
- Summary improvement count: `0`
- Summary regression count: `0`

---

## 21. Generation-Budget and Boundedness Audit

- Maximum generation attempts per task: **$\le 4$** (**0 violations**).
- Evaluator generation attempts on eligible tasks: exactly **1** (**0 violations**).
- Evaluator generation attempts on ineligible tasks: exactly **0** (**0 violations**).
- Evaluator tool calls: **0** (no search, no Python, no file extraction).
- Evaluator retries: **0**.

---

## 22. Scorer and Ground-Truth Firewall Audit

- Prompt inspection confirms the evaluator received only question text, existing search/file evidence, compact execution status, and candidate answer.
- Ground-truth answers, reference labels, and official scorer outputs were completely absent from the runtime agent.
- Correctness labels were joined strictly in post-hoc evaluation after benchmark completion. Zero leakage detected.

---

## 23. Provider & Operational Health Analysis

| Parameter | Canonical V6 | Matched V5 |
| :--- | :---: | :---: |
| **Tavily Search Success Rate** | **100.0%** (165 / 165) | **100.0%** (165 / 165) |
| **Router Fallbacks** | 1 / 165 | 1 / 165 |
| **Python Requested** | 99 | 99 |
| **Python Executed** | 18 | 18 |
| **Python Success** | 11 | 14 |
| **Python Fallback / Unexecuted** | 88 | 88 |
| **Completion Failures** | 89 / 165 | 92 / 165 |

---

## 24. Invalid Initial Matched-V5 Level 3 Run

An initial matched-V5 Level 3 benchmark execution suffered a provider infrastructure collapse:
- **Completed**: 0 / 26
- **Correct**: 0 / 26
- **Router Fallbacks**: 25 / 26 (96.15%)
- **Average Latency**: ~1.79s
- **Average Tokens**: None

This invalid run was quarantined in `experiments/v6_matched_v5_invalid_l3_provider_collapse/`. A healthy rerun was completed achieving 6/26 completed, 2/26 correct, 0 router fallbacks, and 3445.3 average tokens. The quarantined run is preserved as non-canonical operational-failure evidence and does not contaminate canonical matched metrics.

---

## 25. Artifact Integrity & Provenance of Level-3 Recovery Replication

### A. The Level-3 Overwrite Incident
During benchmark execution, the initial Level-3 evaluation completed successfully (26 tasks, 1 correct, 4 completed). The summary was committed to git in commit `e6dce61`. However, because `.gitignore` excluded `predictions*.jsonl`, the predictions log was not versioned. A subsequent execution command with `--no-resume` unlinked the predictions file and was aborted at task 11, leaving `predictions_level_3.jsonl` truncated to 11 records.

### B. Recovery Hierarchy Evaluation
Under strict benchmark governance:
- **Option A (Exact Original File Recovery)**: Impossible (untracked file was overwritten in place).
- **Option B (Lossless Reconstruction from Local Logs)**: Impossible without fabricating provider API traces (`raw_response`, `router_prompt`, `worker_raw_response`, provider `response_id`, `run_id`, `timestamp`, `finish_reason`). Fabricating traces violates scientific integrity.
- **Option C (Strict Freeze Blocker)**: Triggered. Terminal freeze was blocked, and the original evidence was archived.

### C. Archiving Historical Evidence
The complete original evaluation data and truncated predictions file were preserved in:
```text
experiments/v6_original_l3_pre_recovery/
├── predictions_level_3.jsonl (INCOMPLETE — 11/26 RECORDS, SHA-256: 1b2260b7...)
├── detailed_eval_level_3.jsonl (COMPLETE — 26 RECORDS, SHA-256: b808c631...)
└── summary_level_3.json (COMPLETE — 26 TASKS, SHA-256: c6f900ca...)
```

### D. Strictly Predeclared Recovery Replication
Under the scientific rule that *the first operationally healthy recovery run is accepted regardless of score*, a recovery replication was executed once in dedicated namespaces:
- `experiments/v6_l3_recovery/` (V6 Level 3)
- `experiments/v6_l3_recovery_matched_v5/` (Matched frozen V5 Level 3)

Both runs passed all operational health gates (0 router fallbacks, 100% search success rate, full provider telemetry).

### E. Promotion Audit
The recovery artifacts passed all 10 promotion criteria:
1. 26 prediction records in both V6 and Matched V5.
2. 26 detailed evaluation records in both.
3. 26 summary tasks in both.
4. Identical task-ID sets matching GAIA Level 3 validation.
5. Healthy provider telemetry and zero fallback collapses.
6. Zero V6 invariant violations.
7. Healthy matched V5 run.
8. Complete namespace isolation prior to promotion.
9. Zero API keys or secrets in logs.
10. Zero duplicate task IDs.

Following this audit, the recovery artifacts were promoted to canonical `experiments/v6/` and `experiments/v6_matched_v5/`.

---

## 26. Scientific Interpretation

### Supported Conclusions
1. **High-Precision Warning Signal**: On eligible non-empty answers, `SUSPECT` provides an 88.89% reliable error alert (16 TP, 2 FP).
2. **PASS Is Not a Guarantee**: 29.82% of `PASS` evaluations were actually incorrect (17 FN), with high evaluator overconfidence (mean confidence 0.988).
3. **Upstream Candidate Starvation Dominates**: 73.17% of all system failures occurred before self-evaluation could run. Full-system reliability is bottlenecked by upstream candidate production, not downstream diagnostic discrimination.

### Unsupported Claims (Explicitly Refuted)
- V6 did NOT cause the observed -3.03 pp delta vs matched V5.
- V6 does NOT solve agent self-correction.
- Level 3 failure detection is NOT proven perfect.
- V6 does NOT have high end-to-end recall (13.01% over all benchmark errors).

---

## 27. Implications for V7 (Targeted Repair)

1. **Repair Trigger**: High precision of `SUSPECT` (88.89%) suggests that a future V7 repair stage should trigger exclusively on `SUSPECT`.
2. **Addressing False Positives**: Because 11.11% of `SUSPECT` verdicts are false alarms, repair mechanisms must include validation to avoid regressing correct answers.
3. **Addressing Candidate Starvation**: Post-answer repair cannot fix the 73.17% of failures caused by missing candidates; a separate upstream fallback recovery mechanism is required.

---

## 28. Freeze-Readiness Verdict

### **Verdict: READY_TO_FREEZE_WITH_DOCUMENTED_LIMITATIONS**

- **Blocking Criteria Status**: **PASSED**.
  - All 18 canonical artifacts (V6 and matched V5 across Levels 1, 2, 3) are 100% complete and verified with SHA-256 checksums.
  - Zero answer mutations, zero tool calls by evaluator, zero generation cap violations, zero ground-truth leaks.
  - 100% schema validity on all 75 eligible answers.
  - Zero blocking issues remain.

- **Documented Limitations**:
  1. Candidate starvation rate of 73.17% (90 / 123 errors).
  2. Small Level 3 sample ($n=6$ eligible answers).
  3. Observational cross-run delta of -5 tasks (-3.03 pp) reflecting upstream stochasticity.
  4. Quarantined invalid matched-V5 L3 run preserved as operational failure evidence.
  5. Level 3 recovery replication provenance fully documented, with historical evidence archived in `experiments/v6_original_l3_pre_recovery/`.
