"""Application configuration using Pydantic Settings.

All steps in this walkthrough share this module. It reads settings from a
local `.env` file so you can swap models or providers without editing code.
"""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Attributes:
        model: LLM model name (e.g. ``openai/o1-mini``,
            ``anthropic:claude-sonnet-4-5-20250929``).
        model_provider: LangChain provider name (``openai``, ``anthropic``, ...).
        base_url: Base URL for the LLM provider API.
        api_key: API key for the LLM provider.
        tavily_api_key: API key for Tavily web search.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    model: str = "openai/o1-mini"
    model_provider: str = "openai"
    base_url: str = "https://api.openai.com/v1/chat/completions"
    api_key: SecretStr
    tavily_api_key: SecretStr


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton.

    Returns:
        The shared Settings instance.
    """
    return Settings() # ty:ignore[missing-argument]


def get_model() -> BaseChatModel:
    """Build a LangChain chat model from the current Settings.

    Returns:
        A configured chat model ready to be passed to ``create_agent`` or
        ``create_deep_agent``.
    """
    settings = get_settings()
    return init_chat_model(
        model=settings.model,
        model_provider=settings.model_provider,
        base_url=settings.base_url,
        api_key=settings.api_key.get_secret_value(),
        temperature=0.0,
    )
