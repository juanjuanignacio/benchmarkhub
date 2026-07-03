import time
import logging

from .base import BaseProviderBackend

logger = logging.getLogger(__name__)

ANTHROPIC_MODELS = [
    'claude-opus-4-8',
    'claude-opus-4-7',
    'claude-opus-4-6',
    'claude-sonnet-5',
    'claude-sonnet-4-6',
    'claude-sonnet-4-5',
    'claude-haiku-4-5',
]

# Model families that reject sampling parameters (temperature/top_p/top_k
# return HTTP 400 on these models).
_NO_SAMPLING_PREFIXES = (
    'claude-fable-5',
    'claude-mythos',
    'claude-opus-4-7',
    'claude-opus-4-8',
    'claude-sonnet-5',
)


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
                 max_tokens: int = 512, images=None, audio=None) -> dict:
        start = time.time()
        if audio:
            return self._unsupported(start, 'audio', 'Anthropic')
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
            kwargs = {
                'model': model,
                'max_tokens': max_tokens,
                'messages': messages,
            }
            # Current models (Opus 4.7+, Sonnet 5, Fable 5) reject temperature
            if not model.startswith(_NO_SAMPLING_PREFIXES):
                kwargs['temperature'] = temperature
            resp = client.messages.create(**kwargs)
            text = next((b.text for b in resp.content if b.type == 'text'), '')
            return {'text': text, 'response_time': time.time() - start, 'error': None}
        except Exception as e:
            err = str(e)
            logger.error(f"Anthropic error: {err}", exc_info=True)
            return {'text': '', 'response_time': time.time() - start, 'error': err}

    def list_models(self) -> list:
        try:
            client = self._get_client()
            return [m.id for m in client.models.list()]
        except Exception as e:
            logger.warning(f"Failed to list Anthropic models, using static list: {e}")
            return ANTHROPIC_MODELS

    def test_connection(self) -> dict:
        start = time.time()
        try:
            client = self._get_client()
            model = self.provider.default_model or 'claude-haiku-4-5'
            kwargs = {
                'model': model,
                'max_tokens': 5,
                'messages': [{'role': 'user', 'content': 'Say "OK"'}],
            }
            if not model.startswith(_NO_SAMPLING_PREFIXES):
                kwargs['temperature'] = 0
            resp = client.messages.create(**kwargs)
            text = next((b.text for b in resp.content if b.type == 'text'), '')
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
