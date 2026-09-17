# V9 — Upstream Candidate Recovery

**Status**: `PREREGISTERED_PRE_IMPLEMENTATION`  
**Branch**: `v9-upstream-candidate-recovery`  
**Scientific Parent**: Frozen V7 (`v7-targeted-repair`)  
**Architecture**: Design A — Upstream Worker Candidate Recovery  
**Date**: September 2026  

---

## Overview

Version 9 (V9) investigates **Upstream Candidate Recovery** to overcome the primary bottleneck identified in V7 and V8: **candidate starvation**.

In the GAIA benchmark, nearly half (~49.7%) of all tasks fail upstream without emitting any candidate answer (`""`), leaving them structurally unreachable by downstream verification (V5), self-evaluation (V6), or targeted repair (V7).

V9 introduces at most **one bounded, text-only recovery generation** for explicitly eligible upstream failures, while strictly preserving 100.0% of answers for tasks that already produce a candidate.

---

## Directory Contents

| File | Purpose |
| :--- | :--- |
| [`DESIGN.md`](./DESIGN.md) | Comprehensive technical design: architecture, state machine, eligibility function, failure taxonomy, recovery prompt contract, schema, budgets, telemetry, and safety invariants. |
| [`PRE_BENCHMARK.md`](./PRE_BENCHMARK.md) | Binding pre-benchmark preregistration: hypotheses, primary/secondary metrics, within-run evaluation design, 11 deterministic smoke test scenarios, and scientific decision rule. |

---

## Scientific Governance & Rules of Engagement

1. **Preregistration Precedes Implementation**: No runtime code is altered until design and preregistration are fully reviewed and committed.
2. **Strict Invariant**: Non-Triggered Answer Preservation Rate must be strictly $100.0\%$.
3. **No Added Tools**: Candidate recovery operates strictly on already-gathered runtime evidence (zero new web searches, zero new Python executions, zero file rereads).
4. **Transport vs. Scientific Separation**: Multi-key credential failover in `agent/llm.py` and `tools/web_search.py` is operational transport infrastructure, completely separated from the V9 scientific generation budget ($\le 1$ recovery generation).
5. **No Premature Benchmarking**: No GAIA benchmark runs may be launched until runtime implementation and unit/smoke tests are fully verified.

