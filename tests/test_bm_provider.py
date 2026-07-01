"""
Tests for: python manage.py bm_provider list|add|test|models|delete
"""
import io
from unittest.mock import patch, MagicMock

from django.core.management import call_command
from django.core.management.base import CommandError

from apps.providers.models import Provider
from tests.base import BaseCommandTest, call_cmd


class TestProviderList(BaseCommandTest):
    def test_list_shows_provider(self):
        out = self.call('bm_provider', 'list')
        self.assertIn('test-provider', out)
        self.assertIn('Test Provider', out)

    def test_list_empty(self):
        Provider.objects.all().delete()
        out = self.call('bm_provider', 'list')
        self.assertIn('No providers', out)


class TestProviderAdd(BaseCommandTest):
    def test_add_new_provider(self):
        out = self.call('bm_provider', 'add', 'my-ollama', 'My Ollama',
                        '--type', 'ollama', '--url', 'http://localhost:11434')
        self.assertIn('my-ollama', out)
        self.assertTrue(Provider.objects.filter(slug='my-ollama').exists())

    def test_add_with_api_key(self):
        out = self.call('bm_provider', 'add', 'my-openai', 'My OpenAI',
                        '--type', 'openai', '--key', 'sk-test123',
                        '--default-model', 'gpt-4o')
        p = Provider.objects.get(slug='my-openai')
        self.assertEqual(p.api_key, 'sk-test123')
        self.assertEqual(p.default_model, 'gpt-4o')

    def test_add_duplicate_slug_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_provider', 'add', 'test-provider', 'Dup',
                      '--type', 'ollama')

    def test_add_invalid_slug_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_provider', 'add', 'Bad Slug!', 'Name',
                      '--type', 'ollama')

    def test_add_all_supported_types(self):
        types = ['ollama', 'openai', 'anthropic', 'vllm', 'gemini', 'groq', 'mistral', 'cohere', 'together']
        for i, ptype in enumerate(types):
            self.call('bm_provider', 'add', f'p-{ptype}', f'Provider {ptype}',
                      '--type', ptype)
            self.assertTrue(Provider.objects.filter(slug=f'p-{ptype}').exists())


class TestProviderTest(BaseCommandTest):
    def test_test_provider_not_found(self):
        with self.assertRaises(CommandError):
            self.call('bm_provider', 'test', 'nonexistent')

    def test_test_provider_success(self):
        mock_result = {'success': True, 'response_time': 123, 'models': ['llama3.2', 'mistral']}
        mock_backend = MagicMock()
        mock_backend.test_connection.return_value = mock_result

        with patch('apps.providers.backends.get_backend', return_value=mock_backend):
            out = self.call('bm_provider', 'test', 'test-provider')
        self.assertIn('OK', out)
        self.assertIn('123', out)

    def test_test_provider_failure(self):
        mock_result = {'success': False, 'error': 'Connection refused'}
        mock_backend = MagicMock()
        mock_backend.test_connection.return_value = mock_result

        with patch('apps.providers.backends.get_backend', return_value=mock_backend):
            out = self.call('bm_provider', 'test', 'test-provider')
        self.assertIn('FAILED', out)
        self.assertIn('Connection refused', out)

    def test_test_provider_with_model(self):
        mock_result = {'success': True, 'response_time': 50}
        mock_backend = MagicMock()
        mock_backend.test_connection.return_value = mock_result

        with patch('apps.providers.backends.get_backend', return_value=mock_backend):
            out = self.call('bm_provider', 'test', 'test-provider', '--model', 'llama3.2')
        self.assertIn('OK', out)


class TestProviderModels(BaseCommandTest):
    def test_models_not_found(self):
        with self.assertRaises(CommandError):
            self.call('bm_provider', 'models', 'nonexistent')

    def test_models_lists_models(self):
        mock_backend = MagicMock()
        mock_backend.list_models.return_value = ['llama3.2', 'mistral', 'phi3']

        with patch('apps.providers.backends.get_backend', return_value=mock_backend):
            out = self.call('bm_provider', 'models', 'test-provider')
        self.assertIn('llama3.2', out)
        self.assertIn('mistral', out)

    def test_models_empty(self):
        mock_backend = MagicMock()
        mock_backend.list_models.return_value = []

        with patch('apps.providers.backends.get_backend', return_value=mock_backend):
            out = self.call('bm_provider', 'models', 'test-provider')
        self.assertIn('No models', out)


class TestProviderDelete(BaseCommandTest):
    def test_delete_existing(self):
        out = self.call('bm_provider', 'delete', 'test-provider')
        self.assertIn('deleted', out)
        self.assertFalse(Provider.objects.filter(slug='test-provider').exists())

    def test_delete_nonexistent_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_provider', 'delete', 'ghost-provider')
