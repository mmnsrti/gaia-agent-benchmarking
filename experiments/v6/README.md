# V6 — Self-Evaluation / Failure Detection

Status: AUDITED / READY FOR FREEZE WITH DOCUMENTED LIMITATIONS  
Parent Baseline: Frozen V5 (`v5-one-shot-verification`)  
Branch: `v6-self-evaluation-agent`  

See [`docs/V6_POST_BENCHMARK_AUDIT.md`](../../docs/V6_POST_BENCHMARK_AUDIT.md) for the complete scientific post-benchmark audit, failure and mechanism analysis, calibration diagnostics, and freeze review.

---

## 1. Research Definition

V6 evaluates bounded read-only self-evaluation following the frozen V5 agent pipeline:

```text
V6 = frozen V5 + one read-only Self-Evaluator generation
```

### Research Question
> Can a bounded self-evaluator reliably detect when the agent's non-empty final answer is likely incorrect, without modifying the answer or using additional tools?

### Single Intervention & Architecture
1. **Upstream Pipeline**: Identical to frozen V5 (search $\le 1$, file extraction $\le 1$, capability router selecting `DIRECT` vs `PYTHON`, worker, candidate eligibility guard, one-shot conservative verifier `KEEP`/`REVISE`).
2. **Read-Only Self-Evaluator**: If and only if the V5 final answer is non-empty, a single text-only LLM call evaluates the answer against existing evidence, producing a diagnostic assessment:
   ```text
   ASSESSMENT: PASS|SUSPECT
   RISK_TYPE: NONE|EVIDENCE|REASONING|CALCULATION|FORMAT|EXECUTION|UNKNOWN
   CONFIDENCE: 0.00–1.00
   ```
3. **Strict Invariants**:
   - **Answer Immutability**: The self-evaluator cannot modify or rewrite the answer (`self_eval_answer_unchanged = True` across all 165 tasks).
   - **Tool Isolation**: Zero tools, zero searches, zero Python executions, zero retries.
   - **Generation Bound**: Standard generation attempts $\le 4$ per task ($\le 3$ for V5 upstream + $\le 1$ for self-evaluator).
   - **Ground-Truth Firewall**: Evaluator receives no reference answers, scorer outputs, or ground truth at runtime. Diagnostic scoring is performed post-hoc.

---

## 2. Canonical Headline Results (GAIA 2023 Validation Set, 165 Tasks)

Evaluated against the contemporaneous matched frozen V5 control run:

| Benchmark Metric | Contemporaneous Matched V5 Control | Canonical V6 | Observed Delta |
| :--- | :---: | :---: | :---: |
| **Overall Accuracy** | **28.48%** (47 / 165) | **25.45%** (42 / 165) | **-3.03 pp (-5 tasks)** |
| Level 1 Accuracy | 47.17% (25 / 53) | 43.40% (23 / 53) | -3.77 pp (-2 tasks) |
| Level 2 Accuracy | 23.26% (20 / 86) | 20.93% (18 / 86) | -2.33 pp (-2 tasks) |
| Level 3 Accuracy | 7.69% (2 / 26) | 3.85% (1 / 26) | -3.85 pp (-1 task) |
| **Completion Rate** | **50.91%** (84 / 165) | **44.85%** (74 / 165) | **-6.06 pp (-10 tasks)** |

> **Critical Methodological Note on Delta**:
> The observed -5 task (-3.03 pp) difference between V6 and matched V5 is **observational and non-causal**. Because `self_eval_answer_unchanged == True` for all 165 tasks, the self-evaluator never modified an answer. The cross-run difference reflects upstream model sampling, routing differences, and provider completion behavior across independent runs.

---

## 3. Primary Diagnostic Evaluation (All 73 Eligible Answers)

On tasks where a non-empty final answer was produced (73 / 165):

| Diagnostic Metric | Value | Interpretation |
| :--- | :---: | :--- |
| **Diagnostic Coverage** | **100.0%** (73 / 73) | All eligible tasks received valid schema-compliant evaluations (0 parser failures) |
| **True Positives (TP)** | **14** | Erroneous answers correctly flagged as `SUSPECT` |
| **False Positives (FP)** | **2** | Correct answers mistakenly flagged as `SUSPECT` (false alarms) |
| **True Negatives (TN)** | **40** | Correct answers appropriately classified as `PASS` |
| **False Negatives (FN)** | **17** | Erroneous answers missed by evaluator (classified as `PASS`) |
| **Precision** | **87.50%** (14 / 16) | A `SUSPECT` verdict was highly reliable (87.5% empirical error rate) |
| **Recall (Eligible)** | **45.16%** (14 / 31) | Evaluator detected 45.2% of errors among eligible answers |
| **F1 Score** | **0.5957** | Balanced diagnostic score on eligible answers |
| **Specificity** | **95.24%** (40 / 42) | High preservation of correct candidate answers |
| **False Alarm Rate** | **4.76%** (2 / 42) | Low rate of erroneous suspicion on correct answers |
| **Missed Error Rate** | **54.84%** (17 / 31) | Over half of eligible errors passed without suspicion |
| **PASS Group Correctness (NPV)** | **70.18%** (40 / 57) | `PASS` indicates moderate reliability, not guaranteed correctness |
| **SUSPECT Group Error Rate** | **87.50%** (14 / 16) | Strong error concentration in `SUSPECT` group |
| **Overall Brier Score** | **0.2490** | Mean squared error on predicted error probabilities |

---

## 4. Key Scientific Findings & Limitations

1. **High Precision Warning Signal**: When the evaluator issues `SUSPECT`, it is accurate 87.5% of the time (14/16).
2. **Dominant Candidate Starvation**: 92 of 165 tasks (55.8%) produced no eligible candidate answer. These 92 tasks account for **74.80%** (92 / 123) of all system errors. The evaluator cannot diagnose what the upstream agent fails to generate.
3. **End-to-End System Recall**: Across the full 165 benchmark tasks, the self-evaluator flagged **11.38%** (14 / 123) of all system failures.
4. **False Negatives & High Confidence**: The 17 false negatives had high mean `PASS` confidence (0.947), indicating evaluator overconfidence on subtle factual, visual, or numerical errors.
5. **False Positives (2 tasks)**: Both occurred in Level 2 under `EVIDENCE` risk (`ad37a656-079a-49f9-a493-7b739c9167d1`, `366e2f2b-8632-4ef2-81eb-bc3877489217`) where the model doubted its own correct calculations.
6. **Risk Type Distribution**: `NONE`: 57, `EVIDENCE`: 11 (9 TP, 2 FP), `EXECUTION`: 4 (4 TP, 0 FP), `FORMAT`: 1 (1 TP, 0 FP). Categories `REASONING`, `CALCULATION`, and `UNKNOWN` were not assigned by the model.

---

## 5. Canonical Artifact Integrity

| Level | Detailed Eval (SHA-256) | Predictions (SHA-256) | Summary (SHA-256) |
| :---: | :---: | :---: | :---: |
| **L1** | `ed9a9a89985eb3b4fca95cbf03fd87abd1109139e933c7d8ced7777afe0fc940` | `b7cec9d1c5ef31418282d207b5066e5f8e81d65b50b2fff2af88b92139cdbb1e` | `33cd2088b9e07011f7d84ea5a23a74cd93034f68e8c55a33fed0f2d96a23a065` |
| **L2** | `0d691c98504f0bf08844b9adb124f50f627059764b62b2e436123b2f0c027898` | `7ea2fd941b1d22759dff9d105f3e5b925b4bfffa7448da51c207666ecceccf9d` | `9d2365ba559254e1edbd0f2053d373c734928dd2d434b7394640622314e8b555` |
| **L3** | `b808c6316c195586d1db6ee8d2fddee1906e3fc8031fba6f22910df16404ddda` | `1b2260b7c1f8817ca7fd7319bc30bedda19f8bfd19c9c94f783b0d79699db183` | `c6f900caed11074e728282b60702ce95e05c6f1b7e18c0fc236e6180c560c986` |

*Note on L3 predictions file: `predictions_level_3.jsonl` contains 11 lines due to an interrupted re-run, but canonical `detailed_eval_level_3.jsonl` contains the complete, authoritative evaluation for all 26 Level 3 tasks.*

