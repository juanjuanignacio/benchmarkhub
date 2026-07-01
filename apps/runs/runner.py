import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.utils import timezone

logger = logging.getLogger(__name__)

# Global registry of active threads for cancellation
_active_runs = {}
_active_runs_lock = threading.Lock()


def _is_retryable_error(error_str):
    """Return True if the error message indicates a transient failure worth retrying."""
    s = error_str.lower()
    return any(kw in s for kw in ('rate', 'timeout', 'timed out', 'connect', 'temporarily'))


def _process_question_with_retry(backend, prompt, model, temperature, max_tokens,
                                 max_retries=3, images=None):
    """Call backend with exponential backoff retry.

    Retries on:
    - Rate-limit errors
    - Timeout errors (Ollama can time out under heavy parallel load)
    - Connection errors
    - Any exception raised by the backend
    """
    last_error = 'Max retries exceeded'
    for attempt in range(max_retries):
        try:
            result = backend.complete(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                images=images,
            )
            error_str = str(result.get('error') or '')
            if error_str and _is_retryable_error(error_str):
                last_error = error_str
                wait = 2 ** attempt
                logger.warning(
                    f"Retryable error (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {wait}s: {error_str}"
                )
                time.sleep(wait)
                continue
            return result
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {wait}s: {e}"
                )
                time.sleep(wait)
            else:
                return {'text': '', 'response_time': 0.0, 'error': last_error}
    return {'text': '', 'response_time': 0.0, 'error': last_error}


def _send_webhook(run):
    """Send webhook notification when run completes."""
    try:
        import requests
        payload = {
            'run_id': run.id,
            'status': run.status,
            'score': run.score,
            'benchmark': run.benchmark.slug,
            'model': run.model_name,
            'total_questions': run.total_questions,
            'correct_answers': run.correct_answers,
            'completed_at': run.completed_at.isoformat() if run.completed_at else None,
        }
        requests.post(run.webhook_url, json=payload, timeout=10)
    except Exception as e:
        logger.warning(f"Webhook failed for run {run.id}: {e}")


class BenchmarkRunner:
    def __init__(self, run_id, shared_semaphore=None, run_serializer=None):
        self.run_id = run_id
        self._cancelled = False
        # ── Mode A: shared workers ──────────────────────────────────────────
        # Semaphore shared across all runs in the batch.  Each question
        # acquires one slot before calling the API and releases after.
        # Total concurrent API calls == semaphore value.
        # Runs stay 'pending' until they get their first question slot.
        self._shared_semaphore = shared_semaphore
        # ── Mode B: run-by-run ──────────────────────────────────────────────
        # Semaphore(1) shared across all runs.  Each run acquires it before
        # starting and holds it until completion, so runs execute one at a
        # time while using all parallel_workers internally.
        self._run_serializer = run_serializer

    def _poll_acquire(self, sem):
        """Acquire sem with polling so cancellation is detected within 1 s."""
        while not self._cancelled:
            if sem.acquire(timeout=1.0):
                return True
        return False

    def _acquire_slot(self):
        sem = self._shared_semaphore
        if sem is None:
            return True
        return self._poll_acquire(sem)

    def _release_slot(self):
        if self._shared_semaphore is not None:
            self._shared_semaphore.release()

    def run(self):
        """Main benchmark execution method."""
        from .models import BenchmarkRun, RunResult
        from .cost_table import estimate_cost
        from apps.benchmarks.registry import get_loader

        sem = self._shared_semaphore
        ser = self._run_serializer

        try:
            run = BenchmarkRun.objects.get(id=self.run_id)
        except BenchmarkRun.DoesNotExist:
            logger.error(f"Run {self.run_id} not found")
            return

        # ── Mode B: run-by-run — wait until no other run is active ─────────
        if ser is not None:
            if not self._poll_acquire(ser):
                # Cancelled while waiting for the run slot
                try:
                    run.status = 'cancelled'
                    run.completed_at = timezone.now()
                    run.save(update_fields=['status', 'completed_at'])
                except Exception:
                    pass
                return

        # Mark as running (mode B got its slot; mode A keeps pending until
        # first question; no-semaphore marks immediately).
        if ser is not None or sem is None:
            run.status = 'running'
            run.started_at = timezone.now()
            run.save(update_fields=['status', 'started_at'])

        try:
            # Get provider backend
            provider = run.provider
            backend = provider.get_backend()

            # Get benchmark questions
            questions_qs = run.benchmark.questions.all()

            # Check for retry question IDs
            retry_ids = run.metadata.get('retry_question_ids', [])
            if retry_ids:
                questions_qs = questions_qs.filter(question_id__in=retry_ids)
            elif run.num_questions and run.num_questions > 0:
                questions_qs = questions_qs[:run.num_questions]

            questions = list(questions_qs)
            if not questions:
                run.status = 'failed'
                run.error_message = 'No questions found for this benchmark. Please load the benchmark first.'
                run.completed_at = timezone.now()
                run.save()
                return

            run.total_questions = len(questions)
            run.save(update_fields=['total_questions'])

            # Get loader for prompt formatting and answer evaluation
            loader = get_loader(run.benchmark.slug)

            # Get few-shot examples if needed
            few_shot_examples = []
            if run.few_shot_count > 0:
                import random
                all_questions = list(run.benchmark.questions.all())
                sample_pool = [q for q in all_questions if q not in questions]
                if sample_pool:
                    k = min(run.few_shot_count, len(sample_pool))
                    few_shot_examples = random.sample(sample_pool, k)

            def _build_prompt(question):
                custom_tpl = run.benchmark.prompt_template
                if custom_tpl:
                    base = custom_tpl.format(
                        question=question.question,
                        choice_a=question.choice_a or '',
                        choice_b=question.choice_b or '',
                        choice_c=question.choice_c or '',
                        choice_d=question.choice_d or '',
                    )
                elif loader:
                    base = loader.format_prompt(question)
                else:
                    base = question.question

                if run.system_prompt:
                    base = f"{run.system_prompt}\n\n{base}"

                # Add few-shot examples
                if few_shot_examples:
                    shots_text = []
                    for ex in few_shot_examples:
                        if loader:
                            ex_prompt = loader.format_prompt(ex)
                        else:
                            ex_prompt = ex.question
                        ex_answer = ex.correct_answer
                        shots_text.append(f"{ex_prompt}\nAnswer: {ex_answer}")
                    shots_block = "\n\n".join(shots_text)
                    base = f"Here are some example questions and answers:\n\n{shots_block}\n\nNow answer the following:\n\n{base}"

                # Chain-of-thought
                if run.use_cot:
                    base = base + "\n\nLet's think step by step."

                return base

            correct_count = 0
            results_batch = []
            correct_lock = threading.Lock()

            def process_question(idx, question):
                nonlocal correct_count

                if self._is_cancelled(run):
                    return None

                prompt = _build_prompt(question)

                # Load images for vision benchmarks
                images_b64 = None
                if loader:
                    imgs = loader.get_images_b64(question)
                    if imgs:
                        images_b64 = imgs

                result_data = _process_question_with_retry(
                    backend, prompt, run.model_name, run.temperature, run.max_tokens,
                    images=images_b64,
                )
                model_response = result_data.get('text', '')
                response_time = result_data.get('response_time', 0.0)
                error_msg = result_data.get('error') or ''
                tokens_in = result_data.get('tokens_input', 0) or 0
                tokens_out = result_data.get('tokens_output', 0) or 0
                cost = estimate_cost(run.model_name, tokens_in, tokens_out)

                if error_msg:
                    is_correct = False
                    parsed_answer = ''
                else:
                    try:
                        if loader:
                            is_correct, parsed_answer = loader.evaluate_answer(question, model_response)
                        else:
                            parsed_answer = model_response.strip()[:50]
                            is_correct = parsed_answer.upper() == question.correct_answer.upper()
                    except Exception as e:
                        logger.warning(f"Error evaluating answer: {e}")
                        is_correct = False
                        parsed_answer = model_response[:50] if model_response else ''

                return {
                    'question': question,
                    'model_response': model_response,
                    'parsed_answer': parsed_answer,
                    'is_correct': is_correct,
                    'response_time': response_time,
                    'error_msg': error_msg,
                    'tokens_in': tokens_in,
                    'tokens_out': tokens_out,
                    'cost': cost,
                }

            def _append_result(result, idx):
                """Store a result dict into results_batch, flushing every 50."""
                nonlocal correct_count
                if result is None:
                    return
                if result['is_correct']:
                    correct_count += 1
                results_batch.append(RunResult(
                    run=run,
                    question=result['question'],
                    model_response=result['model_response'],
                    parsed_answer=result['parsed_answer'],
                    is_correct=result['is_correct'],
                    response_time=result['response_time'],
                    error_message=result['error_msg'],
                    tokens_input=result['tokens_in'],
                    tokens_output=result['tokens_out'],
                    estimated_cost=result['cost'],
                ))
                if len(results_batch) >= 50:
                    RunResult.objects.bulk_create(results_batch)
                    results_batch.clear()
                    run.correct_answers = correct_count
                    run.score = (correct_count / len(questions) * 100)
                    run.save(update_fields=['correct_answers', 'score'])

            if sem is not None:
                # ── Shared-semaphore mode (bulk / sweep / suite) ────────────
                # One question at a time per run; slots are shared globally so
                # total concurrent API calls across all runs == semaphore value.
                # The run stays 'pending' until it acquires its first slot.
                run_started = False
                for idx, question in enumerate(questions):
                    if self._is_cancelled(run):
                        run.status = 'cancelled'
                        run.completed_at = timezone.now()
                        run.correct_answers = correct_count
                        run.total_questions = idx
                        run.score = (correct_count / idx * 100) if idx > 0 else 0.0
                        run.save()
                        return

                    if not self._acquire_slot():
                        # Cancelled while waiting for a free slot
                        run.status = 'cancelled'
                        run.completed_at = timezone.now()
                        run.correct_answers = correct_count
                        run.total_questions = idx
                        run.score = (correct_count / idx * 100) if idx > 0 else 0.0
                        run.save()
                        return

                    # First slot acquired → transition to 'running'
                    if not run_started:
                        run.status = 'running'
                        run.started_at = timezone.now()
                        run.save(update_fields=['status', 'started_at'])
                        run_started = True

                    try:
                        result = process_question(idx, question)
                    finally:
                        self._release_slot()

                    _append_result(result, idx)

            elif run.parallel_workers > 1:
                # ── Per-run parallel execution (single run, no shared pool) ──
                with ThreadPoolExecutor(max_workers=run.parallel_workers) as executor:
                    future_to_idx = {
                        executor.submit(process_question, idx, q): idx
                        for idx, q in enumerate(questions)
                    }
                    for future in as_completed(future_to_idx):
                        if self._is_cancelled(run):
                            break
                        _append_result(future.result(), future_to_idx[future])
            else:
                # ── Sequential execution (single run, no shared pool) ─────────
                for idx, question in enumerate(questions):
                    if self._is_cancelled(run):
                        run.status = 'cancelled'
                        run.completed_at = timezone.now()
                        run.correct_answers = correct_count
                        run.total_questions = idx
                        run.score = (correct_count / idx * 100) if idx > 0 else 0.0
                        run.save()
                        return

                    _append_result(process_question(idx, question), idx)

            # Save remaining results
            if results_batch:
                RunResult.objects.bulk_create(results_batch)

            # Finalize run
            total = len(questions)
            run.status = 'completed'
            run.completed_at = timezone.now()
            run.total_questions = total
            run.correct_answers = correct_count
            run.score = (correct_count / total * 100) if total > 0 else 0.0
            run.save()

            logger.info(
                f"Run {self.run_id} completed: {correct_count}/{total} correct "
                f"({run.score:.1f}%)"
            )

            # Send webhook if configured
            if run.webhook_url:
                _send_webhook(run)

        except Exception as e:
            logger.error(f"Run {self.run_id} failed: {e}", exc_info=True)
            try:
                run = BenchmarkRun.objects.get(id=self.run_id)
                run.status = 'failed'
                run.error_message = str(e)
                run.completed_at = timezone.now()
                run.save()
                if run.webhook_url:
                    _send_webhook(run)
            except Exception:
                pass
        finally:
            with _active_runs_lock:
                _active_runs.pop(self.run_id, None)
            # Release the run-level slot so the next queued run can start
            if ser is not None:
                ser.release()

    def _is_cancelled(self, run):
        if self._cancelled:
            return True
        # Re-read from DB to check for cancellation or deletion
        try:
            from .models import BenchmarkRun
            fresh = BenchmarkRun.objects.only('status').get(id=self.run_id)
            return fresh.status == 'cancelled'
        except BenchmarkRun.DoesNotExist:
            # Run was deleted — stop immediately
            self._cancelled = True
            return True
        except Exception:
            return False


def start_run_in_background(run_id, shared_semaphore=None, run_serializer=None):
    """Start a benchmark run in a background thread.

    shared_semaphore: Semaphore(N) — N total concurrent API calls shared
        across all runs (mode A: "shared workers").
    run_serializer: Semaphore(1) — runs execute one at a time, each using
        its own parallel_workers internally (mode B: "run-by-run").
    """
    from .models import BenchmarkRun

    runner = BenchmarkRunner(run_id, shared_semaphore=shared_semaphore,
                             run_serializer=run_serializer)
    thread = threading.Thread(
        target=runner.run,
        name=f"benchmark-run-{run_id}",
        daemon=True,
    )
    thread.start()

    # Store thread reference
    with _active_runs_lock:
        _active_runs[run_id] = (thread, runner)

    # Save thread name to run
    try:
        run = BenchmarkRun.objects.get(id=run_id)
        run.thread_id = thread.name
        run.save(update_fields=['thread_id'])
    except Exception:
        pass

    return thread


def cancel_run(run_id):
    """Cancel a running benchmark run."""
    from .models import BenchmarkRun

    with _active_runs_lock:
        entry = _active_runs.get(run_id)
        if entry:
            _, runner = entry
            runner._cancelled = True

    try:
        run = BenchmarkRun.objects.get(id=run_id)
        if run.status in ('pending', 'running'):
            run.status = 'cancelled'
            run.completed_at = timezone.now()
            run.save(update_fields=['status', 'completed_at'])
            return True
    except Exception as e:
        logger.error(f"Error cancelling run {run_id}: {e}")
    return False
