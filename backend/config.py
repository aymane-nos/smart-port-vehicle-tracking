"""
Configuration centralisée du backend, chargée depuis les variables
d'environnement / le fichier .env (voir docker-compose.yml -> env_file).
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    PROJECT_NAME: str = "Smart Port Vehicle Tracking System"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "change_me_super_secret_key"

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://sp_admin:change_me@db:5432/smart_port_db"
    )

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:8501"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
