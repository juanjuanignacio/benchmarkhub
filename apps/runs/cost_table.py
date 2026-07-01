# Price per 1K tokens (input, output) in USD
MODEL_COSTS = {
    'gpt-4o': (0.005, 0.015),
    'gpt-4o-mini': (0.00015, 0.0006),
    'gpt-4-turbo': (0.01, 0.03),
    'gpt-3.5-turbo': (0.0005, 0.0015),
    'claude-3-opus': (0.015, 0.075),
    'claude-3-5-sonnet': (0.003, 0.015),
    'claude-3-5-haiku': (0.0008, 0.004),
    'claude-3-sonnet': (0.003, 0.015),
    'claude-3-haiku': (0.00025, 0.00125),
    'mistral-large': (0.003, 0.009),
    'mistral-medium': (0.0027, 0.0081),
    'mistral-small': (0.001, 0.003),
    'gemini-1.5-pro': (0.0035, 0.0105),
    'gemini-1.5-flash': (0.00035, 0.00105),
    'llama-3.1-70b-versatile': (0.00059, 0.00079),
    'llama-3.1-8b-instant': (0.00005, 0.00008),
    'mixtral-8x7b-32768': (0.00024, 0.00024),
    # Default for unknown models
    'default': (0.001, 0.002),
}


def get_model_cost(model_name: str) -> tuple:
    """Return (cost_per_1k_input, cost_per_1k_output) for a model."""
    model_lower = model_name.lower()
    for pattern, costs in MODEL_COSTS.items():
        if pattern == 'default':
            continue
        if pattern in model_lower:
            return costs
    return MODEL_COSTS['default']


def estimate_cost(model_name: str, tokens_input: int, tokens_output: int) -> float:
    cost_in, cost_out = get_model_cost(model_name)
    return (tokens_input / 1000 * cost_in) + (tokens_output / 1000 * cost_out)


def estimate_run_cost(model_name: str, num_questions: int, avg_prompt_tokens: int = 150, avg_response_tokens: int = 50) -> float:
    """Estimate total cost before running."""
    return estimate_cost(model_name, num_questions * avg_prompt_tokens, num_questions * avg_response_tokens)
