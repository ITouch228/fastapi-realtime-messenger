from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / 'app' / 'static'
TEMPLATES_DIR = BASE_DIR / 'app' / 'templates'
FILES_ROOT = STATIC_DIR / 'files'
LOGS_DIR = BASE_DIR / 'logs'


class Settings(BaseSettings):
    # Postgres
    DB_USER: str = Field(default='postgres')
    DB_PASSWORD: str = Field(default='')
    DB_HOST: str = Field(default='localhost')
    DB_PORT: int = Field(default=5432)
    DB_NAME: str = Field(default='messenger_db')

    # JWT
    ALGORITHM: str = 'RS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=120)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)
    PRIVATE_KEY_PATH: Path = Field(default=BASE_DIR / 'keys' / 'private.pem')
    PUBLIC_KEY_PATH: Path = Field(default=BASE_DIR / 'keys' / 'public.pem')

    # Redis
    REDIS_URL: str = Field(default='redis://localhost:6379/0')

    # Cookie
    # Безопасный дефолт: куки только по HTTPS. Для локальной разработки
    # по http задайте COOKIE_SECURE=false в .env.
    COOKIE_SECURE: bool = Field(default=True)
    COOKIE_SAMESITE: Literal['lax', 'strict', 'none'] = Field(default='lax')

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / 'app' / '.env', env_file_encoding='utf-8', extra='ignore'
    )

    def get_db_url(self):
        return (
            f'postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@'
            f'{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}'
        )

    @property
    def PRIVATE_KEY(self) -> str:
        return self.PRIVATE_KEY_PATH.read_text(encoding='utf-8')

    @property
    def PUBLIC_KEY(self) -> str:
        return self.PUBLIC_KEY_PATH.read_text(encoding='utf-8')


settings = Settings()
