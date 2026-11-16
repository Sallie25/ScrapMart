"""No provider is selected implicitly; adapters must use idempotent delivery."""
from typing import Protocol
from app.infrastructure.storage.private_documents import VerificationInfrastructureUnavailable


class SmsDelivery(Protocol):
    def send_code(self, phone_number: str, code: str, *, idempotency_key: str) -> None: ...


def get_sms_delivery() -> SmsDelivery:
    from app.core.config import get_settings
    from app.infrastructure.providers import load_adapter
    try:
        settings = get_settings()
        return load_adapter(settings.sms_delivery_factory, settings, ('send_code',))
    except Exception:
        raise VerificationInfrastructureUnavailable() from None
