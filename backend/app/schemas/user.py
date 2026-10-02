from pydantic import BaseModel, Field


class UserBase(BaseModel):
    email: str = Field(...)


class UserCreate(UserBase):
    username: str = Field(...)
    password: str = Field(...)


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
