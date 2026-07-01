# BenchmarkHub Expansion Plan: Vision, Agentic, and Audio Benchmarks

*All dataset structures verified against HuggingFace Hub (July 2026).*

## Executive Summary

Three new benchmark modalities, in priority order:
1. **Phase 1 -- Vision** (images): Smallest architectural change; MCQ benchmarks with images.
2. **Phase 2 -- Agentic** (tool use): Minimal mode first (GAIA text-only, BFCL simple); full agents deferred.
3. **Phase 3 -- Audio** (speech): Most complex; requires WER metric and limited provider support.

---

## Current Architecture Constraints

Before detailing changes, these are the hard constraints imposed by the existing codebase:

| Component | Current State | Impact |
|-----------|---------------|--------|
| `BenchmarkQuestion` model | `question`, `choice_a`/`b`/`c`/`d`, `correct_answer`, `context`, `metadata` (JSONField) | No image/audio fields. `metadata` JSONField available for extension without migration. |
| `BaseProviderBackend.complete()` | `(prompt: str, model, temperature, max_tokens) -> dict` | Text-only. Must be extended for multimodal. |
| `BaseBenchmarkLoader` | `load_questions()`, `format_prompt(q)`, `evaluate_answer(q, resp)` | Returns `(is_correct: bool, parsed_answer: str)`. No continuous metrics. |
| `BenchmarkRunner` | Single `complete()` call per question. | Cannot do multi-turn agent loops. |
| Database | SQLite WAL | Large binary blobs (images) must go to filesystem, not DB. |
| `Benchmark.CATEGORY_CHOICES` | 8 text categories | Need new categories for vision/audio/agentic. |

---

## Phase 1: Vision Benchmarks

### Target Benchmarks (verified field names)

| # | Benchmark | HF Hub Slug | Split | Questions | Format | Answer Field | Image Field |
|---|-----------|-------------|-------|-----------|--------|--------------|-------------|
| 1 | ScienceQA | `derek-thomas/ScienceQA` | test: 4,241 | MCQ | `answer` (int, 0-based index into `choices` list) | `image` (PIL or None) |
| 2 | AI2D | `lmms-lab/ai2d` | test: 3,090 | MCQ (4 options) | `answer` (str index: "0"-"3" into `options` list) | `image` (PIL) |
| 3 | MMMU | `MMMU/MMMU` | val: 900, test: 10,500 | MCQ + Open | `answer` (letter "A"-"D" for MCQ, text for open) | `image_1`..`image_7` (PIL, up to 7) |
| 4 | MMBench | `HuggingFaceM4/MMBench` | val: 4,330, test: 6,670 | MCQ | `answer` (letter "A"-"D") | `image` (base64 string!) |
| 5 | ChartQA | `HuggingFaceM4/ChartQA` | test: 2,500 | Open-ended | `label` (list[str], length 1) | `image` (PIL) |

**Priority order: ScienceQA > AI2D > MMMU > MMBench > ChartQA**

ScienceQA and AI2D are simplest: single image, MCQ, clean structure. MMMU is the most complex (multi-image, 30 configs, mixed MCQ/open).

### Verified Dataset Schemas

#### ScienceQA (`derek-thomas/ScienceQA`)
```
Fields: image (PIL|None), question (str), choices (list[str]),
        answer (int8, 0-based index), hint (str), subject (str),
        topic (str), category (str), grade (str), skill (str),
        lecture (str), solution (str), task (str)
Notes: ~48.7% have images, rest are text-only.
       choices is a native list, NOT separate columns.
       answer is an INDEX, NOT a letter.
```

#### AI2D (`lmms-lab/ai2d`)
```
Fields: question (str), options (list[str], always 4),
        answer (str: "0"|"1"|"2"|"3"), image (PIL)
Notes: Test split only (3,090 rows). All questions have images.
       answer is a STRING index, must cast to int.
```

#### MMMU (`MMMU/MMMU`)
```
Fields: id (str), question (str, contains <image N> placeholders),
        options (str -- STRINGIFIED Python list, needs ast.literal_eval!),
        answer (str: letter for MCQ, text for open),
        question_type (str: "multiple-choice"|"open"),
        topic_difficulty (str), subfield (str), img_type (str),
        image_1..image_7 (PIL|None), explanation (str), split (str)
Notes: 30 separate configs (one per subject). Must load each and concatenate.
       Up to 7 images per question. Question text references them as <image 1>.
       options is NOT a list -- it is a STRING that must be parsed with ast.literal_eval().
```

#### MMBench (`HuggingFaceM4/MMBench`)
```
Fields: index (int), question (str), hint (str),
        A (str), B (str), C (str|null), D (str|null),
        answer (str: "A"|"B"|"C"|"D"), category (str),
        image (str -- BASE64 ENCODED, not PIL!),
        source (str), l2-category (str), comment (str), split (str)
Notes: opencompass/MMBench is EMPTY. Use HuggingFaceM4/MMBench.
       image field is already base64 -- no PIL decoding needed.
       C and D columns can be null (some questions have only 2-3 options).
```

#### ChartQA (`HuggingFaceM4/ChartQA`)
```
Fields: image (PIL), query (str -- NOT "question"!),
        label (list[str], typically length 1),
        human_or_machine (ClassLabel), imagewidth (px) (int)
Notes: Open-ended, NOT MCQ. Question field is called "query".
       Answer field is called "label" and is a list.
```

### Architecture Changes

#### 1. Database Migration (`0006_add_multimodal_support.py`)

**`Benchmark` model -- add type field and new categories:**
```python
# New field
benchmark_type = models.CharField(
    max_length=20,
    choices=[('text','Text'), ('vision','Vision'), ('audio','Audio'), ('agentic','Agentic')],
    default='text',
)

# New CATEGORY_CHOICES entries
('vision', 'Vision & Multimodal'),
('audio', 'Audio & Speech'),
('agentic', 'Agentic / Tool Use'),
```

**`BenchmarkQuestion` model -- add multimodal fields:**
```python
# For multi-image support (MMMU has up to 7 images per question)
image_paths = models.JSONField(default=list, blank=True)
# Stores: ["benchmark_images/mmmu/val_Chemistry_1_img1.jpg", "benchmark_images/mmmu/val_Chemistry_1_img2.jpg"]
# Empty list for text-only questions.

# For audio (Phase 3)
audio_path = models.CharField(max_length=500, blank=True, default='')
```

**Why `image_paths` as JSONField (list) instead of CharField:**
- MMMU has up to 7 images per question
- ScienceQA/AI2D have 0 or 1 image -- stored as `[]` or `["path"]`
- Avoids a separate `QuestionImage` model and the JOIN overhead
- Already have JSONField support (metadata field)

#### 2. Settings -- MEDIA_ROOT

```python
# settings.py
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'
```

Estimated disk:
- ScienceQA images: ~500 MB
- AI2D images: ~200 MB
- MMMU images: ~2 GB (all 30 subjects)

#### 3. `BaseProviderBackend.complete()` -- backward-compatible extension

```python
# apps/providers/backends/base.py
def complete(self, prompt: str, model: str, temperature: float = 0,
             max_tokens: int = 512, images: list[str] | None = None) -> dict:
    # images: list of base64-encoded image strings, or None for text-only
    raise NotImplementedError
```

All 9 existing backends add `**kwargs` or `images=None` to their signature and ignore it. Zero behavior change for text benchmarks.

#### 4. Vision-capable backends (3 of 9)

**OpenAI** (`openai_backend.py`):
```python
def complete(self, prompt, model, temperature=0, max_tokens=512, images=None):
    start = time.time()
    try:
        client = self._get_client()
        if images:
            content = [{'type': 'text', 'text': prompt}]
            for b64 in images:
                content.append({
                    'type': 'image_url',
                    'image_url': {'url': f'data:image/jpeg;base64,{b64}'},
                })
            messages = [{'role': 'user', 'content': content}]
        else:
            messages = [{'role': 'user', 'content': prompt}]
        resp = client.chat.completions.create(
            model=model, messages=messages,
            temperature=temperature, max_tokens=max_tokens,
        )
        text = resp.choices[0].message.content or ''
        return {'text': text, 'response_time': time.time() - start, 'error': None}
    except Exception as e:
        return {'text': '', 'response_time': time.time() - start, 'error': str(e)}
```

**Anthropic** (`anthropic_backend.py`):
```python
def complete(self, prompt, model, temperature=0, max_tokens=512, images=None):
    start = time.time()
    try:
        client = self._get_client()
        if images:
            content = []
            for b64 in images:
                content.append({
                    'type': 'image',
                    'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': b64},
                })
            content.append({'type': 'text', 'text': prompt})
            messages = [{'role': 'user', 'content': content}]
        else:
            messages = [{'role': 'user', 'content': prompt}]
        resp = client.messages.create(
            model=model, max_tokens=max_tokens,
            temperature=temperature, messages=messages,
        )
        text = resp.content[0].text if resp.content else ''
        return {'text': text, 'response_time': time.time() - start, 'error': None}
    except Exception as e:
        return {'text': '', 'response_time': time.time() - start, 'error': str(e)}
```

**Gemini** (`gemini_backend.py`):
```python
def complete(self, prompt, model, temperature=0, max_tokens=512, images=None):
    start = time.time()
    try:
        genai = self._configure()
        generation_config = genai.types.GenerationConfig(
            temperature=temperature, max_output_tokens=max_tokens,
        )
        model_obj = genai.GenerativeModel(
            model_name=model, generation_config=generation_config,
        )
        if images:
            import base64, io
            from PIL import Image
            parts = []
            for b64 in images:
                img = Image.open(io.BytesIO(base64.b64decode(b64)))
                parts.append(img)
            parts.append(prompt)
            response = model_obj.generate_content(parts)
        else:
            response = model_obj.generate_content(prompt)
        text = response.text if hasattr(response, 'text') else ''
        return {'text': text, 'response_time': time.time() - start, 'error': None}
    except Exception as e:
        return {'text': '', 'response_time': time.time() - start, 'error': str(e)}
```

**Remaining 6 backends** (Ollama, vLLM, Cohere, Mistral, Groq, Together): add `images=None` parameter, ignore it. Ollama can be extended later (supports `images` in `/api/generate`).

#### 5. `BaseBenchmarkLoader` -- new method for images

```python
class BaseBenchmarkLoader:
    # Existing methods unchanged...

    def get_images_b64(self, question) -> list[str]:
        """Return list of base64-encoded images for this question.
        Default: reads from question.image_paths field."""
        paths = question.image_paths or []
        if not paths:
            return []
        import base64, os
        from django.conf import settings
        result = []
        for rel_path in paths:
            full = os.path.join(settings.MEDIA_ROOT, rel_path)
            try:
                with open(full, 'rb') as f:
                    result.append(base64.b64encode(f.read()).decode('ascii'))
            except OSError:
                continue
        return result
```

#### 6. Runner changes

`apps/runs/runner.py`, inside `process_question()`:

```python
# After building prompt, before calling backend:
images_b64 = []
if loader:
    images_b64 = loader.get_images_b64(question)

result_data = _process_question_with_retry(
    backend, prompt, run.model_name, run.temperature, run.max_tokens,
    images=images_b64 or None,
)
```

`_process_question_with_retry()` passes `images` through to `backend.complete()`.

### Vision Loader Implementations

#### ScienceQA Loader (Priority 1 -- simplest)

```python
class ScienceQAVisionLoader(BaseBenchmarkLoader):
    """ScienceQA -- derek-thomas/ScienceQA.
    MCQ with optional images. choices is a list, answer is 0-based int index."""

    LETTERS = 'ABCDEFGHIJ'

    def load_questions(self):
        from datasets import load_dataset
        import os
        from django.conf import settings

        ds = load_dataset('derek-thomas/ScienceQA', split='test')
        img_dir = os.path.join(settings.MEDIA_ROOT, 'benchmark_images', 'scienceqa')
        os.makedirs(img_dir, exist_ok=True)
        questions = []

        for item in ds:
            qid = f"sciqa_{item.get('task', 'q')}_{len(questions)}"
            choices = item['choices']           # list[str]
            correct_idx = item['answer']        # int, 0-based
            correct_letter = self.LETTERS[correct_idx]

            # Map variable-length choices list to choice_a/b/c/d
            choice_a = choices[0] if len(choices) > 0 else None
            choice_b = choices[1] if len(choices) > 1 else None
            choice_c = choices[2] if len(choices) > 2 else None
            choice_d = choices[3] if len(choices) > 3 else None

            # Save image if present
            image_paths = []
            if item['image'] is not None:
                fname = f"{qid}.jpg"
                full_path = os.path.join(img_dir, fname)
                item['image'].save(full_path, 'JPEG')
                image_paths = [os.path.join('benchmark_images', 'scienceqa', fname)]

            # Use hint as context if available
            context = item['hint'] if item['hint'] else ''

            questions.append(BenchmarkQuestion(
                benchmark=self.benchmark,
                question_id=qid,
                question=item['question'],
                choice_a=choice_a,
                choice_b=choice_b,
                choice_c=choice_c,
                choice_d=choice_d,
                correct_answer=correct_letter,
                subject=item['subject'],
                difficulty=item['grade'],
                context=context,
                image_paths=image_paths,
            ))
        return questions

    def format_prompt(self, question):
        choices = ''
        for letter, field in [('A', question.choice_a), ('B', question.choice_b),
                               ('C', question.choice_c), ('D', question.choice_d)]:
            if field:
                choices += f'({letter}) {field}\n'

        prompt = ''
        if question.context:
            prompt += f"Context: {question.context}\n\n"
        prompt += f"{question.question}\n\n{choices}\n"
        prompt += "Answer with a single letter."
        if question.image_paths:
            prompt = "Look at the image and answer the following question.\n\n" + prompt
        return prompt

    # evaluate_answer: inherited MCQ letter-matching evaluator
```

#### AI2D Loader (Priority 2)

```python
class AI2DLoader(BaseBenchmarkLoader):
    """AI2D -- lmms-lab/ai2d.
    MCQ, always 4 options, all questions have images.
    answer field is string index ("0"-"3")."""

    LETTERS = 'ABCD'

    def load_questions(self):
        from datasets import load_dataset
        import os
        from django.conf import settings

        ds = load_dataset('lmms-lab/ai2d', split='test')
        img_dir = os.path.join(settings.MEDIA_ROOT, 'benchmark_images', 'ai2d')
        os.makedirs(img_dir, exist_ok=True)
        questions = []

        for idx, item in enumerate(ds):
            qid = f"ai2d_{idx}"
            options = item['options']               # list[str], always 4
            correct_idx = int(item['answer'])       # "0"-"3" -> int
            correct_letter = self.LETTERS[correct_idx]

            # Save image (all questions have one)
            fname = f"{qid}.jpg"
            full_path = os.path.join(img_dir, fname)
            item['image'].save(full_path, 'JPEG')
            rel_path = os.path.join('benchmark_images', 'ai2d', fname)

            questions.append(BenchmarkQuestion(
                benchmark=self.benchmark,
                question_id=qid,
                question=item['question'],
                choice_a=options[0],
                choice_b=options[1],
                choice_c=options[2],
                choice_d=options[3],
                correct_answer=correct_letter,
                image_paths=[rel_path],
            ))
        return questions

    def format_prompt(self, question):
        return (
            f"Look at the diagram and answer the following question.\n\n"
            f"{question.question}\n\n"
            f"(A) {question.choice_a}\n"
            f"(B) {question.choice_b}\n"
            f"(C) {question.choice_c}\n"
            f"(D) {question.choice_d}\n\n"
            f"Answer with a single letter: A, B, C, or D."
        )
```

#### MMMU Loader (Priority 3 -- multi-image, multi-config)

```python
class MMMULoader(BaseBenchmarkLoader):
    """MMMU -- MMMU/MMMU.
    30 separate configs (subjects). Up to 7 images per question.
    options is a STRINGIFIED Python list -- must use ast.literal_eval().
    question_type is "multiple-choice" or "open"."""

    SUBJECTS = [
        'Accounting', 'Agriculture', 'Architecture_and_Engineering',
        'Art', 'Art_Theory', 'Basic_Medical_Science', 'Biology',
        'Chemistry', 'Clinical_Medicine', 'Computer_Science', 'Design',
        'Diagnostics_and_Laboratory_Medicine', 'Economics', 'Electronics',
        'Energy_and_Power', 'Finance', 'Geography', 'History',
        'Literature', 'Manage', 'Marketing', 'Materials',
        'Math', 'Mechanical_Engineering', 'Music',
        'Pharmacy', 'Physics', 'Psychology', 'Public_Health', 'Sociology',
    ]

    def load_questions(self):
        from datasets import load_dataset
        import ast, os
        from django.conf import settings

        img_dir = os.path.join(settings.MEDIA_ROOT, 'benchmark_images', 'mmmu')
        os.makedirs(img_dir, exist_ok=True)
        questions = []

        for subject in self.SUBJECTS:
            try:
                ds = load_dataset('MMMU/MMMU', name=subject, split='validation',
                                  trust_remote_code=True)
            except Exception:
                continue

            for item in ds:
                qid = item['id']  # e.g. "validation_Chemistry_1"
                question_type = item['question_type']  # "multiple-choice" or "open"

                # Parse options (stringified Python list)
                try:
                    options = ast.literal_eval(item['options'])
                except (ValueError, SyntaxError):
                    options = []

                # Map to choice_a/b/c/d (MCQ only)
                choice_a = options[0] if len(options) > 0 else None
                choice_b = options[1] if len(options) > 1 else None
                choice_c = options[2] if len(options) > 2 else None
                choice_d = options[3] if len(options) > 3 else None

                # Save all images (up to 7)
                image_paths = []
                for img_idx in range(1, 8):
                    img_key = f'image_{img_idx}'
                    img = item.get(img_key)
                    if img is not None:
                        fname = f"{qid}_img{img_idx}.jpg"
                        full_path = os.path.join(img_dir, fname)
                        img.save(full_path, 'JPEG')
                        image_paths.append(
                            os.path.join('benchmark_images', 'mmmu', fname)
                        )

                questions.append(BenchmarkQuestion(
                    benchmark=self.benchmark,
                    question_id=qid,
                    question=item['question'],
                    choice_a=choice_a,
                    choice_b=choice_b,
                    choice_c=choice_c,
                    choice_d=choice_d,
                    correct_answer=item['answer'],
                    subject=subject,
                    difficulty=item.get('topic_difficulty', ''),
                    image_paths=image_paths,
                    metadata={
                        'question_type': question_type,
                        'subfield': item.get('subfield', ''),
                        'img_type': item.get('img_type', ''),
                    },
                ))
        return questions

    def format_prompt(self, question):
        # Replace <image N> placeholders with generic reference
        text = question.question
        for i in range(1, 8):
            text = text.replace(f'<image {i}>', f'[Image {i}]')

        prompt = f"{text}\n\n"
        qtype = question.metadata.get('question_type', 'multiple-choice')
        if qtype == 'multiple-choice':
            for letter, field in [('A', question.choice_a), ('B', question.choice_b),
                                   ('C', question.choice_c), ('D', question.choice_d)]:
                if field:
                    prompt += f'({letter}) {field}\n'
            prompt += '\nAnswer with a single letter.'
        else:
            prompt += 'Give a short, precise answer.'
        return prompt

    def evaluate_answer(self, question, model_response):
        qtype = question.metadata.get('question_type', 'multiple-choice')
        if qtype == 'multiple-choice':
            # Use standard MCQ evaluator (letter matching)
            import re
            match = re.search(r'\b([A-D])\b', model_response.strip().upper())
            if match:
                parsed = match.group(1)
                return parsed == question.correct_answer.upper(), parsed
            return False, model_response[:50]
        else:
            # Open-ended: normalized string comparison
            expected = question.correct_answer.strip().lower()
            actual = model_response.strip().lower()
            return expected == actual, actual[:100]
```

#### MMBench Loader (Priority 4 -- base64 image, not PIL)

```python
class MMBenchLoader(BaseBenchmarkLoader):
    """MMBench -- HuggingFaceM4/MMBench.
    MCQ with A/B/C/D columns. image is already a base64 string.
    C and D can be null."""

    def load_questions(self):
        from datasets import load_dataset
        import os, base64
        from django.conf import settings

        ds = load_dataset('HuggingFaceM4/MMBench', split='validation')
        img_dir = os.path.join(settings.MEDIA_ROOT, 'benchmark_images', 'mmbench')
        os.makedirs(img_dir, exist_ok=True)
        questions = []

        for item in ds:
            qid = f"mmbench_{item['index']}"

            # image field is base64 string -- decode and save to file
            image_paths = []
            if item['image']:
                fname = f"{qid}.jpg"
                full_path = os.path.join(img_dir, fname)
                with open(full_path, 'wb') as f:
                    f.write(base64.b64decode(item['image']))
                image_paths = [os.path.join('benchmark_images', 'mmbench', fname)]

            questions.append(BenchmarkQuestion(
                benchmark=self.benchmark,
                question_id=qid,
                question=item['question'],
                choice_a=item.get('A'),
                choice_b=item.get('B'),
                choice_c=item.get('C'),     # can be None
                choice_d=item.get('D'),     # can be None
                correct_answer=item['answer'],  # letter "A"-"D"
                subject=item.get('category', ''),
                context=item.get('hint', ''),
                image_paths=image_paths,
            ))
        return questions

    def format_prompt(self, question):
        prompt = ''
        if question.context:
            prompt += f"Hint: {question.context}\n\n"
        prompt += f"{question.question}\n\n"
        for letter, field in [('A', question.choice_a), ('B', question.choice_b),
                               ('C', question.choice_c), ('D', question.choice_d)]:
            if field:
                prompt += f'({letter}) {field}\n'
        prompt += '\nAnswer with a single letter.'
        return prompt
```

#### ChartQA Loader (Priority 5 -- open-ended)

```python
class ChartQALoader(BaseBenchmarkLoader):
    """ChartQA -- HuggingFaceM4/ChartQA.
    Open-ended. Question field is "query". Answer field is "label" (list[str])."""

    def load_questions(self):
        from datasets import load_dataset
        import os
        from django.conf import settings

        ds = load_dataset('HuggingFaceM4/ChartQA', split='test')
        img_dir = os.path.join(settings.MEDIA_ROOT, 'benchmark_images', 'chartqa')
        os.makedirs(img_dir, exist_ok=True)
        questions = []

        for idx, item in enumerate(ds):
            qid = f"chartqa_{idx}"
            # label is list[str], typically length 1
            correct = item['label'][0] if item['label'] else ''

            # Save image
            fname = f"{qid}.jpg"
            full_path = os.path.join(img_dir, fname)
            item['image'].save(full_path, 'JPEG')
            rel_path = os.path.join('benchmark_images', 'chartqa', fname)

            questions.append(BenchmarkQuestion(
                benchmark=self.benchmark,
                question_id=qid,
                question=item['query'],     # NOT "question"!
                correct_answer=correct,
                image_paths=[rel_path],
                metadata={'source': item.get('human_or_machine', '')},
            ))
        return questions

    def format_prompt(self, question):
        return (
            f"Look at the chart and answer the following question.\n\n"
            f"{question.question}\n\n"
            f"Give a short, precise answer."
        )

    def evaluate_answer(self, question, model_response):
        # Relaxed match for ChartQA (standard practice)
        expected = question.correct_answer.strip().lower()
        actual = model_response.strip().lower()
        # Exact match or contained match
        is_correct = (expected == actual) or (expected in actual and len(expected) > 2)
        return is_correct, actual[:100]
```

---

## Phase 2: Agentic Benchmarks

### Target Benchmarks (verified)

| # | Benchmark | HF Hub Slug | Scope | Questions (usable) |
|---|-----------|-------------|-------|--------------------|
| 1 | GAIA (text-only) | `gaia-benchmark/GAIA` (gated) | Skip file-attachment questions | ~127 of 165 validation (77%) |
| 2 | BFCL (simple only) | `gorilla-llm/Berkeley-Function-Calling-Leaderboard` | `BFCL_v3_simple.json` only | ~400 |

### Verified Dataset Schemas

#### GAIA (`gaia-benchmark/GAIA`)
```
Config: "2023_all", split: "validation" (165 questions, answers public)
Fields (MIXED CASING!):
  task_id (str, UUID)
  Question (str, capital Q!)
  Level (str: "1"|"2"|"3", capital L!)
  Final answer (str, two words with space!)
  file_name (str, empty "" if no attachment)
  file_path (str, empty "" if no attachment)
  Annotator Metadata (dict with Steps, Tools, etc.)
Notes: GATED dataset -- requires HF token + terms acceptance.
       ~77% of validation questions have no file attachment.
       Skip rows with task_id == "0-0-0-0-0" (sentinel rows).
```

#### BFCL (`gorilla-llm/Berkeley-Function-Calling-Leaderboard`)
```
NOT a standard HF dataset! Raw JSONL files in a repo.
Must use hf_hub_download() to get individual files.

BFCL_v3_simple.json entry structure:
  id (str: "simple_0")
  question (list[list[dict]]): [[{"role":"user","content":"..."}]]
    --> Access prompt: item["question"][0][0]["content"]
  function (list[dict]): OpenAI-style schemas with "type":"dict" (not "object")

Ground truth in separate file: possible_answer/BFCL_v3_simple.json
  id (str: "simple_0")
  ground_truth (list[dict]): [{"func_name": {"param": [acceptable_values]}}]
    --> Values are always lists of acceptable alternatives
    --> [""] in value list means parameter is optional
```

### GAIA Loader

```python
class GAIALoader(BaseBenchmarkLoader):
    """GAIA text-only -- gaia-benchmark/GAIA (gated).
    Uses validation split only (test answers are hidden).
    Skips questions with file attachments."""

    def load_questions(self):
        from datasets import load_dataset

        ds = load_dataset('gaia-benchmark/GAIA', '2023_all', split='validation',
                          trust_remote_code=True)
        questions = []
        for item in ds:
            # Skip sentinel rows
            if item['task_id'] == '0-0-0-0-0':
                continue
            # Skip questions requiring file attachments
            if item['file_name']:
                continue

            questions.append(BenchmarkQuestion(
                benchmark=self.benchmark,
                question_id=item['task_id'],
                question=item['Question'],           # capital Q
                correct_answer=item['Final answer'],  # two words with space
                difficulty=item['Level'],             # capital L, str "1"/"2"/"3"
                subject='multi-step reasoning',
            ))
        return questions

    def format_prompt(self, question):
        return (
            f"{question.question}\n\n"
            f"Give a direct, concise answer. Do not explain your reasoning."
        )

    def evaluate_answer(self, question, model_response):
        # Normalized string comparison (GAIA standard)
        expected = question.correct_answer.strip().lower()
        actual = model_response.strip().lower()
        # Remove trailing punctuation for comparison
        import re
        expected_clean = re.sub(r'[.,;:!?]+$', '', expected).strip()
        actual_clean = re.sub(r'[.,;:!?]+$', '', actual).strip()
        is_correct = expected_clean == actual_clean
        return is_correct, actual_clean[:200]
```

### BFCL Simple Loader

```python
class BFCLSimpleLoader(BaseBenchmarkLoader):
    """BFCL Simple -- gorilla-llm/Berkeley-Function-Calling-Leaderboard.
    Only loads BFCL_v3_simple.json (single function call, Python).
    NOT a standard HF dataset -- must download JSONL files manually."""

    def load_questions(self):
        from huggingface_hub import hf_hub_download
        import json

        repo = 'gorilla-llm/Berkeley-Function-Calling-Leaderboard'

        # Download question file
        q_path = hf_hub_download(repo_id=repo, filename='BFCL_v3_simple.json',
                                  repo_type='dataset')
        with open(q_path) as f:
            q_data = [json.loads(line) for line in f]

        # Download ground truth file
        gt_path = hf_hub_download(repo_id=repo,
                                   filename='possible_answer/BFCL_v3_simple.json',
                                   repo_type='dataset')
        with open(gt_path) as f:
            gt_data = {json.loads(line)['id']: json.loads(line)['ground_truth']
                       for line in f}

        questions = []
        for item in q_data:
            qid = item['id']
            # Extract user prompt: question[0][0]["content"]
            user_prompt = item['question'][0][0]['content']
            # Function schemas
            func_schemas = json.dumps(item['function'], indent=2)
            # Ground truth
            gt = gt_data.get(qid, [])
            correct_answer = json.dumps(gt)

            questions.append(BenchmarkQuestion(
                benchmark=self.benchmark,
                question_id=qid,
                question=user_prompt,
                context=func_schemas,       # function schemas as context
                correct_answer=correct_answer,
                subject='function-calling',
            ))
        return questions

    def format_prompt(self, question):
        return (
            f"You have access to the following functions:\n\n"
            f"{question.context}\n\n"
            f"Based on the user request below, call the appropriate function. "
            f"Respond with a Python function call (e.g., func_name(arg1=val1, arg2=val2)).\n\n"
            f"User request: {question.question}"
        )

    def evaluate_answer(self, question, model_response):
        """Evaluate function call against BFCL ground truth.
        Ground truth format: [{"func_name": {"param": [acceptable_values]}}]"""
        import json, re

        try:
            gt_list = json.loads(question.correct_answer)
        except json.JSONDecodeError:
            return False, model_response[:100]

        if not gt_list:
            return False, model_response[:100]

        gt = gt_list[0]  # Simple: always 1 function call
        expected_func = list(gt.keys())[0]
        expected_params = gt[expected_func]

        # Extract function name from response
        # Match patterns: func_name(args) or func_name (args)
        match = re.search(r'(\w+(?:\.\w+)*)\s*\(', model_response)
        if not match:
            return False, model_response[:100]

        called_func = match.group(1)
        # Check function name
        if called_func != expected_func:
            return False, f"called {called_func}, expected {expected_func}"

        # Check that required parameters are mentioned
        required_params = [k for k, v in expected_params.items()
                           if '' not in v]  # "" means optional
        response_lower = model_response.lower()
        params_present = all(p.lower() in response_lower for p in required_params)

        return params_present, called_func
```

### Full Agentic Execution (deferred -- Phase 2b)

Multi-turn agentic evaluation (SWE-bench, WebArena) requires:
- New `AgentRunner` class with episode loop (action -> observation -> repeat)
- Tool registry with sandboxed execution (Docker/Podman)
- Task success rate metric instead of accuracy

This is a separate engineering project, not an extension of the current runner.

---

## Phase 3: Audio Benchmarks

### Target Benchmarks (verified)

| # | Benchmark | HF Hub Slug | Config | Test Split | Audio Format |
|---|-----------|-------------|--------|------------|--------------|
| 1 | LibriSpeech | `openslr/librispeech_asr` | `clean` | 2,620 | 16 kHz WAV |
| 2 | FLEURS | `google/fleurs` | per-language (e.g. `en_us`) | ~264/lang | varies |

### Verified Dataset Schemas

#### LibriSpeech (`openslr/librispeech_asr`)
```
Config: "clean" (or "other", "all")
Splits: train.100, train.360, validation (2,703), test (2,620)
Fields:
  file (str, path)
  audio (dict: {path: str, array: float[], sampling_rate: 16000})
  text (str, transcription -- UPPERCASE)
  speaker_id (int)
  chapter_id (int)
  id (str, unique sample ID)
```

#### FLEURS (`google/fleurs`)
```
102 language configs (e.g. "en_us", "fr_fr", "cmn_hans_cn")
Fields:
  id (int)
  audio (dict: {path: str, array: float[], sampling_rate: int})
  transcription (str, normalized)
  raw_transcription (str, original)
  gender (int)
  speaker_id (int)
  language (str, e.g. "English")
  lang_id (int)
  lang_group_id (int)
  num_samples (int)
  path (str)
```

### Architecture Changes

#### 1. Evaluation metric: WER

The binary `is_correct` interface stays. WER is stored in `parsed_answer` as `"WER=0.042"` and in `metadata` for programmatic access:

```python
def evaluate_answer(self, question, model_response):
    from jiwer import wer
    score = wer(question.correct_answer, model_response.strip().lower())
    is_correct = score < 0.1  # 10% WER threshold
    return is_correct, f"WER={score:.4f}"
```

For aggregate metrics, `RunResult.parsed_answer` values starting with `"WER="` can be extracted and averaged in the results view.

#### 2. Provider support for audio

Only 2 providers support native audio input:
- **Gemini**: 1.5 Pro, 2.0 Flash -- pass audio bytes as content part
- **OpenAI**: gpt-4o-audio-preview -- pass audio as input_audio content block

For the MVP, use **pipeline ASR**: Whisper API transcribes the audio first, then the transcription is evaluated. This decouples audio loading from provider capability.

#### 3. LibriSpeech Loader

```python
class LibriSpeechLoader(BaseBenchmarkLoader):
    """LibriSpeech -- openslr/librispeech_asr, config 'clean', split 'test'."""

    def load_questions(self):
        from datasets import load_dataset
        import os, soundfile as sf
        from django.conf import settings

        ds = load_dataset('openslr/librispeech_asr', 'clean', split='test')
        audio_dir = os.path.join(settings.MEDIA_ROOT, 'benchmark_audio', 'librispeech')
        os.makedirs(audio_dir, exist_ok=True)
        questions = []

        for item in ds:
            qid = item['id']
            fname = f"{qid}.wav"
            full_path = os.path.join(audio_dir, fname)
            sf.write(full_path, item['audio']['array'],
                     item['audio']['sampling_rate'])
            rel_path = os.path.join('benchmark_audio', 'librispeech', fname)

            questions.append(BenchmarkQuestion(
                benchmark=self.benchmark,
                question_id=qid,
                question='Transcribe the following audio clip.',
                correct_answer=item['text'].lower(),  # text is UPPERCASE in dataset
                audio_path=rel_path,
                subject=str(item['speaker_id']),
            ))
        return questions

    def evaluate_answer(self, question, model_response):
        from jiwer import wer
        ref = question.correct_answer.strip().lower()
        hyp = model_response.strip().lower()
        if not hyp:
            return False, 'WER=1.0000'
        score = wer(ref, hyp)
        return score < 0.1, f'WER={score:.4f}'
```

### New dependencies (Phase 3 only)

```
jiwer>=3.0        # WER computation
soundfile>=0.12   # Audio file I/O (WAV read/write)
```

---

## Summary: All Changes by File

### Database migration (`0006_add_multimodal_support.py`)

| Model | Field | Type | Default |
|-------|-------|------|---------|
| `Benchmark` | `benchmark_type` | `CharField(max_length=20)` | `'text'` |
| `Benchmark` | new `CATEGORY_CHOICES` | 3 new entries | -- |
| `BenchmarkQuestion` | `image_paths` | `JSONField` | `[]` |
| `BenchmarkQuestion` | `audio_path` | `CharField(max_length=500)` | `''` |

### Files to modify

| File | Phase | Change |
|------|-------|--------|
| `apps/benchmarks/models.py` | 1 | Add `benchmark_type`, `image_paths`, `audio_path`, new categories |
| `apps/providers/backends/base.py` | 1 | Add `images=None` to `complete()` |
| `apps/providers/backends/openai_backend.py` | 1 | Handle `images` with content blocks |
| `apps/providers/backends/anthropic_backend.py` | 1 | Handle `images` with content blocks |
| `apps/providers/backends/gemini_backend.py` | 1 | Handle `images` with PIL parts |
| `apps/providers/backends/ollama.py` | 1 | Add `images=None` (ignore) |
| `apps/providers/backends/vllm.py` | 1 | Add `images=None` (ignore) |
| `apps/providers/backends/cohere_backend.py` | 1 | Add `images=None` (ignore) |
| `apps/providers/backends/mistral_backend.py` | 1 | Add `images=None` (ignore) |
| `apps/providers/backends/groq_backend.py` | 1 | Add `images=None` (ignore) |
| `apps/benchmarks/registry.py` | 1-3 | Add `get_images_b64()` to base; add 8 new loaders |
| `apps/runs/runner.py` | 1 | Pass images from loader to backend |
| `settings.py` | 1 | Add `MEDIA_ROOT`, `MEDIA_URL` |

### New loader classes (in `registry.py`)

| Loader | Phase | Benchmark |
|--------|-------|-----------|
| `ScienceQAVisionLoader` | 1 | ScienceQA |
| `AI2DLoader` | 1 | AI2D |
| `MMMULoader` | 1 | MMMU |
| `MMBenchLoader` | 1 | MMBench |
| `ChartQALoader` | 1 | ChartQA |
| `GAIALoader` | 2 | GAIA (text-only) |
| `BFCLSimpleLoader` | 2 | BFCL (simple) |
| `LibriSpeechLoader` | 3 | LibriSpeech |

### New dependencies

| Package | Phase | Required by |
|---------|-------|-------------|
| `Pillow>=10.0` | 1 | Vision loaders (image save/encode) |
| `huggingface_hub>=0.20` | 2 | BFCL file download |
| `jiwer>=3.0` | 3 | WER computation |
| `soundfile>=0.12` | 3 | LibriSpeech audio save |

### Implementation sequence

```
Phase 1a  Migration + MEDIA_ROOT + base.py complete(images=)
Phase 1b  OpenAI/Anthropic/Gemini vision backends
Phase 1c  BaseBenchmarkLoader.get_images_b64() + runner wiring
Phase 1d  ScienceQA + AI2D loaders (single-image MCQ)
Phase 1e  MMMU loader (multi-image, multi-config)
Phase 1f  MMBench + ChartQA loaders
-------------------------------------------------------------
Phase 2a  GAIA text-only loader
Phase 2b  BFCL simple loader + function-call evaluator
-------------------------------------------------------------
Phase 3a  audio_path field (already in migration)
Phase 3b  LibriSpeech loader + WER evaluator + soundfile/jiwer deps
```
