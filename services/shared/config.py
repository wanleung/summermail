from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gmail_user: str = ""
    gmail_app_password: str = ""
    summary_send_to: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    fetch_scope: str = "24h"
    schedule_cron: str = "0 6 * * *"
    scorer_llm_model: str = "ollama/llama3.2"
    summariser_llm_model: str = "ollama/llama3.2"
    llm_base_url: str = "http://llm-proxy:4000"
    ollama_base_url: str = "http://host.docker.internal:11434"
    summary_top_n: int = 20
    db_path: str = "/data/email_summariser.db"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
