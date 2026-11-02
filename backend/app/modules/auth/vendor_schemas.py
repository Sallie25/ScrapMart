"""Strict Vendor inputs; credential values never appear in representations."""
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from app.modules.auth.registration_schemas import BuyerSignupRequest
from app.modules.auth.login_schemas import BuyerLoginRequest


def business_name_valid(value: str) -> str:
    if not value.strip() or "\x00" in value:
        raise ValueError("Invalid business name")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValueError("Invalid business name") from None
    return value


class VendorSignupRequest(BuyerSignupRequest):
    business_name: str = Field(min_length=1, max_length=200, repr=False)
    _business_name = field_validator("business_name")(business_name_valid)


class VendorEnrollmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    business_name: str = Field(min_length=1, max_length=200, repr=False)
    current_password: SecretStr = Field(repr=False)
    _business_name = field_validator("business_name")(business_name_valid)

    @field_validator("current_password")
    @classmethod
    def password_valid(cls, value: SecretStr) -> SecretStr:
        return BuyerLoginRequest.password_valid(value)
