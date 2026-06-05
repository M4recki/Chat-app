"""
Application settings and configuration management using Pydantic.

This module provides centralized configuration handling with
environment variable support, type validation, and sensible defaults.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/Chat app"

    # Security
    secret_key: str = "change-me-in-production"
    chat_secret_key: str = "change-me-in-production"
    token_max_age: int = 3600  # 1 hour in seconds

    # Email
    email_receiver: str = "admin@example.com"
    email_password: str = ""
    email_sender: str = "noreply@chatapp.example.com"

    # AI
    ai_key: str = ""
    chatbot_history_limit: int = 8
    chatbot_max_tokens: int = 2048
    chatbot_timeout_seconds: float = 60.0
    chatbot_max_retries: int = 3
    chatbot_models: list[str] = [
        "stepfun-ai/step-3.5-flash",
        "mistralai/mistral-large-3-675b-instruct-2512",
    ]

    # Rate limiting
    rate_limit_login_max_requests: int = 10
    rate_limit_login_window_seconds: int = 60
    rate_limit_chatbot_max_requests: int = 8
    rate_limit_chatbot_window_seconds: int = 60
    rate_limit_search_max_requests: int = 30
    rate_limit_search_window_seconds: int = 60

    # Application
    environment: str = "development"
    debug: bool = True
    testing: bool = False
    app_name: str = "Chat App"
    app_version: str = "1.0.0"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    reload: bool = True

    @property
    def is_production(self) -> bool:
        """Check if running in production environment.

        Returns:
            bool: True if the environment is set to 'production',
                False otherwise"""
        return self.environment.lower() == "production"

    @property
    def is_testing(self) -> bool:
        """Check if running in test mode.

        Returns:
            bool: True if the environment is set to 'testing',
                False otherwise"""

        return self.testing or self.environment.lower() == "testing"


# Global settings instance
settings = Settings()
