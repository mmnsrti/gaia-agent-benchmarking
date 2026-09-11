# V5 — One-Shot Post-Answer Verification

Status: FROZEN

See [FROZEN.md](FROZEN.md) for the complete canonical freeze manifest, benchmark results, verifier mechanism analysis, failure taxonomy, and scientific conclusions.
See [`docs/V5_FINAL_ANALYSIS.md`](../../docs/V5_FINAL_ANALYSIS.md) and [`docs/V5_POST_BENCHMARK_AUDIT.md`](../../docs/V5_POST_BENCHMARK_AUDIT.md) for the complete post-benchmark audit trail.

Branch: `v5-one-shot-verification`

Parent Baseline: Frozen V4 (`v4-planner-router-final`)

---

## Research Definition

V5 introduces an explicit, single-pass conservative post-answer verification and revision stage on top of the frozen V4 capability-routing pipeline:

```text
V5 = frozen V4 + one-shot conservative post-answer verification/revision
```

### Evaluated Architecture
1. **Search Tool**: At most one Tavily search query on the original question ($N \le 1$).
2. **File Processing**: Deterministic local extraction inherited from frozen V2/V3/V4 ($N \le 1$).
3. **Capability Router**: Frozen V4 explicit router LLM call selecting between `DIRECT` and `PYTHON` worker tracks (`mode="NONE"`).
4. **Route-Specific Worker**:
   - `DIRECT`: Worker generates candidate answer text directly.
   - `PYTHON`: Worker generates code block executed in local deterministic sandbox ($N \le 1$).
5. **Candidate Eligibility Guard**: If upstream worker produces no candidate answer, the verifier is bypassed immediately to maintain empty-candidate failure safety.
6. **One-Shot Verifier**: If a candidate exists, a dedicated verifier LLM call evaluates question, search evidence, file context, and candidate answer (`mode="NONE"`).
7. **Verdict Enforcement**:
   - `KEEP`: Candidate answer is retained without modification (100% preservation).
   - `REVISE`: Substitute alternative answer text.
   - On verifier failure or error, non-destructive fallback deterministically preserves the upstream candidate.
8. **Generation Cap**: Total LLM generation attempts capped at $\le 3$ per task (1 router + 1 worker + 1 verifier).

---

## Canonical Headline Metrics (GAIA 2023 Validation Set, 165 Tasks)

Evaluated against the contemporaneous matched V4 control run:

| Benchmark Metric | Contemporaneous Matched V4 Control | Canonical V5 | Observed Delta |
| :--- | :---: | :---: | :---: |
| **Overall Accuracy** | **34.55%** (57 / 165) | **32.12%** (53 / 165) | **-2.42 pp (-4 tasks)** |
| Level 1 Accuracy | 54.72% (29 / 53) | 52.83% (28 / 53) | -1.89 pp (-1 task) |
| Level 2 Accuracy | 27.91% (24 / 86) | 23.26% (20 / 86) | -4.65 pp (-4 tasks) |
| Level 3 Accuracy | 15.38% (4 / 26) | 19.23% (5 / 26) | +3.85 pp (+1 task) |
| **Attachment Tasks** | **18.42%** (7 / 38) | **15.79%** (6 / 38) | **-2.63 pp (-1 task)** |
| **Non-Attachment Tasks** | **39.37%** (50 / 127) | **37.01%** (47 / 127) | **-2.36 pp (-3 tasks)** |
| **Completion Rate** | **51.52%** (85 / 165) | **47.27%** (78 / 165) | **-4.24 pp (-7 tasks)** |

> **Important Distinction on V4 Results**:
> The 57/165 (34.55%) V4 result above is the *contemporaneous matched V4 control* run executed alongside V5. It does **not** replace the historical frozen V4 canonical baseline of **52 / 165 (31.52%)** documented in [`experiments/v4/`](../v4/).

---

## Primary Verifier Mechanism Result (Within-V5)

Within the same canonical V5 run, comparing candidate answers before and after verification:

| Metric | Pre-Verification | Post-Verification | Net Impact |
| :--- | :---: | :---: | :---: |
| **Correct Tasks** | 53 / 165 (32.12%) | 53 / 165 (32.12%) | **0 tasks (0.00 pp)** |
| Improvements ($0 \rightarrow 1$) | — | — | 0 tasks |
| Regressions ($1 \rightarrow 0$) | — | — | 0 tasks |
| Stable Correct ($1 \rightarrow 1$) | — | — | 53 tasks |
| Stable Failure ($0 \rightarrow 0$) | — | — | 112 tasks |

- **Eligible Candidates Evaluated**: 81 tasks (84 bypassed due to missing upstream candidate).
- **Verifier Decisions**: 78 KEEP (96.30%), 3 REVISE (3.70%), 0 fallbacks.
- **Candidate Preservation**: 78 of 78 KEEP decisions (100%) preserved the candidate answer.
- **Revision Efficacy**: All 3 revisions resulted in net-neutral correctness transitions under the official scorer.

---

## Key Research Takeaways

1. **Zero Net Verifier Delta**: In this canonical V5 run, one-shot conservative post-answer verification produced zero improvements and zero regressions under the official GAIA scorer, leaving accuracy unchanged at 53/165.
2. **Conservative Failure Safety**: The verifier preserved 100% of candidate answers on KEEP decisions and produced zero regressions on correct candidates.
3. **High KEEP Rate on Incorrect Candidates**: On the 28 tasks where an incorrect candidate reached the verifier, the verifier issued KEEP on 26 (92.86%).
4. **Upstream Candidate Starvation**: 84 of 112 failures (75.00%) occurred upstream of the verifier, driven by provider `MALFORMED_FUNCTION_CALL` finish-reason anomalies (76 tasks) on Python workers.
5. **Cross-Run System Comparison**: The observed -4 task difference between V5 (53) and matched V4 (57) occurred across separate stochastic runs and should not be attributed to any single mechanism without stronger causal evidence.
6. **Configuration-Bounded Finding**: In this V5 configuration, a single conservative text-only post-answer verifier did not improve official GAIA accuracy. Future versions may test verification mechanisms with additional evidence-gathering, execution, or targeted re-checking capabilities.

---

## Freeze Rule

V5 is frozen as the immutable research baseline for one-shot post-answer verification:

```text
V5 = frozen V4 + one-shot conservative post-answer verification/revision
```

Future work must not alter V5 results, agent runtime code, prompts, model configurations, or benchmark evaluations. Any further architectural experimentation belongs to **V6+**.
