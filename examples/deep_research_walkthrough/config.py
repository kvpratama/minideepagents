"""Shared configuration for all deep_research walkthrough stages.

Loads settings from a local `.env` file so you can swap models or providers
without editing any stage.

Examples (.env):

    # Default: OpenAI o1-mini (uses OPENAI_API_KEY from env)
    MODEL=openai:o1-mini

    # Switch to Anthropic (uses ANTHROPIC_API_KEY from env)
    MODEL=anthropic:claude-sonnet-4-5-20250929

    # Switch to Google
    MODEL=google_genai:gemini-2.0-flash

    # Custom proxy / self-hosted (Ollama, vLLM, ...)
    MODEL=openai:llama3.1:70b
    BASE_URL=http://localhost:11434/v1
    API_KEY=sk-...
"""

from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Populate os.environ from .env so provider SDKs can find OPENAI_API_KEY,
# ANTHROPIC_API_KEY, TAVILY_API_KEY, LANGCHAIN_TRACING_V2, etc. via their
# default lookups.
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Attributes:
        model: LangChain model identifier with provider prefix
            (e.g. ``anthropic:claude-sonnet-4-5-20250929``,
            ``openai:gpt-4o``, ``google_genai:gemini-2.0-flash``).
        model_provider: Optional explicit provider override. Usually inferred
            from the ``model`` prefix.
        base_url: Optional API base URL (for proxies or self-hosted endpoints).
        api_key: Optional API key. If unset, ``init_chat_model`` falls back to
            the provider's standard env var (``OPENAI_API_KEY``,
            ``ANTHROPIC_API_KEY``, ...).
        temperature: Sampling temperature. Default 0 for deterministic output.
        tavily_api_key: API key for Tavily web search. Required for stages
            that use the ``tavily_search`` tool.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    model: str = "openai:o1-mini"
    model_provider: str | None = None
    base_url: str | None = None
    api_key: SecretStr | None = None
    temperature: float = 0.0
    tavily_api_key: SecretStr


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()  # ty:ignore[missing-argument]


def get_model() -> BaseChatModel:
    """Build a LangChain chat model from the current Settings.

    Only forwards optional fields that are explicitly set, so unset values
    fall through to ``init_chat_model``'s default credential resolution.
    """
    settings = get_settings()
    kwargs: dict = {"model": settings.model, "temperature": settings.temperature}
    if settings.model_provider:
        kwargs["model_provider"] = settings.model_provider
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    if settings.api_key is not None:
        kwargs["api_key"] = settings.api_key.get_secret_value()
    return init_chat_model(**kwargs)
