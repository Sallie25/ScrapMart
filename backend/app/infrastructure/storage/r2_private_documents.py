"""Private identity-evidence storage using a dedicated, non-public Cloudflare R2 bucket.

This adapter does not enable itself. An operator must configure credentials, the bucket,
access restrictions, encryption, retention, and a data-handling policy first. Keys are
opaque and never exposed as URLs. No temporary-file or public-storage fallback exists.
"""
from __future__ import annotations

import hashlib
import re

from app.infrastructure.storage.private_documents import (
    MAX_DOCUMENT_BYTES,
    VerificationInfrastructureUnavailable,
)

_HEX_KEY = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_ACCOUNT = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_BUCKET = re.compile(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]\Z", re.ASCII)
_PREFIX = "vendor-private-identity/"


class R2PrivateDocumentStorage:
    """Implements the existing private-document put/exists/delete/read contract."""

    def __init__(self, bucket: str, client):
        if not isinstance(bucket, str) or not _BUCKET.fullmatch(bucket):
            raise VerificationInfrastructureUnavailable()
        if client is None:
            raise VerificationInfrastructureUnavailable()
        self._bucket = bucket
        self._client = client

    @classmethod
    def from_settings(cls, settings):
        account = settings.private_document_r2_account_id
        bucket = settings.private_document_r2_bucket
        key_id = settings.private_document_r2_access_key_id
        secret = settings.private_document_r2_secret_access_key
        if (not isinstance(account, str) or not _ACCOUNT.fullmatch(account)
                or not isinstance(bucket, str) or not _BUCKET.fullmatch(bucket)
                or not key_id or not secret
                or not key_id.get_secret_value() or not secret.get_secret_value()):
            raise VerificationInfrastructureUnavailable()
        try:
            import boto3
            from botocore.config import Config
            client = boto3.client(
                "s3", endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
                region_name="auto",
                aws_access_key_id=key_id.get_secret_value(),
                aws_secret_access_key=secret.get_secret_value(),
                config=Config(signature_version="s3v4", connect_timeout=3,
                              read_timeout=8, retries={"max_attempts": 0}),
            )
            return cls(bucket, client)
        except Exception as exc:
            raise VerificationInfrastructureUnavailable() from None

    @staticmethod
    def _key(key: str) -> str:
        if not isinstance(key, str) or not _HEX_KEY.fullmatch(key):
            raise VerificationInfrastructureUnavailable()
        return _PREFIX + key

    def _head(self, obj: str):
        from botocore.exceptions import ClientError
        try:
            return self._client.head_object(Bucket=self._bucket, Key=obj)
        except ClientError as exc:
            # Missing objects are not infrastructure errors; all other failures fail closed.
            code = str(exc.response.get("Error", {}).get("Code", ""))
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"404", "NoSuchKey", "NotFound"} and status == 404:
                return None
            raise VerificationInfrastructureUnavailable() from None
        except Exception:
            raise VerificationInfrastructureUnavailable() from None

    def put(self, key: str, content: bytes) -> None:
        obj = self._key(key)
        if not isinstance(content, bytes) or not content or len(content) > MAX_DOCUMENT_BYTES:
            raise VerificationInfrastructureUnavailable()
        digest = hashlib.sha256(content).hexdigest()
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=obj, Body=content,
                ContentType="image/jpeg", CacheControl="private, no-store",
                Metadata={"sha256": digest},
            )
        except Exception:
            raise VerificationInfrastructureUnavailable() from None
        # An acknowledged write must be durably queryable and match these bytes.
        head = self._head(obj)
        if not head or head.get("ContentLength") != len(content) or (
            head.get("Metadata") or {}
        ).get("sha256") != digest:
            raise VerificationInfrastructureUnavailable()

    def exists(self, key: str) -> bool:
        return self._head(self._key(key)) is not None

    def read(self, key: str) -> bytes:
        obj = self._key(key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=obj)
            stream = response["Body"]
            try:
                content = stream.read(MAX_DOCUMENT_BYTES + 1)
            finally:
                stream.close()
            expected = (response.get("Metadata") or {}).get("sha256")
            if (not content or len(content) > MAX_DOCUMENT_BYTES or not expected
                    or hashlib.sha256(content).hexdigest() != expected):
                raise VerificationInfrastructureUnavailable()
            return content
        except Exception:
            raise VerificationInfrastructureUnavailable() from None

    def delete(self, key: str) -> None:
        obj = self._key(key)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=obj)
        except Exception:
            raise VerificationInfrastructureUnavailable() from None
        if self._head(obj) is not None:
            raise VerificationInfrastructureUnavailable()
