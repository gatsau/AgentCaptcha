"""Pydantic settings loaded from .env."""
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator


class Settings(BaseSettings):
    anthropic_api_key: str = Field("", env="ANTHROPIC_API_KEY")
    jwt_secret: str = Field("change-me-to-a-random-32-char-secret", env="JWT_SECRET")
    database_url: str = Field("./agentcaptcha.db", env="DATABASE_URL")
    pow_difficulty: int = Field(4, env="POW_DIFFICULTY")
    pow_timeout_ms: int = Field(200, env="POW_TIMEOUT_MS")
    decision_rounds: int = Field(10, env="DECISION_ROUNDS")
    decision_timeout_s: float = Field(1.5, env="DECISION_TIMEOUT_S")
    # Rate limiting
    rate_limit_requests: int = Field(10, env="RATE_LIMIT_REQUESTS")
    rate_limit_window_s: int = Field(60, env="RATE_LIMIT_WINDOW_S")

    @model_validator(mode="after")
    def derive_mock_mode(self) -> "Settings":
        self._use_mock = not bool(self.anthropic_api_key.strip())
        return self

    @property
    def use_mock_challenges(self) -> bool:
        return self._use_mock

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
