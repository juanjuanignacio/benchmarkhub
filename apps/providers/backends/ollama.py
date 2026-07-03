import time
import logging
import requests

from .base import BaseProviderBackend

logger = logging.getLogger(__name__)


class OllamaBackend(BaseProviderBackend):
    DEFAULT_BASE_URL = 'http://localhost:11434'

    def _base_url(self):
        return self._get_base_url(self.DEFAULT_BASE_URL).rstrip('/')

    def complete(self, prompt: str, model: str, temperature: float = 0,
                 max_tokens: int = 512, images=None, audio=None) -> dict:
        start = time.time()
        if audio:
            return self._unsupported(start, 'audio', 'Ollama')
        url = f"{self._base_url()}/api/generate"
        payload = {
            'model': model,
            'prompt': prompt,
            'stream': False,
            'options': {
                'temperature': temperature,
                'num_predict': max_tokens,
            }
        }
        if images:
            # Native multimodal support (llava, llama3.2-vision, qwen2.5-vl, ...)
            payload['images'] = list(images)
        try:
            resp = requests.post(url, json=payload, timeout=240)
            resp.raise_for_status()
            data = resp.json()
            text = data.get('response', '')
            return {'text': text, 'response_time': time.time() - start, 'error': None}
        except requests.exceptions.ConnectionError as e:
            err = f"Cannot connect to Ollama at {self._base_url()}: {e}"
            logger.error(err)
            return {'text': '', 'response_time': time.time() - start, 'error': err}
        except requests.exceptions.Timeout:
            err = f"Request to Ollama timed out"
            return {'text': '', 'response_time': time.time() - start, 'error': err}
        except Exception as e:
            err = str(e)
            logger.error(f"Ollama error: {err}", exc_info=True)
            return {'text': '', 'response_time': time.time() - start, 'error': err}

    def list_models(self) -> list:
        try:
            url = f"{self._base_url()}/api/tags"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            models = data.get('models', [])
            return [m['name'] for m in models if 'name' in m]
        except Exception as e:
            logger.error(f"Failed to list Ollama models: {e}")
            return []

    def test_connection(self) -> dict:
        start = time.time()
        try:
            url = f"{self._base_url()}/api/tags"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return {
                'success': True,
                'error': None,
                'response_time': time.time() - start,
                'models': self.list_models(),
            }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': f"Cannot connect to Ollama at {self._base_url()}",
                'response_time': time.time() - start,
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'response_time': time.time() - start,
            }
