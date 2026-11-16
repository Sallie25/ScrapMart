"""Unit-only tests for the private R2 adapter; no real account or network calls."""
import hashlib
import io
from unittest.mock import Mock
import pytest
from botocore.exceptions import ClientError
from app.infrastructure.storage.private_documents import VerificationInfrastructureUnavailable
from app.infrastructure.storage.r2_private_documents import R2PrivateDocumentStorage

KEY = "b" * 64

def client_error(code="404", status=404):
    return ClientError({"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}}, "HeadObject")

def test_put_does_not_make_document_public_and_confirms_content():
    raw = b"sanitized jpeg test content"
    digest = hashlib.sha256(raw).hexdigest()
    client = Mock()
    client.head_object.return_value = {"ContentLength": len(raw), "Metadata": {"sha256": digest}}
    storage = R2PrivateDocumentStorage("scrapmart-id-private", client)
    storage.put(KEY, raw)
    kwargs = client.put_object.call_args.kwargs
    assert kwargs["Key"].startswith("vendor-private-identity/")
    assert kwargs["ContentType"] == "image/jpeg"
    assert kwargs["Metadata"] == {"sha256": digest}
    assert "ACL" not in kwargs
    assert "public" not in kwargs.get("CacheControl", "").split(",")

def test_missing_key_is_false_but_denied_access_is_not_false():
    client = Mock()
    client.head_object.side_effect = client_error()
    storage = R2PrivateDocumentStorage("scrapmart-id-private", client)
    assert storage.exists(KEY) is False
    client.head_object.side_effect = client_error("AccessDenied", 403)
    with pytest.raises(VerificationInfrastructureUnavailable):
        storage.exists(KEY)

def test_invalid_key_rejected_before_io():
    client = Mock()
    storage = R2PrivateDocumentStorage("scrapmart-id-private", client)
    with pytest.raises(VerificationInfrastructureUnavailable):
        storage.put("../escape", b"something")
    client.put_object.assert_not_called()

def test_verified_read_and_damaged_bytes_rejected():
    raw = b"the content"
    response = {"Metadata": {"sha256": hashlib.sha256(raw).hexdigest()}, "Body": io.BytesIO(raw)}
    client = Mock()
    client.get_object.return_value = response
    storage = R2PrivateDocumentStorage("scrapmart-id-private", client)
    assert storage.read(KEY) == raw
    client.get_object.return_value = {"Metadata": {"sha256": "0" * 64}, "Body": io.BytesIO(raw)}
    with pytest.raises(VerificationInfrastructureUnavailable):
        storage.read(KEY)

def test_failed_storage_confirmation_never_reports_success():
    client = Mock()
    client.head_object.return_value = {"ContentLength": 999, "Metadata": {"sha256": "0" * 64}}
    storage = R2PrivateDocumentStorage("scrapmart-id-private", client)
    with pytest.raises(VerificationInfrastructureUnavailable):
        storage.put(KEY, b"sanitized image")


def test_incomplete_configuration_fails_closed():
    from types import SimpleNamespace
    incomplete = SimpleNamespace(
        private_document_r2_account_id="a" * 32,
        private_document_r2_bucket="scrapmart-id-private",
        private_document_r2_access_key_id=None,
        private_document_r2_secret_access_key=None,
    )
    with pytest.raises(VerificationInfrastructureUnavailable):
        R2PrivateDocumentStorage.from_settings(incomplete)
