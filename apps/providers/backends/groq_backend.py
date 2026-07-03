import time
import logging

from .base import BaseProviderBackend

logger = logging.getLogger(__name__)

GROQ_MODELS = [
    'llama-3.1-70b-versatile',
    'llama-3.1-8b-instant',
    'llama3-70b-8192',
    'llama3-8b-8192',
    'mixtral-8x7b-32768',
    'gemma2-9b-it',
    'gemma-7b-it',
]


class GroqBackend(BaseProviderBackend):
    def _get_client(self):
        try:
            from groq import Groq
            api_key = self._get_api_key()
            return Groq(api_key=api_key)
        except ImportError:
            raise ImportError("groq package not installed. Run: pip install groq")

    def complete(self, prompt: str, model: str, temperature: float = 0,
                 max_tokens: int = 512, images=None, audio=None) -> dict:
        start = time.time()
        try:
            client = self._get_client()

            # Groq hosts Whisper models for ASR via the transcriptions endpoint
            if audio and 'whisper' in model.lower():
                import base64
                import io
                buf = io.BytesIO(base64.b64decode(audio['data']))
                buf.name = f"audio.{audio.get('format', 'wav')}"
                resp = client.audio.transcriptions.create(model=model, file=buf)
                return {'text': resp.text or '', 'response_time': time.time() - start,
                        'error': None}
            if audio:
                return self._unsupported(start, 'audio (use a whisper-* model)', 'Groq')

            if images:
                # OpenAI-style vision content parts (llama-4 vision models)
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
            logger.error(f"Groq error: {err}", exc_info=True)
            return {'text': '', 'response_time': time.time() - start, 'error': err}

    def list_models(self) -> list:
        try:
            client = self._get_client()
            models = client.models.list()
            return sorted([m.id for m in models.data if hasattr(m, 'id')])
        except Exception as e:
            logger.error(f"Failed to list Groq models: {e}")
            return GROQ_MODELS

    def test_connection(self) -> dict:
        start = time.time()
        try:
            client = self._get_client()
            model = self.provider.default_model or 'llama-3.1-8b-instant'
            resp = client.chat.completions.create(
                model=model,
                messages=[{'role': 'user', 'content': 'Say "OK"'}],
                temperature=0,
                max_tokens=5,
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
