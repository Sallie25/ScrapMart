"""Login input preserves password content; it is never a response model."""
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.modules.auth.email_identity_policy import canonical_registration_key
from app.modules.auth.security import MAX_PASSWORD_LENGTH


class BuyerLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    email: str = Field(repr=False)
    password: SecretStr = Field(repr=False)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value: str) -> str:
        return canonical_registration_key(value)

    @field_validator("password")
    @classmethod
    def password_valid(cls, value: SecretStr) -> SecretStr:
        # Match the existing verifier's input boundary, not signup policy.
        password = value.get_secret_value()
        if not 1 <= len(password) <= MAX_PASSWORD_LENGTH or "\x00" in password:
            raise ValueError("Invalid password")
        try:
            password.encode("utf-8")
        except UnicodeError:
            raise ValueError("Invalid password") from None
        return value
