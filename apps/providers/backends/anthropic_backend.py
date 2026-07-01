import time
import logging

from .base import BaseProviderBackend

logger = logging.getLogger(__name__)

ANTHROPIC_MODELS = [
    'claude-3-5-sonnet-20241022',
    'claude-3-5-haiku-20241022',
    'claude-3-opus-20240229',
    'claude-3-sonnet-20240229',
    'claude-3-haiku-20240307',
]


class AnthropicBackend(BaseProviderBackend):
    def _get_client(self):
        try:
            import anthropic
            api_key = self._get_api_key()
            kwargs = {'api_key': api_key} if api_key else {}
            return anthropic.Anthropic(**kwargs)
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

    def complete(self, prompt: str, model: str, temperature: float = 0,
                 max_tokens: int = 512, images=None) -> dict:
        start = time.time()
        try:
            client = self._get_client()
            if images:
                content = []
                for b64 in images:
                    content.append({
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': 'image/jpeg',
                            'data': b64,
                        },
                    })
                content.append({'type': 'text', 'text': prompt})
                messages = [{'role': 'user', 'content': content}]
            else:
                messages = [{'role': 'user', 'content': prompt}]
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages,
            )
            text = resp.content[0].text if resp.content else ''
            return {'text': text, 'response_time': time.time() - start, 'error': None}
        except Exception as e:
            err = str(e)
            logger.error(f"Anthropic error: {err}", exc_info=True)
            return {'text': '', 'response_time': time.time() - start, 'error': err}

    def list_models(self) -> list:
        return ANTHROPIC_MODELS

    def test_connection(self) -> dict:
        start = time.time()
        try:
            client = self._get_client()
            model = self.provider.default_model or 'claude-3-haiku-20240307'
            resp = client.messages.create(
                model=model,
                max_tokens=5,
                temperature=0,
                messages=[{'role': 'user', 'content': 'Say "OK"'}],
            )
            text = resp.content[0].text if resp.content else ''
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
