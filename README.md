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
Copy `.env.example` to `.env` and set your Google Gemini API key:
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
python evaluation/run_one.py -i 0
```

### 2. Run a Complete Benchmark Level
Run all tasks for a specific GAIA benchmark level from local data:
```bash
python -m evaluation.run_level --level 1
python -m evaluation.run_level --level 2
python -m evaluation.run_level --level 3
```
Useful arguments:
- `--limit 5`: Run only the first 5 tasks of that level.
- `--task-id <id>`: Run a specific task by ID.
- `--no-resume`: Re-run all tasks instead of resuming skipped ones.
- `--no-eval`: Skip automatic local evaluation after the run completes.

### 3. Evaluate Predictions Locally
Compute metrics (accuracy, token usage, latency, attachment breakdown) against local ground truth without calling Hugging Face:
```bash
python -m evaluation.evaluate --level 1
```

### 4. Run Unit Tests
```bash
python -m unittest discover tests
```

### 5. Run Hugging Face Space App (Official Course Submission)
```bash
python app.py
```
