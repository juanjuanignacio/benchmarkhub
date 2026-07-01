import time
import logging
import requests

from .base import BaseProviderBackend

logger = logging.getLogger(__name__)


class VLLMBackend(BaseProviderBackend):
    DEFAULT_BASE_URL = 'http://localhost:8000'

    def _base_url(self):
        return self._get_base_url(self.DEFAULT_BASE_URL).rstrip('/')

    def complete(self, prompt: str, model: str, temperature: float = 0,
                 max_tokens: int = 512, images=None) -> dict:
        start = time.time()
        # Try OpenAI-compatible chat completions first
        url = f"{self._base_url()}/v1/chat/completions"
        headers = {'Content-Type': 'application/json'}
        api_key = self._get_api_key()
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        payload = {
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            text = data['choices'][0]['message']['content']
            return {'text': text, 'response_time': time.time() - start, 'error': None}
        except requests.exceptions.ConnectionError as e:
            err = f"Cannot connect to vLLM at {self._base_url()}: {e}"
            logger.error(err)
            return {'text': '', 'response_time': time.time() - start, 'error': err}
        except requests.exceptions.HTTPError as e:
            # Fall back to completions endpoint
            try:
                comp_url = f"{self._base_url()}/v1/completions"
                comp_payload = {
                    'model': model,
                    'prompt': prompt,
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                }
                resp2 = requests.post(comp_url, json=comp_payload, headers=headers, timeout=120)
                resp2.raise_for_status()
                data2 = resp2.json()
                text = data2['choices'][0]['text']
                return {'text': text, 'response_time': time.time() - start, 'error': None}
            except Exception as e2:
                err = str(e2)
                return {'text': '', 'response_time': time.time() - start, 'error': err}
        except Exception as e:
            err = str(e)
            logger.error(f"vLLM error: {err}", exc_info=True)
            return {'text': '', 'response_time': time.time() - start, 'error': err}

    def list_models(self) -> list:
        try:
            url = f"{self._base_url()}/v1/models"
            headers = {}
            api_key = self._get_api_key()
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return [m['id'] for m in data.get('data', [])]
        except Exception as e:
            logger.error(f"Failed to list vLLM models: {e}")
            return []

    def test_connection(self) -> dict:
        start = time.time()
        try:
            url = f"{self._base_url()}/v1/models"
            headers = {}
            api_key = self._get_api_key()
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            models = self.list_models()
            return {
                'success': True,
                'error': None,
                'response_time': time.time() - start,
                'models': models,
            }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': f"Cannot connect to vLLM at {self._base_url()}",
                'response_time': time.time() - start,
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'response_time': time.time() - start,
            }
