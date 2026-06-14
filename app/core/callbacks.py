"""Custom LangChain callbacks for tracking token usage."""

from typing import Any, Dict, List
from langchain_core.callbacks import AsyncCallbackHandler, BaseCallbackHandler
from langchain_core.outputs import LLMResult

class TokenTrackerCallback(AsyncCallbackHandler, BaseCallbackHandler):
    """Tracks token usage across LLM invocations for a single agent run."""

    def __init__(self) -> None:
        super().__init__()
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def _extract_usage(self, response: LLMResult) -> None:
        """Helper to extract token usage from LLMResult."""
        if response.llm_output and "token_usage" in response.llm_output:
            usage = response.llm_output["token_usage"]
            self.total_tokens += usage.get("total_tokens", 0)
            self.prompt_tokens += usage.get("prompt_tokens", 0)
            self.completion_tokens += usage.get("completion_tokens", 0)
        else:
            # Fallback for models that embed usage in the message metadata (e.g. Anthropic/newer OpenAI)
            for gen_list in response.generations:
                for chunk in gen_list:
                    if hasattr(chunk, "message") and hasattr(chunk.message, "usage_metadata"):
                        usage = chunk.message.usage_metadata
                        if usage:
                            self.total_tokens += usage.get("total_tokens", 0)
                            self.prompt_tokens += usage.get("input_tokens", 0)
                            self.completion_tokens += usage.get("output_tokens", 0)

    def on_llm_end(
        self,
        response: LLMResult,
        **kwargs: Any,
    ) -> None:
        """Called when LLM (sync) ends."""
        self._extract_usage(response)

    async def on_llm_end_async(
        self,
        response: LLMResult,
        **kwargs: Any,
    ) -> None:
        """Called when LLM (async) ends."""
        self._extract_usage(response)

    def get_metrics(self) -> Dict[str, int]:
        """Return the accumulated token metrics."""
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }
