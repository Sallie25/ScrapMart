"""Buyer signup input only; never serialize credential-bearing input models."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.modules.auth.security import PasswordPolicyError, validate_password_policy
from app.modules.auth.email_identity_policy import InvalidRegistrationEmail, canonical_registration_key


def normalize_signup_email(value: str) -> str:
    try:
        return canonical_registration_key(value)
    except InvalidRegistrationEmail:
        raise ValueError("Invalid email address") from None


class BuyerSignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    email: str = Field(repr=False)
    password: SecretStr = Field(repr=False)
    full_name: str = Field(min_length=1, max_length=150, repr=False)
    phone_number: str | None = Field(default=None, max_length=20, repr=False)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value: str) -> str:
        return normalize_signup_email(value)

    @field_validator("password")
    @classmethod
    def password_valid(cls, value: SecretStr) -> SecretStr:
        try:
            validate_password_policy(value.get_secret_value())
        except PasswordPolicyError:
            raise ValueError("Invalid password") from None
        return value

    @field_validator("full_name", "phone_number")
    @classmethod
    def text_valid(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                value.encode("utf-8")
            except UnicodeError:
                raise ValueError("Invalid text") from None
            if "\x00" in value or not value.strip():
                raise ValueError("Invalid text")
        return value


ACKNOWLEDGMENT = "If registration was successful, you can now sign in."


class BuyerSignupAcknowledgment(BaseModel):
    message: Literal["If registration was successful, you can now sign in."] = ACKNOWLEDGMENT
