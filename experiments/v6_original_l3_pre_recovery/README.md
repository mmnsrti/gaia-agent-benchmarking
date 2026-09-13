# Historical Original V6 Level-3 Evidence (Pre-Recovery)

This directory preserves the historical original V6 Level-3 evidence prior to the predeclared recovery replication.

## Artifact Status & Integrity Manifest

| Artifact File | Status | Records / Lines | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :---: | :---: | :--- |
| `predictions_level_3.jsonl` | **INCOMPLETE — 11/26 RECORDS** | 11 | 408,313 | `1b2260b7c1f8817ca7fd7319bc30bedda19f8bfd19c9c94f783b0d79699db183` |
| `detailed_eval_level_3.jsonl` | **COMPLETE** | 26 | 267,610 | `b808c6316c195586d1db6ee8d2fddee1906e3fc8031fba6f22910df16404ddda` |
| `summary_level_3.json` | **COMPLETE** | 200 | 6,137 | `c6f900caed11074e728282b60702ce95e05c6f1b7e18c0fc236e6180c560c986` |

## Historical Evaluation Outcome
- **Tasks**: 26 (Level 3)
- **Completed**: 4 / 26 (15.38%)
- **Correct**: 1 / 26 (3.85%)
- **Self-Evaluation Eligible**: 4
- **Self-Evaluation Valid**: 4 (3 TP, 1 TN, 0 FP, 0 FN)

## Provenance
1. **12:02 PM Sep 13, 2026**: Initial complete canonical execution completed 26 tasks.
2. **12:09 PM Sep 13, 2026**: Summary committed in git `e6dce61`. Predictions were ignored by `.gitignore`.
3. **12:23 PM Sep 13, 2026**: An unintended rerun with `--no-resume` unlinked the predictions file and was aborted at task 11, leaving 11 records.
4. **Post-Audit Action**: Under strict benchmark governance, exact original recovery (Option A) and lossless reconstruction (Option B) are impossible. Option C was triggered, blocking freeze. These files are preserved as permanent historical evidence while a strictly predeclared Level-3 recovery replication is executed.

