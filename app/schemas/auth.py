from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    id: str
    name: str
    email: str
    role: str
    department: str
    title: str
    department_id: str | None = None
    region_id: str | None = None
    is_admin: bool
    must_change_password: bool


class AuthData(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    user: UserOut
    token: str
    refresh_token: str


class LoginResponse(BaseModel):
    data: AuthData


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    token: str
    new_password: str


class MessageResponse(BaseModel):
    message: str


class ChangePasswordResponse(BaseModel):
    data: UserOut
