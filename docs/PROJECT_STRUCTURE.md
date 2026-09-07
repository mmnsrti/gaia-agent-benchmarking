# GAIA Agent Benchmarking — Project Structure

This document defines the initial structure of the **GAIA Agent Benchmarking** project and the responsibility of each module.

The project starts from the official Hugging Face Agents Course final-assignment template and is gradually refactored into a modular, testable, and benchmark-oriented agent system.

---

## Project Structure

```text
gaia-agent-benchmarking/
│
├── app.py
│
├── agent/
│   ├── __init__.py
│   ├── agent.py
│   └── llm.py
│   ├── agent.py                 (GAIAAgent, GAIAWebAgent)
│   └── llm.py                   (LLMClient, GenerateContentConfig)
│
├── tools/
│   ├── __init__.py
│   └── ...
│   └── web_search.py            (TavilySearchTool, WebSearchResult)
│
├── evaluation/
│   ├── __init__.py
│   ├── gaia_client.py
│   ├── dataset.py
│   ├── runner.py
│   ├── run_one.py
│   ├── run_level.py
│   ├── evaluate.py
│   ├── metrics.py
│   ├── runner.py                (execute_task, completion tracking)
│   ├── run_one.py               (single-question debug runner)
│   ├── run_level.py             (level-wide benchmark runner)
│   ├── evaluate.py              (official evaluation & metrics calculator)
│   ├── metrics.py               (official GAIA question scorer)
│   ├── analyze_errors.py        (reproducible V1 error taxonomy & transition)
│   └── experiment_logger.py
│
├── experiments/
│   └── v0/
│       ├── .gitkeep
│       ├── config.json
│       ├── summary_level_1.json
│       ├── runs.jsonl             (gitignored)
│       └── predictions_*.jsonl    (gitignored)
│   ├── runs.jsonl               (gitignored global runs)
│   ├── v0/
│   │   ├── config.json
│   │   ├── summary_level_*.json (public aggregate summaries)
│   │   ├── error_analysis_*.json(public sanitized failure analyses)
│   │   ├── predictions_*.jsonl  (gitignored private task records)
│   │   └── detailed_eval_*.jsonl(gitignored private detailed traces)
│   └── v1/
│       ├── config.json          (frozen V1 configuration)
│       ├── summary_level_*.json (public aggregate summaries)
│       ├── error_analysis_*.json(public sanitized failure analyses)
│       ├── v0_v1_error_comparison.json
│       ├── comparison_summary.json
│       ├── predictions_*.jsonl  (gitignored private task records)
│       └── detailed_eval_*.jsonl(gitignored private detailed traces)
│
├── data/
│   └── gaia/                      (gitignored benchmark data)
│   └── gaia/                    (gitignored benchmark dataset)
│       └── metadata.jsonl
│
├── prompts/
│   ├── __init__.py
│   └── baseline.py
│   ├── baseline.py              (baseline-v1)
│   └── web_search.py            (web-search-v1)
│
├── tests/
│   ├── __init__.py
│   ├── test_agent.py
│   ├── test_llm.py
│   ├── test_web_search.py
│   ├── test_error_analysis.py
│   ├── test_run_one.py
│   ├── test_experiment_logger.py
│   └── test_evaluation_pipeline.py
│
├── requirements.txt
├── README.md
└── .env.example
```

---

## `app.py`

The Hugging Face Space entry point.

Responsibilities:

- Build the Gradio interface.
- Handle Hugging Face authentication.
- Trigger development or evaluation runs.
- Connect the UI to the agent.
- Keep Hugging Face-specific application logic separate from the agent implementation.

`app.py` should remain relatively thin.

It should **not** contain:

- Agent reasoning logic.
- Tool implementations.
- Prompt definitions.
- GAIA API internals.
- File-processing logic.

---

## `agent/`

Contains the core agent implementation.

### `agent/__init__.py`

Marks `agent` as a Python package.

It may later expose the main agent class:

```python
from .agent import GAIAAgent
```

### `agent/agent.py`

The main agent entry point.

Initial responsibility:

```text
Question
   ↓
Agent
   ↓
Final Answer
```

Later versions may evolve into:

```text
Question
   ↓
Understand Task
   ↓
Plan
   ↓
Select Tool
   ↓
Execute
   ↓
Observe
   ↓
Refine
   ↓
Verify
   ↓
Final Answer
```

The agent should eventually receive both:

```python
task_id
question
```

instead of only the question text.

Example interface:

```python
class GAIAAgent:
    def __call__(self, task_id: str, question: str) -> str:
        ...
```

The returned value should be the **final GAIA answer only**, without unnecessary explanation.

---

## `tools/`

Contains all tools available to the agent.

Each tool should have one clear responsibility.

Possible future tools:

```text
tools/
├── web_search.py
├── browser.py
├── python_tool.py
├── file_reader.py
├── spreadsheet.py
├── vision.py
└── youtube.py
```

Examples:

### Web Search

```python
search_web(query)
```

Used to find relevant sources.

### Browser / Page Reader

```python
read_url(url)
```

Used to extract useful information from a webpage.

### Python Tool

```python
run_python(code)
```

Used for:

- Calculations
- Data transformations
- Small reasoning scripts
- Table processing

### File Reader

Responsible for routing files based on their type.

Example:

```text
.xlsx → spreadsheet handler
.csv  → dataframe handler
.txt  → text reader
.pdf  → PDF reader
.png  → vision model
.jpg  → vision model
```

Tools should stay independent from the main agent whenever possible.

---

## `evaluation/`

Contains GAIA-specific evaluation and API logic.

### `evaluation/__init__.py`

Marks the directory as a Python package.

### `evaluation/gaia_client.py`

Responsible for communicating with the Hugging Face GAIA evaluation backend.

Expected responsibilities:

```text
GET /questions
GET /random-question
GET /files/{task_id}
POST /submit
```

Possible interface:

```python
class GAIAClient:
    def get_questions(self):
        ...

    def get_random_question(self):
        ...

    def download_file(self, task_id):
        ...

    def submit(self, username, agent_code, answers):
        ...
```

The goal is to remove GAIA API code from `app.py`.

---

## `prompts/`

Contains prompt definitions used by the agent.

### `prompts/system_prompt.py`

Stores the main system prompt and related prompt templates.

Example responsibilities:

- Define the agent's role.
- Explain when tools should be used.
- Tell the model to verify evidence.
- Enforce concise final answers.
- Prevent unnecessary answer prefixes such as:

```text
FINAL ANSWER:
The answer is:
Based on my research:
```

For GAIA, answer formatting matters because evaluation may depend on exact output matching.

---

## `requirements.txt`

Contains runtime dependencies.

Initial dependencies come from the official Hugging Face template.

Example:

```text
gradio[oauth]
requests
pandas
```

New dependencies should only be added when a feature actually needs them.

Possible future dependencies:

```text
openpyxl
beautifulsoup4
pypdf
```

Avoid adding large frameworks before they are necessary.

---

## `.env.example`

Documents required environment variables without exposing secrets.

Example:

```env
LLM_API_KEY=
SEARCH_API_KEY=
```

Never commit real API keys.

The real local `.env` file should be included in `.gitignore`.

---

## `README.md`

The public project overview.

The final README should eventually include:

- Project goal
- What GAIA measures
- Agent architecture
- Available tools
- Evaluation methodology
- Baseline results
- Improvement experiments
- Error analysis
- Final benchmark score
- Limitations
- How to run locally
- Hugging Face Space link

---

# Development Strategy

The project should evolve incrementally.

Do **not** build every component at once.

---

## Phase 0 — Official Template

Start with the official Hugging Face final-assignment template.

Verify:

- Local execution works.
- Hugging Face login works.
- Questions can be fetched.
- The Space builds successfully.
- GitHub and Hugging Face remotes work.

---

## Phase 1 — Refactor the Agent

Move `BasicAgent` out of `app.py`.

Before:

```text
app.py
├── UI
├── API logic
├── Agent
└── Submission
```

After:

```text
app.py
agent/
└── agent.py
```

No behavior should change yet.

---

## Phase 2 — Development Mode

Separate development from official evaluation.

Development mode:

```text
1 question
↓
Agent
↓
Display result
↓
No submission
```

Official evaluation:

```text
20 questions
↓
Agent
↓
Collect answers
↓
POST /submit
```

This prevents unnecessary full benchmark runs during development.

---

## Phase 3 — Baseline v0

Build the simplest possible baseline:

```text
Question
↓
LLM
↓
Answer
```

No tools.

Measure the initial score.

This establishes a baseline for future improvements.

---

## Phase 4 — Analyze Task Requirements

Categorize the 20 GAIA tasks.

Possible categories:

- Reasoning-only
- Web search
- Multi-hop research
- Video
- Image
- Spreadsheet
- File processing
- Calculation
- Structured data lookup

Only add tools that are actually needed.

---

## Phase 5 — Tool-Using Agent

Add tools incrementally.

Suggested order:

```text
Web Search
↓
Web Page Reader
↓
Python / Calculator
↓
File Downloading
↓
Spreadsheet Processing
↓
Vision
↓
Video / YouTube
```

Measure benchmark performance after meaningful changes.

---

## Phase 6 — Planning and Tool Selection

Upgrade the agent from a single LLM call into a tool-using loop.

Target flow:

```text
Question
↓
Analyze
↓
Plan
↓
Choose Tool
↓
Execute
↓
Observe
↓
Continue or Refine
↓
Verify
↓
Answer
```

Avoid introducing multi-agent systems unless experiments show a clear benefit.

---

## Phase 7 — Answer Normalization

Before submitting an answer:

```text
Raw Model Output
↓
Extract Final Answer
↓
Normalize
↓
Submit
```

Example:

Bad:

```text
The final answer is Saint Petersburg.
```

Preferred:

```text
Saint Petersburg
```

---

## Phase 8 — Error Analysis

Every failed task should be classified.

Suggested failure categories:

```text
Planning failure
Tool-selection failure
Search failure
Navigation failure
Extraction failure
Reasoning failure
Calculation failure
File-processing failure
Answer-formatting failure
```

Example:

```text
Task: Q12

Result:
Incorrect

Failure Type:
Search failure

Root Cause:
The first search query was too broad.

Improvement:
Add query reformulation after weak search results.
```

---

## Phase 9 — Experiment Tracking

Track major agent versions.

Example:

| Version | Change | Score |
|---|---|---:|
| v0 | LLM only | TBD |
| v1 | + Web search | TBD |
| v2 | + File tools | TBD |
| v3 | + Planning | TBD |
| v4 | + Search refinement | TBD |
| v5 | + Verification | TBD |

This turns the project from a course assignment into a proper benchmarking project.

---

# Design Principles

## Keep the agent modular

The LLM, tools, evaluation client, prompts, and UI should not be tightly coupled.

## Start simple

Do not introduce:

- Multi-agent systems
- Vector databases
- Memory systems
- LangGraph
- Complex RAG
- Reflection loops

until there is evidence they are needed.

## Measure every meaningful improvement

A new feature should ideally answer:

> Did this actually improve GAIA performance?

## Preserve the official submission flow

The Hugging Face evaluation endpoint and expected submission format should remain compatible with the official assignment.

## Optimize for reproducibility

The final repository should clearly show:

```text
Baseline
→ Experiment
→ Result
→ Failure Analysis
→ Improvement
```

---

# Target Architecture

The long-term architecture may look like:

```text
                  ┌──────────────┐
                  │   Gradio UI  │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │    app.py    │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │  GAIA Agent  │
                  └──────┬───────┘
                         │
             ┌───────────┼───────────┐
             │           │           │
             ▼           ▼           ▼
        Web Search     Python      File Tools
             │                       │
             ▼                       ▼
        Web Reader              PDF / XLSX /
                                CSV / Vision
             │
             └───────────┬───────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ Verification │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ Final Answer │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ GAIA Client  │
                  └──────┬───────┘
                         │
                         ▼
                    Submission
```

---

# Current Status & Research Evolution

### V0 — Completed LLM-Only Baseline
- Canonical model: `gemini-3.5-flash-lite`
- Clean, tool-free baseline agent (`GAIAAgent` in `agent/agent.py`).
- Reproducible inference tracking with schema version 2 (`experiments/v0/runs.jsonl`, git metadata, thinking tokens, completion-aware success flags).
- Research evaluation pipeline (`evaluation/run_level.py`, `evaluation/evaluate.py`, `evaluation/metrics.py`, `evaluation/dataset.py`) supporting local Level 1/2/3 benchmarking against ground truth without calling Hugging Face `/submit`.
- Frozen historical performance: Level 1: 26.42%, Level 2: 18.60%, Level 3: 11.54%, Overall: 20.00% (33 / 165).
- Matched-control performance: Level 1: 28.30%, Level 2: 19.77%, Level 3: 7.69%, Overall: 20.61% (34 / 165).

### V1 — Completed Single-Shot Web Retrieval Baseline
- Canonical model: `gemini-3.5-flash-lite`
- **Workflow Nature**: V1 is strictly a controlled **single-shot retrieve-then-read workflow** and NOT an autonomous multi-tool or planning agent.
- Exactly one deterministic search is executed per task using the original question.
- On search failure, deterministically falls back to LLM-only baseline prompt (`baseline-v1`) while preserving provenance (`primary_prompt_version = web-search-v1`, `fallback_prompt_version = baseline-v1`).
- Canonical benchmark performance: Level 1: 52.83%, Level 2: 27.91%, Level 3: 11.54%, Overall: 33.33% (55 / 165).
- Provides a matched-control estimate of +24.53 pp accuracy gain on Level 1 and +18.11 pp on non-attachment tasks overall (40.94% vs. 22.83% in V0 matched-control).
- Identified persistent bottleneck: Web retrieval did not improve attachment-task accuracy in this run (7.89% in V1 vs 13.16% in V0 matched-control; observed delta: -5.27 pp; difference may also reflect run-to-run variability). Attachment tasks represent 31.82% of all V1 errors.

### V2 — Next Planned Capability: File / Attachment Handling
- Based on empirical error analysis of V1, external web search alone cannot solve tasks requiring local file inspection.
- V2 will incrementally add file ingestion and processing tools (PDF, XLSX, CSV, images) while preserving controlled benchmarking rigor.

---

## Core Component Responsibilities

- **`GAIAAgent`** (`agent/agent.py`): Minimal, tool-free LLM baseline agent executing Gemini generation via `baseline-v1` prompt.
- **`GAIAWebAgent`** (`agent/agent.py`): Single-shot retrieval baseline executing exactly one Tavily search per task, formatting snippets into `web-search-v1`, and cleanly falling back to `baseline-v1` if retrieval fails.
- **`TavilySearchTool`** (`tools/web_search.py`): Deterministic provider abstraction using `tavily-python` (depth="basic", max_results=5, no answer field, no raw HTML, deterministic 1500-char provider query truncation, logging truncation metadata).
- **`runner`** (`evaluation/runner.py`): Orchestrates task execution, latency timing, token usage extraction from Gemini metadata, completion-aware success tracking, search provenance logging, and append-only record writing.
- **`official GAIA scorer`** (`evaluation/metrics.py`): The official GAIA benchmark question scorer evaluating exact numeric and string normalization against ground truth.
- **`V1 experiment config`** (`experiments/v1/config.json`): Reproducible configuration documenting model name, prompt versions, search depth, token limits, and experiment parameters.
- **`public summaries`** (`experiments/v*/summary_*.json`): High-level, sanitized aggregate metrics (accuracy, latency, token usage, attachment breakdown, search success rates) safe for public repository tracking.
- **`private detailed predictions/evaluations`** (`experiments/v*/detailed_eval_*.jsonl` and `predictions_*.jsonl`): Complete per-task execution traces (including questions, ground truths, raw model responses, and retrieved snippets) strictly gitignored to preserve benchmark security.
