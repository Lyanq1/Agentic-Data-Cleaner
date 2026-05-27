"""Application settings loaded from environment variables via pydantic-settings."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "Agentic Data Cleaner"
    app_version: str = "0.1.0"
    debug: bool = False

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"

    # LLM
    default_llm_provider: str = Field(default="openai")
    default_llm_model: str = Field(default="gpt-4o")
    openai_api_key: str = Field(default="")
    openai_base_url: str | None = Field(default=None, description="Custom OpenAI endpoint URL")
    anthropic_api_key: str = Field(default="")
    llm_temperature: float = 0.0

    # Database
    postgres_url: str = Field(default="postgresql://user:password@localhost:5432/agentic_data_cleaner_db")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")

    # Storage
    upload_dir: str = Field(default="/tmp/agentic_data_cleaner/data/uploads")
    output_dir: str = Field(default="/tmp/agentic_data_cleaner/data/outputs")
    max_upload_size_mb: int = 100

    # LangSmith Observability
    langchain_tracing_v2: bool = False
    langchain_api_key: str = Field(default="")
    langchain_project: str = Field(default="agentic-data-cleaner")

    # Graph
    graph_recursion_limit: int = 50
    # HITL: danh sách node names mà graph sẽ interrupt để chờ user confirm
    hitl_interrupt_before: list[str] = Field(
        default=["cleaner_node", "transformer_node"],
        description="Graph nodes where execution pauses for human approval",
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return cached Settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
