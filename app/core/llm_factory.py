"""LLM factory — creates ChatModel instances from app settings."""
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from app.config.config import get_settings
import logging

logger = logging.getLogger(__name__)

def create_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> BaseChatModel:
    settings = get_settings()
    provider = provider or settings.default_llm_provider
    model = model or settings.default_llm_model
    temperature = temperature if temperature is not None else settings.llm_temperature

    if provider == "openai":

        kwargs = {
            "model": model,
            "temperature": temperature,
            "api_key": settings.openai_api_key,
        }
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
            
        return ChatOpenAI(**kwargs)
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            temperature=temperature,
            api_key=settings.anthropic_api_key,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {provider!r}")
