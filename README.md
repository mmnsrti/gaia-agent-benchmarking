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
GEMINI_TEMPERATURE=0.0
GEMINI_MAX_OUTPUT_TOKENS=512
```

For Hugging Face Spaces deployment, set `GEMINI_API_KEY` under **Space Settings → Variables and secrets**.

---

## Experiment Tracking & Reproducibility

Every development run via `evaluation/run_one.py` records comprehensive provenance and inference metadata into version-segregated, append-only JSONL files (`experiments/v0/runs.jsonl`).

### Stored Metadata
Each experiment record captures:
- **Run Identity**: Unique UUID `run_id` and UTC timestamp.
- **Git State**: Exact commit SHA (`git_commit`), active branch (`git_branch`), and working tree dirty status (`git_dirty`).
- **Configuration**: Model name, `temperature` (default `0.0`), `max_output_tokens` (default `512`), and prompt version (`baseline-v1`).
- **Prompt & Output Separation**: Full `prompt` text, untouched `raw_response`, and cleaned `final_answer` are stored separately.
- **Tokens & Latency**: `input_tokens`, `output_tokens`, and `total_tokens` directly from model metadata, alongside wall-clock latency in seconds.
- **Structured Error Handling**: `success` boolean, `error_type`, and `error_message` instead of converting exceptions into fake answers.

> **Note**: Raw experiment records in `experiments/v0/runs.jsonl` are append-only source-of-truth logs and should not be manually edited after runs.

---

## Running and Testing

### Run One Development Question (No Leaderboard Submission)
Run a single question from the GAIA course benchmark locally without submitting:
```bash
python evaluation/run_one.py -i 0
```
Run a specific task ID:
```bash
python evaluation/run_one.py -t <task_id>
```
Each run appends an experiment record to `experiments/v0/runs.jsonl`.

### Run Unit Tests
```bash
python -m unittest discover tests
```

### Run Gradio App
```bash
python app.py
```
