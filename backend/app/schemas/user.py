from pydantic import BaseModel, EmailStr, Field, field_validator


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)

    @field_validator('username', 'email', mode='before')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class UserLogin(UserBase):
    password: str = Field(...)


class UserInDB(UserBase):
    id: int
    username: str = Field(...)
    hashed_password: str = Field(...)

    class Config:
        from_attributes = True


class UserResponse(BaseModel):
    id: int
    email: str
    username: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: int | None = None
