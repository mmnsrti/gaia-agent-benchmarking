# V2 – File / Attachment Handling

Status: FROZEN

Branch: `v2-file-attachments`

Tag: `v2-file-attachments-final`

## Capability Definition

V2 = V1 + direct local file / attachment access and representation.

V2 does not add:
- Python/code execution
- planner/router
- iterative search
- verification
- query rewriting
- OCR
- autonomous tool loops

## Canonical Dataset

GAIA 2023 Validation

Total tasks: 165

## Controlled Results

Matched V1:
45 / 165 = 27.27%

V2:
61 / 165 = 36.97%

Controlled delta:
+9.70 percentage points

Attachment tasks:

Matched V1:
4 / 38 = 10.53%

V2:
16 / 38 = 42.11%

Attachment delta:
+31.58 percentage points

## Interpretation

Direct attachment access substantially improved performance on attachment-bearing tasks in the controlled comparison.

Level-3 aggregate accuracy did not improve, indicating that direct file access alone was insufficient for many of the hardest tasks in this run.

These results motivate testing computation/code execution as the next controlled capability in V3.

V3 has not yet been validated.

## Freeze Rule

No further runtime, prompt, configuration, scoring, or benchmark-result changes are allowed on V2 after this freeze.

Any new capability work must happen on a new V3 branch.
