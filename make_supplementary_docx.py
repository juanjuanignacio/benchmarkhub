"""
Generate BenchmarkHub_Supplementary.docx — Supplementary Materials for the
BenchmarkHub Application Note.

Usage:
    python make_supplementary_docx.py
"""

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import re


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def set_font(run, name="Times New Roman", size=10, bold=False, italic=False,
             color=None, mono=False):
    if mono:
        run.font.name = "Courier New"
        run.font.size = Pt(9)
    else:
        run.font.name = name
        run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*color)


def para(doc, text="", align=WD_ALIGN_PARAGRAPH.JUSTIFY, size=10,
         space_before=0, space_after=4, bold=False, italic=False):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    if text:
        run = p.add_run(text)
        set_font(run, size=size, bold=bold, italic=italic)
    return p


def heading(doc, text, level=1):
    sizes = {1: 13, 2: 11, 3: 10, 4: 10}
    bold_levels = {1: True, 2: True, 3: True, 4: True}
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(12 if level == 1 else 8 if level == 2 else 6)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    set_font(run, size=sizes[level], bold=bold_levels[level])
    if level >= 3:
        run.font.italic = True
    return p


def render_inline(p, text, default_size=10):
    """Render text with **bold**, *italic*, `code` inline Markdown."""
    pattern = re.compile(r'(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)')
    for part in pattern.split(text):
        if part.startswith('**') and part.endswith('**'):
            r = p.add_run(part[2:-2])
            set_font(r, size=default_size, bold=True)
        elif part.startswith('*') and part.endswith('*'):
            r = p.add_run(part[1:-1])
            set_font(r, size=default_size, italic=True)
        elif part.startswith('`') and part.endswith('`'):
            r = p.add_run(part[1:-1])
            set_font(r, mono=True)
        else:
            r = p.add_run(part)
            set_font(r, size=default_size)


def mixed_para(doc, text, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
               space_after=4, size=10):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    render_inline(p, text, default_size=size)
    return p


def bullet(doc, text, level=0, size=10):
    p = doc.add_paragraph(style="List Bullet")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.left_indent = Cm(0.6 + level * 0.5)
    p.paragraph_format.space_after = Pt(2)
    render_inline(p, text, default_size=size)
    return p


def code_block(doc, lines):
    """Add a shaded code block (monospace, grey background)."""
    for line in lines:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.left_indent = Cm(0.5)
        run = p.add_run(line)
        set_font(run, mono=True, size=8)
        # Grey shading via XML
        pPr = p._p.get_or_add_pPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), 'F2F2F2')
        pPr.append(shd)
    # Small gap after block
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(4)


def add_table(doc, headers, rows, col_widths=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    # Header row
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        for run in hdr_cells[i].paragraphs[0].runs:
            run.font.bold = True
            run.font.size = Pt(9)
            run.font.name = "Times New Roman"
        hdr_cells[i].paragraphs[0].paragraph_format.space_after = Pt(2)
    # Data rows
    for row_data in rows:
        row_cells = table.add_row().cells
        for i, cell_text in enumerate(row_data):
            row_cells[i].text = str(cell_text)
            for run in row_cells[i].paragraphs[0].runs:
                run.font.size = Pt(8.5)
                run.font.name = "Times New Roman"
            row_cells[i].paragraphs[0].paragraph_format.space_after = Pt(2)
    # Column widths
    if col_widths:
        for row in table.rows:
            for i, w in enumerate(col_widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return table


# ---------------------------------------------------------------------------
# Build document
# ---------------------------------------------------------------------------

def build():
    doc = Document()
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(3.0)
        section.right_margin = Cm(3.0)

    # ── Cover ────────────────────────────────────────────────────────────────
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tr = title_p.add_run("BenchmarkHub — Supplementary Materials")
    set_font(tr, size=14, bold=True)
    title_p.paragraph_format.space_after = Pt(4)

    sub_p = doc.add_paragraph()
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sr = sub_p.add_run(
        "Application Note: BenchmarkHub: a web platform for systematic evaluation "
        "of large language models on biomedical and general-purpose benchmarks"
    )
    set_font(sr, size=10, italic=True)
    sub_p.paragraph_format.space_after = Pt(16)

    mixed_para(doc,
        "This document provides supplementary information for the BenchmarkHub "
        "application note, including detailed installation instructions, the complete "
        "built-in benchmark catalogue, full CLI command reference, REST API "
        "documentation, provider configuration, CSV format specifications, model "
        "pricing, and example workflows."
    )

    # ── S1. Installation ─────────────────────────────────────────────────────
    heading(doc, "S1  Installation and Configuration", level=1)

    heading(doc, "S1.1  Requirements", level=2)
    bullet(doc, "Python 3.10 or later (3.11 recommended)")
    bullet(doc, "Conda or pip package manager")
    bullet(doc, "Git (to clone the repository)")
    bullet(doc, "Optional: Ollama (https://ollama.ai/) for local model inference")
    bullet(doc, "Optional: vLLM for high-throughput local inference")

    heading(doc, "S1.2  Step-by-step Installation", level=2)
    code_block(doc, [
        "# 1. Clone the repository",
        "git clone https://github.com/placeholder/benchmarkhub.git",
        "cd benchmarkhub",
        "",
        "# 2. Create and activate a conda environment",
        "conda create -n benchmarkhub python=3.11",
        "conda activate benchmarkhub",
        "",
        "# 3. Install Python dependencies",
        "pip install -r requirements.txt",
        "",
        "# 4. Configure environment variables",
        "cp .env.example .env   # then edit .env with your API keys",
        "",
        "# 5. Apply database migrations",
        "python manage.py migrate",
        "",
        "# 6. (Optional) Load built-in benchmarks",
        "python manage.py load_benchmark --list          # see available datasets",
        "python manage.py load_benchmark mmlu            # load MMLU",
        "python manage.py load_benchmark medqa_usmle     # load MedQA USMLE",
        "",
        "# 7. Start the web server",
        "python manage.py runserver",
        "# Open http://localhost:8000 in your browser",
    ])

    heading(doc, "S1.3  Environment Variables", level=2)
    add_table(doc,
        ["Variable", "Required", "Description"],
        [
            ["SECRET_KEY", "Yes (production)", "Django secret key; any random string for development"],
            ["DEBUG", "No", "Set to True for development; default False"],
            ["ALLOWED_HOSTS", "No", "Comma-separated hostnames; default localhost,127.0.0.1"],
            ["OPENAI_API_KEY", "If using OpenAI", "OpenAI API key (sk-…)"],
            ["ANTHROPIC_API_KEY", "If using Anthropic", "Anthropic API key (sk-ant-…)"],
            ["GOOGLE_API_KEY", "If using Gemini", "Google AI API key"],
            ["GROQ_API_KEY", "If using Groq", "Groq API key"],
            ["MISTRAL_API_KEY", "If using Mistral", "Mistral AI API key"],
            ["COHERE_API_KEY", "If using Cohere", "Cohere API key"],
            ["TOGETHER_API_KEY", "If using Together AI", "Together AI API key"],
        ],
        col_widths=[4.5, 3.5, 8.5]
    )

    heading(doc, "S1.4  Production Deployment", level=2)
    mixed_para(doc,
        "For production use, serve BenchmarkHub behind Gunicorn and Nginx. "
        "WhiteNoise handles static file serving without a dedicated CDN. "
        "Switch the database to PostgreSQL by setting the DATABASE_URL environment "
        "variable to a PostgreSQL connection string. The scheduler daemon "
        "(`python manage.py run_scheduler`) should run as a separate process or "
        "systemd service."
    )

    # ── S2. Benchmark Catalogue ───────────────────────────────────────────────
    heading(doc, "S2  Complete Built-in Benchmark Catalogue", level=1)
    mixed_para(doc,
        "Table S1 lists all built-in benchmarks available in BenchmarkHub. "
        "Benchmarks are loaded on demand from HuggingFace Hub using the "
        "`load_benchmark` management command. All benchmarks listed below can be "
        "loaded without any additional configuration beyond a working internet "
        "connection."
    )

    heading(doc, "S2.1  General Reasoning and Language", level=2)
    add_table(doc,
        ["Slug", "Name", "Category", "Description"],
        [
            ["arc_challenge", "ARC Challenge", "reasoning",
             "Grade-school science questions requiring multi-step reasoning; hard partition."],
            ["arc_easy", "ARC Easy", "reasoning",
             "Grade-school science questions; easy partition solvable by retrieval."],
            ["hellaswag", "HellaSwag", "common sense",
             "Commonsense NLI — select the most plausible continuation of a sentence."],
            ["winogrande", "WinoGrande", "common sense",
             "Adversarial Winograd schema pronoun resolution at scale."],
            ["piqa", "PIQA", "common sense",
             "Physical intuition question answering; two-choice format."],
            ["copa", "COPA", "common sense",
             "Choice of plausible alternatives — cause/effect commonsense reasoning."],
            ["social_iqa", "SocialIQA", "common sense",
             "Social situation reasoning with three answer choices."],
            ["boolq", "BoolQ", "language",
             "Yes/no questions over Wikipedia passages."],
            ["rte", "RTE", "language",
             "Recognizing textual entailment — two-class NLI."],
            ["multinli", "MultiNLI", "language",
             "Multi-genre NLI covering fiction, government, telephone, travel, and other genres."],
            ["anli", "ANLI", "language",
             "Adversarial NLI collected through iterative human-and-model-in-the-loop annotation."],
            ["logiqa", "LogiQA", "reasoning",
             "Logical reasoning from the Chinese Civil Service Exam, translated to English."],
            ["bbh", "BIG-Bench Hard", "reasoning",
             "23 challenging BIG-Bench tasks requiring chain-of-thought reasoning."],
            ["race", "RACE", "reading comp.",
             "Reading comprehension from Chinese middle/high school English exams."],
            ["swag", "SWAG", "common sense",
             "Grounded commonsense inference; predict the most likely next event."],
        ],
        col_widths=[4, 4, 3, 10]
    )

    heading(doc, "S2.2  Knowledge and Factual QA", level=2)
    add_table(doc,
        ["Slug", "Name", "Category", "Description"],
        [
            ["mmlu", "MMLU", "knowledge",
             "57 subjects across STEM, humanities, social sciences; 4-choice MCQ."],
            ["mmlu_pro", "MMLU Pro", "knowledge",
             "Harder MMLU variant with 10-choice options and more complex reasoning."],
            ["openbookqa", "OpenBookQA", "knowledge",
             "Elementary science QA requiring both core science facts and common knowledge."],
            ["truthfulqa", "TruthfulQA", "knowledge",
             "Questions designed to elicit false beliefs; evaluates factual accuracy."],
            ["triviaqa", "TriviaQA", "knowledge",
             "Trivia questions with evidence documents; open-ended answer format."],
            ["nq_open", "Natural Questions Open", "knowledge",
             "Open-domain QA from real Google queries; short answer format."],
            ["simpleqa", "SimpleQA", "knowledge",
             "Fact-seeking questions with single unambiguous answers; tests hallucination."],
            ["gpqa", "GPQA", "knowledge",
             "Graduate-level science questions in biology, chemistry, and physics."],
            ["hle", "Humanity's Last Exam", "knowledge",
             "Extremely challenging expert-level questions across diverse academic fields."],
            ["lambada", "LAMBADA", "language",
             "Language modelling benchmark requiring broad discourse context understanding."],
            ["strategyqa", "StrategyQA", "reasoning",
             "Yes/no questions requiring implicit multi-step reasoning strategies."],
        ],
        col_widths=[4, 4.5, 3, 9.5]
    )

    heading(doc, "S2.3  Mathematics and Coding", level=2)
    add_table(doc,
        ["Slug", "Name", "Category", "Description"],
        [
            ["gsm8k", "GSM8K", "math",
             "8,500 grade-school math word problems with step-by-step solutions."],
            ["math500", "MATH-500", "math",
             "500 competition mathematics problems across algebra, geometry, and calculus."],
            ["aqua_rat", "AQuA-RAT", "math",
             "Algebraic word problems with rationale annotations; 5-choice MCQ."],
            ["mathqa", "MathQA", "math",
             "Math word problems with annotated operation programs."],
            ["aime_2024", "AIME 2024", "math",
             "American Invitational Mathematics Examination 2024; competition-level."],
            ["aime_2025", "AIME 2025", "math",
             "American Invitational Mathematics Examination 2025; competition-level."],
            ["humaneval", "HumanEval", "coding",
             "164 hand-crafted Python programming problems with unit tests."],
            ["mbpp", "MBPP", "coding",
             "Mostly basic Python programming problems from crowd-sourcing."],
        ],
        col_widths=[4, 4.5, 3, 9.5]
    )

    heading(doc, "S2.4  Biomedical and Clinical", level=2)
    add_table(doc,
        ["Slug", "Name", "Category", "Description"],
        [
            ["medqa_usmle", "MedQA USMLE", "biomedical",
             "4,000+ questions from USMLE Steps 1, 2, 3; tests clinical medical knowledge."],
            ["medmcqa", "MedMCQA", "biomedical",
             "194,000+ MCQ from Indian medical entrance exams covering 21 subjects."],
            ["pubmedqa", "PubMedQA", "biomedical",
             "Biomedical research QA; yes/no/maybe answers based on PubMed abstracts."],
            ["bioinfo_bench", "BioInfo-Bench", "biomedical",
             "Bioinformatics knowledge: sequence analysis, genomics, proteomics, structural biology."],
            ["sciq", "SciQ", "biomedical",
             "Science exam questions across biology, chemistry, earth science, and physics."],
            ["mmlu_clinical_knowledge", "MMLU Clinical Knowledge", "biomedical",
             "MMLU subset: clinical knowledge — diagnosis, pharmacology, pathophysiology."],
            ["mmlu_anatomy", "MMLU Anatomy", "biomedical",
             "MMLU subset: human anatomy — gross, histological, and neuroanatomy."],
            ["mmlu_professional_medicine", "MMLU Professional Medicine", "biomedical",
             "MMLU subset: professional medical practice and clinical reasoning."],
            ["mmlu_college_medicine", "MMLU College Medicine", "biomedical",
             "MMLU subset: college-level medicine including physiology and pharmacology."],
            ["mmlu_medical_genetics", "MMLU Medical Genetics", "biomedical",
             "MMLU subset: medical genetics, hereditary disease, and genomics."],
            ["mmlu_college_biology", "MMLU College Biology", "biomedical",
             "MMLU subset: college biology — cell biology, genetics, ecology."],
            ["mmlu_high_school_biology", "MMLU High School Biology", "biomedical",
             "MMLU subset: high school biology curriculum."],
            ["mmlu_virology", "MMLU Virology", "biomedical",
             "MMLU subset: virology — viral structure, replication, pathogenesis."],
            ["mmlu_nutrition", "MMLU Nutrition", "biomedical",
             "MMLU subset: nutritional biochemistry and dietary science."],
            ["mmlu_college_chemistry", "MMLU College Chemistry", "biomedical",
             "MMLU subset: general and organic college chemistry."],
        ],
        col_widths=[5, 5, 2.5, 8.5]
    )

    # ── S3. CLI Reference ─────────────────────────────────────────────────────
    heading(doc, "S3  Command-Line Interface Reference", level=1)
    mixed_para(doc,
        "All management commands are invoked via `python manage.py <command>` and "
        "support a `--help` flag that prints full usage. The Django development server "
        "does not need to be running for CLI commands; they operate directly on the "
        "database. Commands are suitable for use in shell scripts, Makefiles, and "
        "HPC job submissions."
    )

    # bm_provider
    heading(doc, "S3.1  bm_provider — Manage LLM providers", level=2)
    code_block(doc, [
        "# List all registered providers",
        "python manage.py bm_provider list",
        "",
        "# Add a provider",
        "python manage.py bm_provider add <slug> <display-name> --type <type> [options]",
        "",
        "# Provider types: ollama, vllm, openai, anthropic, gemini, groq, mistral, cohere, together",
        "",
        "# Examples",
        "python manage.py bm_provider add ollama Ollama --type ollama --url http://localhost:11434",
        "python manage.py bm_provider add openai-gpt OpenAI --type openai --key sk-...",
        "python manage.py bm_provider add claude Anthropic --type anthropic --key sk-ant-...",
        "python manage.py bm_provider add gemini Gemini --type gemini --key AIza...",
        "",
        "# Test provider connection",
        "python manage.py bm_provider test <slug>",
        "python manage.py bm_provider test ollama --model llama3.2",
        "",
        "# List available models from a provider",
        "python manage.py bm_provider models <slug>",
        "",
        "# Delete a provider",
        "python manage.py bm_provider delete <slug>",
    ])

    # load_benchmark
    heading(doc, "S3.2  load_benchmark — Load built-in datasets", level=2)
    code_block(doc, [
        "# List all available built-in benchmarks",
        "python manage.py load_benchmark --list",
        "",
        "# Load a specific benchmark (downloads from HuggingFace Hub)",
        "python manage.py load_benchmark <slug>",
        "python manage.py load_benchmark mmlu",
        "python manage.py load_benchmark medqa_usmle",
        "python manage.py load_benchmark arc_challenge gsm8k pubmedqa  # multiple",
        "",
        "# Force reload (clears existing questions)",
        "python manage.py load_benchmark mmlu --force",
    ])

    # bm_run
    heading(doc, "S3.3  bm_run — Start a benchmark run", level=2)
    code_block(doc, [
        "python manage.py bm_run <benchmark> <provider> <model> [options]",
        "",
        "Options:",
        "  --temperature FLOAT   Sampling temperature (default: 0.0)",
        "  --max-tokens INT      Maximum output tokens (default: 512)",
        "  --num-questions INT   Number of questions to evaluate; 0 = all (default: 0)",
        "  --system-prompt TEXT  Custom system prompt text",
        "  --few-shot INT        Number of few-shot examples prepended (default: 0)",
        "  --cot                 Enable chain-of-thought prompting",
        "  --workers INT         Parallel worker threads (default: 1)",
        "  --tags TEXT           Comma-separated tags for filtering",
        "  --notes TEXT          Free-text annotation",
        "  --webhook URL         HTTP endpoint to notify on completion",
        "  --wait                Block until run completes and print score",
        "",
        "# Examples",
        "python manage.py bm_run mmlu ollama llama3.2",
        "python manage.py bm_run medqa_usmle openai gpt-4o --temperature 0 --wait",
        "python manage.py bm_run arc_challenge anthropic claude-3-5-sonnet-20241022 \\",
        "    --num-questions 100 --few-shot 3 --cot --workers 4 --wait",
    ])

    # bm_status
    heading(doc, "S3.4  bm_status — Monitor run progress", level=2)
    code_block(doc, [
        "# One-shot status check",
        "python manage.py bm_status <run-id>",
        "",
        "# Live watch mode (polls every 2 seconds until complete)",
        "python manage.py bm_status <run-id> --watch",
    ])

    # bm_bulk
    heading(doc, "S3.5  bm_bulk — Run on multiple models simultaneously", level=2)
    code_block(doc, [
        "python manage.py bm_bulk <benchmark> <provider/model> [<provider/model> ...] [options]",
        "",
        "# Examples",
        "python manage.py bm_bulk mmlu ollama/llama3.2 openai/gpt-4o anthropic/claude-3-5-sonnet",
        "python manage.py bm_bulk medqa_usmle openai/gpt-4o openai/gpt-4o-mini \\",
        "    --num-questions 100 --temperature 0 --wait",
    ])

    # bm_sweep
    heading(doc, "S3.6  bm_sweep — Parameter sweep", level=2)
    code_block(doc, [
        "# Temperature sweep",
        "python manage.py bm_sweep <benchmark> <provider> <model> --temp-range <min> <max> <step>",
        "python manage.py bm_sweep mmlu ollama llama3.2 --temp-range 0.0 1.0 0.2",
        "",
        "# Prompt sweep (by saved prompt IDs from the library)",
        "python manage.py bm_sweep mmlu ollama llama3.2 --prompt-ids 1 2 3",
        "",
        "# Prompt sweep (inline texts)",
        'python manage.py bm_sweep mmlu openai gpt-4o \\',
        '    --prompt-texts "Answer briefly." "Explain your reasoning." \\',
        '    --num-questions 100 --wait',
    ])

    # bm_suite
    heading(doc, "S3.7  bm_suite — Benchmark suites", level=2)
    code_block(doc, [
        "# Create a suite grouping multiple benchmarks",
        "python manage.py bm_suite create <slug> <name> <benchmark-slug> [<benchmark-slug> ...]",
        "python manage.py bm_suite create biomedical 'Biomedical Suite' \\",
        "    medqa_usmle medmcqa pubmedqa bioinfo_bench mmlu_clinical_knowledge",
        "",
        "# Run all benchmarks in a suite",
        "python manage.py bm_suite run <suite-slug> <provider> <model> [options]",
        "python manage.py bm_suite run biomedical openai gpt-4o --wait",
        "",
        "# List suites",
        "python manage.py bm_suite list",
        "",
        "# Delete a suite (does not delete constituent benchmarks)",
        "python manage.py bm_suite delete <slug>",
    ])

    # bm_list
    heading(doc, "S3.8  bm_list — Query objects", level=2)
    code_block(doc, [
        "python manage.py bm_list runs",
        "python manage.py bm_list runs --benchmark mmlu --status completed --limit 20",
        "python manage.py bm_list runs --tag baseline",
        "python manage.py bm_list benchmarks",
        "python manage.py bm_list benchmarks --loaded-only",
        "python manage.py bm_list providers",
        "python manage.py bm_list suites",
    ])

    # bm_leaderboard
    heading(doc, "S3.9  bm_leaderboard — Rankings", level=2)
    code_block(doc, [
        "# Global leaderboard (best score per model across all benchmarks)",
        "python manage.py bm_leaderboard",
        "",
        "# Leaderboard for a specific benchmark",
        "python manage.py bm_leaderboard --benchmark medqa_usmle --limit 10",
    ])

    # bm_export
    heading(doc, "S3.10  bm_export — Export results", level=2)
    code_block(doc, [
        "# Export run results to CSV (default)",
        "python manage.py bm_export run <run-id>",
        "python manage.py bm_export run 42 --output results_42.csv",
        "",
        "# Export run results to Excel",
        "python manage.py bm_export run 42 --format excel --output results_42.xlsx",
        "",
        "# Export benchmark questions to CSV",
        "python manage.py bm_export benchmark mmlu",
        "python manage.py bm_export benchmark arc_challenge --format excel",
    ])

    # bm_cancel
    heading(doc, "S3.11  bm_cancel — Cancel a running run", level=2)
    code_block(doc, [
        "python manage.py bm_cancel <run-id>",
        "python manage.py bm_cancel 42 --delete   # cancel and remove all results",
    ])

    # bm_import_results
    heading(doc, "S3.12  bm_import_results — Import pre-computed results", level=2)
    mixed_para(doc,
        "This command allows importing externally computed results into BenchmarkHub "
        "without making any live API calls. Useful for incorporating results produced "
        "by other evaluation pipelines or for offline analysis."
    )
    code_block(doc, [
        "python manage.py bm_import_results <benchmark> <provider> <model> <results.csv>",
        "python manage.py bm_import_results mmlu ollama llama3.2 llama_mmlu_results.csv",
    ])

    # bm_create / bm_import_hf / bm_import_rag
    heading(doc, "S3.13  Custom benchmark import commands", level=2)
    code_block(doc, [
        "# Create a benchmark from a CSV file",
        "python manage.py bm_create <slug> <name> <questions.csv> [options]",
        "python manage.py bm_create my-bio 'My Biology Benchmark' questions.csv \\",
        "    --category biomedical --description 'Custom protein folding quiz'",
        "",
        "# Import a benchmark from HuggingFace Hub",
        "python manage.py bm_import_hf <dataset-id> <config> <split> [options]",
        "python manage.py bm_import_hf cais/mmlu anatomy test \\",
        "    --question-col question --choices-col choices --answer-col answer \\",
        "    --slug mmlu-anatomy --name 'MMLU Anatomy' --category biomedical",
        "",
        "# Create a RAG benchmark from a context CSV",
        "python manage.py bm_import_rag <slug> <name> <rag_questions.csv> [options]",
        "python manage.py bm_import_rag pubmed-rag 'PubMed RAG Benchmark' rag.csv \\",
        "    --context-col context --category biomedical",
    ])

    # ── S4. REST API ─────────────────────────────────────────────────────────
    heading(doc, "S4  REST API Documentation", level=1)
    mixed_para(doc,
        "The REST API is served at `/api/v1/` and requires no authentication in the "
        "default configuration. All responses are JSON. Interactive documentation with "
        "example requests and response schemas is available at `/api/docs/` when the "
        "server is running."
    )

    heading(doc, "S4.1  Benchmark Endpoints", level=2)
    add_table(doc,
        ["Method", "Endpoint", "Description"],
        [
            ["GET", "/api/v1/benchmarks/",
             "List benchmarks. Filters: loaded=1, category=<cat>. Pagination: limit, offset."],
            ["GET", "/api/v1/benchmarks/{slug}/",
             "Benchmark detail including list of subjects present in loaded questions."],
            ["GET", "/api/v1/benchmarks/{slug}/questions/",
             "Paginated question list. Filters: subject, difficulty, limit, offset."],
        ],
        col_widths=[2, 6, 13]
    )

    heading(doc, "S4.2  Run Endpoints", level=2)
    add_table(doc,
        ["Method", "Endpoint", "Description"],
        [
            ["GET", "/api/v1/runs/",
             "List runs. Filters: status, benchmark, model, tag, limit, offset."],
            ["POST", "/api/v1/runs/",
             "Create and start a run. Required body fields: benchmark, provider, model_name."],
            ["GET", "/api/v1/runs/{id}/",
             "Run detail with full metadata. Add ?subjects=1 for per-subject score breakdown."],
            ["GET", "/api/v1/runs/{id}/status/",
             "Lightweight polling endpoint: status, score, progress_pct, duration_seconds."],
            ["GET", "/api/v1/runs/{id}/results/",
             "Paginated per-question results. Filters: correct=true/false, subject."],
            ["POST", "/api/v1/runs/{id}/cancel/",
             "Cancel a pending or running run."],
            ["DELETE", "/api/v1/runs/{id}/",
             "Delete a run and all its associated results."],
        ],
        col_widths=[2, 5.5, 13.5]
    )

    heading(doc, "S4.3  Other Endpoints", level=2)
    add_table(doc,
        ["Method", "Endpoint", "Description"],
        [
            ["GET", "/api/v1/providers/",
             "List registered providers. Filter: active=1."],
            ["GET", "/api/v1/leaderboard/",
             "Best score per (benchmark, model) pair. Filters: benchmark, limit."],
        ],
        col_widths=[2, 6, 13]
    )

    heading(doc, "S4.4  Example API Calls", level=2)
    code_block(doc, [
        "# List loaded benchmarks",
        "curl 'http://localhost:8000/api/v1/benchmarks/?loaded=1'",
        "",
        "# Create and start a run",
        "curl -X POST http://localhost:8000/api/v1/runs/ \\",
        "  -H 'Content-Type: application/json' \\",
        '  -d \'{"benchmark":"medqa_usmle","provider":"openai","model_name":"gpt-4o",',
        '         "temperature":0,"num_questions":100,"few_shot_count":3,"use_cot":true}\'',
        "",
        "# Poll run status",
        "curl 'http://localhost:8000/api/v1/runs/42/status/'",
        "",
        "# Retrieve per-question results for incorrect answers",
        "curl 'http://localhost:8000/api/v1/runs/42/results/?correct=false&limit=50'",
        "",
        "# Get leaderboard for MedQA",
        "curl 'http://localhost:8000/api/v1/leaderboard/?benchmark=medqa_usmle&limit=10'",
    ])

    # ── S5. CSV Formats ───────────────────────────────────────────────────────
    heading(doc, "S5  CSV Format Specifications", level=1)

    heading(doc, "S5.1  Custom benchmark import CSV", level=2)
    mixed_para(doc,
        "The following columns are expected when importing a custom benchmark via "
        "`bm_create` or the web upload interface. Columns `option_c`, `option_d`, "
        "and `subject` are optional."
    )
    add_table(doc,
        ["Column", "Required", "Description"],
        [
            ["question", "Yes", "The question text."],
            ["option_a", "Yes", "Text for answer choice A."],
            ["option_b", "Yes", "Text for answer choice B."],
            ["option_c", "No", "Text for answer choice C (leave blank for binary questions)."],
            ["option_d", "No", "Text for answer choice D."],
            ["correct_answer", "Yes", "Correct answer letter: A, B, C, or D."],
            ["subject", "No", "Subject or category label for sub-score analysis."],
        ],
        col_widths=[4, 3, 14]
    )

    heading(doc, "S5.2  RAG benchmark import CSV", level=2)
    mixed_para(doc,
        "RAG benchmark CSVs pair each question with a passage of context text that "
        "is prepended to the prompt at inference time."
    )
    add_table(doc,
        ["Column", "Required", "Description"],
        [
            ["question", "Yes", "The question text."],
            ["context", "Yes", "Passage text prepended to the prompt (e.g. PubMed abstract, clinical note)."],
            ["option_a", "Yes", "Text for answer choice A."],
            ["option_b", "Yes", "Text for answer choice B."],
            ["option_c", "No", "Text for answer choice C."],
            ["option_d", "No", "Text for answer choice D."],
            ["correct_answer", "Yes", "Correct answer letter: A, B, C, or D."],
        ],
        col_widths=[4, 3, 14]
    )

    heading(doc, "S5.3  Pre-computed results import CSV", level=2)
    add_table(doc,
        ["Column", "Required", "Description"],
        [
            ["question_id", "Yes", "Question identifier matching those in the loaded benchmark."],
            ["model_answer", "Yes", "The answer letter the model gave (A, B, C, or D)."],
            ["is_correct", "Yes", "true or false."],
            ["response_time_ms", "No", "Response latency in milliseconds."],
            ["input_tokens", "No", "Number of prompt tokens (for cost tracking)."],
            ["output_tokens", "No", "Number of completion tokens."],
        ],
        col_widths=[4, 3, 14]
    )

    # ── S6. Model Pricing ─────────────────────────────────────────────────────
    heading(doc, "S6  Model Pricing Database", level=1)
    mixed_para(doc,
        "Table S2 lists the per-token prices stored in the built-in cost database "
        "and used by the pre-run cost estimator and per-question cost tracker. "
        "Prices are denominated in USD per 1,000 tokens and reflect rates at the "
        "time of writing; users should verify current pricing with the respective "
        "provider before making budgeting decisions."
    )
    add_table(doc,
        ["Model", "Provider", "Input (USD/1K tok)", "Output (USD/1K tok)"],
        [
            ["gpt-4o", "OpenAI", "$0.0050", "$0.0150"],
            ["gpt-4o-mini", "OpenAI", "$0.00015", "$0.00060"],
            ["gpt-4-turbo", "OpenAI", "$0.0100", "$0.0300"],
            ["gpt-3.5-turbo", "OpenAI", "$0.00050", "$0.00150"],
            ["claude-3-opus", "Anthropic", "$0.0150", "$0.0750"],
            ["claude-3-5-sonnet", "Anthropic", "$0.0030", "$0.0150"],
            ["claude-3-5-haiku", "Anthropic", "$0.00080", "$0.00400"],
            ["claude-3-sonnet", "Anthropic", "$0.0030", "$0.0150"],
            ["claude-3-haiku", "Anthropic", "$0.00025", "$0.00125"],
            ["gemini-1.5-pro", "Google", "$0.00350", "$0.01050"],
            ["gemini-1.5-flash", "Google", "$0.00035", "$0.00105"],
            ["mistral-large", "Mistral AI", "$0.0030", "$0.0090"],
            ["mistral-medium", "Mistral AI", "$0.00270", "$0.00810"],
            ["mistral-small", "Mistral AI", "$0.0010", "$0.0030"],
            ["llama-3.1-70b-versatile", "Groq", "$0.00059", "$0.00079"],
            ["llama-3.1-8b-instant", "Groq", "$0.000050", "$0.000080"],
            ["mixtral-8x7b-32768", "Groq", "$0.00024", "$0.00024"],
            ["(unknown models)", "Any", "$0.0010", "$0.0020"],
        ],
        col_widths=[5.5, 3.5, 4, 4]
    )

    # ── S7. Example Workflows ─────────────────────────────────────────────────
    heading(doc, "S7  Example Workflows", level=1)

    heading(doc, "S7.1  Evaluate GPT-4o on the full biomedical benchmark suite", level=2)
    code_block(doc, [
        "# Step 1 — register the provider (one time only)",
        "python manage.py bm_provider add openai OpenAI --type openai --key sk-...",
        "",
        "# Step 2 — load all biomedical benchmarks",
        "python manage.py load_benchmark medqa_usmle medmcqa pubmedqa bioinfo_bench \\",
        "    mmlu_clinical_knowledge mmlu_anatomy mmlu_professional_medicine \\",
        "    mmlu_college_medicine mmlu_medical_genetics mmlu_college_biology",
        "",
        "# Step 3 — create a suite",
        "python manage.py bm_suite create biomedical 'Biomedical Suite' \\",
        "    medqa_usmle medmcqa pubmedqa bioinfo_bench \\",
        "    mmlu_clinical_knowledge mmlu_anatomy mmlu_professional_medicine \\",
        "    mmlu_college_medicine mmlu_medical_genetics mmlu_college_biology",
        "",
        "# Step 4 — run the suite (100 questions per benchmark, temperature 0)",
        "python manage.py bm_suite run biomedical openai gpt-4o \\",
        "    --num-questions 100 --temperature 0 --wait",
        "",
        "# Step 5 — view leaderboard",
        "python manage.py bm_leaderboard --benchmark medqa_usmle",
    ])

    heading(doc, "S7.2  Temperature sweep on MedQA with chain-of-thought", level=2)
    code_block(doc, [
        "python manage.py bm_sweep medqa_usmle openai gpt-4o \\",
        "    --temp-range 0.0 1.0 0.2 \\",
        "    --num-questions 50 \\",
        "    --cot \\",
        "    --wait",
        "",
        "# View comparative results in the web UI at /runs/sweep/",
        "# or export all sweep results:",
        "python manage.py bm_list runs --benchmark medqa_usmle --tag sweep",
    ])

    heading(doc, "S7.3  A/B test of two system prompts", level=2)
    mixed_para(doc,
        "This workflow compares a minimal prompt against an instruction-rich prompt "
        "on MMLU using McNemar's χ² test available in the web UI at `/runs/ab-test/`."
    )
    code_block(doc, [
        "# Run A: minimal prompt",
        "python manage.py bm_run mmlu openai gpt-4o \\",
        '    --system-prompt "Answer with a single letter." \\',
        "    --num-questions 200 --temperature 0 --tags prompt_a --wait",
        "",
        "# Run B: instruction-rich prompt",
        "python manage.py bm_run mmlu openai gpt-4o \\",
        '    --system-prompt "You are an expert. Read carefully and choose the best answer." \\',
        "    --num-questions 200 --temperature 0 --tags prompt_b --wait",
        "",
        "# Open /runs/ab-test/ in the browser, select run A and run B,",
        "# and review the McNemar chi-square test result.",
    ])

    heading(doc, "S7.4  Build and evaluate a custom RAG benchmark", level=2)
    mixed_para(doc,
        "This workflow demonstrates how to create a retrieval-augmented benchmark "
        "from a custom CSV of question–context pairs and evaluate it against a local "
        "model without any cloud API calls."
    )
    code_block(doc, [
        "# Prepare rag_questions.csv with columns:",
        "#   question, context, option_a, option_b, option_c, option_d, correct_answer",
        "",
        "# Import the RAG benchmark",
        "python manage.py bm_import_rag pubmed-rag 'PubMed RAG Eval' rag_questions.csv \\",
        "    --context-col context --category biomedical",
        "",
        "# Register a local Ollama provider (no API key required)",
        "python manage.py bm_provider add ollama-local Ollama --type ollama \\",
        "    --url http://localhost:11434",
        "",
        "# Run evaluation",
        "python manage.py bm_run pubmed-rag ollama-local llama3.2 \\",
        "    --temperature 0 --wait",
    ])

    heading(doc, "S7.5  Scheduled nightly regression on MMLU", level=2)
    code_block(doc, [
        "# Start the scheduler daemon (run as a background service or systemd unit)",
        "python manage.py run_scheduler",
        "",
        "# Create a scheduled run via the web UI at /runs/scheduled/",
        "# or via the REST API:",
        "curl -X POST http://localhost:8000/api/v1/runs/ \\",
        "  -H 'Content-Type: application/json' \\",
        '  -d \'{"benchmark":"mmlu","provider":"openai","model_name":"gpt-4o",',
        '         "num_questions":100,"temperature":0,',
        '         "schedule":"daily","tags":"nightly"}\'',
    ])

    # ── S8. Web Interface Routes ───────────────────────────────────────────────
    heading(doc, "S8  Web Interface Route Reference", level=1)
    add_table(doc,
        ["URL", "Description"],
        [
            ["/", "Dashboard — KPIs, recent runs, leaderboard, benchmark coverage matrix"],
            ["/benchmarks/", "Browse all benchmarks; filter by category; load new benchmarks"],
            ["/benchmarks/<slug>/", "Benchmark detail — question preview, export, start run"],
            ["/benchmarks/suites/", "Manage benchmark suites"],
            ["/benchmarks/suites/<id>/", "Suite run detail — per-benchmark score breakdown"],
            ["/benchmarks/prompts/", "Prompt library — create, edit, and delete saved prompts"],
            ["/providers/", "Manage LLM providers; test connections"],
            ["/providers/<slug>/", "Provider detail — connection status, model listing"],
            ["/runs/", "All runs — filter by benchmark, provider, status, or tag"],
            ["/runs/<id>/", "Run detail — per-question results, score by subject, export"],
            ["/runs/compare/", "Side-by-side comparison of up to 4 runs"],
            ["/runs/ab-test/", "A/B test two prompt variants with McNemar's χ² test"],
            ["/runs/bulk/", "Launch multiple runs simultaneously"],
            ["/runs/sweep/", "Parameter sweep — temperature grid or prompt list"],
            ["/runs/templates/", "Saved run templates — save and restore configurations"],
            ["/runs/scheduled/", "Scheduled runs — create, edit, delete recurring evaluations"],
            ["/runs/leaderboard/", "Model rankings per benchmark"],
            ["/runs/hardness/", "Question hardness — items consistently failed by all models"],
            ["/runs/model-history/", "One model's performance over time across all runs"],
            ["/runs/cost-estimator/", "Pre-run cost estimator — predict API spend before running"],
            ["/api/v1/", "REST API root — list all endpoints"],
            ["/api/docs/", "Interactive REST API documentation"],
            ["/howto/", "In-app how-to guide"],
        ],
        col_widths=[5.5, 15.5]
    )

    # ── Save ─────────────────────────────────────────────────────────────────
    out_path = "BenchmarkHub_Supplementary.docx"
    doc.save(out_path)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    build()
