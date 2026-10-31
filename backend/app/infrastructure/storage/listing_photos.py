"""Public product-photo storage, deliberately separate from private ID evidence.

No provider is configured implicitly. A deployment adapter must durably store
immutable, sanitized JPEG objects in a separate public product-photo namespace,
provide HTTPS delivery URLs, and implement idempotent deletion/reconciliation.
Do not implement this using the private government-ID root or bucket.
"""
import re
from typing import Protocol
from urllib.parse import urlsplit
from app.core.config import Settings
from app.infrastructure.storage.private_documents import sanitize_document, InvalidDocument, MAX_DOCUMENT_BYTES

PHOTO_KEY = re.compile(r'listings/[A-Za-z0-9/_-]{1,200}\.jpg', re.ASCII)
MAX_PHOTO_BYTES = MAX_DOCUMENT_BYTES


class ListingPhotoUnavailable(RuntimeError):
    def __init__(self):
        super().__init__('Listing photo storage is unavailable')


class ListingPhotoStorage(Protocol):
    def put(self, key: str, content: bytes) -> None: ...
    def exists(self, key: str) -> bool: ...
    def public_url(self, key: str) -> str: ...
    def delete(self, key: str) -> None: ...


def get_listing_photo_storage(settings: Settings) -> ListingPhotoStorage:
    # An approved durable public adapter must replace this factory at deployment.
    # There is no local/static fallback and no reuse of private ID storage.
    raise ListingPhotoUnavailable()


def safe_photo_url(storage, key):
    if not isinstance(key, str) or not PHOTO_KEY.fullmatch(key):
        raise ListingPhotoUnavailable()
    try:
        url = storage.public_url(key)
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.path.endswith('/' + key):
            raise ListingPhotoUnavailable()
        return url
    except Exception:
        raise ListingPhotoUnavailable() from None


def sanitize_photo(content):
    # Share the existing bounded raster decoder/metadata stripper, not its
    # private storage backend or its objects. Both products accept JPEG/PNG.
    return sanitize_document(content)
