# V6 — Self-Evaluation / Failure Detection

**Status:** PROPOSED / PRE-BENCHMARK  
**Frozen parent:** V5 — One-Shot Post-Answer Verification

## Research Question

> Can a bounded self-evaluator reliably detect when the agent's non-empty final answer is likely incorrect, without modifying the answer or using additional tools?

The secondary questions are diagnostic precision, missed errors, false alarms, evaluator-assigned risk categories, confidence diagnostics, and whether the signal could motivate a separately designed future repair study. V6 does not test answer-accuracy improvement.

## Intervention

```
V6 = frozen V5 + one read-only Self-Evaluator generation
```

The V5 answer is completed before V6 begins. The evaluator receives existing context and emits an observational `PASS` or `SUSPECT` label. Its result has no write path to the answer.

## Non-Goals

- No repair.
- No answer mutation.
- No retry.
- No active verification.
- No new search.
- No Python.
- No planning.
- No framework migration.

V6 also adds no tool-using evaluator, regeneration, reflection loop, targeted retrieval, answer-selection ensemble, or confidence-based answer suppression.

## Architecture

```text
Question
  -> frozen V5 pipeline
  -> V5 final answer
  -> empty or whitespace-only? -- yes --> evaluator bypassed; same answer returned
                                |
                                no
                                v
                       one text-only Self-Evaluator call
                                v
             PASS / SUSPECT + one risk type + confidence
                                v
                   telemetry only; exact same answer returned
```

The V5 verifier and V6 Self-Evaluator are distinct. The V5 verifier may keep or revise the upstream candidate. The V6 evaluator runs afterward and may only classify reliability of V5's already-final answer.

## Eligibility

Only a non-empty V5 final answer is eligible. Empty and whitespace-only answers bypass the evaluator and consume zero additional model generations. A non-empty answer remains eligible even when completion telemetry is incomplete or the finish reason is not `STOP`.

## Evaluator Inputs

- Original question.
- Existing V5 search evidence.
- Existing extracted file or attachment context.
- Frozen V5 final answer.
- Compact deterministic execution summary: route, search state, attachment state, Python state, non-sensitive error category, completion state, and finish reason.

The evaluator is text-only. Native function calling is disabled and the evaluator does not receive attachment bytes.

## Forbidden Inputs

- Ground truth.
- Scorer result or scorer internals.
- Expected answer.
- V5 verifier raw response.
- V5 verifier decision or confidence.
- Hidden reasoning.
- Raw router/worker responses, generated Python code, or Python stdout/stderr.

## Output Schema

`self-evaluator-v1` requires exactly:

```text
ASSESSMENT: PASS|SUSPECT
RISK_TYPE: NONE|EVIDENCE|REASONING|CALCULATION|FORMAT|EXECUTION|UNKNOWN
CONFIDENCE: 0.00–1.00
```

`PASS` requires `RISK_TYPE: NONE`; `SUSPECT` requires exactly one non-`NONE` risk type. The parser rejects malformed output, duplicate fields, prose, code fences, out-of-range or non-finite confidence, and inconsistent combinations. There is no retry after parser failure.

## Failure-Safety

Provider errors, timeout, empty output, non-`STOP` finish reasons, malformed schema, and parser rejection produce no label. They record explicit failure telemetry and preserve the final answer exactly.

The standard attempt bound is at most four model generations: V5 router, V5 worker, optional V5 verifier, and optional V6 self-evaluator. The V6 evaluator has one provider attempt and zero provider retries.

## Primary Metrics

The error class is positive. On eligible tasks with a valid assessment:

- True positive: `SUSPECT` and officially incorrect.
- False positive: `SUSPECT` and officially correct.
- True negative: `PASS` and officially correct.
- False negative: `PASS` and officially incorrect.

Primary metrics are precision, recall, and F1.

## Secondary Metrics

- False-alarm rate, missed-error rate, and specificity.
- Diagnostic coverage.
- Eligible, attempted, valid, failure/invalid, `PASS`, and `SUSPECT` counts.
- PASS-group correctness and SUSPECT-group error rate.
- Risk-type distribution and conditional error rates.
- Confidence-derived suspect probability and Brier-style diagnostic score.

Risk labels are evaluator-assigned diagnostic categories, not objective causal truth.

## Causal Interpretation Rules

V6 does not test accuracy improvement because the evaluator cannot modify the final answer. In one V6 record, self-evaluation improvements and regressions are structurally zero. Any V6-versus-separately-executed matched V5 answer-accuracy difference is an observational cross-run comparison and must not be attributed to the self-evaluator as a direct per-task answer intervention.

## Planned Benchmark

The planned study is the full 165-task GAIA validation benchmark plus a contemporaneous matched frozen V5 control. Neither run is part of this implementation task, and no V6 benchmark artifacts or performance claims are created here.
