"""LLM factory — trả về LLM instance dựa theo provider config."""
from langchain_core.language_models import BaseChatModel
from app.core.config import get_settings


def create_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    **kwargs,
) -> BaseChatModel:
    """Return a configured LLM instance.

    Args:
        provider: "openai" | "anthropic". Defaults to settings.default_llm_provider.
        model: Model name. Defaults to settings.default_llm_model.
        temperature: Sampling temperature. Defaults to settings.llm_temperature.
        **kwargs: Extra kwargs forwarded to the LLM constructor.

    Returns:
        A BaseChatModel instance ready for use in agents.
    """
    settings = get_settings()
    provider = provider or settings.default_llm_provider
    model = model or settings.default_llm_model
    temperature = temperature if temperature is not None else settings.llm_temperature

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=settings.llm_max_tokens,
            api_key=settings.openai_api_key,
            **kwargs,
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=settings.llm_max_tokens,
            api_key=settings.anthropic_api_key,
            **kwargs,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: '{provider}'. Use 'openai' or 'anthropic'.")
