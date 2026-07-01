from .base import BaseProviderBackend


def get_backend(provider_model):
    """Return the appropriate backend instance for a provider."""
    from .ollama import OllamaBackend
    from .vllm import VLLMBackend
    from .openai_backend import OpenAIBackend
    from .anthropic_backend import AnthropicBackend
    from .cohere_backend import CohereBackend
    from .mistral_backend import MistralBackend
    from .gemini_backend import GeminiBackend
    from .groq_backend import GroqBackend

    backends = {
        'ollama': OllamaBackend,
        'vllm': VLLMBackend,
        'openai': OpenAIBackend,
        'anthropic': AnthropicBackend,
        'cohere': CohereBackend,
        'mistral': MistralBackend,
        'gemini': GeminiBackend,
        'groq': GroqBackend,
        'together': OpenAIBackend,  # Together AI uses OpenAI-compatible API
        'custom': VLLMBackend,
    }

    backend_class = backends.get(provider_model.provider_type, VLLMBackend)
    return backend_class(provider_model)


__all__ = ['BaseProviderBackend', 'get_backend']
