"""LLM factory — returns configured LLM instances via ``LLMFactory``."""
from langchain_core.language_models import BaseChatModel
from app.core.config import get_settings


class LLMFactory:
    """Creates and configures LangChain chat model instances.

    Use the module-level ``get_llm_factory()`` to obtain the singleton.

    Example::

        llm = get_llm_factory().create()
        llm_with_tools = get_llm_factory().create_with_tools([my_tool])
    """

    def create(
        self,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        **kwargs,
    ) -> BaseChatModel:
        """Return a configured LLM instance.

        Args:
            provider: ``"openai"`` | ``"anthropic"``. Defaults to settings value.
            model: Model name. Defaults to settings value.
            temperature: Sampling temperature. Defaults to settings value.
            **kwargs: Extra kwargs forwarded to the LLM constructor.

        Returns:
            A ``BaseChatModel`` instance ready for use in agents.
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
            raise ValueError(
                f"Unsupported LLM provider: '{provider}'. Use 'openai' or 'anthropic'."
            )

    def create_with_tools(
        self,
        tools: list,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        **kwargs,
    ) -> BaseChatModel:
        """Return an LLM instance with tools already bound.

        Args:
            tools: List of LangChain tools to bind. If empty, behaves like ``create()``.
            provider: Passed through to ``create()``.
            model: Passed through to ``create()``.
            temperature: Passed through to ``create()``.
            **kwargs: Passed through to ``create()``.

        Returns:
            A ``BaseChatModel`` instance with tools bound (or unbound if ``tools`` is empty).
        """
        llm = self.create(provider=provider, model=model, temperature=temperature, **kwargs)
        return llm.bind_tools(tools) if tools else llm


# ── Module-level singleton ────────────────────────────────────────────────────

_llm_factory: LLMFactory | None = None


def get_llm_factory() -> LLMFactory:
    """Return the cached ``LLMFactory`` singleton."""
    global _llm_factory
    if _llm_factory is None:
        _llm_factory = LLMFactory()
    return _llm_factory


# ── Backward-compatible shim ──────────────────────────────────────────────────

def create_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    **kwargs,
) -> BaseChatModel:
    """Backward-compatible wrapper — prefer ``get_llm_factory().create()`` in new code."""
    return get_llm_factory().create(
        provider=provider, model=model, temperature=temperature, **kwargs
    )

