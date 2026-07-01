"""
Generate BenchmarkHub_paper.docx from BenchmarkHub_paper.md.
Produces a Word document formatted in the style of a Bioinformatics
(Oxford Academic) Application Note.

Usage:
    python make_docx.py
"""

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import re


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def set_font(run, name="Times New Roman", size=10, bold=False, italic=False, color=None):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*color)


def add_paragraph(doc, text="", style="Normal", alignment=WD_ALIGN_PARAGRAPH.JUSTIFY):
    p = doc.add_paragraph(style=style)
    p.alignment = alignment
    if text:
        run = p.add_run(text)
        set_font(run)
    return p


def add_heading(doc, text, level=1):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run(text)
    sizes = {1: 13, 2: 11, 3: 10}
    set_font(run, size=sizes.get(level, 10), bold=True)
    # spacing before/after
    p.paragraph_format.space_before = Pt(10 if level == 1 else 6)
    p.paragraph_format.space_after = Pt(4)
    return p


def render_inline(p, text):
    """
    Render a line of text with basic inline Markdown:
      **bold**, *italic*, `code`, and plain text.
    Adds runs to existing paragraph p.
    """
    pattern = re.compile(r'(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)')
    parts = pattern.split(text)
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            run = p.add_run(part[2:-2])
            set_font(run, bold=True)
        elif part.startswith('*') and part.endswith('*'):
            run = p.add_run(part[1:-1])
            set_font(run, italic=True)
        elif part.startswith('`') and part.endswith('`'):
            run = p.add_run(part[1:-1])
            set_font(run, name="Courier New", size=9)
        else:
            run = p.add_run(part)
            set_font(run)


def add_mixed_paragraph(doc, text, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY):
    p = doc.add_paragraph()
    p.alignment = alignment
    p.paragraph_format.space_after = Pt(4)
    render_inline(p, text)
    return p


def add_bullet(doc, text, level=0):
    p = doc.add_paragraph(style="List Bullet")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.left_indent = Cm(0.5 + level * 0.5)
    p.paragraph_format.space_after = Pt(2)
    render_inline(p, text)
    return p


# ---------------------------------------------------------------------------
# Document construction
# ---------------------------------------------------------------------------

def build_docx():
    doc = Document()

    # Page margins (narrow to fit ~4 pages)
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(3.0)
        section.right_margin = Cm(3.0)

    # ── Title ────────────────────────────────────────────────────────────────
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_p.add_run(
        "BenchmarkHub: a web platform for systematic evaluation of large language "
        "models on biomedical and general-purpose benchmarks"
    )
    set_font(title_run, size=14, bold=True)
    title_p.paragraph_format.space_after = Pt(6)

    # ── Authors ───────────────────────────────────────────────────────────────
    auth_p = doc.add_paragraph()
    auth_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    auth_run = auth_p.add_run(
        "First Author\u00b9, Second Author\u00b9, Corresponding Author\u00b9,*"
    )
    set_font(auth_run, size=10, bold=True)
    auth_p.paragraph_format.space_after = Pt(2)

    aff_p = doc.add_paragraph()
    aff_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    aff_run = aff_p.add_run(
        "\u00b9 Affiliation, Institution, City, Country.\n"
        "* Corresponding author. Email: author@institution.edu"
    )
    set_font(aff_run, size=9, italic=True)
    aff_p.paragraph_format.space_after = Pt(12)

    # ── Abstract ─────────────────────────────────────────────────────────────
    add_heading(doc, "Abstract", level=1)

    abs_summary = (
        "Summary: BenchmarkHub is an open-source web platform and command-line toolkit "
        "that enables researchers to evaluate and compare large language models (LLMs) "
        "across a curated library of more than 40 standardized benchmarks, including a "
        "dedicated collection of biomedical, clinical, and bioinformatics datasets. "
        "The platform unifies three interaction modes—a browser-based interface, a REST "
        "API, and a command-line interface with 18 management commands—so that both "
        "interactive exploratory analysis and fully automated evaluation pipelines are "
        "supported from the same installation. Key capabilities include parallel benchmark "
        "execution with configurable concurrency, parameter sweeps over temperature and "
        "prompt variants, prompt A/B testing with McNemar\u2019s \u03c7\u00b2 test, "
        "Wilson score confidence intervals, pre-run cost estimation, automated scheduling, "
        "and flexible benchmark import from HuggingFace Hub, CSV files, or "
        "retrieval-augmented generation (RAG) datasets assembled from user-supplied "
        "context passages."
    )
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(4)
    run_label = p.add_run("Summary: ")
    set_font(run_label, bold=True)
    run_body = p.add_run(abs_summary[len("Summary: "):])
    set_font(run_body)

    abs_avail = (
        "BenchmarkHub is implemented in Python 3.11 with the Django 4.2 framework and "
        "runs on Linux, macOS, and Windows without requiring an external database server "
        "(SQLite by default; PostgreSQL-compatible for multi-user deployments). The source "
        "code is freely available under the MIT license at "
        "https://github.com/placeholder/benchmarkhub. Installation requires only "
        "pip install -r requirements.txt and a database migration step. A step-by-step "
        "quickstart is included in the repository README. Supplementary material describing "
        "advanced configuration and worked examples is available online."
    )
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p2.paragraph_format.space_after = Pt(8)
    run_label2 = p2.add_run("Availability and Implementation: ")
    set_font(run_label2, bold=True)
    run_body2 = p2.add_run(abs_avail[len("Availability and Implementation: "):])
    set_font(run_body2)

    # ── 1. Introduction ───────────────────────────────────────────────────────
    add_heading(doc, "1  Introduction", level=1)

    intro_paras = [
        ("Large language models have emerged as transformative tools across biomedical "
         "research, demonstrating remarkable capabilities in clinical question answering, "
         "genomic data interpretation, literature mining, and scientific reasoning "
         "(Brown et al., 2020; Singhal et al., 2023). Evaluating these models rigorously "
         "on standardized benchmarks has become essential for selecting models appropriate "
         "to specific tasks, comparing performance across model families, and tracking "
         "progress over time."),
        ("Despite the importance of evaluation, the current landscape of benchmarking "
         "tools is fragmented. Existing frameworks such as the EleutherAI Language Model "
         "Evaluation Harness (Gao et al., 2024) and HELM (Liang et al., 2022) offer "
         "comprehensive coverage of general-purpose benchmarks but require substantial "
         "technical expertise to operate, provide no graphical interface, lack native "
         "support for cloud API providers, and offer limited biomedical benchmark coverage. "
         "Cloud leaderboard services are opaque about experimental conditions and do not "
         "allow researchers to evaluate proprietary datasets or customize prompting "
         "strategies. Ad-hoc scripted evaluations are common but produce results that are "
         "difficult to reproduce and compare across studies."),
        ("The biomedical domain presents particular challenges. Studies evaluating LLMs "
         "on clinical knowledge benchmarks such as MedQA (Jin et al., 2021b), PubMedQA "
         "(Jin et al., 2019), and the clinical subsets of MMLU (Hendrycks et al., 2021) "
         "use widely varying experimental configurations\u2014different question subsets, "
         "prompting styles, few-shot counts, temperature settings, and "
         "answer-extraction heuristics\u2014making cross-study comparisons unreliable. "
         "There is a clear need for a unified platform that standardizes experimental "
         "conditions, covers the relevant biomedical benchmarks, and is accessible to "
         "researchers without deep software engineering expertise."),
        ("We present BenchmarkHub, a platform that addresses these gaps. It provides a "
         "reproducible, configurable, and user-friendly environment for evaluating LLMs "
         "on both general-purpose and biomedical benchmarks, accessible via a web browser, "
         "a REST API, and a full command-line interface."),
    ]
    for para in intro_paras:
        add_mixed_paragraph(doc, para)

    # ── 2. Implementation ─────────────────────────────────────────────────────
    add_heading(doc, "2  Implementation", level=1)

    # 2.1
    add_heading(doc, "2.1  Architecture and Access Modes", level=2)
    add_mixed_paragraph(doc,
        "BenchmarkHub is a Django web application organized into three apps\u2014"
        "benchmarks, providers, and runs\u2014that correspond to the three core concepts "
        "of the platform. The default database is SQLite configured in write-ahead "
        "logging mode, which supports concurrent readers during benchmark execution; "
        "the application is also compatible with PostgreSQL for deployments requiring "
        "higher concurrency. Static files are served efficiently in production via "
        "WhiteNoise with manifest-based cache busting."
    )
    add_mixed_paragraph(doc,
        "A key design principle of BenchmarkHub is that all platform functionality is "
        "exposed through three interchangeable access modes, each operating on the same "
        "underlying data model:"
    )
    add_bullet(doc,
        "**Web interface.** A responsive Bootstrap 5.3 browser application with more "
        "than 20 views covering benchmark browsing, provider management, run creation "
        "and monitoring, multi-run comparison, statistical analysis, leaderboards, and "
        "scheduling. No JavaScript framework is required.")
    add_bullet(doc,
        "**REST API.** A JSON API that provides full programmatic access to benchmarks, "
        "providers, and runs, including run creation and result retrieval. Interactive "
        "API documentation is served alongside the application. The API enables "
        "integration with continuous integration and delivery pipelines and third-party "
        "analysis tools.")
    add_bullet(doc,
        "**Command-line interface.** Eighteen management commands cover every operation "
        "available in the web UI: registering and testing providers, loading benchmarks, "
        "launching single or multi-model runs, monitoring run status, executing parameter "
        "sweeps and bulk runs, managing benchmark suites, scheduling recurring runs, "
        "displaying leaderboards, and exporting results. All commands accept a help flag "
        "and are suitable for scripting, cluster submission, and automation without a "
        "running web server.")
    add_mixed_paragraph(doc,
        "This tri-modal design ensures that BenchmarkHub is equally well suited to "
        "interactive exploration by a clinical researcher and to automated nightly "
        "regression testing by a software team."
    )

    # 2.2
    add_heading(doc, "2.2  Provider Abstraction Layer", level=2)
    add_mixed_paragraph(doc,
        "BenchmarkHub supports nine LLM provider backends through a unified interface, "
        "so that any benchmark can be run on any provider without changes to the benchmark "
        "definition or the evaluation logic. The cloud providers currently supported are "
        "OpenAI (GPT-4o, GPT-4-turbo, GPT-3.5-turbo), Anthropic Claude (Opus, Sonnet, "
        "Haiku), Google Gemini (1.5 Pro and Flash), Groq, Mistral AI, Cohere, and "
        "Together AI. Two local inference servers are also supported: Ollama and vLLM, "
        "both of which expose an OpenAI-compatible chat completion interface."
    )
    add_mixed_paragraph(doc,
        "Providers are registered once\u2014through the web interface, the API, or the "
        "CLI\u2014and stored in the database. After registration, any number of benchmarks "
        "can be dispatched to any provider/model combination. The local server backends "
        "(Ollama and vLLM) are particularly valuable in biomedical contexts because they "
        "allow evaluation of open-weight models on institutional hardware without "
        "transmitting patient-related or otherwise sensitive evaluation data to external "
        "services."
    )

    # 2.3
    add_heading(doc, "2.3  Benchmark Registry and Custom Benchmark Import", level=2)
    add_mixed_paragraph(doc,
        "BenchmarkHub ships with over 40 built-in benchmark loaders that handle "
        "dataset-specific prompt formatting and answer evaluation. Answer evaluation "
        "strategies are matched to the dataset type:"
    )
    add_bullet(doc,
        "**Multiple-choice questions** (the majority of supported benchmarks): the "
        "model\u2019s response is scanned with a word-boundary regular expression to "
        "extract the predicted letter (A\u2013D), making the evaluation robust to "
        "responses that include explanatory text before or after the answer.")
    add_bullet(doc,
        "**Mathematical problems** (GSM8K, MATH-500, AQuA-RAT, AIME): answers are "
        "extracted by detecting LaTeX boxed notation, matching \u201c= answer\u201d "
        "patterns, and as a last resort, extracting the last numeral in the response. "
        "Numeric comparison is performed with a tolerance of 10\u207b\u2076.")
    add_bullet(doc,
        "**Open-ended factual questions** (TriviaQA): both the model\u2019s answer "
        "and the reference answer are normalized by lowercasing and collapsing "
        "whitespace before word-boundary comparison.")
    add_bullet(doc,
        "**RAG questions** (context-dependent): the evaluation supports "
        "comma-separated alias lists and pipe-separated alternative correct answers, "
        "accommodating datasets where multiple phrasings are acceptable.")
    add_mixed_paragraph(doc,
        "Beyond the built-in collection, researchers can add benchmarks through three "
        "import paths, all of which produce first-class benchmark objects that support "
        "the full set of run, sweep, comparison, and export features:"
    )
    add_bullet(doc,
        "**HuggingFace Hub import.** Users specify a dataset identifier on the "
        "HuggingFace Hub and map its column names to the expected question, "
        "answer-choice, and correct-answer fields. The dataset is downloaded and "
        "ingested automatically, giving access to the thousands of evaluation datasets "
        "published on the Hub.")
    add_bullet(doc,
        "**Custom CSV benchmark.** Users upload a CSV file with columns for the "
        "question text, up to four answer options, the correct answer letter, and "
        "optionally a subject label. This path is intended for proprietary or "
        "domain-specific benchmarks that are not publicly distributed.")
    add_bullet(doc,
        "**RAG benchmark from context CSV.** Users upload a CSV in which each question "
        "is paired with a passage of context text\u2014for example, a clinical note, a "
        "PubMed abstract, or a genomic database record. BenchmarkHub prepends the "
        "context to the prompt at inference time, enabling evaluation of "
        "retrieval-augmented generation pipelines and context-dependent reasoning "
        "without any additional tooling.")

    # 2.4
    add_heading(doc, "2.4  Parallel Execution Engine", level=2)
    add_mixed_paragraph(doc,
        "The execution engine is designed to handle both single-run interactive "
        "evaluations and large-scale batch experiments involving dozens of simultaneous "
        "runs and hundreds of questions per run. It implements three execution modes:"
    )
    add_bullet(doc,
        "**Shared-semaphore mode** (used for bulk runs, parameter sweeps, and suite "
        "runs): a global concurrency pool limits the total number of simultaneous API "
        "calls across all running benchmarks, preventing rate-limit violations when "
        "many runs are active at once.")
    add_bullet(doc,
        "**Run-serializer mode**: runs execute one at a time in submission order, "
        "each utilizing all of its configured parallel workers internally. This mode "
        "is appropriate when the provider allows high per-run parallelism but the user "
        "wants predictable run ordering.")
    add_bullet(doc,
        "**Direct parallel mode**: a single run distributes its questions across a "
        "configurable number of worker threads, maximizing throughput for time-sensitive "
        "single-benchmark evaluations.")
    add_mixed_paragraph(doc,
        "Transient failures\u2014rate-limit responses, connection timeouts, and network "
        "errors\u2014are handled with an exponential backoff retry policy of up to three "
        "attempts. Running benchmarks can be cancelled at any time; the cancellation "
        "signal is detected within approximately one second. Database writes are batched "
        "in groups of 50 to keep memory overhead bounded during long runs. Live "
        "progress\u2014questions completed, current score, elapsed time\u2014is updated "
        "incrementally and visible in both the web interface and the CLI status command."
    )

    # 2.5
    add_heading(doc, "2.5  Biomedical Benchmark Collection", level=2)
    add_mixed_paragraph(doc,
        "BenchmarkHub\u2019s built-in collection includes a substantial set of "
        "biomedical and clinical benchmarks that collectively span the major areas of "
        "biomedical AI evaluation. Dedicated datasets include MedQA USMLE (Jin et al., "
        "2021b), MedMCQA (Pal et al., 2022), PubMedQA (Jin et al., 2019), BioInfoBench "
        "(Chen and Deng, 2023), and SciQ. From the Massive Multitask Language "
        "Understanding benchmark (Hendrycks et al., 2021), the platform includes the "
        "Clinical Knowledge, Anatomy, Professional Medicine, College Medicine, Medical "
        "Genetics, College Biology, Virology, and Nutrition subsets. Together these "
        "datasets enable systematic comparison of general-purpose and biomedically "
        "specialized models across clinical decision support, biomedical literature "
        "comprehension, genetics, and life-science reasoning tasks."
    )

    # ── 3. Features ───────────────────────────────────────────────────────────
    add_heading(doc, "3  Features", level=1)

    add_heading(doc, "3.1  Dashboard and Web Interface", level=2)
    add_mixed_paragraph(doc,
        "The dashboard aggregates key performance indicators across all completed runs: "
        "overall accuracy statistics, number of models evaluated, benchmark coverage, "
        "and recent activity. A model coverage matrix displays, for every benchmark and "
        "every registered provider, whether a run has been completed and what score was "
        "achieved, providing at a glance an overview of evaluation coverage and relative "
        "model performance. Dedicated views allow side-by-side comparison of up to four "
        "runs, question-level result inspection with per-question correctness, token "
        "counts, and response times, and model performance history over time."
    )

    add_heading(doc, "3.2  Prompt Engineering", level=2)
    add_mixed_paragraph(doc,
        "BenchmarkHub treats prompt design as a first-class concern. A prompt library "
        "allows researchers to save, name, and version system prompts, which can then be "
        "reused across runs or selected in parameter sweeps. Few-shot evaluation is "
        "supported by randomly sampling a specified number of examples from the benchmark "
        "question pool (excluding the evaluation set) and prepending them to each prompt. "
        "Chain-of-thought prompting (Wei et al., 2022) can be enabled with a single "
        "toggle, appending the standard \u201cLet\u2019s think step by step\u201d "
        "elicitation phrase. Custom prompt templates allow the question text and answer "
        "options to be embedded in arbitrary surrounding instructions, which is useful for "
        "testing instruction-following behavior or domain-specific framing."
    )

    add_heading(doc, "3.3  Statistical Analysis", level=2)
    add_mixed_paragraph(doc,
        "Benchmark accuracy is reported with Wilson score confidence intervals (Wilson, "
        "1927) at configurable significance levels (90%, 95%, 99%). Wilson intervals are "
        "more accurate than normal approximation intervals for small sample sizes and for "
        "proportions near zero or one, making them appropriate for domain-specific "
        "benchmark subsets where few questions are available. A dedicated A/B test view "
        "accepts two runs as input and applies McNemar\u2019s \u03c7\u00b2 test "
        "(McNemar, 1947) for paired binary outcomes, providing a statistically principled "
        "method for comparing prompt variants or model versions on exactly the same "
        "question pool. A question hardness view identifies items that were answered "
        "incorrectly by every model evaluated, flagging them as consistently difficult "
        "across the tested population."
    )

    add_heading(doc, "3.4  Parameter Sweeps and Bulk Runs", level=2)
    add_mixed_paragraph(doc,
        "The parameter sweep feature automates a common experimental workflow: evaluating "
        "the same benchmark under a grid of conditions and comparing the outcomes. Users "
        "specify either a temperature grid (e.g., 0.0, 0.2, 0.4, 0.6, 0.8, 1.0) or a "
        "list of prompt variants from the prompt library; the platform spawns one run per "
        "configuration, groups the results automatically, and displays them in a "
        "comparative view. Bulk runs extend this to the provider/model dimension: a "
        "single benchmark is dispatched simultaneously to any number of provider/model "
        "combinations. In both modes the global concurrency pool is shared across all "
        "spawned runs to avoid exceeding API rate limits."
    )

    add_heading(doc, "3.5  Cost Estimation and Token Tracking", level=2)
    add_mixed_paragraph(doc,
        "A built-in pricing database covering 18 commercial models stores per-token "
        "input and output costs. Before submitting a run, users can open the cost "
        "estimator, which computes an upper-bound cost estimate based on the number of "
        "questions, the selected model\u2019s pricing, and an assumed response length. "
        "Each completed question records its actual input and output token counts alongside "
        "the estimated cost, enabling post-hoc cost analysis at both the per-run and "
        "per-question level and supporting budget-constrained experimental design."
    )

    add_heading(doc, "3.6  Scheduling, Automation, and Export", level=2)
    add_mixed_paragraph(doc,
        "A background scheduler daemon checks for pending scheduled runs every 60 seconds "
        "and supports one-time, daily, and weekly recurrence. Scheduled runs can be "
        "created and managed through the web interface or the CLI, making it "
        "straightforward to monitor model performance regressions on a rolling basis. "
        "Webhook notifications can be configured per run: on completion, BenchmarkHub "
        "posts a JSON payload containing the run identifier, status, score, and metadata "
        "to a user-specified URL, enabling downstream alerting or pipeline chaining. "
        "Pre-computed results can also be imported from CSV files, decoupling the storage "
        "and analysis of external or pre-existing evaluations from live API execution. "
        "Run results and benchmark question sets can be exported to CSV or Excel at any time."
    )

    # ── 4. Discussion ─────────────────────────────────────────────────────────
    add_heading(doc, "4  Discussion", level=1)

    disc_paras = [
        ("BenchmarkHub occupies a practical niche between two common but inadequate "
         "approaches to LLM evaluation: ad-hoc Python scripts that are difficult to "
         "reproduce and extend, and cloud leaderboard services that are opaque about "
         "experimental conditions and inaccessible for custom datasets. Unlike the "
         "EleutherAI Language Model Evaluation Harness (Gao et al., 2024), which targets "
         "command-line power users and focuses on open-weight models, BenchmarkHub "
         "provides a graphical interface that lowers the barrier to entry for biomedical "
         "researchers who are not primarily software engineers. Unlike HELM (Liang et al., "
         "2022), it supports live evaluation against commercial API providers, integrates "
         "biomedical benchmarks natively, and allows the full experimental configuration "
         "to be reproduced exactly by sharing a run template."),
        ("The platform\u2019s support for local inference servers is particularly "
         "relevant for clinical and genomic applications. Evaluating LLMs on datasets "
         "derived from electronic health records, clinical notes, or patient genomic data "
         "using cloud APIs raises privacy and regulatory concerns. By supporting Ollama "
         "and vLLM as first-class provider backends, BenchmarkHub enables evaluation of "
         "open-weight models entirely within an institution\u2019s computational "
         "infrastructure."),
        ("The current implementation has several limitations. Evaluation is restricted to "
         "multiple-choice and short open-ended answer formats; free-form generation "
         "quality\u2014relevant for clinical note generation, report summarization, or "
         "code synthesis\u2014is not yet assessed. The statistical testing module covers "
         "pairwise comparisons but does not currently implement multiple-comparison "
         "corrections for experiments spanning many models simultaneously. Future "
         "development will address these limitations by introducing LLM-as-judge "
         "evaluation for open-ended responses, multimodal benchmark support for "
         "image-based medical questions, and automatic integration with model cards "
         "and FAIR data principles for reproducibility. BenchmarkHub is actively "
         "maintained and accepts community contributions through its GitHub repository."),
    ]
    for para in disc_paras:
        add_mixed_paragraph(doc, para)

    # ── Availability ──────────────────────────────────────────────────────────
    add_heading(doc, "Availability and Implementation", level=1)

    avail_items = [
        ("Project name", "BenchmarkHub"),
        ("Project home page", "https://github.com/placeholder/benchmarkhub"),
        ("Operating system(s)", "Linux, macOS, Windows"),
        ("Programming language", "Python 3.11"),
        ("Other software requirements",
         "Django \u22654.2, HuggingFace datasets and huggingface_hub, requests, "
         "openpyxl, whitenoise; full list in requirements.txt"),
        ("License", "MIT"),
        ("Restrictions to use by non-academics", "None"),
        ("Software availability guarantee",
         "The authors commit to maintaining the repository and ensuring public "
         "availability for a minimum of two years following publication."),
    ]
    for label, value in avail_items:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        bold_run = p.add_run(f"{label}: ")
        set_font(bold_run, bold=True)
        val_run = p.add_run(value)
        set_font(val_run)

    # ── Funding ───────────────────────────────────────────────────────────────
    add_heading(doc, "Funding", level=1)
    add_mixed_paragraph(doc, "[Funding information to be completed by authors.]")

    # ── References ────────────────────────────────────────────────────────────
    add_heading(doc, "References", level=1)

    references = [
        ("Brown,T. et al. (2020) Language models are few-shot learners. "
         "Advances in Neural Information Processing Systems, 33, 1877\u20131901."),
        ("Chen,Q. and Deng,C. (2023) Bioinfo-Bench: a simple benchmark framework for "
         "LLM bioinformatics skills evaluation. bioRxiv, doi:10.1101/2023.10.18.563023."),
        ("Clark,P. et al. (2018) Think you have solved question answering? Try ARC, "
         "the AI2 reasoning challenge. arXiv:1803.05457."),
        ("Cobbe,K. et al. (2021) Training verifiers to solve math word problems. "
         "arXiv:2110.14168."),
        ("Gao,L. et al. (2024) A framework for few-shot language model evaluation. "
         "Zenodo, doi:10.5281/zenodo.10256836. (Version 0.4.3.)"),
        ("Hendrycks,D. et al. (2021) Measuring massive multitask language understanding. "
         "International Conference on Learning Representations."),
        ("Jin,Q. et al. (2019) PubMedQA: a dataset for biomedical research question "
         "answering. Proceedings of EMNLP-IJCNLP, 2567\u20132577."),
        ("Jin,D. et al. (2021b) What disease does this patient have? Applied Sciences, "
         "11, 6421."),
        ("Liang,P. et al. (2022) Holistic evaluation of language models. Transactions "
         "on Machine Learning Research."),
        ("McNemar,Q. (1947) Note on the sampling error of the difference between "
         "correlated proportions or percentages. Psychometrika, 12, 153\u2013157."),
        ("OpenAI (2023) GPT-4 technical report. arXiv:2303.08774."),
        ("Pal,A. et al. (2022) MedMCQA: a large-scale multi-subject multi-choice "
         "dataset for medical entrance exams. Proceedings of CHIL, 174, 248\u2013260."),
        ("Sakaguchi,K. et al. (2021) WinoGrande: an adversarial Winograd schema "
         "challenge at scale. Communications of the ACM, 64, 99\u2013106."),
        ("Sarwal,V. et al. (2023) A benchmark for large language models in "
         "bioinformatics. bioRxiv, doi:10.1101/2023.12.19.572483."),
        ("Singhal,K. et al. (2023) Large language models encode clinical knowledge. "
         "Nature, 620, 172\u2013180."),
        ("Tang,X. et al. (2024) BioCoder: a benchmark for bioinformatics code "
         "generation with large language models. Bioinformatics, 40(Suppl 1), "
         "i266\u2013i276."),
        ("Touvron,H. et al. (2023) Llama 2: open foundation and fine-tuned chat "
         "models. arXiv:2307.09288."),
        ("Wei,J. et al. (2022) Chain-of-thought prompting elicits reasoning in large "
         "language models. Advances in Neural Information Processing Systems, 35, "
         "24824\u201324837."),
        ("Wilson,E.B. (1927) Probable inference, the law of succession, and statistical "
         "inference. Journal of the American Statistical Association, 22, 209\u2013212."),
        ("Zellers,R. et al. (2019) HellaSwag: can a machine really finish your sentence? "
         "Proceedings of ACL, 4791\u20134800."),
    ]
    for ref in references:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.left_indent = Cm(0.5)
        p.paragraph_format.first_line_indent = Cm(-0.5)
        run = p.add_run(ref)
        set_font(run, size=9)

    # ── Save ─────────────────────────────────────────────────────────────────
    out_path = "BenchmarkHub_paper.docx"
    doc.save(out_path)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    build_docx()
