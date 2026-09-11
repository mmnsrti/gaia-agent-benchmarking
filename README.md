---
title: gaia-agent-benchmarking
emoji: 🕵🏻‍♂️
colorFrom: indigo
colorTo: indigo
sdk: gradio
sdk_version: 5.25.2
app_file: app.py
pinned: false
hf_oauth: true
# optional, default duration is 8 hours/480 minutes. Max duration is 30 days/43200 minutes.
hf_oauth_expiration_minutes: 480
---

# GAIA Agent Benchmarking

## Project Goal
This repository evaluates incremental improvements to an AI agent on the General AI Assistants (**GAIA**) benchmark. 

Rather than starting with an opaque multi-agent framework, this project evolves iteratively through measurable stages: establishing a pure LLM baseline first, then measuring the performance effect of adding individual tools (web search, file extraction, python interpreter), planning loops, and verification strategies.

---

## v0 — Tool-Free Baseline
**v0** represents the minimal, tool-free baseline:
```text
GAIA Question
     ↓
GAIAAgent
     ↓
Prompt
     ↓
LLMClient (Gemini)
     ↓
Raw Model Response
     ↓
Minimal Answer Cleaning
     ↓
Final Answer
```

### Capabilities of v0
- Direct question input
- Gemini inference via official `google-genai` SDK
- Minimal, conservative final-answer formatting (`clean_answer`)
- Local single-question runner (`run_one.py`)
- Experiment logging to `experiments/runs.jsonl`

### What v0 intentionally does NOT include
- Web search / browsing tools
- File processing (PDF, XLSX, CSV, images)
- Audio / video / YouTube analysis
- Code execution (Python tool)
- Multi-agent frameworks (LangChain, LangGraph, CrewAI, smolagents)
- Reflection, self-critique, or complex planning loops

Tasks requiring attachments or external documents will have attachments detected and logged, but files will not be processed by agent tools in v0.

### V0 Canonical Results (GAIA 2023 Validation Baseline)

Local research evaluation on the complete GAIA 2023 Validation set (Levels 1, 2, and 3) scored using the official GAIA scoring implementation:

| Benchmark Level | Evaluated Tasks | Completion Rate | Accuracy (Score) | Attachment Acc | Non-Attachment Acc |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Level 1** | 53 / 53 (100%) | 92.45% (49 / 53) | **26.42%** (14 / 53) | 27.27% (3 / 11) | 26.19% (11 / 42) |
| **Level 2** | 86 / 86 (100%) | 96.51% (83 / 86) | **18.60%** (16 / 86) | 10.00% (2 / 20) | 21.21% (14 / 66) |
| **Level 3** | 26 / 26 (100%) | 92.31% (24 / 26) | **11.54%** (3 / 26) | 0.00% (0 / 7) | 15.79% (3 / 19) |
| **Overall** | **165 / 165 (100%)** | **94.55% (156 / 165)** | **20.00% (33 / 165)** | **13.16% (5 / 38)** | **22.05% (28 / 127)** |

> **Baseline Definition**: V0 is a tool-free LLM-only baseline using `gemini-3.5-flash-lite` (prompt `baseline-v1`). It intentionally uses no external tools, web search, file parsing, Python execution, planning, reflection, or verification. This serves as the frozen reference baseline against which subsequent tool-augmented versions (e.g., V1 Web Search) will be measured.

### V0 Failure Taxonomy Summary (Levels 1–3)

Aggregate failure analysis across all incorrect or failed tasks (\(n=132\)) on the GAIA 2023 Validation set:

| Failure Category | Level 1 (n=39) | Level 2 (n=70) | Level 3 (n=23) | Overall (n=132) | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `requires_web` | 12 (30.8%) | 29 (41.4%) | 7 (30.4%) | **48 (36.4%)** | Requires external web browsing, search, or URL inspection |
| `requires_attachment` | 8 (20.5%) | 18 (25.7%) | 7 (30.4%) | **33 (25.0%)** | Requires unparsed file attachments (PDF, XLSX, CSV, images) |
| `knowledge_failure` | 8 (20.5%) | 14 (20.0%) | 4 (17.4%) | **26 (19.7%)** | Factual errors or domain knowledge absent from model weights |
| `reasoning_failure` | 6 (15.4%) | 5 (7.1%) | 3 (13.0%) | **14 (10.6%)** | Complex multi-step deduction or calculation errors |
| `incomplete_generation` | 4 (10.3%) | 3 (4.3%) | 2 (8.7%) | **9 (6.8%)** | Response budget exhaustion (`MAX_TOKENS`) or empty output |
| `formatting_failure` | 1 (2.6%) | 1 (1.4%) | 0 (0.0%) | **2 (1.5%)** | Correct answer found in reasoning but missed strict normalization |
---

## v1 — Single-Shot Web Retrieval Baseline

**v1** answers the core ablation research question:
> **How much does adding web retrieval alone improve the frozen V0 LLM-only baseline?**

In accordance with strict ablation principles:
```text
V1 = V0 + Web Search only
```

### Retrieval Flow
```text
GAIA Question
     ↓
ONE Tavily Search (Original Question as Query)
     ↓
Tavily-retrieved search snippets
     ↓
Prompt (web-search-v1)
     ↓
LLMClient (Gemini)
     ↓
Raw Model Response
     ↓
Minimal Answer Cleaning
     ↓
Final Answer
```

### Critical Research Design & Ablation Rationale
V1 is strictly an ablation baseline, not an optimized final agent. To provide a matched-control estimate of the effect of adding single-shot web retrieval:
1. **Single-Shot Retrieval**: Exactly one search is executed per task.
2. **Original Question as Query**: The original GAIA question is passed directly as the search query without LLM query rewriting or expansion. For long questions, queries are deterministically capped to the first 1,500 characters (`provider_query = cleaned_query[:1500]`) to respect provider input limits while logging truncation metadata (`search_query_truncated`, `original_query_length`, `provider_query_length`).
3. **Deterministic Search Configuration**:
   - Provider: **Tavily Search API** (`tavily-python`)
   - `search_depth = "basic"`
   - `max_results = 5`
   - `include_answer = false` (Tavily's generated answer field is strictly ignored to evaluate the LLM's own reasoning over retrieved evidence)
   - `include_raw_content = false` (evidence consists strictly of Tavily-retrieved search snippets; no raw webpage content or HTML scraping)
   - `include_images = false`
   - `auto_parameters = false`
4. **Retrieved Evidence Format**: Evidence is formatted exclusively as **Tavily-retrieved search snippets** (result number, title, URL, and snippet), never as raw webpage content.
5. **No Planning or Router**: Web retrieval is executed uniformly without an LLM planner deciding whether to search.
6. **Deterministic Search Failure Fallback & Prompt Provenance**:
   If the search API fails (network timeout, HTTP error, missing key), the agent deterministically falls back to the V0 LLM-only prompt path (`fallback_prompt_version = baseline-v1`). The primary prompt version is recorded as `primary_prompt_version = web-search-v1`, ensuring fallback events are accurately tracked per-task without misclassifying the prompt provenance of the entire run.
7. **What V1 Intentionally Does NOT Include**:
   - Multi-hop or iterative searches
   - Query rewriting or keyword extraction
   - Browser automation, full-page HTML crawling, or raw webpage content
   - Planning, reflection, or verification loops
   - File attachment processing
   - Python code execution

### V1 Canonical Results (GAIA 2023 Validation)

Local research evaluation on the complete GAIA 2023 Validation set (Levels 1, 2, and 3) scored using the official GAIA scoring implementation:

| Benchmark Level | V0 Frozen Historical | V0 Matched-Control | V1 Canonical (Web Search) | Controlled Delta | Historical Delta |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Level 1** | 26.42% (14 / 53) | 28.30% (15 / 53) | **52.83%** (28 / 53) | **+24.53 pp** | +26.41 pp |
| **Level 2** | 18.60% (16 / 86) | 19.77% (17 / 86) | **27.91%** (24 / 86) | **+8.14 pp** | +9.31 pp |
| **Level 3** | 11.54% (3 / 26) | 7.69% (2 / 26) | **11.54%** (3 / 26) | **+3.85 pp** | +0.00 pp |
| **Overall** | **20.00%** (33 / 165) | **20.61%** (34 / 165) | **33.33%** (55 / 165) | **+12.72 pp** | **+13.33 pp** |

#### Task Type Breakdown (V1 Overall)

| Task Type | Total Tasks | V0 Matched-Control Correct (Acc) | V1 Canonical Correct (Acc) | Delta (pp) |
| :--- | :--- | :--- | :--- | :--- |
| **Non-Attachment** | 127 | 29 (22.83%) | **52 (40.94%)** | **+18.11 pp** |
| **Attachment-Required** | 38 | 5 (13.16%) | **3 (7.89%)** | **-5.27 pp** |

> **Ablation Comparison & Baseline Differentiation**:
> - **V0 frozen historical**: **20.00%** (33 / 165 correct) — Frozen reference baseline established on the `v0-LLM-only` branch.
> - **V0 matched-control**: **20.61%** (34 / 165 correct) — Contemporary tool-free control runs executed on `v1-web-search` under identical runtime conditions (`gemini-3.5-flash-lite`, prompt `baseline-v1`).
> - **V1 canonical**: **33.33%** (55 / 165 correct) — Single-shot Tavily web retrieval baseline (`gemini-3.5-flash-lite`, prompt `web-search-v1`).
>
> **Core Research Findings**:
> 1. **Web retrieval improved tasks requiring external information**: On non-attachment tasks, accuracy increased from 22.83% (29/127) in the matched control to 40.94% (52/127), and on Level 1 specifically reached 52.83% (+24.53 pp over matched-control).
> 2. **Attachment-heavy tasks remained a major bottleneck**: Web retrieval did not improve attachment-task accuracy in this run (7.89% [3/38] in V1 vs 13.16% [5/38] in V0 matched-control; observed delta: -5.27 pp). The observed difference may also reflect run-to-run variability. Attachment tasks constitute 31.82% of all V1 errors.
> 3. **Controlled Workflow Nature**: V1 is strictly a controlled **retrieve-then-read** baseline (single-shot search without query rewriting, multi-hop crawling, or reflection) and NOT an autonomous multi-tool/planning agent.
> 4. **Empirical Support for V2**: Because external web search alone cannot solve tasks requiring local document parsing, V2 will focus specifically on adding file/attachment processing tools (PDF, XLSX, CSV, images).

---

## v2 — File / Attachment Handling

Status: Frozen

### Controlled Headline Metrics (GAIA 2023 Validation)

```text
Matched V1: 27.27%
V2:         36.97%
Delta:      +9.70 pp

Attachment delta:
+31.58 pp
```

Direct attachment access substantially improved accuracy on attachment-bearing tasks in the controlled comparison. Aggregate Level 3 accuracy remained flat across both runs (15.38%), indicating that direct file access without code execution or advanced tools is insufficient for many difficult tasks. V2 is frozen as an immutable baseline for future comparative evaluations.

**v2** addresses the primary bottleneck uncovered during the V1 error analysis (where attachment tasks accounted for 31.8% of all V1 errors and saw no gain from web search):
> **How much does direct access to GAIA task attachments improve performance beyond the V1 single-shot web retrieval baseline?**

In accordance with strict ablation principles:
```text
V0 = LLM only
V1 = V0 + single-shot web retrieval
V2 = V1 + local file / attachment access
```

### Retrieval & Inspection Flow
```text
GAIA Question + Optional Attachment File
     ↓
ONE Tavily Search (Original Question as Query)
     ↓
FileTool (Deterministic local extraction without execution or OCR)
     ↓
Combined Evidence Prompt (`file-search-v1`) or Multimodal Part Dispatch
     ↓
LLMClient (Gemini 3.5 Flash Lite with Tools Disabled)
     ↓
Raw Model Response
     ↓
Minimal Answer Cleaning
     ↓
Final Answer
```

### Key Architectural & Experimental Guarantees
1. **Single-Shot Web Retrieval Invariance**:
   Every task executes exactly one Tavily search on the original question (capped at 1,500 chars), even when an attachment is present and successfully parsed. Web search is never bypassed or routed away based on attachment presence.
2. **Supported Attachment Types & Handlers**:
   - **Plain text / Data (`.txt`, `.md`, `.csv`, `.json`)**: UTF-8 / Latin-1 text extraction, deterministically truncated to the first 50,000 characters if longer.
   - **Python Source (`.py`)**: Source text extraction only. Code is **strictly prohibited from execution** (`exec`, `eval`, and `subprocess` are completely absent).
   - **Word Documents (`.docx`)**: Paragraph headings, body text, and table cells parsed via `python-docx`.
   - **Spreadsheets (`.xlsx`, `.xls`)**: Sheet structure, merged cell coordinates, and formatted cell coordinates/values via `openpyxl`.
   - **Spreadsheets (`.xlsx`)**: Sheet structure, merged cell coordinates, and formatted cell coordinates/values via `openpyxl`. Legacy binary `.xls` files are unsupported and deterministically trigger fallback.
   - **Presentations (`.pptx`)**: Slide headings, text frames, bullet points, and tables via `python-pptx`.
   - **Native Multimodal Media (`.png`, `.jpg`, `.jpeg`, `.mp3`)**: Binary dispatch to Gemini multimodal parts (`types.Part.from_bytes`) alongside the structured prompt.
   - **PDFs (`.pdf`)**: Native document processing via Gemini multimodal API with `pypdf` text extraction fallback.
3. **Deterministic Fallback Hierarchy**:
   - If attachment processing fails (missing file, unhandled format): falls back cleanly to `web-search-v1` prompt (`file_fallback=True`).
   - If web search also fails: falls back cleanly to `baseline-v1` prompt (`search_fallback=True`).
4. **Strict Ablation Prohibitions Preserved**:
   - No multi-agent frameworks (LangChain, LangGraph, smolagents)
   - No autonomous planner or routing LLM
   - No iterative / multi-hop web searches
   - No Python code execution or shell execution
   - No OCR libraries or calculator tools
   - Tools are explicitly disabled at generation time (`mode="NONE"`)

---

## v3 — Controlled Single-Shot Python Execution Baseline

**Status: FROZEN** (Branch: `v3-python-execution`)

See [`experiments/v3/FROZEN.md`](experiments/v3/FROZEN.md) for full configuration manifest, controlled benchmark results, transition analysis, regression mechanism audit, and research summary.

### Research Definition
```text
V3 = V2 + controlled single-shot local Python execution
```

The research question evaluated by V3 is:
> **How much does adding controlled local Python execution improve GAIA performance beyond single-shot web retrieval and direct attachment access?**

### Execution Flow & Invariants
```text
GAIA Question + Optional Attachment File
     ↓
ONE Tavily Search (Original Question as Query)
     ↓
FileTool (Deterministic local extraction inherited from V2)
     ↓
Single Prompt (`python-execution-v1`)
     ↓
Single Gemini Generation (`llm_generation_count == 1`)
     ↓
[Option A: Direct Answer]       [Option B: Python Code Block]
     ↓                                   ↓
Deterministic Answer Extraction     PythonTool Subprocess (`-I`, Ephemeral Dir, Timeout 15s)
                                         ↓
                                    [Success: stdout contains FINAL_ANSWER: <ans>]
                                    Extract <ans> deterministically
                                         ↓
                                    [Failure / Missing Marker / Security Rejection]
                                    Deterministic fallback to model direct text (no second LLM call, no retry)
```

### Frozen Invariants Preserved
- `llm_generation_count == 1` for every task (strictly no second synthesis turn)
- `python_execution_count in {0, 1}` for every task (maximum 1 execution)
- No Python execution retries or debugging turns
- No autonomous planner or routing agent
- Gemini tools explicitly disabled (`mode="NONE"`)
- Best-effort research execution isolation (`-I` isolated subprocess mode, ephemeral temp directory, read-only attachments, static AST policy)

### Canonical Results (GAIA 2023 Validation Set, 165 Tasks)

| Metric | Matched V2 Control | Canonical V3 | Controlled Delta |
| :--- | :---: | :---: | :---: |
| **Overall Accuracy** | **39.39%** (65 / 165) | **29.09%** (48 / 165) | **-10.30 pp** |
| Level 1 Accuracy | 58.49% (31 / 53) | 45.28% (24 / 53) | -13.21 pp |
| Level 2 Accuracy | 34.88% (30 / 86) | 26.74% (23 / 86) | -8.14 pp |
| Level 3 Accuracy | 15.38% (4 / 26) | 3.85% (1 / 26) | -11.53 pp |
| **Attachment Tasks** | **42.11%** (16 / 38) | **21.05%** (8 / 38) | **-21.05 pp** |
| **Non-Attachment Tasks** | **38.58%** (49 / 127) | **31.50%** (40 / 127) | **-7.09 pp** |
| **Completion Rate** | **65.45%** (108 / 165) | **78.18%** (129 / 165) | **+12.73 pp** |

### Key Research Findings
1. **Experimental Result**: Under the frozen single-generation V3 policy, adding controlled Python execution reduced matched GAIA accuracy from 39.39% to 29.09% (-10.30 percentage points), while completion increased from 65.45% to 78.18%.
2. **Mechanism Finding**: Most observed regressions (22 / 25 = 88.0%) were associated with Python execution failures (12) or provider-response anomalies (10) rather than incorrect outputs following successful Python execution (3).
3. **Successful-Python Subset**: On the 26 tasks where Python execution completed successfully, V3 and matched V2 each solved 12 tasks, with 3 improvements and 3 regressions. *(Note: This subgroup comparison is descriptive because Python routing is endogenous.)*
4. **Main Reliability Finding**: 60 of 69 Python execution failures (86.96%) were clean process executions that failed the required `FINAL_ANSWER:` extraction contract.

### Freeze Rule
V3 is frozen as the immutable research baseline for controlled single-shot local Python execution:
```text
V3 = V2 + controlled single-shot local Python execution
```
Future work must not alter V3 results or configuration. Any subsequent planner/router work belongs to V4.

---

## v4 — Explicit Two-Stage Capability Router

**Status: FROZEN** (Branch: `v4-planner-router`)

See [`experiments/v4/FROZEN.md`](experiments/v4/FROZEN.md) for full configuration manifest, controlled benchmark results, transition analysis, regression mechanism audit, failure taxonomy with confidence tiers, and research summary.

### Research Definition
```text
V4 = frozen V3 + explicit two-stage DIRECT/PYTHON capability-routing architecture
```

The research question evaluated by V4 is:
> **How does adding an explicit capability-routing stage affect GAIA performance, completion, reliability, latency, and tool utilization relative to frozen V3?**

### System-Level Intervention Bundle Definition
The primary comparison between V4 and contemporaneous matched V3 evaluates the **controlled system-level effect of introducing an explicit two-stage capability-routing architecture**, which bundles:
1. **Explicit Router Generation**: An upfront Gemini call classifying the question into `DIRECT` or `PYTHON`.
2. **Additional LLM Inference Turn**: Standard and recoverable V4 execution uses two LLM generation attempts: one router attempt and one worker attempt. If a fatal exception prevents worker dispatch, telemetry records the actual number of attempts rather than forcing the count to two.
3. **Route-Specific Worker Prompting**: Specialized system prompts tailored to direct answer synthesis (`router-direct-worker-v1`) or code generation (`router-python-worker-v1`).
4. **Deterministic Route Enforcement**: Hard architectural enforcement ensuring DIRECT routes cannot invoke Python and cannot be exposed to tool-calling failure modes.
5. **Native Function Calling Disabled**: Router and both workers use Gemini with native function calling disabled (`mode="NONE"`). Python execution is orchestrated locally and deterministically after extracting a Python code block.
6. **Changed Exposure to Provider Stochasticity**: Differential sensitivity to upstream provider `MALFORMED_FUNCTION_CALL` finish-reason anomalies and token budget dynamics.

*(Note: These bundled components cannot be cleanly separated by the primary V3 → V4 comparison alone; V4 does not estimate the pure causal effect of routing in isolation.)*

### Execution Flow & Invariants
```text
GAIA Question + Optional Attachment File
     ↓
ONE Tavily Search (Original Question as Query, Capped at 1,500 Chars)
     ↓
FileTool (Deterministic local extraction inherited from frozen V2/V3)
     ↓
Stage 1: Router Generation (`capability-router-v1`, native function calling disabled, `mode="NONE"`)
     ↓
Deterministic Route Parser (Case-insensitive regex, strict validation, deterministic fallback to DIRECT)
     ↓
Stage 2: Deterministic Route Enforcement & Route-Specific Worker Dispatch
     │
     ├── [Route == DIRECT]
     │        ↓
     │   Worker Prompt: `router-direct-worker-v1`
     │        ↓
     │   Gemini worker generation with native function calling disabled (`mode="NONE"`)
     │        ↓
     │   Deterministic Final Answer Extraction (`FINAL: <answer>`)
     │   (Python execution strictly disabled; 0 execution attempts)
     │
     └── [Route == PYTHON]
              ↓
         Worker Prompt: `router-python-worker-v1`
              ↓
         Gemini worker generation with native function calling disabled (`mode="NONE"`);
         Python execution is orchestrated locally and deterministically after extracting a Python code block
              ↓
         [Worker emits ```python code block]
              ↓
         PythonTool Subprocess (`-I`, Ephemeral Dir, Timeout 15.0s, Cap 20k chars, Static AST Validation)
              ↓
         ├── [Success: stdout contains 'FINAL_ANSWER: <ans>']
         │        ↓
         │   Extract <ans> deterministically
         │
         └── [Failure / Missing Marker / AST Rejection / Timeout / Non-execution]
                  ↓
             Deterministic fallback to model direct text if available
             (Strictly no second LLM synthesis call, no retry, no debugging turn)
```

### Frozen Invariants Preserved
- Standard and recoverable V4 execution uses two LLM generation attempts: one router attempt and one worker attempt. If a fatal exception prevents worker dispatch, telemetry records the actual number of attempts rather than forcing the count to two.
- Maximum one Python execution per task (`python_execution_count in {0, 1}`)
- Router and both workers use Gemini with native function calling disabled (`mode="NONE"`)
- If routed to `DIRECT`, Python execution is structurally prohibited
- No third LLM generation, no retry, no repair turn, and no verification loop
- Best-effort research execution isolation (`-I` isolated subprocess mode, ephemeral temp directory, read-only attachments, static AST policy)

### Canonical Results (GAIA 2023 Validation Set, 165 Tasks)

| Metric | Historical Frozen V3 | Matched V3 Control | Canonical V4 | Controlled Delta (vs Matched V3) |
| :--- | :---: | :---: | :---: | :---: |
| **Overall Accuracy** | **29.09%** (48 / 165) | **29.70%** (49 / 165) | **31.52%** (52 / 165) | **+1.82 pp (+3 tasks)** |
| Level 1 Accuracy | 45.28% (24 / 53) | 47.17% (25 / 53) | 52.83% (28 / 53) | +5.66 pp (+3 tasks) |
| Level 2 Accuracy | 26.74% (23 / 86) | 24.42% (21 / 86) | 24.42% (21 / 86) | +0.00 pp (0 tasks) |
| Level 3 Accuracy | 3.85% (1 / 26) | 11.54% (3 / 26) | 11.54% (3 / 26) | +0.00 pp (0 tasks) |
| **Attachment Tasks** | **21.05%** (8 / 38) | **18.42%** (7 / 38) | **15.79%** (6 / 38) | **-2.63 pp (-1 task)** |
| **Non-Attachment Tasks** | **31.50%** (40 / 127) | **33.07%** (42 / 127) | **36.22%** (46 / 127) | **+3.15 pp (+4 tasks)** |
| **Completion Rate** | **78.18%** (129 / 165) | **77.58%** (128 / 165) | **49.70%** (82 / 165) | **-27.88 pp (-46 tasks)** |

### Key Research Findings
1. **Accuracy Gain**: Under the frozen two-stage capability-routing architecture, V4 solved 52/165 tasks (31.52%) versus 49/165 (29.70%) for the contemporaneous matched V3 control, an observed gain of +3 tasks (+1.82 pp), with improvements concentrated in Level 1 (+5.66 pp).
2. **Completion Rate Reduction**: V4 completion rate dropped from 77.58% to 49.70% (-27.88 pp). The completion reduction was associated primarily with worker-generation `MALFORMED_FUNCTION_CALL` finish-reason anomalies and, to a smaller extent, MAX_TOKENS truncation and other generation failures.
3. **Audited Regression Mechanism**: 10 of 10 regressions (100%) from matched V3 were associated with worker provider anomalies (8) or token budget truncation (2); 0 regressions resulted from calculation errors following successful Python execution.
4. **Successful-Python Subset**: On the 11 tasks where Python executed cleanly with valid answer extraction, V4 solved 9/11 (81.82%) vs. 8/11 (72.73%) for matched V3. *(Note: This comparison is descriptive only; routing is endogenous and does not represent an isolated causal estimate or proof of Python effectiveness in isolation.)*
5. **Operational Funnel & Failure Taxonomy**:
   - Final DIRECT worker dispatches: `74` (including 4 originating from router fallback)
   - Final PYTHON worker dispatches: `91`
   - Check: `74 + 91 = 165`
   - Python executions: `18` (11 successes, 7 failures, 73 unfulfilled, 80 fallbacks; `73 + 7 = 80`)
   - Executed Python failures: 4 MissingFinalAnswerMarker, 2 runtime failure, 1 syntax/AST rejection (total 7).
6. **Operational Latency & Resource Tradeoffs**: V4 increased standard LLM inference attempts per task (2 vs 1) and roughly doubled average wall-clock latency (10.62s vs 5.35s).

### Freeze Rule
V4 is frozen as the immutable research baseline for explicit two-stage capability routing:
```text
V4 = frozen V3 + explicit two-stage DIRECT/PYTHON capability-routing architecture
```
Future work must not alter V4 results or configuration. Any subsequent multi-turn agent, repair loop, or reflection work belongs to V5+.

---

---

## v5 — One-Shot Post-Answer Verification

Status: Frozen

Branch: `v5-one-shot-verification`

See [`experiments/v5/FROZEN.md`](experiments/v5/FROZEN.md) for full configuration manifest, controlled benchmark results, verifier mechanism analysis, failure taxonomy, and scientific conclusions.
See [`experiments/v5/README.md`](experiments/v5/README.md) for experiment overview and landing page.

### Research Question
> *Does adding an explicit, conservative one-shot post-answer verification and revision stage improve candidate answers already generated by the frozen V4 capability-routing pipeline?*

In accordance with strict ablation principles:
```text
V5 = frozen V4 + one-shot conservative post-answer verification/revision
```

### Architecture
```text
GAIA Question + Optional Attachment File
     ↓
ONE Tavily Search (Original Question as Query, Capped at 1,500 Chars, N ≤ 1)
     ↓
FileTool (Deterministic local extraction inherited from frozen V2/V3/V4, N ≤ 1)
     ↓
Stage 1: Frozen V4 Router Generation (`capability-router-v1`, mode="NONE", N ≤ 1)
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
     │   Verifier Bypassed Immediately (0 verifier LLM calls, preserves empty failure safety)
     │        ↓
     │   Final Answer = Empty / Upstream Output
     │
     └── [Candidate Present (Non-Empty)]
              ↓
         Stage 3: One-Shot Verifier Generation (`answer-verifier-v1`, mode="NONE", N ≤ 1)
         (Inputs: Question, Attachment Summary/Bytes, Search Results, Candidate Answer)
              ↓
         Deterministic Verdict Parser (`VERDICT: KEEP` or `VERDICT: REVISE with FINAL: <answer>`)
              ├── [Verdict == KEEP] → Post-Verification Answer = Candidate Answer (100% preservation)
              ├── [Verdict == REVISE] → Post-Verification Answer = Revised Answer
              └── [Verifier Failure / Error] → Fallback preserves Candidate Answer identically
              ↓
         Final Answer
```

### Frozen Invariants
- Standard execution uses up to three LLM generation attempts: 1 router + 1 worker + 1 verifier (if eligible). Total generation attempts per task $\le 3$.
- Maximum one Python execution per task (`python_execution_count in {0, 1}`).
- Router, both workers, and verifier all use Gemini with native function calling disabled (`mode="NONE"`).
- If routed to `DIRECT`, Python execution is structurally prohibited.
- The verifier operates strictly without tools: no search, no Python execution, no retries, and no multi-turn reflection loops.
- Empty candidate answers bypass the verifier immediately, preserving empty-candidate failure safety.
- Verifier parse errors, timeouts, or malformed outputs deterministically fall back to preserving the candidate answer.
- A `KEEP` verdict preserves the upstream candidate answer identically (100% preservation).

### Canonical Results (GAIA 2023 Validation Set, 165 Tasks)

| Metric | Matched V4 Control | Canonical V5 | Observed Delta |
| :--- | :---: | :---: | :---: |
| **Overall Accuracy** | **34.55%** (57 / 165) | **32.12%** (53 / 165) | **-2.42 pp (-4 tasks)** |
| Level 1 Accuracy | 54.72% (29 / 53) | 52.83% (28 / 53) | -1.89 pp (-1 task) |
| Level 2 Accuracy | 27.91% (24 / 86) | 23.26% (20 / 86) | -4.65 pp (-4 tasks) |
| Level 3 Accuracy | 15.38% (4 / 26) | 19.23% (5 / 26) | +3.85 pp (+1 task) |
| **Attachment Tasks** | **18.42%** (7 / 38) | **15.79%** (6 / 38) | **-2.63 pp (-1 task)** |
| **Non-Attachment Tasks** | **39.37%** (50 / 127) | **37.01%** (47 / 127) | **-2.36 pp (-3 tasks)** |
| **Completion Rate** | **51.52%** (85 / 165) | **47.27%** (78 / 165) | **-4.24 pp (-7 tasks)** |

> **Important Distinction on V4 Results**:
> The 57/165 V4 result reported in the V5 section is the contemporaneous matched V4 control for the V5 experimental campaign. It does not replace the historical frozen V4 canonical result of 52/165 documented above.

### Verifier Mechanism Result (Within Canonical V5 Run)

| Metric | Pre-Verification | Post-Verification | Net Impact |
| :--- | :---: | :---: | :---: |
| **Correct Tasks** | 53 / 165 (32.12%) | 53 / 165 (32.12%) | **0 tasks (0.00 pp)** |
| Improvements ($0 \rightarrow 1$) | — | — | 0 tasks |
| Regressions ($1 \rightarrow 0$) | — | — | 0 tasks |
| Stable Correct ($1 \rightarrow 1$) | — | — | 53 tasks |
| Stable Failure ($0 \rightarrow 0$) | — | — | 112 tasks |
| **Eligible Candidates** | — | — | 81 tasks |
| **KEEP Verdicts** | — | — | 78 tasks (96.30%) |
| **REVISE Verdicts** | — | — | 3 tasks (3.70%) |
| **Verifier Fallbacks** | — | — | 0 tasks |

The within-V5 verifier effect was 0 tasks / 0.00 pp under the official scorer. The verifier produced zero improvements and zero regressions on candidate answers.

### Key Research Findings
1. **Zero Net Within-Run Verifier Delta**: In this canonical V5 run, one-shot conservative post-answer verification produced zero improvements and zero regressions under the official GAIA scorer, leaving accuracy unchanged at 53/165.
2. **Conservative Failure Safety**: The verifier demonstrated strict safety on correct answers, producing zero regressions ($1 \rightarrow 0$) and preserving 100% of candidates on KEEP decisions.
3. **High KEEP Rate on Incorrect Candidates**: The verifier accepted 92.86% of incorrect candidate answers that reached it (26 / 28), reflecting high acceptance of plausible-sounding candidates.
4. **Upstream Candidate Starvation**: 84 of 112 failures (75.00%) occurred upstream of the verifier, primarily driven by provider-reported `MALFORMED_FUNCTION_CALL` finish-reason anomalies (76 tasks) on Python workers.
5. **Matched System-Level Comparison**: The observed -4 task difference between V5 (53) and matched V4 (57) occurred across separate stochastic runs and should not be attributed to any single mechanism without stronger causal evidence.
6. **Operational Cost**: V5 showed an observed +5.65s mean end-to-end latency difference versus the matched V4 control across separate runs; this is not an isolated causal measurement of verifier overhead. The verifier stage averaged 7.13s when invoked.

### Limitations
- The comparison between V5 and matched V4 was conducted across separate stochastic runs under the provider-default sampling configuration (temperature not explicitly fixed).
- Level 2 inter-task delay differed (V5: 1.0s, matched V4: 5.0s); classified as a non-blocking comparability limitation.
- The verifier was passive and text-only, operating without tool use, execution feedback, or external queries.

### Freeze Rule
V5 is frozen as the immutable research baseline for one-shot post-answer verification:
```text
V5 = frozen V4 + one-shot conservative post-answer verification/revision
```
Future work must not alter V5 results, agent runtime code, prompts, model configurations, or benchmark evaluations. Any further architectural experimentation belongs to V6+.

## Getting Started

### 1. Installation
Create and activate a virtual environment, then install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and configure your API keys:
```bash
cp .env.example .env
```
In `.env`:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_MAX_OUTPUT_TOKENS=2048
GEMINI_THINKING_LEVEL=medium
# GEMINI_TEMPERATURE= (leave unset for model default sampling)
TAVILY_API_KEY=your_tavily_api_key_here
```

For Hugging Face Spaces deployment, set `GEMINI_API_KEY` under **Space Settings → Variables and secrets**.

---

## Benchmark Data Setup (Private / Gitignored)

Local benchmark data (questions, ground-truth answers, and attachments) must be placed in `data/gaia/`. This directory is strictly gitignored to avoid leaking or publishing benchmark files.

Supported files:
- `data/gaia/metadata.jsonl` (or `val.jsonl`, `test.jsonl`)

Expected fields per task:
```json
{
  "task_id": "task-uuid",
  "question": "question text",
  "level": 1,
  "final_answer": "ground truth answer",
  "file_name": "attachment.xlsx"
}
```

---

## Experiment Tracking & Reproducibility

Every evaluation run records comprehensive provenance and inference metadata into version-segregated, append-only JSONL files (`experiments/v0/predictions_level_1.jsonl` or `experiments/v0/runs.jsonl`).

### Stored Metadata (Schema Version 2)
Each experiment record captures:
- **Run Identity**: Unique UUID `run_id` and UTC timestamp.
- **Git State**: Exact commit SHA (`git_commit`), active branch (`git_branch`), and working tree dirty status (`git_dirty`).
- **Configuration**: Model name, `temperature` (default `null` for model default), `max_output_tokens` (default `2048`), `thinking_level` (default `"medium"`), and prompt version (`baseline-v1`).
- **Prompt & Output Separation**: Full `prompt` text, untouched `raw_response`, normalized text (`normalized_response`), and cleaned `final_answer` are stored separately.
- **Tokens & Latency**: `input_tokens`, `output_tokens` (with candidate fallback), `thinking_tokens`, and `total_tokens` directly from model metadata, alongside wall-clock latency in seconds.
- **Completion-Aware Success**:
  - `request_success`: API executed without network/rate-limit exceptions.
  - `completion_success`: `true` only when `finish_reason == "STOP"` and `raw_response` is non-empty. Truncated answers (`MAX_TOKENS`) evaluate to `false`.

> **Note**: Raw experiment records are append-only logs and are ignored by Git. Safe, aggregated summaries (e.g. `experiments/v0/summary_level_1.json`) containing only high-level statistics are safe to track and publish.

---

## Running and Testing

### 1. Run One Development Question (Debug / Smoke Test)
Run a single question locally without submitting:
```bash
# Run with V5 one-shot post-answer verification
python evaluation/run_one.py --version v5 -i 0

# Run with V4 explicit two-stage capability router
python evaluation/run_one.py --version v4 -i 0

# Run with V3 controlled Python execution baseline
python evaluation/run_one.py --version v3 -i 0

# Run with V2 file attachment + web baseline
python evaluation/run_one.py --version v2 -i 0

# Run with V1 web search baseline
python evaluation/run_one.py --version v1 -i 0

# Run with V0 tool-free baseline
python evaluation/run_one.py --version v0 -i 0
```

### 2. Run a Complete Benchmark Level
Run tasks for a specific GAIA benchmark level from local data:
```bash
# Run V5 one-shot post-answer verification
python -m evaluation.run_level --version v5 --level 1

# Run V4 explicit two-stage capability router
python -m evaluation.run_level --version v4 --level 1

# Run V3 controlled Python execution baseline
python -m evaluation.run_level --version v3 --level 1

# Run V2 file attachment + web retrieval baseline
python -m evaluation.run_level --version v2 --level 1

# Run V1 single-shot web retrieval baseline
python -m evaluation.run_level --version v1 --level 1

# Run V0 tool-free baseline
python -m evaluation.run_level --version v0 --level 1
```
Useful arguments:
- `--limit 5`: Run only the first 5 tasks of that level.
- `--task-id <id>`: Run a single specific task by ID.
- `--no-resume`: Re-run all tasks instead of resuming skipped ones.
- `--no-eval`: Skip automatic local evaluation after the run completes.
- `--delay 1.0`: Throttle calls by N seconds between tasks.

### 3. Evaluate Predictions Locally
Compute metrics (accuracy, token usage, latency, attachment breakdown, file metrics, search metrics) against local ground truth without calling Hugging Face:
```bash
# Evaluate V5 predictions
python -m evaluation.evaluate --version v5 --level 1

# Evaluate V4 predictions
python -m evaluation.evaluate --version v4 --level 1

# Evaluate V3 predictions
python -m evaluation.evaluate --version v3 --level 1

# Evaluate V2 predictions
python -m evaluation.evaluate --version v2 --level 1

# Evaluate V1 predictions
python -m evaluation.evaluate --version v1 --level 1

# Evaluate V0 predictions
python -m evaluation.evaluate --version v0 --level 1
```

### 4. Run Unit Tests
```bash
python -m unittest discover tests
```

### 5. Run Hugging Face Space App (Official Course Submission)
```bash
python app.py
```
