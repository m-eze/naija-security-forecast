from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    SYNC_DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    ACLED_EMAIL: str = ""
    ACLED_API_KEY: str = ""  # From acleddata.com account → Access Portal

    SECRET_KEY: str = "change-me"
    ENVIRONMENT: str = "development"


settings = Settings()
