# BenchmarkHub

A web platform for systematically evaluating and comparing Large Language Models across standardized benchmarks — **text, vision, audio, and agentic**.

Built with Django 4, Bootstrap 5.3, and SQLite. Supports local models (Ollama, vLLM) and cloud APIs (OpenAI, Anthropic, Mistral, Google Gemini, Groq, Cohere, Together AI). Vision benchmarks (MMMU, ScienceQA, AI2D, MMBench, ChartQA), audio/ASR benchmarks (LibriSpeech), and agentic benchmarks (GAIA, BFCL) are supported out of the box.

---

## Requirements

- Python 3.10+
- [Conda](https://docs.conda.io/) or pip
- (Optional) [Ollama](https://ollama.ai/) for local models

Python dependencies (see `requirements.txt`):

```
django>=4.2
datasets
huggingface_hub
pillow          # vision benchmarks (image decoding/saving)
soundfile       # audio benchmarks (WAV export)
jiwer           # audio benchmarks (Word Error Rate metric)
openpyxl
requests
whitenoise
```

---

## Installation

```bash
# 1. Clone the repository
git clone <repo-url>
cd benchmark_web_2_style

# 2. Create and activate a conda environment
conda create -n benchmark_web_2 python=3.11
conda activate benchmark_web_2

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables (copy and edit)
cp .env.example .env   # or export manually:
export SECRET_KEY="change-me-in-production"
export DEBUG=True
export ALLOWED_HOSTS=localhost,127.0.0.1

# 5. Apply migrations
python manage.py migrate

# 6. (Optional) Load built-in benchmarks
python manage.py load_benchmark --list          # see available datasets ([IMG]/[AUD]/[AGT] = multimodal)
python manage.py load_benchmark mmlu            # load MMLU
python manage.py load_benchmark arc_challenge   # load ARC Challenge
python manage.py load_benchmark mmbench         # load a vision benchmark (images saved to media/)
python manage.py load_benchmark librispeech     # load an audio benchmark (WAVs saved to media/)

# 7. Start the development server
python manage.py runserver
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Quick Start (3-step)

```bash
# Step 1 — Add a provider
python manage.py bm_provider add ollama Ollama --type ollama --url http://localhost:11434

# Step 2 — Load a benchmark
python manage.py load_benchmark mmlu

# Step 3 — Run the benchmark
python manage.py bm_run mmlu ollama llama3.2 --num-questions 50 --wait
```

---

## Web Interface

| URL | Description |
|-----|-------------|
| `/` | Dashboard — KPIs, recent runs, top models, coverage matrix |
| `/benchmarks/` | Browse and manage benchmarks |
| `/benchmarks/<slug>/` | Benchmark detail — questions, export, run |
| `/providers/` | Manage providers |
| `/providers/<slug>/` | Provider detail — connection test, model list |
| `/runs/` | All benchmark runs with filters |
| `/runs/<id>/` | Run detail — per-question results, score breakdown, export |
| `/runs/compare/` | Side-by-side comparison of up to 4 runs |
| `/runs/ab-test/` | A/B test two prompt variants (McNemar's χ² test) |
| `/runs/bulk/` | Launch multiple runs at once |
| `/runs/sweep/` | Parameter sweep (temperature or prompt) |
| `/runs/templates/` | Saved run templates |
| `/runs/scheduled/` | Scheduled runs — once, daily, or weekly |
| `/runs/leaderboard/` | Model rankings per benchmark |
| `/runs/hardness/` | Question difficulty classification across all runs |
| `/runs/model-history/` | One model's performance over time |
| `/runs/cost-estimator/` | Pre-run cost estimate |
| `/benchmarks/suites/` | Benchmark suites — group and run multiple benchmarks |
| `/benchmarks/suites/<id>/` | Suite run detail |
| `/benchmarks/prompts/` | Prompt library |
| `/howto/` | How-to guide |
| `/api/v1/` | REST API root |
| `/api/docs/` | API documentation |

---

## CLI Reference

All management commands support `--help`:

```bash
python manage.py bm_run --help
python manage.py bm_provider --help
# etc.
```

### `bm_provider` — Manage providers

```bash
# List all configured providers
python manage.py bm_provider list

# Add a provider
python manage.py bm_provider add ollama Ollama \
    --type ollama --url http://localhost:11434

python manage.py bm_provider add my-openai "OpenAI" \
    --type openai --key sk-...

python manage.py bm_provider add claude Anthropic \
    --type anthropic --key sk-ant-... --default-model claude-opus-4-8

python manage.py bm_provider add gemini "Google Gemini" \
    --type gemini --key AIza...

# Test connection
python manage.py bm_provider test ollama
python manage.py bm_provider test ollama --model llama3.2

# List available models from a provider
python manage.py bm_provider models ollama

# Delete a provider
python manage.py bm_provider delete old-provider
```

Supported `--type` values: `ollama`, `openai`, `anthropic`, `vllm`, `gemini`, `groq`, `mistral`, `cohere`, `together`

---

### `bm_run` — Start a benchmark run

```bash
python manage.py bm_run <benchmark> <provider> <model> [options]

# Examples
python manage.py bm_run mmlu ollama llama3.2
python manage.py bm_run medqa openai gpt-4o --temperature 0 --wait
python manage.py bm_run arc_challenge anthropic claude-opus-4-8 \
    --num-questions 100 \
    --system-prompt "Answer with a single letter." \
    --few-shot 3 \
    --cot \
    --tags baseline,v1 \
    --wait

# Vision benchmark — use a vision-capable model
python manage.py bm_run mmbench ollama qwen2.5vl:7b --num-questions 50 --wait
python manage.py bm_run mmmu openai gpt-4o --num-questions 100 --wait

# Audio benchmark (ASR) — use an audio-capable model
python manage.py bm_run librispeech openai gpt-4o-audio-preview --num-questions 50 --wait
python manage.py bm_run librispeech groq whisper-large-v3 --num-questions 50 --wait
```

| Option | Default | Description |
|--------|---------|-------------|
| `--temperature` | `0.0` | Sampling temperature |
| `--max-tokens` | `512` | Maximum output tokens |
| `--num-questions` | `0` (all) | Limit number of questions |
| `--system-prompt` | `""` | Custom system prompt text |
| `--few-shot` | `0` | Number of few-shot examples |
| `--cot` | off | Append "Let's think step by step" |
| `--workers` | `1` | Parallel worker threads |
| `--tags` | `""` | Comma-separated tags |
| `--notes` | `""` | Free-text notes |
| `--webhook` | `""` | Webhook URL for completion notification |
| `--wait` | off | Block until run completes and print score |

---

### `bm_status` — Check run status

```bash
# One-shot status check
python manage.py bm_status 42

# Watch live until complete (poll every 2s)
python manage.py bm_status 42 --watch
```

---

### `bm_list` — List objects

```bash
# List runs (default)
python manage.py bm_list runs
python manage.py bm_list runs --benchmark mmlu --status completed --limit 20

# List benchmarks
python manage.py bm_list benchmarks
python manage.py bm_list benchmarks --loaded
python manage.py bm_list benchmarks --type vision    # filter by type: text/vision/audio/agentic

# List providers
python manage.py bm_list providers

# List suites
python manage.py bm_list suites
```

---

### `bm_bulk` — Launch multiple runs at once

```bash
# Run one benchmark on multiple provider/model combos
python manage.py bm_bulk mmlu \
    ollama/llama3.2 \
    openai/gpt-4o \
    anthropic/claude-opus-4-8

# With shared options
python manage.py bm_bulk arc_challenge \
    ollama/llama3.2 ollama/mistral \
    --num-questions 100 --temperature 0 --wait
```

---

### `bm_sweep` — Parameter sweep

```bash
# Temperature sweep
python manage.py bm_sweep mmlu ollama llama3.2 \
    --temp-range 0.0 1.0 0.2

# Prompt sweep (by prompt IDs from the library)
python manage.py bm_sweep mmlu ollama llama3.2 \
    --prompt-ids 1 2 3

# Prompt sweep (inline texts)
python manage.py bm_sweep mmlu ollama llama3.2 \
    --prompt-texts "Answer briefly." "Explain your reasoning." "Answer with a single letter."

# With shared options
python manage.py bm_sweep arc_challenge openai gpt-4o \
    --temp-range 0 1 0.25 --num-questions 50 --wait
```

---

### `bm_suite` — Benchmark suites

```bash
# List all suites
python manage.py bm_suite list

# Create a suite (benchmark slugs)
python manage.py bm_suite create reasoning \
    "Reasoning Suite" \
    arc_challenge hellaswag winogrande

# Run all benchmarks in a suite
python manage.py bm_suite run reasoning ollama llama3.2
python manage.py bm_suite run reasoning openai gpt-4o \
    --num-questions 100 --wait

# Delete a suite
python manage.py bm_suite delete reasoning
```

---

### `bm_export` — Export results

```bash
# Export run results to CSV (default)
python manage.py bm_export run 42

# Export run results to Excel
python manage.py bm_export run 42 --format excel --output results_42.xlsx

# Export benchmark questions to CSV
python manage.py bm_export benchmark mmlu

# Export benchmark questions to Excel
python manage.py bm_export benchmark arc_challenge --format excel
```

---

### `bm_cancel` — Cancel a run

```bash
# Cancel a running run
python manage.py bm_cancel 42

# Cancel and delete the run record
python manage.py bm_cancel 42 --delete
```

---

### `bm_leaderboard` — Show leaderboard

```bash
# All benchmarks
python manage.py bm_leaderboard

# Specific benchmark
python manage.py bm_leaderboard --benchmark mmlu

# Limit rows
python manage.py bm_leaderboard --benchmark arc_challenge --limit 10
```

---

### `bm_import_results` — Import pre-computed results

Import answers from a CSV file to create a run without calling an LLM API.

```bash
python manage.py bm_import_results mmlu ollama llama3.2 results.csv
```

CSV format:

```
question_id,model_answer,is_correct,response_time_ms,input_tokens,output_tokens
1,A,true,120,150,5
2,B,false,98,150,5
```

---

### `bm_create` — Create a custom benchmark

```bash
python manage.py bm_create my-benchmark "My Custom Benchmark" questions.csv \
    --category reasoning \
    --description "Custom benchmark for domain X"
```

CSV format:

```
question,option_a,option_b,option_c,option_d,correct_answer,subject
"What is ...?",A text,B text,C text,D text,A,Biology
```

---

### `bm_import_hf` — Import from HuggingFace Hub

```bash
# Basic import
python manage.py bm_import_hf allenai/ai2_arc ARC-Challenge test

# With explicit column mapping
python manage.py bm_import_hf \
    cais/mmlu anatomy test \
    --question-col question \
    --choices-col choices \
    --answer-col answer \
    --subject-col subject \
    --slug mmlu-anatomy \
    --name "MMLU Anatomy" \
    --category knowledge
```

---

### `bm_import_rag` — Create a RAG benchmark

```bash
python manage.py bm_import_rag my-rag "RAG Benchmark" rag_questions.csv \
    --context-col context \
    --category reading_comprehension
```

CSV format:

```
question,context,option_a,option_b,option_c,option_d,correct_answer
"Based on the passage, ...",<document text>,A,B,C,D,B
```

---

## Scheduled Runs

BenchmarkHub includes a background scheduler that runs benchmarks on a schedule.

```bash
# Start the scheduler daemon
python manage.py run_scheduler

# Manage scheduled runs via the web UI at /runs/scheduled/
# Or create them programmatically via the REST API
```

Schedules can be: `once`, `daily`, or `weekly`.

---

## REST API

Base URL: `/api/v1/`

### Benchmarks

```bash
# List all benchmarks
curl http://localhost:8000/api/v1/benchmarks/

# Get a specific benchmark
curl http://localhost:8000/api/v1/benchmarks/mmlu/
```

### Providers

```bash
# List all providers
curl http://localhost:8000/api/v1/providers/
```

### Runs

```bash
# List all runs
curl http://localhost:8000/api/v1/runs/

# Get run details
curl http://localhost:8000/api/v1/runs/42/

# Get run results
curl http://localhost:8000/api/v1/runs/42/results/

# Create and start a run
curl -X POST http://localhost:8000/api/v1/runs/ \
  -H "Content-Type: application/json" \
  -d '{
    "benchmark": "mmlu",
    "provider": "ollama",
    "model_name": "llama3.2",
    "temperature": 0.0,
    "max_tokens": 512,
    "num_questions": 100
  }'

# Delete a run
curl -X DELETE http://localhost:8000/api/v1/runs/42/
```

Full interactive API docs: [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/)

---

## Supported Providers

| Type | Description | Vision | Audio | Requires |
|------|-------------|:------:|:-----:|----------|
| `ollama` | Local Ollama server | ✅ | — | Running Ollama instance |
| `vllm` | Local vLLM server | ✅ | ✅ | Running vLLM instance |
| `openai` | OpenAI API | ✅ | ✅ | `OPENAI_API_KEY` or `--key` |
| `anthropic` | Anthropic Claude API | ✅ | — | `ANTHROPIC_API_KEY` or `--key` |
| `gemini` | Google Gemini API | ✅ | ✅ | `GOOGLE_API_KEY` or `--key` |
| `groq` | Groq API | ✅ | ✅ (whisper) | `GROQ_API_KEY` or `--key` |
| `mistral` | Mistral AI API | ✅ | — | `MISTRAL_API_KEY` or `--key` |
| `cohere` | Cohere API | — | — | `COHERE_API_KEY` or `--key` |
| `together` | Together AI API | ✅ | ✅ | `TOGETHER_API_KEY` or `--key` |

**Vision** requires a vision-capable model (e.g. `qwen2.5vl`, `gemma3`, `llava` on Ollama; `gpt-4o`; `claude-opus-4-8`; `gemini-2.0-flash`; `pixtral`). **Audio** requires an audio-capable model (`gpt-4o-audio-preview`, `whisper-*` / `gpt-4o-transcribe` on OpenAI, `whisper-large-v3` on Groq, Gemini, or an audio model served by vLLM). Providers without vision/audio support return an explicit per-question error instead of silently evaluating without the media — scores are never computed on text-only input for a multimodal benchmark.

---

## Built-in Benchmarks

A selection of the 50+ available datasets:

| Slug | Name | Category | Type |
|------|------|----------|------|
| `mmlu` | MMLU | knowledge | text |
| `arc_challenge` | ARC Challenge | reasoning | text |
| `arc_easy` | ARC Easy | reasoning | text |
| `hellaswag` | HellaSwag | common_sense | text |
| `winogrande` | WinoGrande | common_sense | text |
| `boolq` | BoolQ | language | text |
| `openbookqa` | OpenBookQA | knowledge | text |
| `truthfulqa` | TruthfulQA | knowledge | text |
| `gsm8k` | GSM8K | math | text |
| `math500` | MATH-500 | math | text |
| `medqa_usmle` | MedQA USMLE | clinical | text |
| `triviaqa` | TriviaQA | knowledge | text |
| `bbh` | BIG-Bench Hard | reasoning | text |
| `aqua_rat` | AQuA-RAT | math | text |
| `rte` | RTE | language | text |
| `multinli` | MultiNLI | language | text |
| `hle` | Humanity's Last Exam | reasoning | text |
| `scienceqa_vision` | ScienceQA (Vision) | vision | vision |
| `ai2d` | AI2D Diagrams | vision | vision |
| `mmmu` | MMMU (30 subjects) | vision | vision |
| `mmbench` | MMBench | vision | vision |
| `chartqa` | ChartQA | vision | vision |
| `gaia` | GAIA (text-only subset) | agentic | agentic |
| `bfcl_simple` | BFCL Simple (function calling) | agentic | agentic |
| `librispeech` | LibriSpeech test-clean (ASR) | audio | audio |

List all available datasets: `python manage.py load_benchmark --list`

---

## Multimodal Benchmarks

BenchmarkHub supports four benchmark types: `text`, `vision`, `audio`, and `agentic`.

### How it works

- **Loading** — vision loaders download the dataset from HuggingFace and save each image as JPEG under `media/benchmark_images/<slug>/`; audio loaders save WAV clips under `media/benchmark_audio/<slug>/`. Paths are stored per-question (`image_paths` JSON list, `audio_path`).
- **Running** — at evaluation time the runner base64-encodes the media and passes it to the provider backend, which embeds it in the provider's native format (Ollama `images` field, OpenAI/vLLM content parts, Anthropic image blocks, Gemini inline parts).
- **Web UI** — the questions view (`/benchmarks/<slug>/questions/`) previews images and plays audio clips inline. The benchmark list and run-create pages show type badges and model-requirement hints.

### Evaluation metrics per type

| Type | Evaluation |
|------|------------|
| vision (MCQ: ScienceQA, AI2D, MMBench, MMMU) | Letter extraction and exact match |
| vision (open: ChartQA) | Normalized exact/containment match |
| agentic (GAIA) | Normalized exact match of final answer |
| agentic (BFCL) | Function-name + required-parameter match |
| audio (LibriSpeech) | Word Error Rate via `jiwer` — correct if WER < 0.1 |

### Notes

- `gaia` is a **gated** dataset — request access on HuggingFace and log in with `huggingface-cli login` before loading.
- Providers that can't handle a modality fail explicitly per-question (visible in run results) rather than silently scoring text-only.
- Few-shot examples are text-only; for vision benchmarks the few-shot examples do not attach their images.

---

## Project Structure

```
benchmark_web_2_style/
├── apps/
│   ├── benchmarks/
│   │   ├── management/commands/
│   │   │   ├── bm_create.py          # Create custom benchmark
│   │   │   ├── bm_import_hf.py       # Import from HuggingFace
│   │   │   └── bm_import_rag.py      # Create RAG benchmark
│   │   ├── registry.py               # 40+ built-in dataset loaders
│   │   ├── dashboard.py              # Dashboard analytics
│   │   └── models.py                 # Benchmark, Question, Suite, Prompt models
│   ├── providers/
│   │   ├── management/commands/
│   │   │   └── bm_provider.py        # Provider management CLI
│   │   ├── backends/                 # One class per provider type
│   │   └── models.py                 # Provider model
│   └── runs/
│       ├── management/commands/
│       │   ├── bm_run.py             # Start a run
│       │   ├── bm_status.py          # Check run status
│       │   ├── bm_list.py            # List runs/benchmarks/providers/suites
│       │   ├── bm_bulk.py            # Bulk run
│       │   ├── bm_sweep.py           # Parameter sweep
│       │   ├── bm_suite.py           # Suite management
│       │   ├── bm_export.py          # Export to CSV/Excel
│       │   ├── bm_cancel.py          # Cancel a run
│       │   ├── bm_leaderboard.py     # Show leaderboard
│       │   └── bm_import_results.py  # Import pre-computed results
│       ├── runner.py                 # Parallel benchmark execution engine
│       ├── scheduler.py              # Background scheduler daemon
│       ├── cost_table.py             # Pricing data for 18+ models
│       └── models.py                 # Run, Result, Template, Schedule models
├── config/                           # Django settings and URL routing
├── templates/                        # 47 HTML templates
├── static/                           # Bootstrap 5, custom CSS, JavaScript
└── requirements.txt
```

---

## Configuration

Key `config/settings.py` options:

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | — | Django secret key (required in production) |
| `DEBUG` | `False` | Enable debug mode |
| `ALLOWED_HOSTS` | `[]` | Comma-separated hostnames |
| `SCHEDULER_INTERVAL` | `60` | Seconds between scheduler checks |
| `DEFAULT_WORKERS` | `1` | Default parallel workers for runs |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend framework | Django 4.2 |
| Database | SQLite (default), PostgreSQL-compatible |
| Frontend | Bootstrap 5.3, Bootstrap Icons |
| Static files | WhiteNoise with compressed manifest |
| LLM datasets | HuggingFace `datasets` + `huggingface_hub` |
| Excel export | openpyxl |
| HTTP client | requests |
| Statistics | McNemar's test (χ²) for A/B testing |
