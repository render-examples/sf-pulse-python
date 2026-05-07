from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.local", extra="ignore")

    database_url: str = ""
    redis_url: str = ""

    host: str = "0.0.0.0"
    port: int = 8000
    app_url: str = ""
    render_external_url: str = ""

    cron_secret: str = ""

    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@example.com"

    llm_api_key: str = ""
    llm_provider: str = ""
    llm_model: str = ""

    render_api_key: str = ""
    sf_pulse_workflow_slug: str = ""

    @property
    def public_app_url(self) -> str:
        return self.app_url or self.render_external_url or f"http://{self.host}:{self.port}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
