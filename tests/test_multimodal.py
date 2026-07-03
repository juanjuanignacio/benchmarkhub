"""
Tests for multimodal (vision/audio) benchmark support:
- BaseBenchmarkLoader.get_images_b64 / get_audio_b64
- Backends: image/audio payload construction and explicit unsupported errors
- Runner passes images/audio through to the backend
"""
import base64
import json
import os
import tempfile
from unittest import mock

from django.test import TestCase, override_settings

from apps.benchmarks.models import Benchmark, BenchmarkQuestion
from apps.benchmarks.registry import BaseBenchmarkLoader
from tests.base import make_provider


class _DummyLoader(BaseBenchmarkLoader):
    slug = 'dummy'
    name = 'Dummy'

    def load_questions(self):
        return []


def _make_question(**kwargs):
    bm = Benchmark.objects.create(slug='mm-test', name='MM Test', category='vision',
                                  benchmark_type='vision')
    defaults = dict(benchmark=bm, question_id='q1', question='What is shown?',
                    correct_answer='A')
    defaults.update(kwargs)
    return BenchmarkQuestion.objects.create(**defaults)


class GetMediaB64Tests(TestCase):
    def test_get_images_b64_reads_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'imgs'), exist_ok=True)
            raw = b'\xff\xd8\xff fake jpeg bytes'
            with open(os.path.join(tmp, 'imgs', 'a.jpg'), 'wb') as f:
                f.write(raw)
            with override_settings(MEDIA_ROOT=tmp):
                q = _make_question(image_paths=['imgs/a.jpg'])
                imgs = _DummyLoader().get_images_b64(q)
        self.assertEqual(len(imgs), 1)
        self.assertEqual(base64.b64decode(imgs[0]), raw)

    def test_get_images_b64_empty_when_no_paths(self):
        q = _make_question(image_paths=[])
        self.assertEqual(_DummyLoader().get_images_b64(q), [])

    def test_get_audio_b64_reads_file_and_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'aud'), exist_ok=True)
            raw = b'RIFF fake wav bytes'
            with open(os.path.join(tmp, 'aud', 'clip.wav'), 'wb') as f:
                f.write(raw)
            with override_settings(MEDIA_ROOT=tmp):
                q = _make_question(audio_path='aud/clip.wav')
                audio = _DummyLoader().get_audio_b64(q)
        self.assertIsNotNone(audio)
        self.assertEqual(audio['format'], 'wav')
        self.assertEqual(base64.b64decode(audio['data']), raw)

    def test_get_audio_b64_none_when_no_audio(self):
        q = _make_question(audio_path='')
        self.assertIsNone(_DummyLoader().get_audio_b64(q))

    def test_get_audio_b64_none_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(MEDIA_ROOT=tmp):
                q = _make_question(audio_path='aud/missing.wav')
                self.assertIsNone(_DummyLoader().get_audio_b64(q))


class OllamaMultimodalTests(TestCase):
    def setUp(self):
        self.provider = make_provider()
        self.backend = self.provider.get_backend()

    @mock.patch('apps.providers.backends.ollama.requests.post')
    def test_images_included_in_payload(self, mock_post):
        mock_post.return_value.json.return_value = {'response': 'B'}
        mock_post.return_value.raise_for_status = lambda: None
        result = self.backend.complete(prompt='Q?', model='gemma3:12b',
                                       images=['aW1n'])
        self.assertIsNone(result['error'])
        payload = mock_post.call_args.kwargs['json']
        self.assertEqual(payload['images'], ['aW1n'])

    @mock.patch('apps.providers.backends.ollama.requests.post')
    def test_no_images_key_for_text_requests(self, mock_post):
        mock_post.return_value.json.return_value = {'response': 'B'}
        mock_post.return_value.raise_for_status = lambda: None
        self.backend.complete(prompt='Q?', model='llama3.1')
        payload = mock_post.call_args.kwargs['json']
        self.assertNotIn('images', payload)

    def test_audio_returns_explicit_error(self):
        result = self.backend.complete(prompt='Q?', model='llama3.1',
                                       audio={'data': 'YQ==', 'format': 'wav'})
        self.assertIn('does not support audio', result['error'])
        self.assertEqual(result['text'], '')


class VLLMMultimodalTests(TestCase):
    def setUp(self):
        self.provider = make_provider(slug='vllm-p', name='vllm-p',
                                      provider_type='vllm')
        self.backend = self.provider.get_backend()

    @mock.patch('apps.providers.backends.vllm.requests.post')
    def test_images_sent_as_content_parts(self, mock_post):
        mock_post.return_value.json.return_value = {
            'choices': [{'message': {'content': 'A'}}]}
        mock_post.return_value.raise_for_status = lambda: None
        result = self.backend.complete(prompt='Q?', model='qwen-vl',
                                       images=['aW1n'])
        self.assertIsNone(result['error'])
        content = mock_post.call_args.kwargs['json']['messages'][0]['content']
        types = [part['type'] for part in content]
        self.assertEqual(types, ['text', 'image_url'])
        self.assertIn('data:image/jpeg;base64,aW1n',
                      content[1]['image_url']['url'])

    @mock.patch('apps.providers.backends.vllm.requests.post')
    def test_audio_sent_as_input_audio_part(self, mock_post):
        mock_post.return_value.json.return_value = {
            'choices': [{'message': {'content': 'hi'}}]}
        mock_post.return_value.raise_for_status = lambda: None
        result = self.backend.complete(prompt='Transcribe', model='qwen-audio',
                                       audio={'data': 'YQ==', 'format': 'wav'})
        self.assertIsNone(result['error'])
        content = mock_post.call_args.kwargs['json']['messages'][0]['content']
        self.assertEqual(content[1]['type'], 'input_audio')
        self.assertEqual(content[1]['input_audio']['format'], 'wav')

    @mock.patch('apps.providers.backends.vllm.requests.post')
    def test_multimodal_never_falls_back_to_completions(self, mock_post):
        import requests as req
        resp = mock.Mock()
        resp.raise_for_status.side_effect = req.exceptions.HTTPError('400')
        mock_post.return_value = resp
        result = self.backend.complete(prompt='Q?', model='m', images=['aW1n'])
        self.assertIsNotNone(result['error'])
        # Only one POST (chat completions) — no text-only fallback that would
        # silently drop the image
        self.assertEqual(mock_post.call_count, 1)


class CohereUnsupportedTests(TestCase):
    def test_images_and_audio_rejected(self):
        provider = make_provider(slug='co', name='co', provider_type='cohere')
        backend = provider.get_backend()
        r1 = backend.complete(prompt='Q?', model='command', images=['aW1n'])
        self.assertIn('does not support image', r1['error'])
        r2 = backend.complete(prompt='Q?', model='command',
                              audio={'data': 'YQ==', 'format': 'wav'})
        self.assertIn('does not support audio', r2['error'])


class AnthropicSamplingGuardTests(TestCase):
    def test_no_sampling_prefixes_cover_current_models(self):
        from apps.providers.backends.anthropic_backend import _NO_SAMPLING_PREFIXES
        for model in ('claude-opus-4-8', 'claude-sonnet-5', 'claude-fable-5'):
            self.assertTrue(model.startswith(_NO_SAMPLING_PREFIXES), model)
        # Older models still accept temperature
        for model in ('claude-sonnet-4-6', 'claude-haiku-4-5', 'claude-opus-4-6'):
            self.assertFalse(model.startswith(_NO_SAMPLING_PREFIXES), model)


class RunnerMultimodalPassthroughTests(TestCase):
    def test_retry_helper_forwards_images_and_audio(self):
        from apps.runs.runner import _process_question_with_retry
        backend = mock.Mock()
        backend.complete.return_value = {'text': 'A', 'response_time': 0.1,
                                         'error': None}
        audio = {'data': 'YQ==', 'format': 'wav'}
        result = _process_question_with_retry(
            backend, 'prompt', 'model', 0.0, 64,
            images=['aW1n'], audio=audio,
        )
        self.assertEqual(result['text'], 'A')
        kwargs = backend.complete.call_args.kwargs
        self.assertEqual(kwargs['images'], ['aW1n'])
        self.assertEqual(kwargs['audio'], audio)
