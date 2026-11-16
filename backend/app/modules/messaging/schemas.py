import uuid
import unicodedata
from pydantic import BaseModel, ConfigDict, StrictStr, field_validator


class StartConversation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    listing_id: uuid.UUID


class SendMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    content: StrictStr
    request_id: uuid.UUID | None = None

    @field_validator('content')
    @classmethod
    def text(cls, value):
        if not 1 <= len(value) <= 4000 or not value.strip():
            raise ValueError('Text must contain 1–4000 characters')
        if any(unicodedata.category(c) in {'Cs', 'Cc'} and c not in '\n\r\t' for c in value):
            raise ValueError('Invalid text character')
        return value


class ReadMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message_id: uuid.UUID
