from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pydantic_core import PydanticCustomError


class UserBase(BaseModel):
    """Базовая модель пользователя."""

    email: EmailStr
    username: str = Field(...)


class UserInDB(UserBase):
    """Полная модель пользователя."""

    id: int
    hashed_password: str = Field(...)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)

    model_config = ConfigDict(from_attributes=True)


class UserCreate(UserBase):
    """Модель для создания пользователя."""

    password: str = Field(...)

    @field_validator('email', mode='before')
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator('username', mode='before')
    @classmethod
    def strip_username(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        if len(v) < 3:
            raise PydanticCustomError(
                'username_too_short',
                'Имя пользователя должно быть не короче 3',
            )
        elif len(v) > 64:
            raise PydanticCustomError(
                'username_too_long',
                'Имя пользователя должно быть не более 64 символов',
            )
        return v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise PydanticCustomError(
                'password_too_short',
                'Пароль должен быть не короче 6 символов',
            )
        return v


class UserLogin(BaseModel):
    """Модель для авторизации пользователя."""

    login: str = Field(...)
    password: str = Field(...)

    @field_validator('login')
    @classmethod
    def validate_login(cls, v: str) -> str:
        if '@' not in v and len(v) < 3:
            raise PydanticCustomError(
                'username_too_short',
                'Имя пользователя должно быть не короче 3',
            )
        if '@' not in v and len(v) > 64:
            raise PydanticCustomError(
                'username_too_long',
                'Имя пользователя должно быть не более 64 символов',
            )
        return v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise PydanticCustomError(
                'password_too_short',
                'Пароль должен быть не короче 6 символов',
            )
        return v


class UserResponse(UserBase):
    """Модель для фронтенда."""

    id: int
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    session_id: str | None = None
