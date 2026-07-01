import time
import logging

from .base import BaseProviderBackend

logger = logging.getLogger(__name__)

MISTRAL_MODELS = [
    'mistral-large-latest',
    'mistral-medium-latest',
    'mistral-small-latest',
    'open-mistral-7b',
    'open-mixtral-8x7b',
    'open-mixtral-8x22b',
    'codestral-latest',
]


class MistralBackend(BaseProviderBackend):
    def _get_client(self):
        try:
            from mistralai import Mistral
            api_key = self._get_api_key()
            return Mistral(api_key=api_key)
        except ImportError:
            raise ImportError("mistralai package not installed. Run: pip install mistralai")

    def complete(self, prompt: str, model: str, temperature: float = 0,
                 max_tokens: int = 512, images=None) -> dict:
        start = time.time()
        try:
            client = self._get_client()
            resp = client.chat.complete(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content if resp.choices else ''
            return {'text': text, 'response_time': time.time() - start, 'error': None}
        except Exception as e:
            err = str(e)
            logger.error(f"Mistral error: {err}", exc_info=True)
            return {'text': '', 'response_time': time.time() - start, 'error': err}

    def list_models(self) -> list:
        try:
            client = self._get_client()
            models = client.models.list()
            return [m.id for m in models.data if hasattr(m, 'id')]
        except Exception as e:
            logger.error(f"Failed to list Mistral models: {e}")
            return MISTRAL_MODELS

    def test_connection(self) -> dict:
        start = time.time()
        try:
            client = self._get_client()
            model = self.provider.default_model or 'mistral-small-latest'
            resp = client.chat.complete(
                model=model,
                messages=[{'role': 'user', 'content': 'Say "OK"'}],
                temperature=0,
                max_tokens=5,
            )
            text = resp.choices[0].message.content if resp.choices else ''
            return {
                'success': True,
                'error': None,
                'response_time': time.time() - start,
                'response': text,
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'response_time': time.time() - start,
            }
