from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_service_key: str
    frontend_origin: str = "http://localhost:5173"
    fred_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
