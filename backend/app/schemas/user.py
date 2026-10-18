from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pydantic_core import PydanticCustomError

from app.schemas.base import BaseDBSchema, IDMixin
from app.utils import is_email


class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(...)


class UserInDB(BaseDBSchema, UserBase):
    hashed_password: str = Field(...)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)

    model_config = ConfigDict(from_attributes=True)


class UserCreate(UserBase):
    password: str = Field(...)

    @field_validator('email', mode='before')
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator('username', mode='before')
    @classmethod
    def strip_username(cls, v: str) -> str:
        # TODO: trim дублируется на уровне схемы и DAO — оставить только в одном месте
        # docs/data_flow.md §1d: B4 — trim дважды: схема + DAO
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
    login: str = Field(...)
    password: str = Field(...)

    @field_validator('login')
    @classmethod
    def validate_login(cls, v: str) -> str:
        v = v.strip()

        if is_email(v):
            if len(v) > 320:
                raise PydanticCustomError(
                    'login_too_long',
                    'Email слишком длинный',
                )
        else:
            if len(v) < 3:
                raise PydanticCustomError(
                    'username_too_short',
                    'Имя пользователя должно быть не короче 3',
                )
            if len(v) > 64:
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


class UserResponse(IDMixin, UserBase):
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)

    model_config = ConfigDict(from_attributes=True)
