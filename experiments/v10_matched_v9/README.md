# Contemporaneous Matched Frozen V9 Control — Validity Notice

**Status:** `INVALID_SECONDARY_CONTROL_PROVIDER_COLLAPSE`  
**Date:** September 19, 2026  
**Inference Commit:** `314d0aecd01a1679a96d85256044c01c8b6c30ce`  
**Execution Type:** Secondary Matched Control (Contemporaneous Full Run)  
**Interpretation:** `EXCLUDED_FROM_SCIENTIFIC_INTERPRETATION`  

---

## 1. Executive Notice

The contemporaneous matched Frozen V9 benchmark execution conducted as part of the V10 evaluation suite experienced severe, widespread upstream provider API transport disruptions during its execution across Levels 1, 2, and 3. As a result, this run does **not** reflect genuine Frozen V9 agent behavior and is classified as **`INVALID_SECONDARY_CONTROL_PROVIDER_COLLAPSE`**.

All raw predictions, summaries, and evaluation artifacts are preserved in this directory strictly for provenance, auditability, and data integrity. They are **excluded from scientific interpretation**.

---

## 2. Telemetry & Defect Analysis

Across the 165 tasks executed in this matched control run:
- **Router Provider API Errors:** Exactly 127 of 165 tasks (77.0%) recorded `router_error_type: "provider_api_error"`.
- **Router Fallback Rate:** 127 of 165 tasks (77.0%) were forced into fallback execution.
- **Worker Provider API Errors:** 127 of 165 tasks suffered cascading `worker_error_type: "provider_api_error"`.
- **Level Breakdown:**
  - **Level 1:** 24 / 53 correct (45.28%), 16 / 53 router provider errors.
  - **Level 2:** 1 / 86 correct (1.16%), 85 / 86 router provider errors (`model_version: null`).
  - **Level 3:** 0 / 26 correct (0.00%), 26 / 26 router provider errors (`model_version: null`).
- **Total Recorded Score:** 25 / 165 (15.15%), with only 37 / 165 tasks reaching completion.

---

## 3. Methodological & Scientific Implications

1. **Non-Validity of the 25/165 Score:** The score of 25 / 165 (15.15%) is **NOT** a valid estimate of Frozen V9 performance. The canonical historical reference for Frozen V9 remains:
   $$\text{Historical Frozen V9 Score} = 73 / 165 = 44.24\%$$
2. **Exclusion of Cross-Run Transition Matrix:** The nominal cross-run matrix comparing canonical V10 against this matched run ($\Delta_{\text{e2e\_observational}} = +59$) is **scientifically uninterpretable** and must not be cited as evidence of V10 superiority.
3. **Isolation of Valid Measurements:** This provider failure in the secondary control run does **NOT** compromise:
   - **Primary Shared-Context Paired Upstream Ablation:** $\Delta_{\text{upstream}} = +8$ (Valid, zero provider errors).
   - **Canonical V10 Full Benchmark:** 84 / 165 = 50.91% (Valid, zero provider errors, 161 / 165 completion).
   - **Historical Frozen V9 Canonical Baseline:** 73 / 165 = 44.24%.
4. **Promotion Decision:** In accordance with the binding preregistration in `experiments/v10/PRE_BENCHMARK.md`, the contemporaneous matched V9 run is classified as **Secondary / Observational / Non-Causal** and is **not** a binding promotion gate. Its invalidation does not block promotion.

