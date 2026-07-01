import time
import logging

from .base import BaseProviderBackend

logger = logging.getLogger(__name__)

OPENAI_MODELS = [
    'gpt-4o',
    'gpt-4o-mini',
    'gpt-4-turbo',
    'gpt-4-turbo-preview',
    'gpt-4',
    'gpt-3.5-turbo',
    'gpt-3.5-turbo-16k',
]


class OpenAIBackend(BaseProviderBackend):
    def _get_client(self):
        try:
            import openai
            api_key = self._get_api_key()
            base_url = self._get_base_url()
            kwargs = {'api_key': api_key} if api_key else {}
            if base_url:
                kwargs['base_url'] = base_url
            return openai.OpenAI(**kwargs)
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")

    def complete(self, prompt: str, model: str, temperature: float = 0,
                 max_tokens: int = 512, images=None) -> dict:
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
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content or ''
            return {'text': text, 'response_time': time.time() - start, 'error': None}
        except Exception as e:
            err = str(e)
            logger.error(f"OpenAI error: {err}", exc_info=True)
            return {'text': '', 'response_time': time.time() - start, 'error': err}

    def list_models(self) -> list:
        try:
            client = self._get_client()
            models = client.models.list()
            return sorted(
                [m.id for m in models.data if 'gpt' in m.id.lower()],
                reverse=True
            )
        except Exception as e:
            logger.error(f"Failed to list OpenAI models: {e}")
            return OPENAI_MODELS

    def test_connection(self) -> dict:
        start = time.time()
        try:
            client = self._get_client()
            model = self.provider.default_model or 'gpt-3.5-turbo'
            resp = client.chat.completions.create(
                model=model,
                messages=[{'role': 'user', 'content': 'Say "OK"'}],
                max_tokens=5,
                temperature=0,
            )
            text = resp.choices[0].message.content or ''
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
