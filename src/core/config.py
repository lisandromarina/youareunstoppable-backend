import os
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql+psycopg2://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql+psycopg2://")
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")

    parsed = urlparse(url)
    if not parsed.scheme.startswith("postgresql"):
        return url
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "pgbouncer"]
    return urlunparse(parsed._replace(query=urlencode(query)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    jwt_secret: str = ""
    google_client_id: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    cookie_secure: bool = False

    @model_validator(mode="after")
    def require_runtime_secrets(self):
        if not self.database_url:
            self.database_url = os.environ.get("POSTGRES_URL", "")
        self.database_url = normalize_database_url(self.database_url)
        if not self.database_url:
            raise ValueError("Set DATABASE_URL or POSTGRES_URL")
        if not self.jwt_secret:
            raise ValueError("Set JWT_SECRET")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
