import time
import logging

from .base import BaseProviderBackend

logger = logging.getLogger(__name__)

COHERE_MODELS = [
    'command-r-plus',
    'command-r',
    'command',
    'command-light',
    'command-nightly',
]


class CohereBackend(BaseProviderBackend):
    def _get_client(self):
        try:
            import cohere
            api_key = self._get_api_key()
            return cohere.Client(api_key=api_key)
        except ImportError:
            raise ImportError("cohere package not installed. Run: pip install cohere")

    def complete(self, prompt: str, model: str, temperature: float = 0,
                 max_tokens: int = 512, images=None) -> dict:
        start = time.time()
        try:
            client = self._get_client()
            resp = client.generate(
                model=model,
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = resp.generations[0].text if resp.generations else ''
            return {'text': text, 'response_time': time.time() - start, 'error': None}
        except Exception as e:
            # Try chat endpoint
            try:
                client2 = self._get_client()
                resp2 = client2.chat(
                    model=model,
                    message=prompt,
                    temperature=temperature,
                )
                text = resp2.text if hasattr(resp2, 'text') else str(resp2)
                return {'text': text, 'response_time': time.time() - start, 'error': None}
            except Exception as e2:
                err = str(e2)
                logger.error(f"Cohere error: {err}", exc_info=True)
                return {'text': '', 'response_time': time.time() - start, 'error': err}

    def list_models(self) -> list:
        try:
            client = self._get_client()
            models = client.models.list()
            return [m.name for m in models.models if hasattr(m, 'name')]
        except Exception as e:
            logger.error(f"Failed to list Cohere models: {e}")
            return COHERE_MODELS

    def test_connection(self) -> dict:
        start = time.time()
        try:
            client = self._get_client()
            model = self.provider.default_model or 'command'
            resp = client.chat(
                model=model,
                message='Say "OK"',
                temperature=0,
            )
            text = resp.text if hasattr(resp, 'text') else 'OK'
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
