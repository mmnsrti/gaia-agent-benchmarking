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
V1 is strictly an ablation baseline, not an optimized final agent. To isolate the contribution of retrieval:
1. **Single-Shot Retrieval**: Exactly one search is executed per task.
2. **Original Question as Query**: The original GAIA question is passed directly as the search query without LLM query rewriting or expansion.
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
6. **Deterministic Search Failure Fallback**:
   If the search API fails (network timeout, HTTP error, missing key), the agent deterministically falls back to the V0 LLM-only prompt path (`baseline-v1`). The fallback is recorded in experiment metadata and the benchmark run continues safely.
6. **Deterministic Search Failure Fallback & Prompt Provenance**:
   If the search API fails (network timeout, HTTP error, missing key), the agent deterministically falls back to the V0 LLM-only prompt path (`fallback_prompt_version = baseline-v1`). The primary prompt version is recorded as `primary_prompt_version = web-search-v1`, ensuring fallback events are accurately tracked per-task without misclassifying the prompt provenance of the entire run.
7. **What V1 Intentionally Does NOT Include**:
   - Multi-hop or iterative searches
   - Query rewriting or keyword extraction
   - Browser automation, full-page HTML crawling, or raw webpage content
   - Planning, reflection, or verification loops
   - File attachment processing
   - Python code execution

---

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
GEMINI_MODEL=gemini-3.5-flash
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
# Run with V1 web search baseline
python evaluation/run_one.py --version v1 -i 0

# Run with V0 tool-free baseline
python evaluation/run_one.py --version v0 -i 0
```

### 2. Run a Complete Benchmark Level
Run tasks for a specific GAIA benchmark level from local data:
```bash
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
Compute metrics (accuracy, token usage, latency, attachment breakdown, search metrics) against local ground truth without calling Hugging Face:
```bash
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
