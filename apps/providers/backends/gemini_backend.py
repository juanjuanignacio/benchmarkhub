import time
import logging

from .base import BaseProviderBackend

logger = logging.getLogger(__name__)

GEMINI_MODELS = [
    'gemini-1.5-pro',
    'gemini-1.5-flash',
    'gemini-1.5-flash-8b',
    'gemini-pro',
    'gemini-1.0-pro',
]


class GeminiBackend(BaseProviderBackend):
    def _configure(self):
        try:
            import google.generativeai as genai
            api_key = self._get_api_key()
            genai.configure(api_key=api_key)
            return genai
        except ImportError:
            raise ImportError(
                "google-generativeai package not installed. Run: pip install google-generativeai"
            )

    def complete(self, prompt: str, model: str, temperature: float = 0,
                 max_tokens: int = 512, images=None) -> dict:
        start = time.time()
        try:
            genai = self._configure()
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            model_obj = genai.GenerativeModel(
                model_name=model,
                generation_config=generation_config,
            )
            if images:
                import base64
                import io
                from PIL import Image
                parts = []
                for b64 in images:
                    img = Image.open(io.BytesIO(base64.b64decode(b64)))
                    parts.append(img)
                parts.append(prompt)
                response = model_obj.generate_content(parts)
            else:
                response = model_obj.generate_content(prompt)
            text = response.text if hasattr(response, 'text') else ''
            return {'text': text, 'response_time': time.time() - start, 'error': None}
        except Exception as e:
            err = str(e)
            logger.error(f"Gemini error: {err}", exc_info=True)
            return {'text': '', 'response_time': time.time() - start, 'error': err}

    def list_models(self) -> list:
        try:
            genai = self._configure()
            models = genai.list_models()
            return [
                m.name.replace('models/', '')
                for m in models
                if 'generateContent' in m.supported_generation_methods
            ]
        except Exception as e:
            logger.error(f"Failed to list Gemini models: {e}")
            return GEMINI_MODELS

    def test_connection(self) -> dict:
        start = time.time()
        try:
            genai = self._configure()
            model = self.provider.default_model or 'gemini-1.5-flash'
            model_obj = genai.GenerativeModel(model_name=model)
            response = model_obj.generate_content('Say "OK"')
            text = response.text if hasattr(response, 'text') else 'OK'
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
