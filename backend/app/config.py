from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "AgriDigitalTwin"
    app_env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./agri_twin.db"

    kamis_api_key: str = ""
    kma_api_key: str = ""
    kosis_api_key: str = ""
    ecos_api_key: str = ""

    api_secret_key: str = "change-this-secret-key"
    jwt_secret_key: str = "change-this-jwt-secret"

    wordpress_base_url: str = ""
    default_rate_limit_per_day: int = 100

    class Config:
        env_file = "../../.env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
