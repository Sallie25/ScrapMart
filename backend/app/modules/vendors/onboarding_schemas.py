"""Private shop inputs only; verification and ownership fields are forbidden."""
import unicodedata
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ShopInformationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    business_name: str = Field(default=None, max_length=200, repr=False)
    shop_location: str = Field(default=None, max_length=200, repr=False)
    shop_address: str = Field(default=None, max_length=500, repr=False)

    @field_validator("business_name", "shop_location", "shop_address", mode="before")
    @classmethod
    def normalized_text(cls, value):
        if not isinstance(value, str):
            raise ValueError("Invalid shop information")
        try:
            value.encode("utf-8")
        except UnicodeError:
            raise ValueError("Invalid shop information") from None
        # Permit Unicode names/addresses; reject control/format characters rather
        # than silently removing hidden input. Store a single-line NFC value.
        if any(unicodedata.category(c).startswith("C") for c in value):
            raise ValueError("Invalid shop information")
        value = " ".join(unicodedata.normalize("NFC", value).split())
        if not value:
            raise ValueError("Invalid shop information")
        return value

    @model_validator(mode="after")
    def nonempty_patch(self):
        if not self.model_fields_set:
            raise ValueError("Provide shop information")
        return self
