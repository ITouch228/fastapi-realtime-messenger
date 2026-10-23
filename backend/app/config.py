from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / 'app' / 'static'
TEMPLATES_DIR = BASE_DIR / 'app' / 'templates'
FILES_ROOT = BASE_DIR / 'uploads'
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

    # CORS
    ALLOWED_ORIGINS: list[str] = Field(
        default=[
            'http://localhost:8000',
            'http://127.0.0.1:8000',
            'https://localhost:8000',
            'https://127.0.0.1:8000',
            'https://itmessage.itouch.pw',
        ]
    )

    # Rate limits
    REGISTER_RATE_LIMIT: str = Field(default='10/hour')
    LOGIN_RATE_LIMIT: str = Field(default='5/minute')

    # Messages
    MAX_MESSAGE_LENGTH: int = Field(default=10000)

    # Files
    MAX_FILE_SIZE: int = Field(default=10 * 1024 * 1024)
    ALLOWED_FILE_EXTENSIONS: set[str] = Field(
        default={
            '.jpg',
            '.jpeg',
            '.png',
            '.gif',
            '.webp',
            '.txt',
            '.pdf',
            '.doc',
            '.docx',
            '.xls',
            '.xlsx',
            '.csv',
        }
    )

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / 'app' / '.env', env_file_encoding='utf-8', extra='ignore'
    )

    @property
    def db_url(self) -> str:
        return (
            f'postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@'
            f'{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}'
        )

    @cached_property
    def PRIVATE_KEY(self) -> str:
        try:
            return self.PRIVATE_KEY_PATH.read_text(encoding='utf-8')
        except FileNotFoundError:
            raise RuntimeError(
                f'RSA private key не найден: {self.PRIVATE_KEY_PATH}. '
                'Сгенерируйте ключи: openssl genpkey -algorithm RSA '
                f'-out {self.PRIVATE_KEY_PATH} -pkeyopt rsa_keygen_bits:2048'
            ) from None

    @cached_property
    def PUBLIC_KEY(self) -> str:
        try:
            return self.PUBLIC_KEY_PATH.read_text(encoding='utf-8')
        except FileNotFoundError:
            raise RuntimeError(
                f'RSA public key не найден: {self.PUBLIC_KEY_PATH}. '
                'Сгенерируйте ключи: openssl genpkey -algorithm RSA '
                f'-out {self.PRIVATE_KEY_PATH} -pkeyopt rsa_keygen_bits:2048'
            ) from None


settings = Settings()
