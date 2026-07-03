import re
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Open-ended answer evaluation helpers
# ---------------------------------------------------------------------------

def _extract_math_answer(response: str) -> str:
    """
    Extract the final numerical/mathematical answer from a model response.

    Tries in order:
    1. LaTeX \\boxed{...} — most common in competition math datasets.
    2. "= <answer>" at the end of the response (e.g. "... = 42").
    3. "Answer: <answer>" / "The answer is <answer>" patterns.
    4. The last number-like token in the response as a last resort.
    """
    # 1. \boxed{...}  (possibly nested braces)
    m = re.search(r'\\boxed\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', response)
    if m:
        return m.group(1).strip()

    # 2. "= <value>" at end (last occurrence)
    m = re.findall(r'=\s*([-\d\s./%^√,a-zA-Z]+?)(?:\.|$|\n)', response)
    if m:
        return m[-1].strip()

    # 3. Explicit "answer is / answer:" patterns
    m = re.search(
        r'(?:the\s+)?answer\s+is[:\s]+([^\n.]+)',
        response, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()
    m = re.search(r'answer\s*:\s*([^\n.]+)', response, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # 4. Last number (int, float, fraction) in the response
    nums = re.findall(r'-?\d+(?:[.,]\d+)?(?:/\d+)?', response)
    if nums:
        return nums[-1].strip()

    return ''


def _normalize_math(s: str) -> str:
    """Strip LaTeX noise and normalise spacing for string comparison."""
    s = s.strip()
    # Remove surrounding $...$
    s = re.sub(r'^\$+|\$+$', '', s).strip()
    # Remove common LaTeX commands that add no semantic content
    s = re.sub(r'\\(?:left|right|cdot|times|approx|pm)', '', s)
    # Normalise \frac{a}{b} → a/b
    s = re.sub(r'\\frac\{([^{}]+)\}\{([^{}]+)\}', r'\1/\2', s)
    # Remove remaining backslashes and braces
    s = re.sub(r'[\\{}]', '', s)
    # Normalise whitespace and commas used as thousands separators
    s = s.replace(',', '').replace(' ', '')
    return s.lower()


def _try_numeric(s: str):
    """Try to parse s as a float. Returns float or None."""
    try:
        return float(s)
    except ValueError:
        pass
    # Handle fractions like 1/2
    m = re.match(r'^(-?\d+)\s*/\s*(\d+)$', s.strip())
    if m and int(m.group(2)) != 0:
        return int(m.group(1)) / int(m.group(2))
    # Handle percentages like 75%
    m = re.match(r'^(-?\d+(?:\.\d+)?)\s*%$', s.strip())
    if m:
        return float(m.group(1)) / 100
    return None


def _math_answers_equal(correct: str, response: str) -> bool:
    """
    Return True if correct and response represent the same mathematical value.
    Tries numeric comparison first, then normalised string equality.
    """
    c_norm = _normalize_math(correct)
    r_norm = _normalize_math(response)

    # Exact match after normalisation
    if c_norm == r_norm:
        return True

    # Numeric equivalence (e.g. 1/2 == 0.5, 75% == 0.75)
    c_num = _try_numeric(c_norm)
    r_num = _try_numeric(r_norm)
    if c_num is not None and r_num is not None:
        return abs(c_num - r_num) < 1e-6

    # Word-boundary containment as last resort (correct answer appears in response)
    if c_norm and re.search(r'\b' + re.escape(c_norm) + r'\b', r_norm):
        return True

    return False


# ---------------------------------------------------------------------------
# TriviaQA answer evaluation helpers
# ---------------------------------------------------------------------------

def _normalize_trivia(s: str) -> str:
    """Lowercase and strip punctuation for trivia answer comparison."""
    s = s.lower()
    s = re.sub(r"[^\w\s]", ' ', s)   # replace punctuation with space
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _trivia_answers_match(norm_response: str, norm_answer: str) -> bool:
    """
    Return True if norm_answer appears as a whole phrase in norm_response,
    using word boundaries to prevent 'paris' matching 'comparison'.
    """
    if not norm_answer:
        return False
    pattern = r'\b' + re.escape(norm_answer) + r'\b'
    return bool(re.search(pattern, norm_response))


class BaseBenchmarkLoader(ABC):
    slug = ''
    name = ''
    description = ''
    category = 'knowledge'

    @abstractmethod
    def load_questions(self):
        """
        Returns a list of dicts with keys:
        question_id, question, choice_a, choice_b, choice_c, choice_d,
        correct_answer, subject, difficulty, metadata
        """
        raise NotImplementedError

    def format_prompt(self, question_obj):
        """Returns formatted prompt string for the model."""
        prompt = f"Question: {question_obj.question}\n"
        if question_obj.choice_a:
            prompt += f"A) {question_obj.choice_a}\n"
        if question_obj.choice_b:
            prompt += f"B) {question_obj.choice_b}\n"
        if question_obj.choice_c:
            prompt += f"C) {question_obj.choice_c}\n"
        if question_obj.choice_d:
            prompt += f"D) {question_obj.choice_d}\n"
        prompt += "Answer:"
        return prompt

    def evaluate_answer(self, question_obj, model_response):
        """Returns (is_correct: bool, parsed_answer: str)"""
        response = model_response.strip().upper()
        # Extract first letter answer
        match = re.search(r'\b([A-E])\b', response)
        if match:
            parsed = match.group(1)
        elif response and response[0] in 'ABCDE':
            parsed = response[0]
        else:
            parsed = response[:1] if response else ''
        is_correct = parsed == question_obj.correct_answer.strip().upper()
        return is_correct, parsed

    def get_images_b64(self, question_obj):
        """Return list of base64-encoded image strings for this question.
        Default implementation reads from question_obj.image_paths field."""
        paths = getattr(question_obj, 'image_paths', None) or []
        if not paths:
            return []
        import base64
        import os
        from django.conf import settings
        result = []
        for rel_path in paths:
            full = os.path.join(settings.MEDIA_ROOT, rel_path)
            try:
                with open(full, 'rb') as f:
                    result.append(base64.b64encode(f.read()).decode('ascii'))
            except OSError:
                logger.warning(f"Could not read image: {full}")
        return result

    def get_audio_b64(self, question_obj):
        """Return {'data': <b64>, 'format': <ext>} for this question's audio clip,
        or None if the question has no audio.
        Default implementation reads from question_obj.audio_path field."""
        rel_path = getattr(question_obj, 'audio_path', '') or ''
        if not rel_path:
            return None
        import base64
        import os
        from django.conf import settings
        full = os.path.join(settings.MEDIA_ROOT, rel_path)
        try:
            with open(full, 'rb') as f:
                data = base64.b64encode(f.read()).decode('ascii')
        except OSError:
            logger.warning(f"Could not read audio: {full}")
            return None
        ext = os.path.splitext(rel_path)[1].lstrip('.').lower() or 'wav'
        return {'data': data, 'format': ext}


class MMLULoader(BaseBenchmarkLoader):
    slug = 'mmlu'
    name = 'MMLU (Massive Multitask Language Understanding)'
    description = 'A benchmark with 57 tasks including STEM, humanities, social sciences, and more.'
    category = 'knowledge'

    def load_questions(self):
        from datasets import load_dataset
        ds = load_dataset("cais/mmlu", "all", split="test")
        questions = []
        answer_map = {0: 'A', 1: 'B', 2: 'C', 3: 'D'}
        for i, item in enumerate(ds):
            choices = item.get('choices', [])
            questions.append({
                'question_id': str(i),
                'question': item['question'],
                'choice_a': choices[0] if len(choices) > 0 else None,
                'choice_b': choices[1] if len(choices) > 1 else None,
                'choice_c': choices[2] if len(choices) > 2 else None,
                'choice_d': choices[3] if len(choices) > 3 else None,
                'correct_answer': answer_map.get(item['answer'], 'A'),
                'subject': item.get('subject', ''),
                'difficulty': '',
                'metadata': {'original_answer': item['answer']},
            })
        return questions

    def format_prompt(self, question_obj):
        prompt = f"Question: {question_obj.question}\n"
        if question_obj.choice_a:
            prompt += f"A) {question_obj.choice_a}\n"
        if question_obj.choice_b:
            prompt += f"B) {question_obj.choice_b}\n"
        if question_obj.choice_c:
            prompt += f"C) {question_obj.choice_c}\n"
        if question_obj.choice_d:
            prompt += f"D) {question_obj.choice_d}\n"
        prompt += "Answer:"
        return prompt


class ARCChallengeLoader(BaseBenchmarkLoader):
    slug = 'arc_challenge'
    name = 'ARC Challenge'
    description = 'AI2 Reasoning Challenge - Challenge set. Difficult science questions.'
    category = 'reasoning'

    def load_questions(self):
        from datasets import load_dataset
        ds = load_dataset("allenai/ai2_arc", "ARC-Challenge", split="test")
        return self._process_arc(ds)

    def _process_arc(self, ds):
        questions = []
        num_to_letter = {'1': 'A', '2': 'B', '3': 'C', '4': 'D'}
        for i, item in enumerate(ds):
            choices_labels = item['choices']['label']
            choices_texts = item['choices']['text']
            choice_map = {}
            for label, text in zip(choices_labels, choices_texts):
                normalized = num_to_letter.get(label, label.upper())
                choice_map[normalized] = text

            answer_key = item['answerKey']
            correct = num_to_letter.get(answer_key, answer_key.upper())

            questions.append({
                'question_id': item.get('id', str(i)),
                'question': item['question'],
                'choice_a': choice_map.get('A'),
                'choice_b': choice_map.get('B'),
                'choice_c': choice_map.get('C'),
                'choice_d': choice_map.get('D'),
                'correct_answer': correct,
                'subject': '',
                'difficulty': '',
                'metadata': {'original_answer_key': answer_key},
            })
        return questions


class ARCEasyLoader(ARCChallengeLoader):
    slug = 'arc_easy'
    name = 'ARC Easy'
    description = 'AI2 Reasoning Challenge - Easy set. Grade school science questions.'
    category = 'reasoning'

    def load_questions(self):
        from datasets import load_dataset
        ds = load_dataset("allenai/ai2_arc", "ARC-Easy", split="test")
        return self._process_arc(ds)


class HellaSwagLoader(BaseBenchmarkLoader):
    slug = 'hellaswag'
    name = 'HellaSwag'
    description = 'Can a Machine Really Finish Your Sentence? Commonsense NLI benchmark.'
    category = 'common_sense'

    def load_questions(self):
        from datasets import load_dataset
        ds = load_dataset("Rowan/hellaswag", split="validation")
        questions = []
        answer_map = {'0': 'A', '1': 'B', '2': 'C', '3': 'D', 0: 'A', 1: 'B', 2: 'C', 3: 'D'}
        for i, item in enumerate(ds):
            endings = item.get('endings', [])
            questions.append({
                'question_id': item.get('ind', str(i)),
                'question': f"{item.get('activity_label', '')}: {item.get('ctx', '')}",
                'choice_a': endings[0] if len(endings) > 0 else None,
                'choice_b': endings[1] if len(endings) > 1 else None,
                'choice_c': endings[2] if len(endings) > 2 else None,
                'choice_d': endings[3] if len(endings) > 3 else None,
                'correct_answer': answer_map.get(item['label'], 'A'),
                'subject': item.get('activity_label', ''),
                'difficulty': '',
                'metadata': {'source_id': item.get('source_id', '')},
            })
        return questions


class TruthfulQALoader(BaseBenchmarkLoader):
    slug = 'truthfulqa'
    name = 'TruthfulQA'
    description = 'Benchmark for measuring whether LLMs are truthful in their answers.'
    category = 'knowledge'

    def load_questions(self):
        from datasets import load_dataset
        ds = load_dataset("truthful_qa", "multiple_choice", split="validation")
        questions = []
        for i, item in enumerate(ds):
            mc1 = item.get('mc1_targets', {})
            mc_choices = mc1.get('choices', [])
            mc_labels = mc1.get('labels', [])

            # Find the correct answer (label=1 is the correct one, it's at index 0)
            correct_idx = 0
            for idx, label in enumerate(mc_labels):
                if label == 1:
                    correct_idx = idx
                    break

            answer_map = {0: 'A', 1: 'B', 2: 'C', 3: 'D'}
            correct_letter = answer_map.get(correct_idx, 'A')

            questions.append({
                'question_id': str(i),
                'question': item['question'],
                'choice_a': mc_choices[0] if len(mc_choices) > 0 else None,
                'choice_b': mc_choices[1] if len(mc_choices) > 1 else None,
                'choice_c': mc_choices[2] if len(mc_choices) > 2 else None,
                'choice_d': mc_choices[3] if len(mc_choices) > 3 else None,
                'correct_answer': correct_letter,
                'subject': item.get('category', ''),
                'difficulty': '',
                'metadata': {'all_choices': mc_choices},
            })
        return questions


class WinoGrandeLoader(BaseBenchmarkLoader):
    slug = 'winogrande'
    name = 'WinoGrande'
    description = 'Large-scale Winograd schema challenge for commonsense reasoning.'
    category = 'common_sense'

    def load_questions(self):
        from datasets import load_dataset
        ds = load_dataset("winogrande", "winogrande_xl", split="validation", trust_remote_code=True)
        questions = []
        for i, item in enumerate(ds):
            answer_str = str(item.get('answer', '1'))
            correct = 'A' if answer_str == '1' else 'B'
            questions.append({
                'question_id': item.get('qID', str(i)),
                'question': item['sentence'],
                'choice_a': item.get('option1', ''),
                'choice_b': item.get('option2', ''),
                'choice_c': None,
                'choice_d': None,
                'correct_answer': correct,
                'subject': '',
                'difficulty': '',
                'metadata': {'original_answer': item.get('answer', '')},
            })
        return questions

    def format_prompt(self, question_obj):
        return (
            f"Complete the sentence by choosing the correct option:\n"
            f"{question_obj.question}\n"
            f"A) {question_obj.choice_a}\n"
            f"B) {question_obj.choice_b}\n"
            f"Answer:"
        )


class GSM8KLoader(BaseBenchmarkLoader):
    slug = 'gsm8k'
    name = 'GSM8K'
    description = 'Grade school math word problems requiring multi-step reasoning.'
    category = 'math'

    def load_questions(self):
        from datasets import load_dataset
        ds = load_dataset("openai/gsm8k", "main", split="test")
        questions = []
        for i, item in enumerate(ds):
            answer_text = item['answer']
            # Extract final numeric answer (after ####)
            final_answer = ''
            if '####' in answer_text:
                final_answer = answer_text.split('####')[-1].strip()
                final_answer = re.sub(r'[^0-9\.\-,]', '', final_answer).replace(',', '')
            questions.append({
                'question_id': str(i),
                'question': item['question'],
                'choice_a': None,
                'choice_b': None,
                'choice_c': None,
                'choice_d': None,
                'correct_answer': final_answer,
                'subject': 'math',
                'difficulty': '',
                'metadata': {'full_answer': answer_text},
            })
        return questions

    def format_prompt(self, question_obj):
        return f"Solve step by step:\n{question_obj.question}\nAnswer:"

    def evaluate_answer(self, question_obj, model_response):
        response = model_response.strip()
        # Extract the last number from the response
        numbers = re.findall(r'-?[\d,]+(?:\.\d+)?', response.replace(',', ''))
        if numbers:
            parsed = numbers[-1].replace(',', '')
        else:
            parsed = ''

        correct = question_obj.correct_answer.strip().replace(',', '')
        try:
            is_correct = abs(float(parsed) - float(correct)) < 0.01
        except (ValueError, TypeError):
            is_correct = parsed == correct

        return is_correct, parsed


class CommonsenseQALoader(BaseBenchmarkLoader):
    slug = 'commonsenseqa'
    name = 'CommonsenseQA'
    description = 'Commonsense question answering with 5 choices per question.'
    category = 'common_sense'

    def load_questions(self):
        from datasets import load_dataset
        ds = load_dataset("commonsense_qa", split="validation")
        questions = []
        for i, item in enumerate(ds):
            choices = item.get('choices', {})
            labels = choices.get('label', [])
            texts = choices.get('text', [])
            choice_map = dict(zip(labels, texts))

            questions.append({
                'question_id': item.get('id', str(i)),
                'question': item['question'],
                'choice_a': choice_map.get('A'),
                'choice_b': choice_map.get('B'),
                'choice_c': choice_map.get('C'),
                'choice_d': choice_map.get('D'),
                'correct_answer': item.get('answerKey', 'A').upper(),
                'subject': item.get('question_concept', ''),
                'difficulty': '',
                'metadata': {'choice_e': choice_map.get('E')},
            })
        return questions

    def format_prompt(self, question_obj):
        meta = question_obj.metadata or {}
        prompt = f"Question: {question_obj.question}\n"
        if question_obj.choice_a:
            prompt += f"A) {question_obj.choice_a}\n"
        if question_obj.choice_b:
            prompt += f"B) {question_obj.choice_b}\n"
        if question_obj.choice_c:
            prompt += f"C) {question_obj.choice_c}\n"
        if question_obj.choice_d:
            prompt += f"D) {question_obj.choice_d}\n"
        if meta.get('choice_e'):
            prompt += f"E) {meta['choice_e']}\n"
        prompt += "Answer:"
        return prompt


class BoolQLoader(BaseBenchmarkLoader):
    slug = 'boolq'
    name = 'BoolQ'
    description = 'Boolean question answering based on passages.'
    category = 'reasoning'

    def load_questions(self):
        from datasets import load_dataset
        ds = load_dataset("google/boolq", split="validation")
        questions = []
        for i, item in enumerate(ds):
            correct = 'True' if item['answer'] else 'False'
            questions.append({
                'question_id': str(i),
                'question': f"Passage: {item['passage']}\n\nQuestion: {item['question']}",
                'choice_a': 'True',
                'choice_b': 'False',
                'choice_c': None,
                'choice_d': None,
                'correct_answer': correct,
                'subject': '',
                'difficulty': '',
                'metadata': {'title': item.get('title', '')},
            })
        return questions

    def format_prompt(self, question_obj):
        return f"{question_obj.question}\nAnswer (True or False):"

    def evaluate_answer(self, question_obj, model_response):
        response = model_response.strip().lower()
        if 'true' in response:
            parsed = 'True'
        elif 'false' in response:
            parsed = 'False'
        else:
            parsed = response[:10]

        is_correct = parsed.lower() == question_obj.correct_answer.lower()
        return is_correct, parsed


class PIQALoader(BaseBenchmarkLoader):
    slug = 'piqa'
    name = 'PIQA'
    description = 'Physical Intuition QA - tests understanding of physical world interactions.'
    category = 'common_sense'

    def load_questions(self):
        from datasets import load_dataset
        ds = load_dataset("ybisk/piqa", split="validation", trust_remote_code=True)
        questions = []
        for i, item in enumerate(ds):
            label = item.get('label', 0)
            correct = 'A' if label == 0 else 'B'
            questions.append({
                'question_id': str(i),
                'question': item['goal'],
                'choice_a': item.get('sol1', ''),
                'choice_b': item.get('sol2', ''),
                'choice_c': None,
                'choice_d': None,
                'correct_answer': correct,
                'subject': '',
                'difficulty': '',
                'metadata': {'original_label': label},
            })
        return questions

    def format_prompt(self, question_obj):
        return (
            f"Goal: {question_obj.question}\n"
            f"Which solution achieves this goal?\n"
            f"A) {question_obj.choice_a}\n"
            f"B) {question_obj.choice_b}\n"
            f"Answer:"
        )


class OpenBookQALoader(BaseBenchmarkLoader):
    slug = 'openbookqa'
    name = 'OpenBookQA'
    description = 'Open book QA requiring elementary science knowledge.'
    category = 'knowledge'

    def load_questions(self):
        from datasets import load_dataset
        ds = load_dataset("allenai/openbookqa", split="test")
        questions = []
        for i, item in enumerate(ds):
            choices = item.get('choices', {})
            labels = choices.get('label', [])
            texts = choices.get('text', [])
            choice_map = dict(zip(labels, texts))
            questions.append({
                'question_id': item.get('id', str(i)),
                'question': item['question_stem'],
                'choice_a': choice_map.get('A'),
                'choice_b': choice_map.get('B'),
                'choice_c': choice_map.get('C'),
                'choice_d': choice_map.get('D'),
                'correct_answer': item.get('answerKey', 'A').upper(),
                'subject': '',
                'difficulty': '',
                'metadata': {'fact1': item.get('fact1', '')},
            })
        return questions


class MathQALoader(BaseBenchmarkLoader):
    slug = 'mathqa'
    name = 'MathQA'
    description = 'Math word problems with multiple choice answers (5 choices).'
    category = 'math'

    def load_questions(self):
        from datasets import load_dataset
        ds = load_dataset("allenai/math_qa", split="test", trust_remote_code=True)
        questions = []
        for i, item in enumerate(ds):
            options_str = item.get('options', '')
            # Options are formatted like: a ) text , b ) text , ...
            option_map = {}
            for opt in re.finditer(r'([a-e])\s*\)\s*([^,]+?)(?:\s*,\s*(?=[a-e]\s*\))|$)', options_str, re.IGNORECASE):
                letter = opt.group(1).upper()
                text = opt.group(2).strip()
                option_map[letter] = text

            correct = item.get('correct', 'a').upper()
            questions.append({
                'question_id': str(i),
                'question': item['Problem'],
                'choice_a': option_map.get('A'),
                'choice_b': option_map.get('B'),
                'choice_c': option_map.get('C'),
                'choice_d': option_map.get('D'),
                'correct_answer': correct,
                'subject': item.get('category', 'math'),
                'difficulty': '',
                'metadata': {'choice_e': option_map.get('E'), 'rationale': item.get('Rationale', '')},
            })
        return questions

    def format_prompt(self, question_obj):
        meta = question_obj.metadata or {}
        prompt = f"Math Problem: {question_obj.question}\n"
        if question_obj.choice_a:
            prompt += f"A) {question_obj.choice_a}\n"
        if question_obj.choice_b:
            prompt += f"B) {question_obj.choice_b}\n"
        if question_obj.choice_c:
            prompt += f"C) {question_obj.choice_c}\n"
        if question_obj.choice_d:
            prompt += f"D) {question_obj.choice_d}\n"
        if meta.get('choice_e'):
            prompt += f"E) {meta['choice_e']}\n"
        prompt += "Answer:"
        return prompt


class SocialIQALoader(BaseBenchmarkLoader):
    slug = 'social_iqa'
    name = 'Social IQA'
    description = 'Social interaction QA benchmark testing social and emotional intelligence.'
    category = 'reasoning'

    def load_questions(self):
        from datasets import load_dataset
        ds = load_dataset("allenai/social_i_qa", split="validation", trust_remote_code=True)
        questions = []
        answer_map = {'1': 'A', '2': 'B', '3': 'C'}
        for i, item in enumerate(ds):
            label = str(item.get('label', '1'))
            correct = answer_map.get(label, 'A')
            questions.append({
                'question_id': str(i),
                'question': f"Context: {item['context']}\nQuestion: {item['question']}",
                'choice_a': item.get('answerA', ''),
                'choice_b': item.get('answerB', ''),
                'choice_c': item.get('answerC', ''),
                'choice_d': None,
                'correct_answer': correct,
                'subject': '',
                'difficulty': '',
                'metadata': {},
            })
        return questions

    def format_prompt(self, question_obj):
        return (
            f"{question_obj.question}\n"
            f"A) {question_obj.choice_a}\n"
            f"B) {question_obj.choice_b}\n"
            f"C) {question_obj.choice_c}\n"
            f"Answer:"
        )


class ANLILoader(BaseBenchmarkLoader):
    slug = 'anli'
    name = 'ANLI (Adversarial NLI)'
    description = 'Natural language inference benchmark with adversarially collected examples.'
    category = 'reasoning'

    def load_questions(self):
        from datasets import load_dataset
        ds = load_dataset("facebook/anli", split="test_r1")
        questions = []
        label_map = {0: 'entailment', 1: 'neutral', 2: 'contradiction'}
        answer_map = {0: 'A', 1: 'B', 2: 'C'}
        for i, item in enumerate(ds):
            label = item.get('label', 0)
            questions.append({
                'question_id': item.get('uid', str(i)),
                'question': f"Premise: {item['premise']}\nHypothesis: {item['hypothesis']}\nWhat is the relationship?",
                'choice_a': 'Entailment',
                'choice_b': 'Neutral',
                'choice_c': 'Contradiction',
                'choice_d': None,
                'correct_answer': answer_map.get(label, 'A'),
                'subject': 'nli',
                'difficulty': 'adversarial',
                'metadata': {'original_label': label_map.get(label, 'unknown')},
            })
        return questions

    def format_prompt(self, question_obj):
        return (
            f"{question_obj.question}\n"
            f"A) Entailment\n"
            f"B) Neutral\n"
            f"C) Contradiction\n"
            f"Answer:"
        )


class LogiQALoader(BaseBenchmarkLoader):
    slug = 'logiqa'
    name = 'LogiQA'
    description = 'Logical reasoning QA dataset with 4-choice questions requiring multi-step logical inference.'
    category = 'reasoning'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset("lucasmccabe/logiqa", split="test", trust_remote_code=True)
            questions = []
            answer_map = {0: 'A', 1: 'B', 2: 'C', 3: 'D'}
            for i, item in enumerate(ds):
                options = item.get('options', [])
                correct_idx = item.get('correct_option', 0)
                questions.append({
                    'question_id': str(i),
                    'question': item.get('query', item.get('question', '')),
                    'choice_a': options[0] if len(options) > 0 else None,
                    'choice_b': options[1] if len(options) > 1 else None,
                    'choice_c': options[2] if len(options) > 2 else None,
                    'choice_d': options[3] if len(options) > 3 else None,
                    'correct_answer': answer_map.get(correct_idx, 'A'),
                    'subject': 'logic',
                    'difficulty': '',
                    'metadata': {'correct_option': correct_idx},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load LogiQA: {e}")
            return []


class RACELoader(BaseBenchmarkLoader):
    slug = 'race'
    name = 'RACE'
    description = 'Reading comprehension dataset from English exams for middle and high school students.'
    category = 'language'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset("ehovy/race", "all", split="test", trust_remote_code=True)
            questions = []
            for i, item in enumerate(ds):
                options = item.get('options', [])
                answer_letter = item.get('answer', 'A').upper()
                article = item.get('article', '')
                full_question = f"Read the passage:\n{article[:500]}\n\nQuestion: {item.get('question', '')}"
                questions.append({
                    'question_id': item.get('example_id', str(i)),
                    'question': full_question,
                    'choice_a': options[0] if len(options) > 0 else None,
                    'choice_b': options[1] if len(options) > 1 else None,
                    'choice_c': options[2] if len(options) > 2 else None,
                    'choice_d': options[3] if len(options) > 3 else None,
                    'correct_answer': answer_letter,
                    'subject': '',
                    'difficulty': '',
                    'metadata': {},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load RACE: {e}")
            return []

    def format_prompt(self, question_obj):
        prompt = f"{question_obj.question}\n"
        if question_obj.choice_a:
            prompt += f"A) {question_obj.choice_a}\n"
        if question_obj.choice_b:
            prompt += f"B) {question_obj.choice_b}\n"
        if question_obj.choice_c:
            prompt += f"C) {question_obj.choice_c}\n"
        if question_obj.choice_d:
            prompt += f"D) {question_obj.choice_d}\n"
        prompt += "Answer:"
        return prompt


class MedMCQALoader(BaseBenchmarkLoader):
    slug = 'medmcqa'
    name = 'MedMCQA'
    description = 'Medical multiple-choice QA from USMLE-style questions covering diverse medical subjects.'
    category = 'clinical'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset("openlifescienceai/medmcqa", split="validation", trust_remote_code=True)
            questions = []
            answer_map = {0: 'A', 1: 'B', 2: 'C', 3: 'D'}
            for i, item in enumerate(ds):
                cop = item.get('cop', 0)
                questions.append({
                    'question_id': item.get('id', str(i)),
                    'question': item.get('question', ''),
                    'choice_a': item.get('opa', None),
                    'choice_b': item.get('opb', None),
                    'choice_c': item.get('opc', None),
                    'choice_d': item.get('opd', None),
                    'correct_answer': answer_map.get(cop, 'A'),
                    'subject': item.get('subject_name', 'medicine'),
                    'difficulty': '',
                    'metadata': {'exp': item.get('exp', '')},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load MedMCQA: {e}")
            return []


class LambadaLoader(BaseBenchmarkLoader):
    slug = 'lambada'
    name = 'LAMBADA'
    description = 'Language modeling benchmark measuring ability to predict the last word of a passage.'
    category = 'language'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset("EleutherAI/lambada_openai", split="test")
            questions = []
            for i, item in enumerate(ds):
                text = item.get('text', '')
                words = text.rsplit(' ', 1)
                if len(words) == 2:
                    context = words[0]
                    last_word = words[1].strip()
                else:
                    context = text
                    last_word = ''
                questions.append({
                    'question_id': str(i),
                    'question': context,
                    'choice_a': None,
                    'choice_b': None,
                    'choice_c': None,
                    'choice_d': None,
                    'correct_answer': last_word,
                    'subject': 'language_modeling',
                    'difficulty': '',
                    'metadata': {'full_text': text},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load LAMBADA: {e}")
            return []

    def format_prompt(self, question_obj):
        return f"Complete the passage by filling in the last word:\n{question_obj.question} _____\nLast word:"

    def evaluate_answer(self, question_obj, model_response):
        correct = question_obj.correct_answer.strip().lower()
        response = model_response.strip()

        # Strip common verbose prefixes models produce:
        # "The last word is fire", "Answer: fire", "Last word: fire", etc.
        cleaned = re.sub(
            r'^(?:the\s+)?(?:last\s+)?(?:missing\s+)?word\s*(?:is|:)\s*',
            '', response, flags=re.IGNORECASE
        ).strip()
        cleaned = re.sub(
            r'^answer\s*:\s*', '', cleaned, flags=re.IGNORECASE
        ).strip()

        # Extract first token (strip punctuation)
        def _first_token(s):
            tokens = s.split()
            return tokens[0].strip('.,!?;:\'"()[]') if tokens else ''

        first = _first_token(cleaned).lower()

        # 1. First token of cleaned response matches
        if first == correct:
            return True, first

        # 2. Exact word boundary match anywhere in the response
        #    (handles "The passage ends with fire." or quoted answers)
        if re.search(r'\b' + re.escape(correct) + r'\b', response, re.IGNORECASE):
            return True, correct

        # 3. Full response (stripped) matches exactly
        if response.strip().lower() == correct:
            return True, response.strip().lower()

        parsed = first if first else response.strip()[:20]
        return False, parsed


class NQOpenLoader(BaseBenchmarkLoader):
    slug = 'nq_open'
    name = 'NQ Open'
    description = 'Natural Questions open-domain QA: questions from Google search with short answers.'
    category = 'knowledge'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset("nq_open", split="validation", trust_remote_code=True)
            questions = []
            for i, item in enumerate(ds):
                answers = item.get('answer', [])
                correct_answer = answers[0] if answers else ''
                questions.append({
                    'question_id': str(i),
                    'question': item.get('question', ''),
                    'choice_a': None,
                    'choice_b': None,
                    'choice_c': None,
                    'choice_d': None,
                    'correct_answer': correct_answer,
                    'subject': 'open_qa',
                    'difficulty': '',
                    'metadata': {'all_answers': answers},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load NQ Open: {e}")
            return []

    def format_prompt(self, question_obj):
        return f"Answer the question briefly:\n{question_obj.question}\nAnswer:"

    def evaluate_answer(self, question_obj, model_response):
        response = model_response.strip().lower()
        all_answers = question_obj.metadata.get('all_answers', [question_obj.correct_answer])
        for ans in all_answers:
            if ans.lower() in response:
                return True, response[:100]
        return False, response[:100]


class SCIQLoader(BaseBenchmarkLoader):
    slug = 'sciq'
    name = 'SciQ'
    description = 'Science multiple-choice QA with 4 choices (correct answer + 3 distractors) on physics, chemistry, biology.'
    category = 'biomedical'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset("allenai/sciq", split="test", trust_remote_code=True)
            questions = []
            for i, item in enumerate(ds):
                correct = item.get('correct_answer', '')
                d1 = item.get('distractor1', '')
                d2 = item.get('distractor2', '')
                d3 = item.get('distractor3', '')
                # Always put correct as A
                questions.append({
                    'question_id': str(i),
                    'question': item.get('question', ''),
                    'choice_a': correct,
                    'choice_b': d1,
                    'choice_c': d2,
                    'choice_d': d3,
                    'correct_answer': 'A',
                    'subject': 'science',
                    'difficulty': '',
                    'metadata': {'correct_text': correct},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load SciQ: {e}")
            return []


class StrategyQALoader(BaseBenchmarkLoader):
    slug = 'strategyqa'
    name = 'StrategyQA'
    description = 'Yes/No questions requiring multi-hop reasoning and implicit strategy to answer.'
    category = 'reasoning'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset("wics/strategy-qa", split="test", trust_remote_code=True)
            questions = []
            for i, item in enumerate(ds):
                answer_bool = item.get('answer', True)
                correct = 'Yes' if answer_bool else 'No'
                questions.append({
                    'question_id': item.get('qid', str(i)),
                    'question': item.get('question', ''),
                    'choice_a': 'Yes',
                    'choice_b': 'No',
                    'choice_c': None,
                    'choice_d': None,
                    'correct_answer': correct,
                    'subject': 'strategy',
                    'difficulty': '',
                    'metadata': {'facts': item.get('facts', [])},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load StrategyQA: {e}")
            return []

    def format_prompt(self, question_obj):
        return f"Answer Yes or No:\n{question_obj.question}\nAnswer:"

    def evaluate_answer(self, question_obj, model_response):
        response = model_response.strip().lower()
        correct = question_obj.correct_answer.strip().lower()
        if 'yes' in response:
            parsed = 'Yes'
        elif 'no' in response:
            parsed = 'No'
        else:
            parsed = response[:10]
        is_correct = parsed.lower() == correct
        return is_correct, parsed


class SimpleQALoader(BaseBenchmarkLoader):
    slug = 'simpleqa'
    name = 'SimpleQA'
    description = 'OpenAI\'s short, fact-seeking questions with a single, unambiguous answer. Tests factual accuracy.'
    category = 'knowledge'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset("basicv8vc/SimpleQA", split="test", trust_remote_code=True)
            questions = []
            for i, item in enumerate(ds):
                questions.append({
                    'question_id': str(i),
                    'question': item.get('problem', item.get('question', '')),
                    'choice_a': None,
                    'choice_b': None,
                    'choice_c': None,
                    'choice_d': None,
                    'correct_answer': item.get('answer', ''),
                    'subject': item.get('metadata', {}).get('topic', '') if isinstance(item.get('metadata'), dict) else '',
                    'difficulty': '',
                    'metadata': {},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load SimpleQA: {e}")
            return []

    def format_prompt(self, question_obj):
        return f"Answer the following question with a short, direct answer:\n{question_obj.question}\nAnswer:"

    def evaluate_answer(self, question_obj, model_response):
        correct = question_obj.correct_answer.strip().lower()
        response = model_response.strip().lower()
        # Check if correct answer appears in response
        is_correct = correct in response or response in correct
        return is_correct, model_response.strip()[:100]


class PubMedQALoader(BaseBenchmarkLoader):
    slug = 'pubmedqa'
    name = 'PubMedQA'
    description = 'Biomedical yes/no/maybe QA based on PubMed abstracts. Tests medical literature comprehension.'
    category = 'biomedical'

    def load_questions(self):
        try:
            from datasets import load_dataset
            # NOTE: pqa_labeled only has a single 'train' split on HuggingFace (1000 items).
            # This IS the evaluation set — the uploader named it 'train' but it contains the labeled test data.
            ds = load_dataset("qiaojin/PubMedQA", "pqa_labeled", split="train", trust_remote_code=True)
            questions = []
            for i, item in enumerate(ds):
                context = ' '.join(item.get('context', {}).get('contexts', []))[:600]
                decision = item.get('final_decision', 'yes').lower()
                # Map yes/no/maybe to A/B/C
                answer_map = {'yes': 'A', 'no': 'B', 'maybe': 'C'}
                correct = answer_map.get(decision, 'A')
                questions.append({
                    'question_id': item.get('pubid', str(i)),
                    'question': f"Abstract: {context}\n\nQuestion: {item.get('question', '')}",
                    'choice_a': 'Yes',
                    'choice_b': 'No',
                    'choice_c': 'Maybe',
                    'choice_d': None,
                    'correct_answer': correct,
                    'subject': 'biomedicine',
                    'difficulty': '',
                    'metadata': {'decision': decision},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load PubMedQA: {e}")
            return []

    def format_prompt(self, question_obj):
        return (
            f"{question_obj.question}\n"
            f"A) Yes\nB) No\nC) Maybe\n"
            f"Answer (A, B, or C):"
        )

    def evaluate_answer(self, question_obj, model_response):
        response = model_response.strip().upper()
        correct = question_obj.correct_answer.strip().upper()
        # Check for letter or full word
        answer_words = {'YES': 'A', 'NO': 'B', 'MAYBE': 'C'}
        parsed = ''
        for word, letter in answer_words.items():
            if word in response:
                parsed = letter
                break
        if not parsed:
            match = re.search(r'\b([ABC])\b', response)
            parsed = match.group(1) if match else response[:1]
        return parsed == correct, parsed


class GPQALoader(BaseBenchmarkLoader):
    slug = 'gpqa'
    name = 'GPQA Diamond'
    description = 'Graduate-level Google-proof QA. Expert-level questions in biology, physics, and chemistry.'
    category = 'biomedical'

    def load_questions(self):
        try:
            from datasets import load_dataset
            # NOTE: gpqa_diamond only has a single 'train' split on HuggingFace (198 items).
            # This IS the evaluation set — the paper's test data was uploaded under the 'train' split name.
            ds = load_dataset("Idavidrein/gpqa", "gpqa_diamond", split="train", trust_remote_code=True)
            questions = []
            for i, item in enumerate(ds):
                # GPQA has: Question, Correct Answer, Incorrect Answer 1/2/3
                choices = [
                    item.get('Correct Answer', ''),
                    item.get('Incorrect Answer 1', ''),
                    item.get('Incorrect Answer 2', ''),
                    item.get('Incorrect Answer 3', ''),
                ]
                # Shuffle choices and track correct position
                import random
                indices = list(range(4))
                random.seed(i)  # deterministic shuffle per question
                random.shuffle(indices)
                shuffled = [choices[j] for j in indices]
                correct_pos = indices.index(0)  # where did correct answer (index 0) end up?
                letter_map = {0: 'A', 1: 'B', 2: 'C', 3: 'D'}
                questions.append({
                    'question_id': str(i),
                    'question': item.get('Question', ''),
                    'choice_a': shuffled[0],
                    'choice_b': shuffled[1],
                    'choice_c': shuffled[2],
                    'choice_d': shuffled[3],
                    'correct_answer': letter_map[correct_pos],
                    'subject': item.get('Subdomain', item.get('High-level domain', 'science')),
                    'difficulty': 'expert',
                    'metadata': {'explanation': item.get('Explanation', '')},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load GPQA: {e}")
            return []


class MMLUProLoader(BaseBenchmarkLoader):
    slug = 'mmlu_pro'
    name = 'MMLU-Pro'
    description = 'Harder version of MMLU with 10 choices per question and more complex reasoning required.'
    category = 'knowledge'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset("TIGER-Lab/MMLU-Pro", split="test", trust_remote_code=True)
            questions = []
            letter_map = {0: 'A', 1: 'B', 2: 'C', 3: 'D', 4: 'E', 5: 'F', 6: 'G', 7: 'H', 8: 'I', 9: 'J'}
            for i, item in enumerate(ds):
                options = item.get('options', [])
                answer_idx = item.get('answer_index', 0)
                # Store extra options (E-J) in metadata
                questions.append({
                    'question_id': str(item.get('question_id', i)),
                    'question': item.get('question', ''),
                    'choice_a': options[0] if len(options) > 0 else None,
                    'choice_b': options[1] if len(options) > 1 else None,
                    'choice_c': options[2] if len(options) > 2 else None,
                    'choice_d': options[3] if len(options) > 3 else None,
                    'correct_answer': item.get('answer', letter_map.get(answer_idx, 'A')),
                    'subject': item.get('category', ''),
                    'difficulty': '',
                    'metadata': {
                        'choice_e': options[4] if len(options) > 4 else None,
                        'choice_f': options[5] if len(options) > 5 else None,
                        'choice_g': options[6] if len(options) > 6 else None,
                        'choice_h': options[7] if len(options) > 7 else None,
                        'choice_i': options[8] if len(options) > 8 else None,
                        'choice_j': options[9] if len(options) > 9 else None,
                    },
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load MMLU-Pro: {e}")
            return []

    def format_prompt(self, question_obj):
        meta = question_obj.metadata or {}
        prompt = f"Question: {question_obj.question}\n"
        for letter, field in [('A', question_obj.choice_a), ('B', question_obj.choice_b),
                               ('C', question_obj.choice_c), ('D', question_obj.choice_d),
                               ('E', meta.get('choice_e')), ('F', meta.get('choice_f')),
                               ('G', meta.get('choice_g')), ('H', meta.get('choice_h')),
                               ('I', meta.get('choice_i')), ('J', meta.get('choice_j'))]:
            if field:
                prompt += f"{letter}) {field}\n"
        prompt += "Answer:"
        return prompt

    def evaluate_answer(self, question_obj, model_response):
        match = re.search(r'\b([A-J])\b', model_response.upper())
        parsed = match.group(1) if match else model_response.strip().upper()[:1]
        return parsed == question_obj.correct_answer.strip().upper(), parsed


class AQuaRATLoader(BaseBenchmarkLoader):
    slug = 'aqua_rat'
    name = 'AQuA-RAT'
    description = 'Algebra Question Answering with Rationales. Math word problems with 5-choice MCQ and step-by-step rationales.'
    category = 'math'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset('deepmind/aqua_rat', 'raw', split='test')
            questions = []
            letter_map = {'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D', 'E': 'E'}
            for i, item in enumerate(ds):
                opts = item.get('options', [])
                # options look like ["A)...", "B)...", ...]
                choices = {}
                for opt in opts:
                    if opt and len(opt) >= 2 and opt[0] in 'ABCDE' and opt[1] == ')':
                        choices[opt[0]] = opt[2:].strip()
                correct = item.get('correct', 'A').strip().upper()
                questions.append({
                    'question_id': f'aqua_{i}',
                    'question': item.get('question', ''),
                    'choice_a': choices.get('A'),
                    'choice_b': choices.get('B'),
                    'choice_c': choices.get('C'),
                    'choice_d': choices.get('D'),
                    'correct_answer': correct,
                    'subject': 'math',
                    'difficulty': '',
                    'metadata': {
                        'choice_e': choices.get('E'),
                        'rationale': item.get('rationale', ''),
                    },
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load AQuA-RAT: {e}")
            return []

    def format_prompt(self, question_obj):
        meta = question_obj.metadata or {}
        prompt = f"Question: {question_obj.question}\n"
        for letter, field in [('A', question_obj.choice_a), ('B', question_obj.choice_b),
                               ('C', question_obj.choice_c), ('D', question_obj.choice_d),
                               ('E', meta.get('choice_e'))]:
            if field:
                prompt += f"{letter}) {field}\n"
        prompt += "Answer:"
        return prompt

    def evaluate_answer(self, question_obj, model_response):
        match = re.search(r'\b([A-E])\b', model_response.upper())
        parsed = match.group(1) if match else model_response.strip().upper()[:1]
        return parsed == question_obj.correct_answer.strip().upper(), parsed


class SWAGLoader(BaseBenchmarkLoader):
    slug = 'swag'
    name = 'SWAG'
    description = 'Situations With Adversarial Generations. 4-choice commonsense sentence completion based on video captions.'
    category = 'reasoning'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset('allenai/swag', 'regular', split='validation')
            label_map = {0: 'A', 1: 'B', 2: 'C', 3: 'D'}
            questions = []
            for i, item in enumerate(ds):
                # Build the full sentence start
                startphrase = item.get('startphrase', item.get('sent1', '') + ' ' + item.get('sent2', '')).strip()
                label = item.get('label', 0)
                questions.append({
                    'question_id': f'swag_{i}',
                    'question': f"Complete the sentence: {startphrase}",
                    'choice_a': item.get('ending0', ''),
                    'choice_b': item.get('ending1', ''),
                    'choice_c': item.get('ending2', ''),
                    'choice_d': item.get('ending3', ''),
                    'correct_answer': label_map.get(label, 'A'),
                    'subject': 'commonsense',
                    'difficulty': '',
                    'metadata': {},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load SWAG: {e}")
            return []


class MedQAUSMLELoader(BaseBenchmarkLoader):
    slug = 'medqa_usmle'
    name = 'MedQA USMLE'
    description = 'USMLE-style medical licensing exam questions (4 options). Tests clinical and biomedical knowledge.'
    category = 'clinical'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset('GBaker/MedQA-USMLE-4-options', split='test')
            questions = []
            for i, item in enumerate(ds):
                opts = item.get('options', {})
                # options is a dict like {"A": "...", "B": "...", ...}
                answer_idx = item.get('answer_idx', item.get('answer', 'A'))
                if isinstance(answer_idx, int):
                    answer_idx = 'ABCD'[answer_idx] if answer_idx < 4 else 'A'
                questions.append({
                    'question_id': f'medqa_{i}',
                    'question': item.get('question', ''),
                    'choice_a': opts.get('A', opts.get('opa', '')),
                    'choice_b': opts.get('B', opts.get('opb', '')),
                    'choice_c': opts.get('C', opts.get('opc', '')),
                    'choice_d': opts.get('D', opts.get('opd', '')),
                    'correct_answer': str(answer_idx).strip().upper()[:1],
                    'subject': item.get('meta_info', 'medicine'),
                    'difficulty': '',
                    'metadata': {},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load MedQA USMLE: {e}")
            return []


class BBHLoader(BaseBenchmarkLoader):
    slug = 'bbh'
    name = 'BIG-Bench Hard'
    description = 'BIG-Bench Hard — 23 challenging tasks where models previously performed near chance. Tests complex reasoning.'
    category = 'reasoning'

    BBH_SUBTASKS = [
        'boolean_expressions', 'causal_judgement', 'date_understanding',
        'formal_fallacies', 'geometric_shapes', 'hyperbaton',
        'logical_deduction_five_objects', 'logical_deduction_seven_objects',
        'logical_deduction_three_objects', 'movie_recommendation',
        'multistep_arithmetic_two', 'navigate', 'object_counting',
        'penguins_in_a_table', 'reasoning_about_colored_objects',
        'ruin_names', 'salient_translation_error_detection',
        'snarks', 'sports_understanding', 'temporal_sequences',
        'tracking_shuffled_objects_five_objects',
        'tracking_shuffled_objects_seven_objects',
        'tracking_shuffled_objects_three_objects',
        'web_of_lies', 'word_sorting',
    ]

    def load_questions(self):
        try:
            from datasets import load_dataset
            questions = []
            for task in self.BBH_SUBTASKS[:10]:  # Load first 10 subtasks
                try:
                    ds = load_dataset('lukaemon/bbh', task, split='test')
                    for i, item in enumerate(ds):
                        questions.append({
                            'question_id': f'bbh_{task}_{i}',
                            'question': item.get('input', ''),
                            'choice_a': None,
                            'choice_b': None,
                            'choice_c': None,
                            'choice_d': None,
                            'correct_answer': item.get('target', ''),
                            'subject': task.replace('_', ' '),
                            'difficulty': 'hard',
                            'metadata': {'subtask': task},
                        })
                except Exception as task_err:
                    logger.warning(f"BBH subtask {task} failed: {task_err}")
            return questions
        except Exception as e:
            logger.error(f"Failed to load BBH: {e}")
            return []

    def format_prompt(self, question_obj):
        return f"Answer the following:\n{question_obj.question}\nAnswer:"

    def evaluate_answer(self, question_obj, model_response):
        correct = question_obj.correct_answer.strip().lower()
        response = model_response.strip().lower()
        # Exact match or contained in response
        is_correct = correct == response or correct in response
        return is_correct, model_response.strip()[:100]


class COPALoader(BaseBenchmarkLoader):
    slug = 'copa'
    name = 'COPA'
    description = 'Choice Of Plausible Alternatives. 2-choice causal reasoning: given a premise, select cause or effect.'
    category = 'reasoning'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset('super_glue', 'copa', split='validation')
            questions = []
            for i, item in enumerate(ds):
                label = item.get('label', 0)
                q_type = item.get('question', 'effect')
                if q_type == 'cause':
                    question_text = f"What was the CAUSE of this? {item.get('premise', '')}"
                else:
                    question_text = f"What happened as a RESULT? {item.get('premise', '')}"
                questions.append({
                    'question_id': f"copa_{item.get('idx', i)}",
                    'question': question_text,
                    'choice_a': item.get('choice1', ''),
                    'choice_b': item.get('choice2', ''),
                    'choice_c': None,
                    'choice_d': None,
                    'correct_answer': 'A' if label == 0 else 'B',
                    'subject': 'causal reasoning',
                    'difficulty': '',
                    'metadata': {'question_type': q_type},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load COPA: {e}")
            return []

    def format_prompt(self, question_obj):
        return (
            f"Question: {question_obj.question}\n"
            f"A) {question_obj.choice_a}\n"
            f"B) {question_obj.choice_b}\n"
            f"Answer (A or B):"
        )


class RTELoader(BaseBenchmarkLoader):
    slug = 'rte'
    name = 'RTE'
    description = 'Recognizing Textual Entailment. Given a premise and hypothesis, determine if the hypothesis is entailed.'
    category = 'reasoning'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset('super_glue', 'rte', split='validation')
            questions = []
            for i, item in enumerate(ds):
                label = item.get('label', 0)
                # 0 = entailment, 1 = not entailment
                questions.append({
                    'question_id': f"rte_{item.get('idx', i)}",
                    'question': (
                        f"Premise: {item.get('premise', '')}\n"
                        f"Hypothesis: {item.get('hypothesis', '')}\n"
                        f"Does the premise entail the hypothesis?"
                    ),
                    'choice_a': 'Yes (entailment)',
                    'choice_b': 'No (not entailment)',
                    'choice_c': None,
                    'choice_d': None,
                    'correct_answer': 'A' if label == 0 else 'B',
                    'subject': 'textual entailment',
                    'difficulty': '',
                    'metadata': {},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load RTE: {e}")
            return []

    def format_prompt(self, question_obj):
        return (
            f"{question_obj.question}\n"
            f"A) Yes (entailment)\n"
            f"B) No (not entailment)\n"
            f"Answer (A or B):"
        )


class MultiNLILoader(BaseBenchmarkLoader):
    slug = 'multinli'
    name = 'MultiNLI'
    description = 'Multi-Genre Natural Language Inference. 3-class classification: entailment, neutral, or contradiction.'
    category = 'reasoning'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset('nyu-mll/multi_nli', split='validation_matched')
            label_map = {0: 'A', 1: 'B', 2: 'C'}
            questions = []
            for i, item in enumerate(ds):
                label = item.get('label', 0)
                questions.append({
                    'question_id': f"multinli_{item.get('pairID', i)}",
                    'question': (
                        f"Premise: {item.get('premise', '')}\n"
                        f"Hypothesis: {item.get('hypothesis', '')}\n"
                        f"What is the relationship?"
                    ),
                    'choice_a': 'Entailment',
                    'choice_b': 'Neutral',
                    'choice_c': 'Contradiction',
                    'choice_d': None,
                    'correct_answer': label_map.get(label, 'A'),
                    'subject': item.get('genre', 'nli'),
                    'difficulty': '',
                    'metadata': {},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load MultiNLI: {e}")
            return []

    def format_prompt(self, question_obj):
        return (
            f"{question_obj.question}\n"
            f"A) Entailment\n"
            f"B) Neutral\n"
            f"C) Contradiction\n"
            f"Answer (A, B, or C):"
        )

    def evaluate_answer(self, question_obj, model_response):
        response = model_response.strip().upper()
        correct = question_obj.correct_answer.strip().upper()
        # Check for word match too
        word_map = {'ENTAILMENT': 'A', 'NEUTRAL': 'B', 'CONTRADICTION': 'C'}
        parsed = ''
        for word, letter in word_map.items():
            if word in response:
                parsed = letter
                break
        if not parsed:
            match = re.search(r'\b([ABC])\b', response)
            parsed = match.group(1) if match else response[:1]
        return parsed == correct, parsed


class MATH500Loader(BaseBenchmarkLoader):
    slug = 'math500'
    name = 'MATH-500'
    description = 'Hendrycks MATH benchmark — 500 challenging competition math problems across 7 subjects. Open-ended answers.'
    category = 'math'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset('HuggingFaceH4/MATH-500', split='test')
            questions = []
            for i, item in enumerate(ds):
                questions.append({
                    'question_id': item.get('unique_id', str(i)),
                    'question': item.get('problem', ''),
                    'choice_a': None,
                    'choice_b': None,
                    'choice_c': None,
                    'choice_d': None,
                    'correct_answer': item.get('answer', ''),
                    'subject': item.get('subject', 'math'),
                    'difficulty': str(item.get('level', '')),
                    'metadata': {'solution': item.get('solution', '')},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load MATH-500: {e}")
            return []

    def format_prompt(self, question_obj):
        return f"Solve the following math problem and give only the final answer:\n{question_obj.question}\nAnswer:"

    def evaluate_answer(self, question_obj, model_response):
        """
        Evaluate open-ended math answers with multi-step normalization:
        1. Extract the final answer from the model response (handles CoT output).
        2. Normalize both strings (strip LaTeX, $, backslashes, whitespace).
        3. Attempt numeric equivalence comparison (handles 1/2 == 0.5, etc.).
        4. Fall back to exact normalized-string equality.
        """
        correct_raw = question_obj.correct_answer.strip()
        extracted = _extract_math_answer(model_response)
        parsed = extracted or model_response.strip()[:200]

        is_correct = _math_answers_equal(correct_raw, extracted if extracted else model_response)
        return is_correct, parsed


class TriviaQALoader(BaseBenchmarkLoader):
    slug = 'triviaqa'
    name = 'TriviaQA'
    description = 'Large-scale open-domain trivia QA with evidence documents. 95K question-answer pairs from trivia enthusiasts.'
    category = 'knowledge'

    def load_questions(self):
        try:
            from datasets import load_dataset
            ds = load_dataset('mandarjoshi/trivia_qa', 'rc', split='validation')
            questions = []
            for i, item in enumerate(ds):
                ans = item.get('answer', {})
                correct = ans.get('value', '') if isinstance(ans, dict) else str(ans)
                aliases = ans.get('aliases', []) if isinstance(ans, dict) else []
                questions.append({
                    'question_id': item.get('question_id', str(i)),
                    'question': item.get('question', ''),
                    'choice_a': None,
                    'choice_b': None,
                    'choice_c': None,
                    'choice_d': None,
                    'correct_answer': correct,
                    'subject': 'trivia',
                    'difficulty': '',
                    'metadata': {'aliases': aliases},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load TriviaQA: {e}")
            return []

    def format_prompt(self, question_obj):
        return f"Answer the following trivia question with a short answer:\n{question_obj.question}\nAnswer:"

    def evaluate_answer(self, question_obj, model_response):
        """
        Evaluate open-ended trivia answers:
        - Normalizes both strings (lowercase, strip punctuation).
        - Checks for word-boundary match so "Paris" doesn't match "comparison".
        - Checks all official aliases provided by the dataset.
        """
        aliases = question_obj.metadata.get('aliases', []) if question_obj.metadata else []
        all_answers = [question_obj.correct_answer] + list(aliases)
        norm_response = _normalize_trivia(model_response)
        for ans in all_answers:
            if ans and _trivia_answers_match(norm_response, _normalize_trivia(ans)):
                return True, model_response.strip()[:100]
        return False, model_response.strip()[:100]


# ---------------------------------------------------------------------------
# Bioinformatics
# ---------------------------------------------------------------------------

class BioInfoBenchLoader(BaseBenchmarkLoader):
    slug = 'bioinfo_bench'
    name = 'BioInfo-Bench'
    description = (
        'Bioinformatics knowledge benchmark covering sequence analysis, genomics, '
        'proteomics, structural biology, and computational biology tools.'
    )
    category = 'biomedical'

    def load_questions(self):
        """
        The dataset has two CSV files with different schemas; load each explicitly.

        bioinfo-bench-qa.csv  → MCQ with columns: Question, Option A-D, Correct Answer, Subdomain
        bioinfo-bench-seq.csv → sequence-style: ID, User Question, Options (pipe-sep), Answer
        """
        try:
            from datasets import load_dataset
            questions = []

            # ── File 1: MCQ questions ──────────────────────────────────────
            try:
                ds_qa = load_dataset(
                    'Qiyuan04/bioinfo-bench',
                    data_files='bioinfo-bench-qa.csv',
                    split='train',
                )
                for i, item in enumerate(ds_qa):
                    correct_raw = str(item.get('Correct Answer', '')).strip().upper()
                    # Correct Answer may be a letter (A-D) or full option text
                    if correct_raw not in ('A', 'B', 'C', 'D'):
                        # Try matching against option text
                        opt_map = {
                            str(item.get('Option A', '')): 'A',
                            str(item.get('Option B', '')): 'B',
                            str(item.get('Option C', '')): 'C',
                            str(item.get('Option D', '')): 'D',
                        }
                        correct_raw = opt_map.get(
                            str(item.get('Correct Answer', '')), 'A'
                        )
                    questions.append({
                        'question_id': f'qa_{i}',
                        'question': str(item.get('Question', '')),
                        'choice_a': str(item.get('Option A', '')) or None,
                        'choice_b': str(item.get('Option B', '')) or None,
                        'choice_c': str(item.get('Option C', '')) or None,
                        'choice_d': str(item.get('Option D', '')) or None,
                        'correct_answer': correct_raw,
                        'subject': str(item.get('Subdomain', 'bioinformatics')),
                        'difficulty': '',
                        'metadata': {},
                    })
            except Exception as e:
                logger.error(f"BioInfo-Bench qa file error: {e}")

            # ── File 2: Sequence/open-ended questions ──────────────────────
            try:
                ds_seq = load_dataset(
                    'Qiyuan04/bioinfo-bench',
                    data_files='bioinfo-bench-seq.csv',
                    split='train',
                )
                for i, item in enumerate(ds_seq):
                    # Options are stored as a Python dict string:
                    # {'A': 'text', 'B': 'text', 'C': 'text', 'D': 'text'}
                    import ast
                    opts_raw = str(item.get('Options', ''))
                    choice_a = choice_b = choice_c = choice_d = None
                    if opts_raw.strip().startswith('{'):
                        try:
                            opts_dict = ast.literal_eval(opts_raw)
                            choice_a = str(opts_dict.get('A', '')) or None
                            choice_b = str(opts_dict.get('B', '')) or None
                            choice_c = str(opts_dict.get('C', '')) or None
                            choice_d = str(opts_dict.get('D', '')) or None
                        except (ValueError, SyntaxError):
                            pass
                    elif '|' in opts_raw:
                        parts = [p.strip() for p in opts_raw.split('|') if p.strip()]
                        def _strip_prefix(s):
                            return re.sub(r'^[A-Da-d][.)]\s*', '', s).strip()
                        choice_a = _strip_prefix(parts[0]) if len(parts) > 0 else None
                        choice_b = _strip_prefix(parts[1]) if len(parts) > 1 else None
                        choice_c = _strip_prefix(parts[2]) if len(parts) > 2 else None
                        choice_d = _strip_prefix(parts[3]) if len(parts) > 3 else None
                    answer_raw = str(item.get('Answer', '')).strip().upper()
                    if answer_raw not in ('A', 'B', 'C', 'D'):
                        answer_raw = answer_raw[:1] if answer_raw else 'A'
                    questions.append({
                        'question_id': f'seq_{item.get("ID", i)}',
                        'question': str(item.get('User Question', '')),
                        'choice_a': choice_a,
                        'choice_b': choice_b,
                        'choice_c': choice_c,
                        'choice_d': choice_d,
                        'correct_answer': answer_raw,
                        'subject': 'sequence analysis',
                        'difficulty': '',
                        'metadata': {},
                    })
            except Exception as e:
                logger.error(f"BioInfo-Bench seq file error: {e}")

            return questions
        except Exception as e:
            logger.error(f"Failed to load BioInfo-Bench: {e}")
            return []

    # Regex to detect embedded nucleotide sequences (runs of ≥20 ACGTU chars)
    _NUCL_SEQ_RE = re.compile(r'[ACGTUacgtu]{20,}')

    def format_prompt(self, question_obj):
        choices = question_obj.get_choices()
        is_seq = (question_obj.subject or '').lower() == 'sequence analysis'
        is_nucl = is_seq and bool(self._NUCL_SEQ_RE.search(question_obj.question or ''))

        if choices:
            opts = '\n'.join(f"  {k}) {v}" for k, v in choices.items())
            if is_nucl:
                return (
                    f"You are given a nucleotide sequence that was originally a valid RNA. "
                    f"Exactly one error has been introduced randomly. "
                    f"Your task is to identify the type of error applied.\n\n"
                    f"{question_obj.question}\n\n{opts}\n\n"
                    f"Choose the most appropriate error type. "
                    f"Reply with ONLY the letter (A, B, C, or D).\nAnswer:"
                )
            if is_seq:
                return (
                    f"The following is a sequence analysis question in bioinformatics.\n"
                    f"Read the question carefully and select the single best answer.\n"
                    f"Reply with ONLY the letter (A, B, C, or D) — no explanation.\n\n"
                    f"{question_obj.question}\n\n{opts}\n\nAnswer:"
                )
            return (
                f"Answer the following bioinformatics question.\n"
                f"Choose the correct letter (A, B, C, or D) and reply with the letter only.\n\n"
                f"{question_obj.question}\n\n{opts}\n\nAnswer:"
            )

        if is_nucl:
            return (
                f"You are given a nucleotide sequence that was originally a valid RNA. "
                f"Exactly one error has been introduced randomly. "
                f"Your task is to identify the type of error applied. "
                f"Reply with ONLY the letter (A, B, C, or D).\n\n"
                f"{question_obj.question}\nAnswer:"
            )
        if is_seq:
            return (
                f"The following is a sequence analysis question in bioinformatics.\n"
                f"Reply with ONLY the letter (A, B, C, or D).\n\n"
                f"{question_obj.question}\nAnswer:"
            )
        return f"{question_obj.question}\nAnswer:"

    def evaluate_answer(self, question_obj, model_response):
        """
        Robust evaluation for bioinformatics questions.

        Models often produce chain-of-thought (CoT) ending with $\\boxed{Answer}$
        or write the full option text instead of a letter.  The naive
        re.search(r'\\b([A-D])\\b') mis-fires on the article "a" that appears
        throughout CoT text, making everything score as A.

        Priority order:
          1. $\\boxed{X}$ where X is a single letter  → letter answer
          2. $\\boxed{text}$ where text matches a choice → map to letter
          3. "answer is X" / "Answer: X" pattern near the end → letter
          4. Standalone letter on the last non-empty line → letter
          5. Choice-text match anywhere in response (full then partial)
        """
        response = model_response.strip()
        correct = question_obj.correct_answer.strip().upper()

        choices = {
            'A': (question_obj.choice_a or '').strip(),
            'B': (question_obj.choice_b or '').strip(),
            'C': (question_obj.choice_c or '').strip(),
            'D': (question_obj.choice_d or '').strip(),
        }

        def _match_text(text):
            """Return letter whose choice text matches `text`, or None."""
            t = text.strip().lower()
            if not t:
                return None
            for letter, choice in choices.items():
                if choice and choice.lower() == t:
                    return letter
            for letter, choice in choices.items():
                if choice and choice.lower() in t:
                    return letter
            return None

        # 1 & 2. $\boxed{...}$ — highest priority
        boxed = re.search(r'\$?\\boxed\{([^}]*)\}\$?', response)
        if boxed:
            inner = boxed.group(1).strip()
            if inner.upper() in ('A', 'B', 'C', 'D'):
                parsed = inner.upper()
                return parsed == correct, parsed
            letter = _match_text(inner)
            if letter:
                return letter == correct, letter

        # 3. Explicit "answer is X" / "Answer: X" anywhere (last occurrence wins)
        # Handles: "answer is A", "answer is: A", "Answer: A", "final answer is A"
        explicit = re.findall(
            r'(?:the\s+)?(?:final\s+)?answer\s*(?:is\s*:?|:)\s*([A-Da-d])\b',
            response, re.IGNORECASE
        )
        if explicit:
            parsed = explicit[-1].upper()
            return parsed == correct, parsed

        # 4. Standalone letter on the LAST non-empty line
        last_line = ''
        for line in reversed(response.splitlines()):
            if line.strip():
                last_line = line.strip()
                break
        m = re.fullmatch(r'([A-Da-d])[.):\s]*', last_line)
        if m:
            parsed = m.group(1).upper()
            return parsed == correct, parsed
        # Also accept a leading lone letter on the last line
        m = re.match(r'^([A-Da-d])\b', last_line)
        if m:
            parsed = m.group(1).upper()
            return parsed == correct, parsed

        # 5. Choice-text match in entire response
        letter = _match_text(response)
        if letter:
            return letter == correct, letter

        return False, response[:15] if response else ''


# ---------------------------------------------------------------------------
# MMLU medical subsets  (cais/mmlu)
# ---------------------------------------------------------------------------

def _load_mmlu_config(config_name, subject_label):
    """Load a single MMLU configuration from cais/mmlu."""
    try:
        from datasets import load_dataset
        ds = load_dataset('cais/mmlu', config_name, split='test')
        questions = []
        for i, item in enumerate(ds):
            choices = item.get('choices', [])
            answer_idx = item.get('answer', 0)
            if isinstance(answer_idx, str):
                answer_letter = answer_idx.upper()
            else:
                answer_letter = 'ABCD'[int(answer_idx)] if int(answer_idx) < 4 else 'A'
            questions.append({
                'question_id': f'{config_name}_{i}',
                'question': item.get('question', ''),
                'choice_a': choices[0] if len(choices) > 0 else None,
                'choice_b': choices[1] if len(choices) > 1 else None,
                'choice_c': choices[2] if len(choices) > 2 else None,
                'choice_d': choices[3] if len(choices) > 3 else None,
                'correct_answer': answer_letter,
                'subject': subject_label,
                'difficulty': '',
                'metadata': {},
            })
        return questions
    except Exception as e:
        logger.error(f"Failed to load MMLU config '{config_name}': {e}")
        return []


class MMLUClinicalKnowledgeLoader(BaseBenchmarkLoader):
    slug = 'mmlu_clinical_knowledge'
    name = 'MMLU – Clinical Knowledge'
    description = 'MMLU subset covering clinical knowledge: diagnosis, treatment, patient management.'
    category = 'clinical'

    def load_questions(self):
        return _load_mmlu_config('clinical_knowledge', 'clinical knowledge')


class MMLUMedicalGeneticsLoader(BaseBenchmarkLoader):
    slug = 'mmlu_medical_genetics'
    name = 'MMLU – Medical Genetics'
    description = 'MMLU subset covering medical genetics: inheritance, molecular genetics, genetic disorders.'
    category = 'biomedical'

    def load_questions(self):
        return _load_mmlu_config('medical_genetics', 'medical genetics')


class MMLUAnatomyLoader(BaseBenchmarkLoader):
    slug = 'mmlu_anatomy'
    name = 'MMLU – Anatomy'
    description = 'MMLU subset covering human anatomy: gross anatomy, histology, neuroanatomy.'
    category = 'clinical'

    def load_questions(self):
        return _load_mmlu_config('anatomy', 'anatomy')


class MMLUProfessionalMedicineLoader(BaseBenchmarkLoader):
    slug = 'mmlu_professional_medicine'
    name = 'MMLU – Professional Medicine'
    description = 'MMLU subset covering professional medicine: clinical scenarios at physician level.'
    category = 'clinical'

    def load_questions(self):
        return _load_mmlu_config('professional_medicine', 'professional medicine')


class MMLUCollegeMedicineLoader(BaseBenchmarkLoader):
    slug = 'mmlu_college_medicine'
    name = 'MMLU – College Medicine'
    description = 'MMLU subset covering college-level medicine: physiology, pharmacology, pathology.'
    category = 'clinical'

    def load_questions(self):
        return _load_mmlu_config('college_medicine', 'college medicine')


class MMLUCollegeBiologyLoader(BaseBenchmarkLoader):
    slug = 'mmlu_college_biology'
    name = 'MMLU – College Biology'
    description = 'MMLU subset covering college biology: cell biology, genetics, evolution, ecology.'
    category = 'biomedical'

    def load_questions(self):
        return _load_mmlu_config('college_biology', 'college biology')


class MMLUVirologyLoader(BaseBenchmarkLoader):
    slug = 'mmlu_virology'
    name = 'MMLU – Virology'
    description = 'MMLU subset covering virology: viral structure, replication, pathogenesis, vaccines.'
    category = 'biomedical'

    def load_questions(self):
        return _load_mmlu_config('virology', 'virology')


class MMLUNutritionLoader(BaseBenchmarkLoader):
    slug = 'mmlu_nutrition'
    name = 'MMLU – Nutrition'
    description = 'MMLU subset covering nutrition: macronutrients, micronutrients, dietary guidelines, metabolism.'
    category = 'clinical'

    def load_questions(self):
        return _load_mmlu_config('nutrition', 'nutrition')


class MMLUCollegeChemistryLoader(BaseBenchmarkLoader):
    slug = 'mmlu_college_chemistry'
    name = 'MMLU – College Chemistry'
    description = 'MMLU subset covering college chemistry: organic, inorganic, biochemistry, thermodynamics.'
    category = 'biomedical'

    def load_questions(self):
        return _load_mmlu_config('college_chemistry', 'college chemistry')


class MMLUHighSchoolBiologyLoader(BaseBenchmarkLoader):
    slug = 'mmlu_high_school_biology'
    name = 'MMLU – High School Biology'
    description = 'MMLU subset covering high-school biology: cells, genetics, evolution, ecosystems.'
    category = 'biomedical'

    def load_questions(self):
        return _load_mmlu_config('high_school_biology', 'high school biology')


# ---------------------------------------------------------------------------
# Competition Math
# ---------------------------------------------------------------------------

class AIME2024Loader(BaseBenchmarkLoader):
    slug = 'aime_2024'
    name = 'AIME 2024'
    description = 'American Invitational Mathematics Examination 2024 (I & II). 30 competition math problems with integer answers (000–999).'
    category = 'math'

    def load_questions(self):
        try:
            from datasets import load_dataset
            # NOTE: Maxwell-Jia/AIME_2024 only has a single 'train' split (30 problems total).
            # This IS the evaluation set — competition problems uploaded under the 'train' split name.
            ds = load_dataset('Maxwell-Jia/AIME_2024', split='train')
            questions = []
            for i, item in enumerate(ds):
                questions.append({
                    'question_id': item.get('ID', str(i)),
                    'question': item.get('Problem', ''),
                    'choice_a': None,
                    'choice_b': None,
                    'choice_c': None,
                    'choice_d': None,
                    'correct_answer': str(item.get('Answer', '')),
                    'subject': 'competition math',
                    'difficulty': 'competition',
                    'metadata': {'solution': item.get('Solution', '')},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load AIME 2024: {e}")
            return []

    def format_prompt(self, question_obj):
        return (
            f"Solve the following AIME competition math problem. "
            f"Your final answer must be an integer between 000 and 999.\n\n"
            f"{question_obj.question}\n\nAnswer:"
        )

    def evaluate_answer(self, question_obj, model_response):
        correct_raw = question_obj.correct_answer.strip()
        extracted = _extract_math_answer(model_response)
        # Prefer 1–3 digit integers from extracted answer, then full response
        nums = re.findall(r'\b(\d{1,3})\b', extracted or model_response)
        parsed = nums[-1] if nums else (extracted or model_response.strip()[:10])
        try:
            is_correct = int(parsed) == int(correct_raw)
        except (ValueError, TypeError):
            is_correct = _math_answers_equal(correct_raw, extracted or model_response)
        return is_correct, parsed


class AIME2025Loader(BaseBenchmarkLoader):
    slug = 'aime_2025'
    name = 'AIME 2025'
    description = 'American Invitational Mathematics Examination 2025 (I & II). 30 competition math problems with integer answers (000–999).'
    category = 'math'

    def load_questions(self):
        try:
            from datasets import load_dataset
            questions = []
            for part_name, hf_id in [
                ('AIME 2025 I', 'MathArena/aime_2025_I'),
                ('AIME 2025 II', 'MathArena/aime_2025_II'),
            ]:
                try:
                    # NOTE: MathArena AIME datasets only have a single 'train' split (15 problems each).
                    # This IS the evaluation set.
                    ds = load_dataset(hf_id, split='train')
                    for i, item in enumerate(ds):
                        questions.append({
                            'question_id': f"{part_name.replace(' ', '_')}_{i + 1}",
                            'question': item.get('problem', ''),
                            'choice_a': None,
                            'choice_b': None,
                            'choice_c': None,
                            'choice_d': None,
                            'correct_answer': str(item.get('answer', '')),
                            'subject': item.get('problem_type', 'competition math'),
                            'difficulty': 'competition',
                            'metadata': {'source': item.get('source', part_name)},
                        })
                except Exception as e:
                    logger.warning(f"Failed to load {hf_id}: {e}")
            return questions
        except Exception as e:
            logger.error(f"Failed to load AIME 2025: {e}")
            return []

    def format_prompt(self, question_obj):
        return (
            f"Solve the following AIME competition math problem. "
            f"Your final answer must be an integer between 000 and 999.\n\n"
            f"{question_obj.question}\n\nAnswer:"
        )

    def evaluate_answer(self, question_obj, model_response):
        correct_raw = question_obj.correct_answer.strip()
        extracted = _extract_math_answer(model_response)
        nums = re.findall(r'\b(\d{1,3})\b', extracted or model_response)
        parsed = nums[-1] if nums else (extracted or model_response.strip()[:10])
        try:
            is_correct = int(parsed) == int(correct_raw)
        except (ValueError, TypeError):
            is_correct = _math_answers_equal(correct_raw, extracted or model_response)
        return is_correct, parsed


# ---------------------------------------------------------------------------
# HLE – Humanity's Last Exam
# ---------------------------------------------------------------------------

class HLELoader(BaseBenchmarkLoader):
    slug = 'hle'
    name = "HLE (Humanity's Last Exam)"
    excludes_images = True
    description = (
        "2,500 expert-level questions across mathematics, science, and humanities, "
        "designed to be resistant to web search. "
        "Image-based questions (~14%) are excluded — text-only questions loaded."
    )
    category = 'knowledge'

    def load_questions(self):
        try:
            from datasets import load_dataset, Features, Value, Image as HFImage
            # Pass explicit features matching the real parquet schema, with Image
            # columns set to decode=False to avoid the Pillow requirement.
            # Actual columns (from schema inspection):
            #   image        → string (filename only)
            #   image_preview → struct<bytes, path>  ← actual image data
            #   rationale_image → struct<bytes, path>
            hle_features = Features({
                'id': Value('string'),
                'question': Value('string'),
                'image': Value('string'),
                'image_preview': HFImage(decode=False),
                'answer': Value('string'),
                'answer_type': Value('string'),
                'author_name': Value('string'),
                'rationale': Value('string'),
                'rationale_image': HFImage(decode=False),
                'raw_subject': Value('string'),
                'category': Value('string'),
                'canary': Value('string'),
            })
            ds = load_dataset('cais/hle', split='test', features=hle_features)
            questions = []
            for i, item in enumerate(ds):
                # Skip image-based questions: image_preview has bytes when an image exists.
                img = item.get('image_preview')
                if img and (img.get('bytes') or img.get('path')):
                    continue
                answer_type = item.get('answer_type', 'exact_match')
                questions.append({
                    'question_id': item.get('id', str(i)),
                    'question': item.get('question', ''),
                    'choice_a': None,
                    'choice_b': None,
                    'choice_c': None,
                    'choice_d': None,
                    'correct_answer': str(item.get('answer', '')),
                    'subject': item.get('category', item.get('subject', '')),
                    'difficulty': 'expert',
                    'metadata': {'answer_type': answer_type},
                })
            return questions
        except Exception as e:
            logger.error(f"Failed to load HLE: {e}")
            return []

    def format_prompt(self, question_obj):
        meta = question_obj.metadata or {}
        answer_type = meta.get('answer_type', 'exact_match')
        if answer_type == 'multiple_choice':
            return (
                f"{question_obj.question}\n\n"
                f"Reply with only the single letter of the correct option (e.g. A, B, C …). "
                f"Do not write anything else.\nAnswer:"
            )
        return (
            f"{question_obj.question}\n\n"
            f"Provide only the final answer, as concisely as possible. "
            f"Do not explain your reasoning.\nAnswer:"
        )

    # ---------- helpers ----------

    @staticmethod
    def _hle_candidates(response: str) -> list:
        """
        Return a prioritised list of candidate answer strings extracted from
        a model response. Earlier entries are more reliable.
        """
        cands = []

        # 1. \\boxed{...}  (most reliable — models trained for math use this)
        for m in re.finditer(r'\\boxed\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', response):
            cands.append(m.group(1).strip())

        # 2. Explicit "The final answer is …" / "Answer: …" patterns (last occurrence first)
        for m in reversed(list(re.finditer(
            r'(?:the\s+)?(?:final\s+)?answer\s*(?:is|:)\s*\$?([^\n$]{1,200})',
            response, re.IGNORECASE
        ))):
            cands.append(m.group(1).strip().rstrip('.,'))

        # 3. "Therefore/Thus/Hence, X" conclusion lines
        for m in reversed(list(re.finditer(
            r'(?:therefore|thus|hence|so)\s*[,:]?\s*\$?([^\n$]{1,150})',
            response, re.IGNORECASE
        ))):
            cands.append(m.group(1).strip().rstrip('.,'))

        # 4. Last non-empty line as a last resort
        lines = [l.strip() for l in response.split('\n') if l.strip()]
        if lines:
            cands.append(lines[-1])

        return cands

    def evaluate_answer(self, question_obj, model_response):
        meta = question_obj.metadata or {}
        answer_type = meta.get('answer_type', 'exact_match')
        correct = question_obj.correct_answer.strip()
        response = model_response.strip()

        if answer_type == 'multiple_choice':
            # HLE has choices up to H or more — search the full alphabet.
            # Priority:
            # 1. Response starts with "X." or "X)" — e.g. "C. A student with…"
            # 2. Explicit "answer is X" / "answer: X" pattern
            # 3. Any "X." or "(X)" anywhere in the response (last occurrence)
            # 4. First standalone letter as last resort
            up = response.upper().strip()
            m = re.match(r'^([A-Z])[.):\s]', up)
            if m:
                parsed = m.group(1)
            else:
                m = re.search(r'(?:answer\s*(?:is|:)\s*)([A-Z])\b', up)
                if m:
                    parsed = m.group(1)
                else:
                    dots = re.findall(r'([A-Z])[.)]', up)
                    if dots:
                        parsed = dots[-1]
                    else:
                        sa = re.findall(r'\b([A-Z])\b', up)
                        parsed = sa[0] if sa else (up[:1] if up else '')
            return parsed == correct.upper(), parsed

        # ── exact_match ──────────────────────────────────────────────────────
        # Extract the model's final answer rather than searching the whole
        # response — prevents "3" in "## Step 3" from triggering a match.
        norm_correct = _normalize_math(correct)

        candidates = self._hle_candidates(response)
        best_parsed = candidates[0][:100] if candidates else response[:100]

        for cand in candidates:
            norm_cand = _normalize_math(cand)

            # Direct normalised match
            if norm_cand and norm_cand == norm_correct:
                return True, cand[:100]

            # Numeric equivalence (handles "1/2 == 0.5" etc.)
            if _math_answers_equal(correct, cand):
                return True, cand[:100]

            # If the candidate is an equation "LHS = RHS", also try just the RHS
            # e.g. "\pi_1(\mathcal{H}) = \mathbb{Z}"  →  try "\mathbb{Z}"
            eq_parts = cand.rsplit('=', 1)
            if len(eq_parts) == 2:
                rhs = eq_parts[1].strip().rstrip('$.,')
                norm_rhs = _normalize_math(rhs)
                if norm_rhs and norm_rhs == norm_correct:
                    return True, rhs[:100]
                if _math_answers_equal(correct, rhs):
                    return True, rhs[:100]

        return False, best_parsed


# ---------------------------------------------------------------------------
# Vision Benchmark Loaders
# ---------------------------------------------------------------------------

class ScienceQAVisionLoader(BaseBenchmarkLoader):
    slug = 'scienceqa_vision'
    name = 'ScienceQA (Vision)'
    description = 'Science questions with optional images. MCQ from derek-thomas/ScienceQA.'
    category = 'vision'
    benchmark_type = 'vision'

    LETTERS = 'ABCDEFGHIJ'

    def load_questions(self):
        from datasets import load_dataset
        import os
        from django.conf import settings

        ds = load_dataset('derek-thomas/ScienceQA', split='test')
        img_dir = os.path.join(settings.MEDIA_ROOT, 'benchmark_images', 'scienceqa')
        os.makedirs(img_dir, exist_ok=True)
        questions = []

        for idx, item in enumerate(ds):
            qid = f"sciqa_{idx}"
            choices = item['choices']
            correct_idx = item['answer']
            correct_letter = self.LETTERS[correct_idx] if correct_idx < len(self.LETTERS) else 'A'

            choice_a = choices[0] if len(choices) > 0 else None
            choice_b = choices[1] if len(choices) > 1 else None
            choice_c = choices[2] if len(choices) > 2 else None
            choice_d = choices[3] if len(choices) > 3 else None

            image_paths = []
            if item['image'] is not None:
                fname = f"{qid}.jpg"
                full_path = os.path.join(img_dir, fname)
                item['image'].convert('RGB').save(full_path, 'JPEG')
                image_paths = [os.path.join('benchmark_images', 'scienceqa', fname)]

            context = item['hint'] if item['hint'] else ''

            questions.append({
                'question_id': qid,
                'question': item['question'],
                'choice_a': choice_a,
                'choice_b': choice_b,
                'choice_c': choice_c,
                'choice_d': choice_d,
                'correct_answer': correct_letter,
                'subject': item.get('subject', ''),
                'difficulty': item.get('grade', ''),
                'context': context,
                'image_paths': image_paths,
                'metadata': {'topic': item.get('topic', ''), 'has_image': bool(image_paths)},
            })
        return questions

    def format_prompt(self, question_obj):
        choices = ''
        for letter, field in [('A', question_obj.choice_a), ('B', question_obj.choice_b),
                               ('C', question_obj.choice_c), ('D', question_obj.choice_d)]:
            if field:
                choices += f'({letter}) {field}\n'
        prompt = ''
        if question_obj.context:
            prompt += f"Context: {question_obj.context}\n\n"
        if getattr(question_obj, 'image_paths', None):
            prompt += "Look at the image and answer the following question.\n\n"
        prompt += f"{question_obj.question}\n\n{choices}\nAnswer with a single letter."
        return prompt


class AI2DLoader(BaseBenchmarkLoader):
    slug = 'ai2d'
    name = 'AI2D (AI2 Diagrams)'
    description = 'Diagram understanding benchmark. MCQ with 4 options from lmms-lab/ai2d.'
    category = 'vision'
    benchmark_type = 'vision'

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
            options = item['options']
            correct_idx = int(item['answer'])
            correct_letter = self.LETTERS[correct_idx]

            fname = f"{qid}.jpg"
            full_path = os.path.join(img_dir, fname)
            item['image'].convert('RGB').save(full_path, 'JPEG')
            rel_path = os.path.join('benchmark_images', 'ai2d', fname)

            questions.append({
                'question_id': qid,
                'question': item['question'],
                'choice_a': options[0] if len(options) > 0 else None,
                'choice_b': options[1] if len(options) > 1 else None,
                'choice_c': options[2] if len(options) > 2 else None,
                'choice_d': options[3] if len(options) > 3 else None,
                'correct_answer': correct_letter,
                'image_paths': [rel_path],
                'metadata': {'has_image': True},
            })
        return questions

    def format_prompt(self, question_obj):
        return (
            f"Look at the diagram and answer the following question.\n\n"
            f"{question_obj.question}\n\n"
            f"(A) {question_obj.choice_a}\n"
            f"(B) {question_obj.choice_b}\n"
            f"(C) {question_obj.choice_c}\n"
            f"(D) {question_obj.choice_d}\n\n"
            f"Answer with a single letter: A, B, C, or D."
        )


class MMMULoader(BaseBenchmarkLoader):
    slug = 'mmmu'
    name = 'MMMU (Massive Multitask Multimodal Understanding)'
    description = 'Multi-discipline multimodal benchmark with 30 subjects. Up to 7 images per question.'
    category = 'vision'
    benchmark_type = 'vision'

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
        import ast
        import os
        from django.conf import settings

        img_dir = os.path.join(settings.MEDIA_ROOT, 'benchmark_images', 'mmmu')
        os.makedirs(img_dir, exist_ok=True)
        questions = []

        for subject in self.SUBJECTS:
            try:
                ds = load_dataset('MMMU/MMMU', name=subject, split='validation',
                                  trust_remote_code=True)
            except Exception as e:
                logger.warning(f"MMMU: skipping subject {subject}: {e}")
                continue

            for item in ds:
                qid = item['id']
                question_type = item.get('question_type', 'multiple-choice')

                try:
                    options = ast.literal_eval(item['options']) if item.get('options') else []
                except (ValueError, SyntaxError):
                    options = []

                choice_a = options[0] if len(options) > 0 else None
                choice_b = options[1] if len(options) > 1 else None
                choice_c = options[2] if len(options) > 2 else None
                choice_d = options[3] if len(options) > 3 else None

                image_paths = []
                for img_idx in range(1, 8):
                    img = item.get(f'image_{img_idx}')
                    if img is not None:
                        fname = f"{qid}_img{img_idx}.jpg"
                        full_path = os.path.join(img_dir, fname)
                        img.convert('RGB').save(full_path, 'JPEG')
                        image_paths.append(
                            os.path.join('benchmark_images', 'mmmu', fname)
                        )

                questions.append({
                    'question_id': qid,
                    'question': item['question'],
                    'choice_a': choice_a,
                    'choice_b': choice_b,
                    'choice_c': choice_c,
                    'choice_d': choice_d,
                    'correct_answer': item.get('answer', ''),
                    'subject': subject,
                    'difficulty': item.get('topic_difficulty', ''),
                    'image_paths': image_paths,
                    'metadata': {
                        'question_type': question_type,
                        'subfield': item.get('subfield', ''),
                        'img_type': item.get('img_type', ''),
                        'has_image': bool(image_paths),
                    },
                })
        return questions

    def format_prompt(self, question_obj):
        text = question_obj.question
        for i in range(1, 8):
            text = text.replace(f'<image {i}>', f'[Image {i}]')

        prompt = f"{text}\n\n"
        qtype = (question_obj.metadata or {}).get('question_type', 'multiple-choice')
        if qtype == 'multiple-choice':
            for letter, field in [('A', question_obj.choice_a), ('B', question_obj.choice_b),
                                   ('C', question_obj.choice_c), ('D', question_obj.choice_d)]:
                if field:
                    prompt += f'({letter}) {field}\n'
            prompt += '\nAnswer with a single letter.'
        else:
            prompt += 'Give a short, precise answer.'
        return prompt

    def evaluate_answer(self, question_obj, model_response):
        qtype = (question_obj.metadata or {}).get('question_type', 'multiple-choice')
        if qtype == 'multiple-choice':
            response = model_response.strip().upper()
            match = re.search(r'\b([A-J])\b', response)
            if match:
                parsed = match.group(1)
                return parsed == question_obj.correct_answer.strip().upper(), parsed
            return False, response[:50]
        else:
            expected = question_obj.correct_answer.strip().lower()
            actual = model_response.strip().lower()
            return expected == actual, actual[:100]


class MMBenchLoader(BaseBenchmarkLoader):
    slug = 'mmbench'
    name = 'MMBench'
    description = 'Multimodal benchmark with MCQ questions. From HuggingFaceM4/MMBench.'
    category = 'vision'
    benchmark_type = 'vision'

    def load_questions(self):
        from datasets import load_dataset
        import os
        import base64
        from django.conf import settings

        ds = load_dataset('HuggingFaceM4/MMBench', split='validation')
        img_dir = os.path.join(settings.MEDIA_ROOT, 'benchmark_images', 'mmbench')
        os.makedirs(img_dir, exist_ok=True)
        questions = []

        for item in ds:
            qid = f"mmbench_{item['index']}"

            image_paths = []
            if item.get('image'):
                fname = f"{qid}.jpg"
                full_path = os.path.join(img_dir, fname)
                try:
                    img_bytes = base64.b64decode(item['image'])
                    with open(full_path, 'wb') as f:
                        f.write(img_bytes)
                    image_paths = [os.path.join('benchmark_images', 'mmbench', fname)]
                except Exception as e:
                    logger.warning(f"MMBench: failed to save image for {qid}: {e}")

            questions.append({
                'question_id': qid,
                'question': item['question'],
                'choice_a': item.get('A'),
                'choice_b': item.get('B'),
                'choice_c': item.get('C'),
                'choice_d': item.get('D'),
                'correct_answer': item.get('answer', ''),
                'subject': item.get('category', ''),
                'context': item.get('hint', ''),
                'image_paths': image_paths,
                'metadata': {'has_image': bool(image_paths)},
            })
        return questions

    def format_prompt(self, question_obj):
        prompt = ''
        if question_obj.context:
            prompt += f"Hint: {question_obj.context}\n\n"
        prompt += f"{question_obj.question}\n\n"
        for letter, field in [('A', question_obj.choice_a), ('B', question_obj.choice_b),
                               ('C', question_obj.choice_c), ('D', question_obj.choice_d)]:
            if field:
                prompt += f'({letter}) {field}\n'
        prompt += '\nAnswer with a single letter.'
        return prompt


class ChartQALoader(BaseBenchmarkLoader):
    slug = 'chartqa'
    name = 'ChartQA'
    description = 'Chart comprehension benchmark. Open-ended answers. From HuggingFaceM4/ChartQA.'
    category = 'vision'
    benchmark_type = 'vision'

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
            correct = item['label'][0] if item.get('label') else ''

            fname = f"{qid}.jpg"
            full_path = os.path.join(img_dir, fname)
            item['image'].convert('RGB').save(full_path, 'JPEG')
            rel_path = os.path.join('benchmark_images', 'chartqa', fname)

            questions.append({
                'question_id': qid,
                'question': item['query'],
                'correct_answer': correct,
                'image_paths': [rel_path],
                'metadata': {'has_image': True},
            })
        return questions

    def format_prompt(self, question_obj):
        return (
            f"Look at the chart and answer the following question.\n\n"
            f"{question_obj.question}\n\n"
            f"Give a short, precise answer."
        )

    def evaluate_answer(self, question_obj, model_response):
        expected = question_obj.correct_answer.strip().lower()
        actual = model_response.strip().lower()
        is_correct = (expected == actual) or (len(expected) > 2 and expected in actual)
        return is_correct, actual[:100]


# ---------------------------------------------------------------------------
# Agentic Benchmark Loaders
# ---------------------------------------------------------------------------

class GAIALoader(BaseBenchmarkLoader):
    slug = 'gaia'
    name = 'GAIA (text-only)'
    description = 'General AI Assistants benchmark. Text-only questions from validation set (gated dataset).'
    category = 'agentic'
    benchmark_type = 'agentic'

    def load_questions(self):
        from datasets import load_dataset

        ds = load_dataset('gaia-benchmark/GAIA', '2023_all', split='validation',
                          trust_remote_code=True)
        questions = []
        for item in ds:
            if item['task_id'] == '0-0-0-0-0':
                continue
            if item['file_name']:
                continue

            questions.append({
                'question_id': item['task_id'],
                'question': item['Question'],
                'correct_answer': item['Final answer'],
                'difficulty': item['Level'],
                'subject': 'multi-step reasoning',
                'metadata': {'level': item['Level']},
            })
        return questions

    def format_prompt(self, question_obj):
        return (
            f"{question_obj.question}\n\n"
            f"Give a direct, concise answer. Do not explain your reasoning."
        )

    def evaluate_answer(self, question_obj, model_response):
        expected = re.sub(r'[.,;:!?]+$', '', question_obj.correct_answer.strip().lower()).strip()
        actual = re.sub(r'[.,;:!?]+$', '', model_response.strip().lower()).strip()
        return expected == actual, actual[:200]


class BFCLSimpleLoader(BaseBenchmarkLoader):
    slug = 'bfcl_simple'
    name = 'BFCL Simple (Function Calling)'
    description = 'Berkeley Function Calling Leaderboard - simple single-function Python calls.'
    category = 'agentic'
    benchmark_type = 'agentic'

    def load_questions(self):
        import json
        from huggingface_hub import hf_hub_download

        repo = 'gorilla-llm/Berkeley-Function-Calling-Leaderboard'

        q_path = hf_hub_download(repo_id=repo, filename='BFCL_v3_simple.json',
                                  repo_type='dataset')
        with open(q_path) as f:
            q_data = [json.loads(line) for line in f if line.strip()]

        gt_path = hf_hub_download(repo_id=repo,
                                   filename='possible_answer/BFCL_v3_simple.json',
                                   repo_type='dataset')
        gt_map = {}
        with open(gt_path) as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    gt_map[entry['id']] = entry.get('ground_truth', [])

        questions = []
        for item in q_data:
            qid = item['id']
            user_prompt = item['question'][0][0]['content']
            func_schemas = json.dumps(item['function'], indent=2)
            gt = gt_map.get(qid, [])

            questions.append({
                'question_id': qid,
                'question': user_prompt,
                'context': func_schemas,
                'correct_answer': json.dumps(gt),
                'subject': 'function-calling',
                'metadata': {},
            })
        return questions

    def format_prompt(self, question_obj):
        return (
            f"You have access to the following functions:\n\n"
            f"{question_obj.context}\n\n"
            f"Based on the user request below, call the appropriate function. "
            f"Respond with a Python function call (e.g., func_name(arg1=val1, arg2=val2)).\n\n"
            f"User request: {question_obj.question}"
        )

    def evaluate_answer(self, question_obj, model_response):
        import json

        try:
            gt_list = json.loads(question_obj.correct_answer)
        except json.JSONDecodeError:
            return False, model_response[:100]

        if not gt_list:
            return False, model_response[:100]

        gt = gt_list[0]
        expected_func = list(gt.keys())[0]
        expected_params = gt[expected_func]

        match = re.search(r'(\w+(?:\.\w+)*)\s*\(', model_response)
        if not match:
            return False, model_response[:100]

        called_func = match.group(1)
        if called_func != expected_func:
            return False, f"called {called_func}, expected {expected_func}"

        required_params = [k for k, v in expected_params.items() if '' not in v]
        response_lower = model_response.lower()
        params_present = all(p.lower() in response_lower for p in required_params)

        return params_present, called_func


# ---------------------------------------------------------------------------
# Audio Benchmark Loaders
# ---------------------------------------------------------------------------

class LibriSpeechLoader(BaseBenchmarkLoader):
    slug = 'librispeech'
    name = 'LibriSpeech (ASR - clean test)'
    description = 'Automatic speech recognition on LibriSpeech test-clean. Metric: WER.'
    category = 'audio'
    benchmark_type = 'audio'

    def load_questions(self):
        from datasets import load_dataset
        import os
        from django.conf import settings

        # streaming=True downloads only the test-clean shards; the non-streaming
        # path would generate every split of the 'clean' config (train.100 is
        # ~6 GB) just to read the test split.
        ds = load_dataset('openslr/librispeech_asr', 'clean', split='test',
                          streaming=True)
        audio_dir = os.path.join(settings.MEDIA_ROOT, 'benchmark_audio', 'librispeech')
        os.makedirs(audio_dir, exist_ok=True)
        questions = []

        for item in ds:
            try:
                qid = item['id']
                fname = f"{qid}.wav"
                full_path = os.path.join(audio_dir, fname)

                import soundfile as sf
                sf.write(full_path, item['audio']['array'],
                         item['audio']['sampling_rate'])
            except Exception as e:
                logger.warning(f"LibriSpeech: failed to save audio clip: {e}")
                continue

            rel_path = os.path.join('benchmark_audio', 'librispeech', fname)
            questions.append({
                'question_id': qid,
                'question': 'Transcribe the following audio clip.',
                'correct_answer': item['text'].lower(),
                'audio_path': rel_path,
                'subject': str(item.get('speaker_id', '')),
                'metadata': {'has_audio': True},
            })
        return questions

    def format_prompt(self, question_obj):
        return "Transcribe the following audio clip accurately."

    def evaluate_answer(self, question_obj, model_response):
        try:
            from jiwer import wer
            ref = question_obj.correct_answer.strip().lower()
            hyp = model_response.strip().lower()
            if not hyp:
                return False, 'WER=1.0000'
            score = wer(ref, hyp)
            return score < 0.1, f'WER={score:.4f}'
        except ImportError:
            # jiwer not installed: fall back to exact match
            expected = question_obj.correct_answer.strip().lower()
            actual = model_response.strip().lower()
            return expected == actual, actual[:100]


BENCHMARK_REGISTRY = {
    # ── General / Reasoning ──────────────────────────────────────────────────
    'mmlu': MMLULoader,
    'mmlu_pro': MMLUProLoader,
    'arc_challenge': ARCChallengeLoader,
    'arc_easy': ARCEasyLoader,
    'hellaswag': HellaSwagLoader,
    'truthfulqa': TruthfulQALoader,
    'winogrande': WinoGrandeLoader,
    'commonsenseqa': CommonsenseQALoader,
    'boolq': BoolQLoader,
    'openbookqa': OpenBookQALoader,
    'anli': ANLILoader,
    'race': RACELoader,
    'lambada': LambadaLoader,
    'nq_open': NQOpenLoader,
    'simpleqa': SimpleQALoader,
    'bbh': BBHLoader,
    'copa': COPALoader,
    'rte': RTELoader,
    'multinli': MultiNLILoader,
    'triviaqa': TriviaQALoader,
    'swag': SWAGLoader,
    # ── Math ────────────────────────────────────────────────────────────────
    'gsm8k': GSM8KLoader,
    'aqua_rat': AQuaRATLoader,
    'math500': MATH500Loader,
    'aime_2024': AIME2024Loader,
    'aime_2025': AIME2025Loader,
    # ── Frontier / Expert ────────────────────────────────────────────────────
    'hle': HLELoader,
    # ── Science (Biomedical) ─────────────────────────────────────────────────
    'sciq': SCIQLoader,
    'mmlu_college_biology': MMLUCollegeBiologyLoader,
    'mmlu_high_school_biology': MMLUHighSchoolBiologyLoader,
    'mmlu_college_chemistry': MMLUCollegeChemistryLoader,
    'mmlu_medical_genetics': MMLUMedicalGeneticsLoader,
    'mmlu_virology': MMLUVirologyLoader,
    'bioinfo_bench': BioInfoBenchLoader,
    'pubmedqa': PubMedQALoader,
    # 'gpqa': GPQALoader,   # Gated: requires HuggingFace access request
    # ── Clinical Medicine ────────────────────────────────────────────────────
    'medmcqa': MedMCQALoader,
    'medqa_usmle': MedQAUSMLELoader,
    'mmlu_clinical_knowledge': MMLUClinicalKnowledgeLoader,
    'mmlu_anatomy': MMLUAnatomyLoader,
    'mmlu_professional_medicine': MMLUProfessionalMedicineLoader,
    'mmlu_college_medicine': MMLUCollegeMedicineLoader,
    'mmlu_nutrition': MMLUNutritionLoader,
    # ── Broken / disabled ────────────────────────────────────────────────────
    # 'piqa': PIQALoader,         # old loading script
    # 'mathqa': MathQALoader,     # old loading script
    # 'social_iqa': SocialIQALoader,  # old loading script
    # 'logiqa': LogiQALoader,     # old loading script
    # 'strategyqa': StrategyQALoader, # old loading script
    # ── Vision & Multimodal ──────────────────────────────────────────────────
    'scienceqa_vision': ScienceQAVisionLoader,
    'ai2d': AI2DLoader,
    'mmmu': MMMULoader,
    'mmbench': MMBenchLoader,
    'chartqa': ChartQALoader,
    # ── Agentic / Tool Use ───────────────────────────────────────────────────
    'gaia': GAIALoader,
    'bfcl_simple': BFCLSimpleLoader,
    # ── Audio / Speech ───────────────────────────────────────────────────────
    'librispeech': LibriSpeechLoader,
}


def get_registry():
    return BENCHMARK_REGISTRY


# ---------------------------------------------------------------------------
# Dynamic loaders for custom and RAG benchmarks (not in the static registry)
# ---------------------------------------------------------------------------

class CustomBenchmarkLoader(BaseBenchmarkLoader):
    """
    Generic loader for user-uploaded MCQ benchmarks created via CSV.
    Used automatically for any benchmark with metadata['is_custom'] = True
    that does not have a static registry entry.
    """

    def load_questions(self):
        return []  # Questions already in DB; loader only used for eval/prompt.

    def format_prompt(self, question_obj):
        choices = question_obj.get_choices()
        if choices:
            opts = '\n'.join(f"  {k}. {v}" for k, v in choices.items())
            return f"{question_obj.question}\n{opts}\nAnswer:"
        return f"{question_obj.question}\nAnswer:"

    def evaluate_answer(self, question_obj, model_response):
        correct = question_obj.correct_answer.strip()
        response = model_response.strip()
        choices = question_obj.get_choices()
        if choices:
            # Multiple-choice: extract letter
            parsed = _parse_mc_answer(response)
            is_correct = parsed.upper() == correct.upper()
            return is_correct, parsed
        # Open-ended fallback: word-boundary match
        norm_r = _normalize_trivia(response)
        norm_c = _normalize_trivia(correct)
        return _trivia_answers_match(norm_r, norm_c), response[:200]


class RAGBenchmarkLoader(BaseBenchmarkLoader):
    """
    Loader for Retrieval-Augmented Generation (RAG) benchmarks created from CSV.
    Each question has an associated context passage stored in question_obj.context.

    Prompt format:
        Based on the following passage, answer the question.

        Passage:
        {context}

        Question: {question}
        Answer:

    Evaluation uses word-boundary normalised matching with support for
    comma-separated alias lists in correct_answer (e.g. "Paris,City of Light").
    """

    def load_questions(self):
        return []

    def format_prompt(self, question_obj):
        context = (question_obj.context or '').strip()
        question = question_obj.question.strip()
        if context:
            return (
                "Based on the following passage, answer the question concisely.\n\n"
                f"Passage:\n{context}\n\n"
                f"Question: {question}\n"
                "Answer:"
            )
        # Fallback if context is missing (treat as open-ended QA)
        return f"{question}\nAnswer:"

    def evaluate_answer(self, question_obj, model_response):
        """
        Score the model response against correct_answer.
        correct_answer may contain comma-separated aliases (e.g. "Paris,City of Light").
        Uses word-boundary matching so partial strings don't cause false positives.
        """
        norm_response = _normalize_trivia(model_response)
        # Support comma-separated aliases in the answer field
        raw_answers = question_obj.correct_answer.split('|')
        # Also check metadata aliases if present
        aliases = question_obj.metadata.get('aliases', []) if question_obj.metadata else []
        all_answers = raw_answers + list(aliases)
        for ans in all_answers:
            if ans.strip() and _trivia_answers_match(norm_response, _normalize_trivia(ans.strip())):
                return True, model_response.strip()[:200]
        return False, model_response.strip()[:200]


def get_loader(slug):
    """
    Return a loader instance for the given benchmark slug.

    For benchmarks in the static registry, return the registered loader.
    For custom user-created benchmarks, inspect the database record and
    return an appropriate dynamic loader (RAG or generic custom MCQ/open-ended).
    """
    loader_class = BENCHMARK_REGISTRY.get(slug)
    if loader_class:
        return loader_class()

    # Dynamic loader for custom benchmarks
    try:
        from apps.benchmarks.models import Benchmark
        benchmark = Benchmark.objects.get(slug=slug)
        meta = benchmark.metadata or {}
        if meta.get('is_rag'):
            loader = RAGBenchmarkLoader()
            loader.slug = slug
            loader.name = benchmark.name
            return loader
        if meta.get('is_custom'):
            loader = CustomBenchmarkLoader()
            loader.slug = slug
            loader.name = benchmark.name
            return loader
    except Exception:
        pass

    return None
