# V6 — Self-Evaluation / Failure Detection

Status: FROZEN  
Branch: `v6-self-evaluation-agent`  
Parent Baseline: Frozen V5 (`v5-one-shot-verification`)  
Date: September 2026  

---

## 1. Research Definition & Capability Boundary

```text
V6 = frozen V5 + one bounded read-only post-answer self-evaluation generation
```

The primary research question evaluated by V6 is:
> *Can a bounded self-evaluator reliably detect when the agent's non-empty final answer is likely incorrect, without modifying the answer or using additional tools?*

### What V6 Does
- Inspects the candidate answer emitted by the frozen V5 upstream pipeline.
- Emits a structured diagnostic label adhering to `self-evaluator-v1`:
  ```text
  ASSESSMENT: PASS|SUSPECT
  RISK_TYPE: NONE|EVIDENCE|REASONING|CALCULATION|FORMAT|EXECUTION|UNKNOWN
  CONFIDENCE: 0.00–1.00
  ```
- Evaluates errors as the positive detection class (`SUSPECT` indicates a predicted failure).
- Operates strictly downstream and post-hoc, logging telemetry alongside the unchanged answer.

### What V6 Does NOT Do
- Does **NOT** repair, revise, or edit candidate answers.
- Does **NOT** retry failed worker generations or re-execute code.
- Does **NOT** execute web searches or make tool calls during evaluation.
- Does **NOT** execute Python code or access local files during evaluation.
- Does **NOT** possess access to ground-truth answers, reference labels, or official scorer internals.
- Does **NOT** alter the final answer returned to the user (`self_eval_answer_unchanged == True`).

---

## 2. Execution Flow & Architecture

```text
GAIA Question + Optional Attachment File
     ↓
ONE Tavily Search (Original Question as Query, Capped at 1,500 Chars, N ≤ 1)
     ↓
FileTool (Deterministic local extraction inherited from frozen V2/V3/V4/V5, N ≤ 1)
     ↓
Stage 1: Frozen Router Generation (`capability-router-v1`, mode="NONE", N ≤ 1)
     ↓
Deterministic Route Parser (Regex validation, deterministic fallback to DIRECT)
     ↓
Stage 2: Route-Specific Worker Dispatch (`router-direct-worker-v1` or `router-python-worker-v1`, mode="NONE", N ≤ 1)
     │
     ├── [Route == DIRECT] → Generates direct response text (`FINAL: <answer>`)
     │
     └── [Route == PYTHON] → Emits ```python code block executed in local sandbox
                             (Timeout 15.0s, Cap 20k chars, Static AST Validation, N ≤ 1)
     ↓
Candidate Answer Extraction (`pre_verification_answer`)
     ↓
Candidate Eligibility Guard
     ├── [Empty Candidate / Upstream Failure]
     │        ↓
     │   Verifier Bypassed Immediately (0 verifier LLM calls)
     │        ↓
     │   Final Answer = Empty
     │
     └── [Candidate Present (Non-Empty)]
              ↓
         Stage 3: One-Shot Verifier Generation (`answer-verifier-v1`, mode="NONE", N ≤ 1)
              ↓
         Deterministic Verdict Parser (`VERDICT: KEEP` or `VERDICT: REVISE with FINAL: <answer>`)
              ↓
         Post-Verification Candidate Answer
              ↓
         Stage 4: Read-Only Self-Evaluation Guard
              ├── [Empty Answer] → Self-Evaluation Bypassed (0 evaluator LLM calls)
              │
              └── [Non-Empty Answer]
                       ↓
                  One-Shot Self-Evaluator Generation (`self-evaluator-v1`, mode="NONE", N ≤ 1)
                  (Inputs: Question, Evidence, File Context, Final Answer, Compact Status)
                       ↓
                  Deterministic Diagnostic Assessment (`PASS` / `SUSPECT`)
                       ↓
         Final Answer Emitted Verbatim (100% Preserved)
```

---

## 3. Strict Frozen Invariants

The V6 architecture strictly enforces the following invariants:
- **Answer Immutability**: `self_eval_answer_unchanged == True` across all 165 tasks (zero answer modifications).
- **Read-Only Scope**: The evaluator has zero tool access, executes zero searches, runs zero Python subprocesses, and makes zero API queries.
- **Single Evaluation Budget**: At most 1 self-evaluator generation attempt per task ($N \in \{0, 1\}$).
- **Generation Cap**: Maximum 4 LLM generation attempts per task across the entire pipeline.
- **Empty-Candidate Safety**: Empty candidate answers bypass self-evaluation immediately (0 evaluator attempts).
- **Ground-Truth Isolation**: Runtime evaluation operates behind a strict firewall; correctness scoring is conducted strictly post-hoc.
- **Native Tool Mode**: Native function calling is disabled (`mode="NONE"`).

---

## 4. Canonical Benchmark Results

Evaluated on the full GAIA 2023 Validation set (165 tasks across Levels 1, 2, and 3):

### V6 Task Performance
| Level | Total Tasks | Correct | Accuracy | Completed | Completion Rate |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 53 | 23 | 43.40% | 35 | 66.04% |
| **Level 2** | 86 | 18 | 20.93% | 35 | 40.70% |
| **Level 3** | 26 | 1 | 3.85% | 6 | 23.08% |
| **Overall** | **165** | **42** | **25.45%** | **76** | **46.06%** |

### Contemporaneous Matched Frozen V5 Control
| Level | Total Tasks | Matched V5 Correct | Matched V5 Accuracy | Matched V5 Completed | Matched V5 Completion Rate |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 53 | 25 | 47.17% | 32 | 60.38% |
| **Level 2** | 86 | 20 | 23.26% | 33 | 38.37% |
| **Level 3** | 26 | 2 | 7.69% | 8 | 30.77% |
| **Overall** | **165** | **47** | **28.48%** | **73** | **44.24%** |

### Observed Cross-Run Differences ($V6 - \text{Matched } V5$)
- **Accuracy Delta**: **-5 tasks (-3.03 pp)**
  - Level 1: -2 tasks (-3.77 pp; 23 vs 25)
  - Level 2: -2 tasks (-2.33 pp; 18 vs 20)
  - Level 3: -1 task (-3.85 pp; 1 vs 2)
- **Completed Delta**: **+3 tasks (+1.82 pp)**
  - Level 1: +3 tasks (+5.66 pp; 35 vs 32)
  - Level 2: +2 tasks (+2.33 pp; 35 vs 33)
  - Level 3: -2 tasks (-7.69 pp; 6 vs 8)

> [!IMPORTANT]
> **Observational, Non-Causal Nature of Delta**:  
> Because `self_eval_answer_unchanged == True` for all 165 tasks, the self-evaluator had zero write access to candidate answers. The observed cross-run difference of -5 tasks (-3.03 pp) reflects run-to-run stochasticity in upstream LLM sampling, capability routing, tool execution, and provider completion behavior across separate runs (29 tasks were correct in both, 105 wrong in both, 13 improved V5$\rightarrow$V6, and 18 regressed V5$\rightarrow$V6). It must never be cited as "accuracy degradation caused by self-evaluation."

---

## 5. Primary Diagnostic Performance (75 Eligible Tasks)

On tasks where a non-empty final answer was produced (75 / 165):

$$\begin{array}{rcc}
& \textbf{Actual Error } (Y=1) & \textbf{Actual Correct } (Y=0) \\
\textbf{Flagged SUSPECT } (\hat{Y}=1): & TP = 16 & FP = 2 \\
\textbf{Flagged PASS } (\hat{Y}=0): & FN = 17 & TN = 40
\end{array}$$

| Diagnostic Metric | Value | Interpretation |
| :--- | :---: | :--- |
| **Diagnostic Coverage** | **100.0%** (75 / 75) | All eligible tasks evaluated with valid schema compliance (0 parser failures) |
| **Precision** | **88.89%** (16 / 18) | High-precision alarm: when `SUSPECT` is issued, the answer is incorrect 88.9% of the time |
| **Recall (Eligible)** | **48.48%** (16 / 33) | Evaluator detected roughly half of errors among generated candidate answers |
| **F1 Score** | **0.6274** | Harmonic mean of diagnostic precision and recall |
| **Specificity** | **95.24%** (40 / 42) | High preservation of correct candidate answers |
| **False Alarm Rate (FAR)** | **4.76%** (2 / 42) | Low rate of erroneous suspicion on correct answers |
| **Missed Error Rate (MER)** | **51.52%** (17 / 33) | Roughly half of eligible errors escaped without detection |
| **PASS Group Correctness (NPV)** | **70.18%** (40 / 57) | `PASS` indicates moderate reliability, not guaranteed correctness |
| **SUSPECT Group Error Rate** | **88.89%** (16 / 18) | High concentration of true errors in the `SUSPECT` bucket |
| **Overall Brier Diagnostic Score** | **0.2428** | Mean squared error of predicted error probability (L1: 0.1739, L2: 0.3555, L3: 0.0059) |

---

## 6. Candidate Starvation: The Dominant System Bottleneck

A central scientific finding of V6 is candidate starvation:

```text
Total Benchmark Tasks:                165
├── Eligible Answers Evaluated:        75 (45.45%)
│    ├── Correct Answers:              42
│    └── Erroneous Answers:            33
│         ├── Flagged as SUSPECT (TP): 16
│         └── Missed as PASS (FN):     17
│
└── Ineligible (No Candidate Answer):  90 (54.55%)
     └── Starvation System Errors:     90 (100.0% failure)
```

- **Total System Errors**: 123 tasks (74.55% of benchmark)
- **Upstream Starvation Errors**: 90 tasks (**73.17%** of all system errors)
- **Reachable Errors**: 33 tasks (26.83% of all system errors)
- **Actually Flagged Errors (TP)**: 16 tasks (**13.01%** end-to-end failure detection across full benchmark)

> [!WARNING]
> While diagnostic recall on eligible answers is **48.48%**, the end-to-end system failure detection rate is **13.01%**. Post-answer self-evaluation is fundamentally bottlenecked by upstream candidate production: **73.17% of all benchmark failures occurred before self-evaluation had an answer to evaluate**.

---

## 7. Level-3 Recovery Replication Provenance

The canonical Level-3 evidence reflects a strictly predeclared recovery replication:
1. **Original Execution**: At 12:02 PM Sep 13, 2026, Level 3 ran to completion (26 tasks, 1 correct, 4 completed). The summary was committed to git in commit `e6dce61`.
2. **Artifact Truncation**: Because `.gitignore` excluded `predictions*.jsonl`, the predictions log was not versioned. A subsequent unintended rerun with `--no-resume` deleted the file and was terminated at task 11, leaving 11 records.
3. **Recovery Hierarchy Evaluation**: Exact original recovery (Option A) and lossless reconstruction (Option B) were impossible without fabricating API generation traces. Under benchmark governance, Option C blocked freeze.
4. **Archiving**: The original incomplete predictions log and evaluation records were permanently archived in `experiments/v6_original_l3_pre_recovery/`.
5. **Predeclared Replication**: Under the invariant that *the first operationally healthy recovery run is accepted regardless of score*, one complete Level-3 recovery attempt was executed in `experiments/v6_l3_recovery/` and `experiments/v6_l3_recovery_matched_v5/`.
6. **Promotion**: Both runs passed all operational health gates (0 router fallbacks, 100% search success, full provider telemetry) and all 10 promotion audit gates, and were promoted to canonical `experiments/v6/` and `experiments/v6_matched_v5/`.

---

## 8. Documented Scientific Limitations

1. **Dominant Candidate Starvation**: Post-answer inspection cannot address the 73.17% of system failures caused by missing or uncompleted candidate answers.
2. **High-Confidence False Negatives**: On 17 incorrect answers, the evaluator emitted `PASS` with high confidence (mean 0.988), failing to detect subtle numerical, chronological, or visual errors.
3. **Small Level-3 Eligible Sample**: Diagnostic accuracy on Level 3 reflects only 6 eligible answers (5 TP, 0 FP, 1 TN, 0 FN) and cannot be generalized without caveats.
4. **Observational Cross-Run Variation**: The -3.03 pp (-5 tasks) difference between V6 and matched V5 reflects upstream stochasticity rather than evaluator intervention.
5. **Quarantined Infrastructure Failure**: An initial matched-V5 Level-3 run suffered a provider collapse (0/26 completed, 25/26 router fallbacks) and was quarantined in `experiments/v6_matched_v5_invalid_l3_provider_collapse/`.

---

## 9. Handoff to V7 (Targeted Repair)

V6 concludes the self-evaluation diagnostic phase. The recommended research direction for V7 is:
$$\text{V7} = \text{Frozen V6} + \text{bounded targeted repair triggered exclusively on } \text{SUSPECT}$$

### Lessons for V7 Design:
1. **Trigger Exclusively on `SUSPECT`**: Given the 88.89% precision of `SUSPECT`, repair generation should be restricted to `SUSPECT` verdicts.
2. **Address False Alarms**: Because 11.11% of `SUSPECT` verdicts are false positives (2 tasks), repair mechanisms must guard against regressing already-correct answers.
3. **Starvation Requires Upstream Fallbacks**: Targeted post-answer repair cannot fix candidate starvation; addressing the remaining 73.17% of system failures requires separate upstream fallback recovery mechanisms.

