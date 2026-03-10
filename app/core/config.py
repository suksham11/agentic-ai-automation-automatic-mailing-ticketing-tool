from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "customer-support-agent"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    api_auth_enabled: bool = False
    api_key: str = ""
    api_key_header: str = "X-API-Key"
    rate_limit_enabled: bool = False
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    model_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    zendesk_base_url: str = ""
    zendesk_email: str = ""
    zendesk_api_token: str = ""
    gmail_sender_email: str = ""
    gmail_access_token: str = ""
    gmail_refresh_token: str = ""
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_token_url: str = "https://oauth2.googleapis.com/token"
    email_delivery_mode: str = "safe"
    email_allowed_recipients: str = ""

    postgres_dsn: str = "postgresql+psycopg://postgres:postgres@localhost:5432/support_agent"
    redis_url: str = "redis://localhost:6379/0"
    kb_dir: str = "./data/kb"
    analytics_log_path: str = "./data/eval/ticket_events.jsonl"


@lru_cache
def get_settings() -> Settings:
    return Settings()
