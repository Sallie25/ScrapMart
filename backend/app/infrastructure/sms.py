"""No provider is selected implicitly; adapters must use idempotent delivery."""
from typing import Protocol
from app.infrastructure.storage.private_documents import VerificationInfrastructureUnavailable


class SmsDelivery(Protocol):
    def send_code(self, phone_number: str, code: str, *, idempotency_key: str) -> None: ...


def get_sms_delivery() -> SmsDelivery:
    # No paid provider is introduced. Deployment must supply an approved adapter.
    # Offline tests inject an in-memory adapter; there is no demo/development code.
    raise VerificationInfrastructureUnavailable()
