"""Application configuration using Pydantic Settings."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All configuration values are loaded from environment variables via python-dotenv.

    Attributes:
        model: LLM model name to use for generation.
        model_provider: LLM provider name (e.g., 'openai').
        base_url: Base URL for the LLM provider API.
        api_key: API key for the LLM provider.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Required settings (loaded from environment variables)
    model: str = "openai/o1-mini"
    model_provider: str = "openai"
    base_url: str = "http://172.30.80.1:1234/v1"
    api_key: SecretStr


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton.

    Returns:
        The shared Settings instance.
    """
    return Settings()  # ty:ignore[missing-argument]
