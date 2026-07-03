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
    discord_webhook_url: str = ""
    default_rate_limit_per_day: int = 100

    # SMS 인증 (알리고 Aligo). 미설정 시 개발환경에서만 코드 노출.
    sms_provider: str = ""          # "aligo" | "" (미설정)
    aligo_api_key: str = ""
    aligo_user_id: str = ""
    aligo_sender: str = ""          # 발신번호 (사전 등록 필요)

    class Config:
        env_file = "../../.env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
