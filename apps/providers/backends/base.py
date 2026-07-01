import time
import logging

logger = logging.getLogger(__name__)


class BaseProviderBackend:
    def __init__(self, provider_model):
        self.provider = provider_model

    def complete(self, prompt: str, model: str, temperature: float = 0,
                 max_tokens: int = 512, images=None) -> dict:
        """
        Generate a completion for the given prompt.

        Args:
            images: optional list of base64-encoded image strings for vision models.

        Returns:
            dict with keys:
                - text (str): the generated text
                - response_time (float): time in seconds
                - error (str or None): error message if failed
        """
        raise NotImplementedError

    def list_models(self) -> list:
        """
        Return a list of available model names.

        Returns:
            list of str
        """
        raise NotImplementedError

    def test_connection(self) -> dict:
        """
        Test that the provider is reachable and working.

        Returns:
            dict with keys:
                - success (bool)
                - error (str or None)
                - response_time (float)
        """
        raise NotImplementedError

    def _get_api_key(self):
        """Return API key from provider or environment."""
        import os
        if self.provider.api_key:
            return self.provider.api_key
        # Try environment variable based on provider type
        env_map = {
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
            'cohere': 'COHERE_API_KEY',
            'mistral': 'MISTRAL_API_KEY',
            'gemini': 'GOOGLE_API_KEY',
            'groq': 'GROQ_API_KEY',
            'together': 'TOGETHER_API_KEY',
        }
        env_key = env_map.get(self.provider.provider_type, '')
        if env_key:
            return os.environ.get(env_key, '')
        return ''

    def _get_base_url(self, default=''):
        return self.provider.base_url or default
