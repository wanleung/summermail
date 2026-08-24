from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gmail_user: str
    gmail_app_password: SecretStr
    summary_send_to: str
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    fetch_scope: str = "24h"
    schedule_cron: str = "0 6 * * *"
    scorer_llm_model: str = "ollama/qwen3.8"
    summariser_llm_model: str = "ollama/qwen3.8"
    llm_base_url: str = "http://llm-proxy:4000"
    litellm_master_key: SecretStr = SecretStr("ignored")
    ollama_base_url: str = "http://host.docker.internal:11434"
    # Per-LLM-call ceilings. The digest is one long generation over many emails,
    # so it needs far longer than a single email's score.
    scorer_llm_timeout: int = 120
    summariser_llm_timeout: int = 600
    # Ceiling for the whole scoring pass, which is one LLM call per new email
    scorer_run_timeout: int = 3600
    fetcher_run_timeout: int = 300
    summary_top_n: int = 20
    dashboard_url: str = "http://localhost:18001"
    db_path: str = "/data/email_summariser.db"
    schedule_timezone: str = "UTC"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
