#!/usr/bin/env python
"""
Generate BenchmarkHub_paper_revised.docx — Bioinformatics Application Note.

Revision notes (July 2026): addresses all reviewer comments in
"BenchmarkHub_paper (1).docx" and adds the multimodal benchmark support
(vision / audio / agentic). Main text kept within the Application Note
limit (~1,300 words, no figure).

Usage:  python make_docx.py
"""
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

TITLE = ("BenchmarkHub: a configurable web platform for systematic evaluation "
         "of large language models on general-purpose, biomedical and "
         "multimodal benchmarks")

AUTHORS = "JI. Alvarez-Arenas1,2, D. Jimenez-Carretero1,3, F. Sanchez-Cabo1,3*"

AFFILIATIONS = [
    "1 Centro Nacional de Investigaciones Cardiovasculares (CNIC), Madrid, Spain",
    "2 Universidad Autónoma de Madrid, Escuela de Doctorado, Madrid, Spain",
    "3 CIBER de Enfermedades Cardiovasculares (CIBER-CV), Madrid, Spain",
]

CORRESPONDING = "* Corresponding author. Email: fscabo@cnic.es"

ABSTRACT_SUMMARY = (
    "Summary: BenchmarkHub is an open-source web platform and command-line "
    "toolkit for evaluating and comparing large language models (LLMs) on a "
    "curated, extensible library of 50 standardised benchmarks spanning four "
    "modalities: text, vision, audio, and agentic function calling. All "
    "functionality is exposed through three interchangeable access modes—a "
    "browser interface, a REST API, and a command-line interface—so the same "
    "installation serves interactive exploration and automated pipelines. "
    "Evaluations can be compared along every experimental axis: models, "
    "benchmark suites, prompt variants, and sampling parameters, with parallel "
    "dispatch, paired statistical testing, pre-run cost estimation, and "
    "per-question token accounting. New benchmarks are added without code "
    "from the HuggingFace Hub, from custom CSV files, or as "
    "retrieval-augmented generation (RAG) benchmarks—a CSV in which each "
    "question carries its own context passage, letting researchers evaluate "
    "document-grounded question answering on their own clinical notes or "
    "literature. Any benchmark runs on cloud APIs or on local inference "
    "servers, keeping sensitive data within institutional infrastructure."
)

ABSTRACT_AVAILABILITY = (
    "Availability and Implementation: Implemented in Python (Django); runs on "
    "Linux, macOS, and Windows with no external database server required. "
    "Source code is freely available under the MIT license at "
    "https://github.com/placeholder/benchmarkhub."
)

# (heading, [paragraphs]) — a paragraph starting with "• " renders as a bullet.
SECTIONS = [
    ("1  Introduction", [
        "Large language models have become transformative tools across "
        "biomedical research, with demonstrated capabilities in clinical "
        "question answering, literature mining, and scientific reasoning "
        "(Singhal et al., 2023). Rigorous benchmark evaluation is therefore "
        "essential for selecting models for specific tasks and tracking "
        "progress over time.",

        "The current tooling landscape is fragmented. Frameworks such as the "
        "EleutherAI Language Model Evaluation Harness (Sutawika et al., 2026) "
        "and HELM (Liang et al., 2023) offer broad benchmark coverage but "
        "require substantial technical expertise, provide no graphical "
        "interface, and offer limited support for commercial API providers. "
        "Cloud leaderboards are opaque about experimental conditions and "
        "closed to custom datasets. Ad-hoc scripts remain the norm, producing "
        "results that are hard to reproduce. The problem is acute in "
        "biomedicine, where studies evaluating LLMs on MedQA (D. Jin et al., "
        "2020), PubMedQA (Q. Jin et al., 2019), or the clinical subsets of "
        "MMLU (Hendrycks et al., 2021) use widely varying question subsets, "
        "prompting styles, and answer-extraction heuristics, making "
        "cross-study comparison unreliable.",

        "We present BenchmarkHub, a reproducible and highly configurable "
        "evaluation platform. Its central design goal is domain adaptability: "
        "researchers can assemble ad-hoc benchmark collections for any field "
        "of interest—or keep them general-purpose—reusing the same execution, "
        "comparison, and costing machinery. We demonstrate this with a "
        "curated biomedical collection, and with native multimodal support "
        "covering image, audio, and function-calling benchmarks. Concretely, "
        "the platform contributes: a single evaluation model exposed through "
        "web, API, and command-line interfaces; a nine-backend provider "
        "abstraction that runs any benchmark on any model, cloud or local; "
        "parallelisation along every experimental axis with integrated "
        "cost control; full control of the prompt; and three import paths "
        "that turn arbitrary datasets into first-class benchmarks.",
    ]),

    ("2  Implementation", []),

    ("2.1  Access Modes", [
        "All platform functionality operates on a single data model exposed "
        "through three interchangeable modes: (i) a responsive web interface "
        "for browsing benchmarks, launching and monitoring runs, comparison, "
        "and scheduling; (ii) a JSON REST API with interactive documentation, "
        "enabling integration into continuous-integration pipelines; and "
        "(iii) a command-line interface, whose fifteen management commands "
        "cover every operation headlessly and are suitable for scripting and "
        "cluster submission. Because the three modes share one data store, a "
        "run launched from the CLI is inspected in the browser and queried "
        "through the API interchangeably—making the platform equally suited "
        "to interactive exploration by a clinical researcher and to automated "
        "nightly regression testing by a software team. The default SQLite "
        "database (write-ahead-logging mode) supports concurrent readers "
        "during execution; PostgreSQL is supported for multi-user "
        "deployments.",
    ]),

    ("2.2  Provider Abstraction Layer", [
        "Nine provider backends sit behind a unified interface, so any "
        "benchmark can run on any provider without changes to benchmark "
        "definitions: seven cloud APIs (OpenAI, Anthropic, Google, Groq, "
        "Mistral, Cohere, Together) and two local inference servers, Ollama "
        "and vLLM (Kwon et al., 2023)—any endpoint exposing an "
        "OpenAI-compatible chat interface is likewise usable. Multimodal "
        "inputs are delivered in each provider's native format (base64 image "
        "blocks, audio content parts); a provider that does not support a "
        "modality fails explicitly per question rather than silently scoring "
        "the model on text alone. Local backends allow open-weight models to "
        "be evaluated on institutional hardware without transmitting "
        "sensitive clinical or genomic data to external services.",
    ]),

    ("2.3  Benchmark Registry and Import", [
        "Fifty built-in loaders handle dataset-specific prompt formatting and "
        "answer evaluation across four benchmark types: text (42 benchmarks); "
        "vision, including ScienceQA, AI2D, MMBench, ChartQA, and MMMU (Yue "
        "et al., 2024); audio speech recognition on LibriSpeech (Panayotov et "
        "al., 2015); and agentic evaluation with GAIA (Mialon et al., 2023) "
        "and the Berkeley Function Calling Leaderboard. Answer evaluation is "
        "matched to the "
        "question type: multiple-choice letters are extracted with "
        "word-boundary regular expressions robust to surrounding explanatory "
        "text; mathematical answers are parsed from LaTeX or equality "
        "patterns and compared numerically with 10⁻⁶ tolerance; open-ended "
        "answers are normalised and matched on word boundaries, with "
        "pipe-separated acceptable alternatives; transcriptions are scored by "
        "word error rate. Vision and audio loaders store media locally, "
        "preview it in the question browser, and pass it to providers at run "
        "time.",

        "Researchers extend the registry through three import paths, all "
        "producing first-class benchmarks with full run, sweep, suite, and "
        "export support. HuggingFace Hub import ingests any of the thousands "
        "of Hub datasets by mapping its columns to the question, answer-choice, "
        "and correct-answer fields. Custom CSV import accepts a file of "
        "questions with up to four options and a correct answer, selecting the "
        "multiple-choice or open-ended evaluator automatically. RAG import "
        "pairs each question with a context passage—a clinical note, a PubMed "
        "abstract, or a genomic database record; the context is a distinct "
        "input modality prepended to the prompt at inference time, while the "
        "answer is still scored by its question type above. Concretely, the "
        "uploaded CSV has one column for the context passage, one for the "
        "question, and one for the correct answer (optionally subject and "
        "difficulty); a downloadable example documents the format. This is "
        "how a group builds a concrete document-grounded benchmark over its "
        "own in-house corpus—the material most likely to be private—without "
        "writing any code, and runs it against a local model so the documents "
        "never leave the institution.",
    ]),

    ("2.4  Parallel Execution and Cost Control", [
        "Run-level parallelism is available along three combinable axes: "
        "several models evaluated on one benchmark, several benchmarks on one "
        "model (the basis of benchmark suites), and several parameter "
        "configurations—temperature, prompt variant, few-shot count—on one "
        "model and benchmark. Within each run, questions are additionally "
        "evaluated concurrently by a configurable worker pool. Two "
        "concurrency strategies govern simultaneous runs: the default shares "
        "a global cap on in-flight API calls across all runs, respecting "
        "provider rate limits; the alternative serialises runs while "
        "parallelising questions within each, intended for GPU-bound local "
        "servers where concurrent models would exhaust memory. Transient "
        "failures are retried with exponential backoff, runs are cancellable "
        "within a second, and live progress is visible from both the web "
        "interface and the CLI.",

        "Cost control is integrated throughout: a pricing table drives a "
        "pre-run upper-bound cost estimate, and every completed question "
        "records its actual input/output token counts and estimated cost, "
        "enabling per-run and per-question cost analysis and "
        "budget-constrained experimental design.",
    ]),

    ("2.5  Domain Collections: a Biomedical Use Case", [
        "The same extensibility supports curating domain compendia, which we "
        "demonstrate with the bundled biomedical collection: MedQA USMLE, "
        "MedMCQA (Pal et al., 2022), PubMedQA, BioInfoBench (Chen & Deng, "
        "2023), SciQ (Welbl et al., 2017), and eight clinical and "
        "life-science MMLU subsets; MMMU further contributes image-based "
        "clinical and diagnostic questions. Benchmark suites group any such "
        "collection into a single dispatchable evaluation with an aggregate "
        "score—the identical mechanism serves any other domain. A typical "
        "workflow is: load the biomedical suite, dispatch it in one bulk run "
        "to several open-weight models on a local vLLM server alongside a "
        "commercial API baseline, and read off the leaderboard and per-subject "
        "comparison—no data leaving the institution for the local models.",
    ]),

    ("3  Features", []),

    ("3.1  Comparison and Experimentation", [
        "Parameter sweeps evaluate a benchmark under a grid of temperatures "
        "or a list of saved prompt variants; bulk runs dispatch one benchmark "
        "to any number of provider/model combinations; suites evaluate a "
        "model across a benchmark collection. Results feed dedicated "
        "comparison views: side-by-side inspection of up to four runs with "
        "per-subject breakdowns and question-level disagreements; a "
        "leaderboard ranked by Wilson score confidence intervals (Wilson, "
        "1927), which remain accurate for the small question subsets typical "
        "of specialised biomedical benchmarks; paired A/B testing of two runs "
        "with McNemar's test (McNemar, 1947) on the identical question pool; "
        "a question-hardness view flagging items missed by every model; and "
        "per-model performance history over time.",
    ]),

    ("3.2  Full Prompt Control", [
        "Every part of the prompt reaching the model is user-controllable: a "
        "versioned prompt library, custom templates embedding the question "
        "and options in arbitrary instructions, few-shot examples sampled "
        "from outside the evaluation set, and one-toggle chain-of-thought "
        "elicitation (Wei et al., 2023).",
    ]),

    ("3.3  Automation and Interoperability", [
        "A background scheduler supports one-time, daily, and weekly runs for "
        "rolling regression monitoring; webhooks post run results to "
        "user-specified URLs for pipeline chaining. Externally computed "
        "results can be imported from CSV—supporting evaluations that cannot "
        "leave a secure enclave—and all results and question sets export to "
        "CSV or Excel. A dashboard summarises activity, best scores, and a "
        "benchmark-coverage matrix.",
    ]),

    ("4  Discussion", [
        "BenchmarkHub occupies a practical niche between ad-hoc evaluation "
        "scripts and opaque cloud leaderboards. Compared with the EleutherAI "
        "harness and HELM, it adds a graphical interface that lowers the "
        "barrier for researchers who are not software engineers, live "
        "evaluation of commercial APIs, and exact reproducibility through "
        "shareable run templates. Its distinguishing strengths are (i) "
        "parallelisation along every experimental axis, uncommon among "
        "comparable tools; (ii) integrated cost-control tooling; (iii) full "
        "control of the prompt; (iv) domain customisation, from thematic "
        "compendia to general-purpose collections; and (v) privacy-preserving "
        "operation, combining local inference backends, user-built RAG "
        "benchmarks over in-house documents, and offline result import so that "
        "no sensitive data need leave the institution. Adaptation is "
        "deliberately cheap: new OpenAI-compatible "
        "endpoints are configuration rather than code, and new provider "
        "backends implement a single-method interface.",

        "Limitations remain. Free-form generation quality—clinical note "
        "writing, summarisation—is not yet assessed; LLM-as-judge evaluation "
        "is planned. Statistical testing covers paired comparisons without "
        "multiple-comparison correction. Multimodal support currently spans "
        "image question answering, speech transcription, and single-turn "
        "function calling; multi-turn agentic tasks and richer medical "
        "imaging formats are future work, alongside integration with model "
        "cards and FAIR principles. BenchmarkHub is actively maintained and "
        "welcomes community contributions.",
    ]),
]

AVAILABILITY_ITEMS = [
    "Project name: BenchmarkHub",
    "Project home page: https://github.com/placeholder/benchmarkhub",
    "Operating system(s): Linux, macOS, Windows",
    "Programming language: Python 3",
    "Other software requirements: Django, HuggingFace datasets and "
    "huggingface_hub, pillow, soundfile, jiwer, requests, openpyxl, "
    "whitenoise; full list in requirements.txt",
    "License: MIT",
    "Restrictions to use by non-academics: None",
    "Software availability guarantee: The authors commit to maintaining the "
    "repository and ensuring public availability for a minimum of two years "
    "following publication.",
]

FUNDING = "[Funding information to be completed]"

REFERENCES = [
    "Chen, Q., & Deng, C. (2023). Bioinfo-Bench: A Simple Benchmark Framework "
    "for LLM Bioinformatics Skills Evaluation. "
    "https://doi.org/10.1101/2023.10.18.563023",

    "Hendrycks, D., Burns, C., Basart, S., Zou, A., Mazeika, M., Song, D., & "
    "Steinhardt, J. (2021). Measuring Massive Multitask Language "
    "Understanding.",

    "Jin, D., Pan, E., Oufattole, N., Weng, W.-H., Fang, H., & Szolovits, P. "
    "(2020). What Disease does this Patient Have? A Large-scale Open Domain "
    "Question Answering Dataset from Medical Exams.",

    "Jin, Q., Dhingra, B., Liu, Z., Cohen, W. W., & Lu, X. (2019). PubMedQA: "
    "A Dataset for Biomedical Research Question Answering.",

    "Kwon, W., Li, Z., Zhuang, S., Sheng, Y., Zheng, L., Yu, C. H., Gonzalez, "
    "J. E., Zhang, H., & Stoica, I. (2023). Efficient Memory Management for "
    "Large Language Model Serving with PagedAttention. Proceedings of the "
    "29th Symposium on Operating Systems Principles.",

    "Liang, P., Bommasani, R., Lee, T., Tsipras, D., Soylu, D., Yasunaga, M., "
    "Zhang, Y., Narayanan, D., Wu, Y., Kumar, A., Newman, B., Yuan, B., Yan, "
    "B., Zhang, C., Cosgrove, C., Manning, C. D., Ré, C., Acosta-Navas, D., "
    "Hudson, D. A., … Koreeda, Y. (2023). Holistic Evaluation of Language "
    "Models.",

    "McNemar, Q. (1947). Note on the Sampling Error of the Difference Between "
    "Correlated Proportions or Percentages. Psychometrika, 12(2), 153–157. "
    "https://doi.org/10.1007/BF02295996",

    "Mialon, G., Fourrier, C., Swift, C., Wolf, T., LeCun, Y., & Scialom, T. "
    "(2023). GAIA: a benchmark for General AI Assistants.",

    "Pal, A., Umapathi, L. K., & Sankarasubbu, M. (2022). MedMCQA: A "
    "Large-scale Multi-Subject Multi-Choice Dataset for Medical domain "
    "Question Answering.",

    "Panayotov, V., Chen, G., Povey, D., & Khudanpur, S. (2015). Librispeech: "
    "An ASR corpus based on public domain audio books. IEEE International "
    "Conference on Acoustics, Speech and Signal Processing (ICASSP).",

    "Singhal, K., Azizi, S., Tu, T., Mahdavi, S. S., Wei, J., Chung, H. W., "
    "Scales, N., Tanwani, A., Cole-Lewis, H., Pfohl, S., Payne, P., "
    "Seneviratne, M., Gamble, P., Kelly, C., Babiker, A., Schärli, N., "
    "Chowdhery, A., Mansfield, P., Demner-Fushman, D., … Natarajan, V. "
    "(2023). Large language models encode clinical knowledge. Nature, "
    "620(7972). https://doi.org/10.1038/s41586-023-06291-2",

    "Sutawika, L., Schoelkopf, H., Gao, L., Abbasi, B., Biderman, S., Tow, "
    "J., fattori, b., & Lovering, C. (2026). EleutherAI/lm-evaluation-harness "
    "(v0.4.11). Zenodo.",

    "Wei, J., Wang, X., Schuurmans, D., Bosma, M., Ichter, B., Xia, F., Chi, "
    "E., Le, Q., & Zhou, D. (2023). Chain-of-Thought Prompting Elicits "
    "Reasoning in Large Language Models.",

    "Welbl, J., Liu, N. F., & Gardner, M. (2017). Crowdsourcing Multiple "
    "Choice Science Questions.",

    "Wilson, E. B. (1927). Probable Inference, the Law of Succession, and "
    "Statistical Inference. Journal of the American Statistical Association, "
    "22(158), 209. https://doi.org/10.2307/2276774",

    "Yue, X., Ni, Y., Zhang, K., Zheng, T., Liu, R., Zhang, G., Stevens, S., "
    "Jiang, D., Ren, W., Sun, Y., Wei, C., Yu, B., Yuan, R., Sun, R., Yin, "
    "M., Zheng, B., Yang, Z., Liu, Y., Huang, W., … Chen, W. (2024). MMMU: A "
    "Massive Multi-discipline Multimodal Understanding and Reasoning "
    "Benchmark for Expert AGI. CVPR.",
]


# ---------------------------------------------------------------------------
# Document assembly
# ---------------------------------------------------------------------------

def main():
    doc = Document()

    # Base style
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(10)

    # Title
    p = doc.add_paragraph()
    run = p.add_run(TITLE)
    run.bold = True
    run.font.size = Pt(14)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Authors + affiliations
    p = doc.add_paragraph()
    p.add_run(AUTHORS).italic = True
    for aff in AFFILIATIONS:
        doc.add_paragraph(aff)
    doc.add_paragraph(CORRESPONDING)

    # Abstract
    p = doc.add_paragraph()
    p.add_run('Abstract').bold = True
    doc.add_paragraph(ABSTRACT_SUMMARY)
    doc.add_paragraph(ABSTRACT_AVAILABILITY)

    # Sections
    for heading, paragraphs in SECTIONS:
        p = doc.add_paragraph()
        r = p.add_run(heading)
        r.bold = True
        r.font.size = Pt(11.5) if heading[0].isdigit() and '.' not in heading.split()[0] else Pt(10.5)
        for text in paragraphs:
            if text.startswith('• '):
                doc.add_paragraph(text[2:], style='List Bullet')
            else:
                doc.add_paragraph(text)

    # Availability block
    p = doc.add_paragraph()
    p.add_run('Availability and Implementation').bold = True
    for item in AVAILABILITY_ITEMS:
        doc.add_paragraph(item)

    # Funding
    p = doc.add_paragraph()
    p.add_run('Funding').bold = True
    doc.add_paragraph(FUNDING)

    # References
    p = doc.add_paragraph()
    p.add_run('References').bold = True
    for ref in REFERENCES:
        doc.add_paragraph(ref)

    out = 'BenchmarkHub_paper_revised.docx'
    doc.save(out)

    # Word-count report. Bioinformatics Application Note limit: up to 4 printed
    # pages ≈ 2,600 words (or 2,000 words + one figure). The page limit counts
    # everything — title, abstract, body, availability, references — so the
    # total below is the number that matters.
    main_words = sum(len(t.split()) for _, ps in SECTIONS for t in ps)
    abstract_words = len(ABSTRACT_SUMMARY.split()) + len(ABSTRACT_AVAILABILITY.split())
    front = len(TITLE.split()) + len(AUTHORS.split()) + sum(len(a.split()) for a in AFFILIATIONS)
    avail_words = sum(len(a.split()) for a in AVAILABILITY_ITEMS)
    ref_words = sum(len(r.split()) for r in REFERENCES)
    total = front + abstract_words + main_words + avail_words + ref_words + len(FUNDING.split())
    print(f"Saved {out}")
    print(f"  Abstract:                 {abstract_words} words")
    print(f"  Main text (sections 1-4): {main_words} words")
    print(f"  References ({len(REFERENCES)}):           {ref_words} words")
    print(f"  TOTAL (counts to 4 pages):{total:>5} words   (limit ≈ 2600, no figure)")


if __name__ == '__main__':
    main()
