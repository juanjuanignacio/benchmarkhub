# BenchmarkHub: a web platform for systematic evaluation of large language models on biomedical and general-purpose benchmarks

**First Author**¹, **Second Author**¹, **Corresponding Author**¹,\*

¹ Affiliation, Institution, City, Country.

\* To whom correspondence should be addressed. Email: author@institution.edu

---

## Abstract

**Summary:** BenchmarkHub is an open-source web platform and command-line toolkit that enables researchers to evaluate and compare large language models (LLMs) across a curated library of more than 40 standardized benchmarks, including a dedicated collection of biomedical, clinical, and bioinformatics datasets. The platform unifies three interaction modes—a browser-based interface, a REST API, and a command-line interface with 18 management commands—so that both interactive exploratory analysis and fully automated evaluation pipelines are supported from the same installation. Key capabilities include parallel benchmark execution with configurable concurrency, parameter sweeps over temperature and prompt variants, prompt A/B testing with McNemar's χ² test, Wilson score confidence intervals, pre-run cost estimation, automated scheduling, and flexible benchmark import from HuggingFace Hub, CSV files, or retrieval-augmented generation (RAG) datasets assembled from user-supplied context passages.

**Availability and Implementation:** BenchmarkHub is implemented in Python 3.11 with the Django 4.2 framework and runs on Linux, macOS, and Windows without requiring an external database server (SQLite by default; PostgreSQL-compatible for multi-user deployments). The source code is freely available under the MIT license at [https://github.com/placeholder/benchmarkhub](https://github.com/placeholder/benchmarkhub). Installation requires only `pip install -r requirements.txt` and a database migration step. A step-by-step quickstart is included in the repository README. Supplementary material describing advanced configuration and worked examples is available online.

---

## 1 Introduction

Large language models have emerged as transformative tools across biomedical research, demonstrating remarkable capabilities in clinical question answering, genomic data interpretation, literature mining, and scientific reasoning (Brown *et al.*, 2020; Singhal *et al.*, 2023). Evaluating these models rigorously on standardized benchmarks has become essential for selecting models appropriate to specific tasks, comparing performance across model families, and tracking progress over time.

Despite the importance of evaluation, the current landscape of benchmarking tools is fragmented. Existing frameworks such as the EleutherAI Language Model Evaluation Harness (Gao *et al.*, 2024) and HELM (Liang *et al.*, 2022) offer comprehensive coverage of general-purpose benchmarks but require substantial technical expertise to operate, provide no graphical interface, lack native support for cloud API providers, and offer limited biomedical benchmark coverage. Cloud leaderboard services, on the other hand, are opaque about experimental conditions and do not allow researchers to evaluate proprietary datasets or customize prompting strategies. Ad-hoc scripted evaluations are common but produce results that are difficult to reproduce and compare across studies.

The biomedical domain presents particular challenges. Studies evaluating LLMs on clinical knowledge benchmarks such as MedQA (Jin *et al.*, 2021b), PubMedQA (Jin *et al.*, 2019), and the clinical subsets of MMLU (Hendrycks *et al.*, 2021) use widely varying experimental configurations—different question subsets, prompting styles, few-shot counts, temperature settings, and answer-extraction heuristics—making cross-study comparisons unreliable. There is a clear need for a unified platform that standardizes experimental conditions, covers the relevant biomedical benchmarks, and is accessible to researchers without deep software engineering expertise.

We present BenchmarkHub, a platform that addresses these gaps. It provides a reproducible, configurable, and user-friendly environment for evaluating LLMs on both general-purpose and biomedical benchmarks, accessible via a web browser, a REST API, and a full command-line interface.

---

## 2 Implementation

### 2.1 Architecture and Access Modes

BenchmarkHub is a Django web application organized into three Django apps—*benchmarks*, *providers*, and *runs*—that correspond to the three core concepts of the platform. The default database is SQLite configured in write-ahead logging mode, which supports concurrent readers during benchmark execution; the application is also compatible with PostgreSQL for deployments requiring higher concurrency. Static files are served efficiently in production via WhiteNoise with manifest-based cache busting.

A key design principle of BenchmarkHub is that all platform functionality is exposed through three interchangeable access modes, each operating on the same underlying data model:

- **Web interface.** A responsive Bootstrap 5.3 browser application with more than 20 views covering benchmark browsing, provider management, run creation and monitoring, multi-run comparison, statistical analysis, leaderboards, and scheduling. No JavaScript framework is required.

- **REST API.** A JSON API at `/api/v1/` that provides full programmatic access to benchmarks, providers, and runs, including run creation and result retrieval. Interactive API documentation is available at `/api/docs/`. The API enables integration with continuous integration and delivery pipelines and third-party analysis tools.

- **Command-line interface.** Eighteen management commands, all accessible via the standard Django management interface, cover every operation available in the web UI: registering and testing providers, loading benchmarks, launching single or multi-model runs, monitoring run status, executing parameter sweeps and bulk runs, managing benchmark suites, scheduling recurring runs, displaying leaderboards, and exporting results. All commands accept a `--help` flag and are suitable for scripting, high-performance cluster submission, and automation without a running web server.

This tri-modal design ensures that BenchmarkHub is equally well suited to interactive exploration by a clinical researcher and to automated nightly regression testing by a software team.

### 2.2 Provider Abstraction Layer

BenchmarkHub supports nine LLM provider backends through a unified interface, so that any benchmark can be run on any provider without changes to the benchmark definition or the evaluation logic. The cloud providers currently supported are OpenAI (GPT-4o, GPT-4-turbo, GPT-3.5-turbo), Anthropic Claude (Opus, Sonnet, Haiku), Google Gemini (1.5 Pro and Flash), Groq, Mistral AI, Cohere, and Together AI. Two local inference servers are also supported: Ollama and vLLM, both of which expose an OpenAI-compatible chat completion interface.

Providers are registered once—through the web interface, the API, or the CLI—and stored in the database. After registration, any number of benchmarks can be dispatched to any provider/model combination. The local server backends (Ollama and vLLM) are particularly valuable in biomedical contexts because they allow evaluation of open-weight models on institutional hardware without transmitting patient-related or otherwise sensitive evaluation data to external services.

### 2.3 Benchmark Registry and Custom Benchmark Import

BenchmarkHub ships with over 40 built-in benchmark loaders that handle dataset-specific prompt formatting and answer evaluation. Answer evaluation strategies are matched to the dataset type:

- **Multiple-choice questions** (the majority of supported benchmarks): the model's response is scanned with a word-boundary regular expression to extract the predicted letter (A–D), making the evaluation robust to responses that include explanatory text before or after the answer.
- **Mathematical problems** (GSM8K, MATH-500, AQuA-RAT, AIME): answers are extracted by detecting LaTeX boxed notation, matching "= answer" patterns, and as a last resort, extracting the last numeral in the response. Numeric comparison is performed with a tolerance of 10⁻⁶ to handle floating-point representations.
- **Open-ended factual questions** (TriviaQA): both the model's answer and the reference answer are normalized by lowercasing and collapsing whitespace before word-boundary comparison.
- **RAG questions** (context-dependent): the evaluation supports comma-separated alias lists and pipe-separated alternative correct answers, accommodating datasets where multiple phrasings are acceptable.

Beyond the built-in collection, researchers can add benchmarks through three import paths, all of which produce first-class benchmark objects that support the full set of run, sweep, comparison, and export features:

- **HuggingFace Hub import.** Users specify a dataset identifier on the HuggingFace Hub and map its column names to the expected question, answer-choice, and correct-answer fields. The dataset is downloaded and ingested automatically, giving access to the thousands of evaluation datasets published on the Hub.

- **Custom CSV benchmark.** Users upload a CSV file with columns for the question text, up to four answer options, the correct answer letter, and optionally a subject label. This path is intended for proprietary or domain-specific benchmarks that are not publicly distributed.

- **RAG benchmark from context CSV.** Users upload a CSV in which each question is paired with a passage of context text—for example, a clinical note, a PubMed abstract, or a genomic database record. BenchmarkHub prepends the context to the prompt at inference time, enabling evaluation of retrieval-augmented generation pipelines and context-dependent reasoning without any additional tooling.

### 2.4 Parallel Execution Engine

The execution engine is designed to handle both single-run interactive evaluations and large-scale batch experiments involving dozens of simultaneous runs and hundreds of questions per run. It implements three execution modes:

1. **Shared-semaphore mode** (used for bulk runs, parameter sweeps, and suite runs): a global concurrency pool limits the total number of simultaneous API calls across all running benchmarks, preventing rate-limit violations when many runs are active at once.
2. **Run-serializer mode**: runs execute one at a time in submission order, each utilizing all of its configured parallel workers internally. This mode is appropriate when the provider allows high per-run parallelism but the user wants predictable run ordering.
3. **Direct parallel mode**: a single run distributes its questions across a configurable number of worker threads, maximizing throughput for time-sensitive single-benchmark evaluations.

Transient failures—rate-limit responses, connection timeouts, and network errors—are handled with an exponential backoff retry policy of up to three attempts, with wait times of 1, 2, and 4 seconds. Running benchmarks can be cancelled at any time; the cancellation signal is detected by the worker threads with a polling interval of approximately one second. Database writes are batched in groups of 50 to keep memory overhead bounded during long runs. Live progress—questions completed, current score, elapsed time—is updated incrementally and visible in both the web interface and the CLI status command.

### 2.5 Biomedical Benchmark Collection

BenchmarkHub's built-in collection includes a substantial set of biomedical and clinical benchmarks that collectively span the major areas of biomedical AI evaluation. Dedicated datasets include MedQA USMLE (Jin *et al.*, 2021b), MedMCQA (Pal *et al.*, 2022), PubMedQA (Jin *et al.*, 2019), BioInfoBench (Chen and Deng, 2023), and SciQ. From the Massive Multitask Language Understanding benchmark (Hendrycks *et al.*, 2021), the platform includes the Clinical Knowledge, Anatomy, Professional Medicine, College Medicine, Medical Genetics, College Biology, Virology, and Nutrition subsets. Together these datasets enable systematic comparison of general-purpose and biomedically specialized models across clinical decision support, biomedical literature comprehension, genetics, and life-science reasoning tasks.

---

## 3 Features

### 3.1 Dashboard and Web Interface

The dashboard aggregates key performance indicators across all completed runs: overall accuracy statistics, number of models evaluated, benchmark coverage, and recent activity. A model coverage matrix displays, for every benchmark and every registered provider, whether a run has been completed and what score was achieved, providing at a glance an overview of evaluation coverage and relative model performance. Dedicated views allow side-by-side comparison of up to four runs, question-level result inspection with per-question correctness, token counts, and response times, and model performance history over time.

### 3.2 Prompt Engineering

BenchmarkHub treats prompt design as a first-class concern. A prompt library allows researchers to save, name, and version system prompts, which can then be reused across runs or selected in parameter sweeps. Few-shot evaluation is supported by randomly sampling a specified number of examples from the benchmark question pool (excluding the evaluation set) and prepending them to each prompt. Chain-of-thought prompting (Wei *et al.*, 2022) can be enabled with a single toggle, appending the standard "Let's think step by step" elicitation phrase. Custom prompt templates allow the question text and answer options to be embedded in arbitrary surrounding instructions, which is useful for testing instruction-following behavior or domain-specific framing.

### 3.3 Statistical Analysis

Benchmark accuracy is reported with Wilson score confidence intervals (Wilson, 1927) at configurable significance levels (90%, 95%, 99%). Wilson intervals are more accurate than normal approximation intervals for small sample sizes and for proportions near zero or one, making them appropriate for domain-specific benchmark subsets where few questions are available. A dedicated A/B test view accepts two runs as input and applies McNemar's χ² test (McNemar, 1947) for paired binary outcomes, providing a statistically principled method for comparing prompt variants or model versions on exactly the same question pool. A question hardness view identifies items that were answered incorrectly by every model evaluated, flagging them as consistently difficult across the tested population.

### 3.4 Parameter Sweeps and Bulk Runs

The parameter sweep feature automates a common experimental workflow: evaluating the same benchmark under a grid of conditions and comparing the outcomes. Users specify either a temperature grid (e.g., 0.0, 0.2, 0.4, 0.6, 0.8, 1.0) or a list of prompt variants from the prompt library; the platform spawns one run per configuration, groups the results automatically, and displays them in a comparative view. Bulk runs extend this to the provider/model dimension: a single benchmark is dispatched simultaneously to any number of provider/model combinations, again with results grouped for comparison. In both modes the global concurrency pool is shared across all spawned runs to avoid exceeding API rate limits.

### 3.5 Cost Estimation and Token Tracking

A built-in pricing database covering 18 commercial models stores per-token input and output costs. Before submitting a run, users can open the cost estimator, which computes an upper-bound cost estimate based on the number of questions, the selected model's pricing, and an assumed response length. Each completed question records its actual input and output token counts alongside the estimated cost, enabling post-hoc cost analysis at both the per-run and per-question level and supporting budget-constrained experimental design.

### 3.6 Scheduling, Automation, and Export

A background scheduler daemon checks for pending scheduled runs every 60 seconds and supports one-time, daily, and weekly recurrence. Scheduled runs can be created and managed through the web interface or the CLI, making it straightforward to monitor model performance regressions on a rolling basis. Webhook notifications can be configured per run: on completion, BenchmarkHub posts a JSON payload containing the run identifier, status, score, and metadata to a user-specified URL, enabling downstream alerting or pipeline chaining. Pre-computed results can also be imported from CSV files, decoupling the storage and analysis of external or pre-existing evaluations from live API execution. Run results and benchmark question sets can be exported to CSV or Excel at any time.

---

## 4 Discussion

BenchmarkHub occupies a practical niche between two common but inadequate approaches to LLM evaluation: ad-hoc Python scripts that are difficult to reproduce and extend, and cloud leaderboard services that are opaque about experimental conditions and inaccessible for custom datasets. Unlike the EleutherAI Language Model Evaluation Harness (Gao *et al.*, 2024), which targets command-line power users and focuses on open-weight models, BenchmarkHub provides a graphical interface that lowers the barrier to entry for biomedical researchers who are not primarily software engineers. Unlike HELM (Liang *et al.*, 2022), it supports live evaluation against commercial API providers, integrates biomedical benchmarks natively, and allows the full experimental configuration to be reproduced exactly by sharing a run template.

The platform's support for local inference servers is particularly relevant for clinical and genomic applications. Evaluating LLMs on datasets derived from electronic health records, clinical notes, or patient genomic data using cloud APIs raises privacy and regulatory concerns. By supporting Ollama and vLLM as first-class provider backends, BenchmarkHub enables evaluation of open-weight models entirely within an institution's computational infrastructure.

The current implementation has several limitations. Evaluation is restricted to multiple-choice and short open-ended answer formats; free-form generation quality—relevant for clinical note generation, report summarization, or code synthesis—is not yet assessed. The statistical testing module covers pairwise comparisons but does not currently implement multiple-comparison corrections for experiments spanning many models simultaneously. Future development will address these limitations by introducing LLM-as-judge evaluation for open-ended responses (following emerging practices in the field), multimodal benchmark support for image-based medical questions, and automatic integration with model cards and FAIR data principles for reproducibility. BenchmarkHub is actively maintained and accepts community contributions through its GitHub repository.

---

## Availability and Implementation

**Project name:** BenchmarkHub
**Project home page:** https://github.com/placeholder/benchmarkhub
**Operating system(s):** Linux, macOS, Windows
**Programming language:** Python 3.11
**Other software requirements:** Django ≥ 4.2, HuggingFace `datasets` and `huggingface_hub`, `requests`, `openpyxl`, `whitenoise`; full list in `requirements.txt`
**License:** MIT
**Restrictions to use by non-academics:** None
**Software availability guarantee:** The authors commit to maintaining the repository and ensuring public availability for a minimum of two years following publication.

---

## Funding

[Funding information to be completed by authors.]

---

## References

Brown, T., Mann, B., Ryder, N. *et al.* (2020) Language models are few-shot learners. *Advances in Neural Information Processing Systems*, **33**, 1877–1901.

Chen, Q. and Deng, C. (2023) Bioinfo-Bench: a simple benchmark framework for LLM bioinformatics skills evaluation. *bioRxiv*, doi:10.1101/2023.10.18.563023.

Clark, P., Cowhey, I., Etzioni, O. *et al.* (2018) Think you have solved question answering? Try ARC, the AI2 reasoning challenge. *arXiv*, arXiv:1803.05457.

Cobbe, K., Kosaraju, V., Bavarian, M. *et al.* (2021) Training verifiers to solve math word problems. *arXiv*, arXiv:2110.14168.

Gao, L., Biderman, S., Black, S. *et al.* (2024) A framework for few-shot language model evaluation. *Zenodo*, doi:10.5281/zenodo.10256836. (Version 0.4.3.)

Hendrycks, D., Burns, C., Basart, S. *et al.* (2021) Measuring massive multitask language understanding. *International Conference on Learning Representations*.

Jin, Q., Dhingra, B., Liu, Z. *et al.* (2019) PubMedQA: a dataset for biomedical research question answering. *Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing*, 2567–2577.

Jin, D., Pan, E., Oufattole, N. *et al.* (2021b) What disease does this patient have? A large-scale open domain question answering dataset from medical exams. *Applied Sciences*, **11**, 6421.

Liang, P., Bommasani, R., Lee, T. *et al.* (2022) Holistic evaluation of language models. *Transactions on Machine Learning Research*.

McNemar, Q. (1947) Note on the sampling error of the difference between correlated proportions or percentages. *Psychometrika*, **12**, 153–157.

OpenAI (2023) GPT-4 technical report. *arXiv*, arXiv:2303.08774.

Pal, A., Umapathi, L. K. and Sankarasubbu, M. (2022) MedMCQA: a large-scale multi-subject multi-choice dataset for medical entrance exams. *Proceedings of the Conference on Health, Inference, and Learning*, **174**, 248–260.

Sakaguchi, K., Bras, R. L., Bhagavatula, C. and Choi, Y. (2021) WinoGrande: an adversarial Winograd schema challenge at scale. *Communications of the ACM*, **64**, 99–106.

Sarwal, V., Andreoletti, G., Munteanu, V. *et al.* (2023) A benchmark for large language models in bioinformatics. *bioRxiv*, doi:10.1101/2023.12.19.572483.

Singhal, K., Azizi, S., Tu, T. *et al.* (2023) Large language models encode clinical knowledge. *Nature*, **620**, 172–180.

Tang, X., Qian, B., Gao, R. *et al.* (2024) BioCoder: a benchmark for bioinformatics code generation with large language models. *Bioinformatics*, **40** (Suppl. 1), i266–i276.

Touvron, H., Martin, L., Stone, K. *et al.* (2023) Llama 2: open foundation and fine-tuned chat models. *arXiv*, arXiv:2307.09288.

Wei, J., Wang, X., Schuurmans, D. *et al.* (2022) Chain-of-thought prompting elicits reasoning in large language models. *Advances in Neural Information Processing Systems*, **35**, 24824–24837.

Wilson, E. B. (1927) Probable inference, the law of succession, and statistical inference. *Journal of the American Statistical Association*, **22**, 209–212.

Zellers, R., Holtzman, A., Bisk, Y. *et al.* (2019) HellaSwag: can a machine really finish your sentence? *Proceedings of the 57th Annual Meeting of the Association for Computational Linguistics*, 4791–4800.
