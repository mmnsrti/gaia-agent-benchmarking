# V4 — Explicit Two-Stage Capability Router

Status: FROZEN

See [FROZEN.md](FROZEN.md) for the complete canonical freeze manifest, benchmark results, transition analysis, regression mechanism audit, failure taxonomy, and research summary.

Branch: `v4-planner-router`

Base Tag: `v3-python-execution-final` (commit `f1a8e9d9e6eb132ca6cf6a09048c1e7ceebad573`)

---

## Capability Definition

V4 introduces an explicit capability-routing stage before worker execution:

```text
V4 = frozen V3 + explicit two-stage DIRECT/PYTHON capability-routing architecture
```

### Evaluated System Intervention
V4 differs from V3 through a **system-level bundle** rather than isolated routing:
1. **Explicit Router Generation**: An upfront Gemini call classifying the question into `DIRECT` or `PYTHON`.
2. **Additional Inference Turn**: Standard and recoverable V4 execution uses two LLM generation attempts: one router attempt and one worker attempt. If a fatal exception prevents worker dispatch, telemetry records the actual number of attempts rather than forcing the count to two.
3. **Route-Specific Worker Prompting**: Dedicated worker prompts for direct text answers (`router-direct-worker-v1`) vs. Python code generation (`router-python-worker-v1`).
4. **Deterministic Route Enforcement**: Hardware enforcement ensuring `DIRECT` tasks cannot call Python and are shielded from tool-calling syntax errors.
5. **Native Function Calling Disabled**: Router and both workers use Gemini with native function calling disabled (`mode="NONE"`). Python execution is orchestrated locally and deterministically after extracting a Python code block.
6. **Changed Exposure to Provider Stochasticity**: Differential sensitivity to upstream provider `MALFORMED_FUNCTION_CALL` finish-reason anomalies and token budget dynamics.

*(Note: Because these elements are co-introduced, V4 evaluates the system-level effect of the capability-routing architecture, not a pure causal estimate of routing alone.)*

---

## Canonical Controlled Results (GAIA 2023 Validation Set, 165 Tasks)

Evaluated against the contemporaneous matched V3 control run under identical runtime conditions:

| Benchmark Metric | Historical Frozen V3 | Matched V3 Control | Canonical V4 | Controlled Delta (vs Matched V3) |
| :--- | :---: | :---: | :---: | :---: |
| **Overall Accuracy** | **29.09%** (48 / 165) | **29.70%** (49 / 165) | **31.52%** (52 / 165) | **+1.82 pp (+3 tasks)** |
| Level 1 Accuracy | 45.28% (24 / 53) | 47.17% (25 / 53) | 52.83% (28 / 53) | +5.66 pp (+3 tasks) |
| Level 2 Accuracy | 26.74% (23 / 86) | 24.42% (21 / 86) | 24.42% (21 / 86) | +0.00 pp (0 tasks) |
| Level 3 Accuracy | 3.85% (1 / 26) | 11.54% (3 / 26) | 11.54% (3 / 26) | +0.00 pp (0 tasks) |
| **Attachment Tasks** | **21.05%** (8 / 38) | **18.42%** (7 / 38) | **15.79%** (6 / 38) | **-2.63 pp (-1 task)** |
| **Non-Attachment Tasks** | **31.50%** (40 / 127) | **33.07%** (42 / 127) | **36.22%** (46 / 127) | **+3.15 pp (+4 tasks)** |
| **Completion Rate** | **78.18%** (129 / 165) | **77.58%** (128 / 165) | **49.70%** (82 / 165) | **-27.88 pp (-46 tasks)** |

---

## Key Research Findings

1. **Accuracy Gain**: V4 solved 52 tasks compared to 49 for matched V3 (+3 tasks, +1.82 pp), with gains concentrated in Level 1 (+5.66 pp).
2. **Completion Rate Tradeoff**: Completion collapsed from 77.58% to 49.70% (-27.88 pp). The completion reduction was associated primarily with worker-generation `MALFORMED_FUNCTION_CALL` finish-reason anomalies and, to a smaller extent, MAX_TOKENS truncation and other generation failures.
3. **Regression Mechanism**: 10 of 10 regressions (100%) from matched V3 were associated with worker provider finish-reason anomalies (8) or token budget exhaustion (2); zero regressions resulted from incorrect calculation following successful Python execution.
4. **Successful-Python Subset**: On the 11 tasks where Python executed cleanly with valid answer extraction, V4 solved 9/11 (81.82%) vs. 8/11 (72.73%) for matched V3. *(Note: This comparison is descriptive only; routing is endogenous and does not represent an isolated causal estimate or proof of Python effectiveness in isolation.)*
5. **Operational Funnel & Counts**:
   - Final DIRECT worker dispatches: `74` (including 4 originating from router fallback)
   - Final PYTHON worker dispatches: `91`
   - Python executions: `18`, successes: `11`, execution failures: `7`, unfulfilled routes: `73`, fallbacks: `80` (`73 + 7 = 80`).
   - Executed Python failure taxonomy: 4 MissingFinalAnswerMarker, 2 runtime failure, 1 syntax/AST rejection (total 7).
6. **Operational Costs**: V4 increased standard LLM inference attempts per task (2 vs 1) and roughly doubled average wall-clock latency (10.62s vs 5.35s).

---

## Freeze Rule

V4 is frozen as the immutable research baseline for explicit two-stage capability routing:

```text
V4 = frozen V3 + explicit two-stage DIRECT/PYTHON capability-routing architecture
```

Future work must not alter V4 results, agent runtime behavior, prompts, model settings, tool configurations, or benchmark evaluations. Any subsequent work belongs to V5+.
