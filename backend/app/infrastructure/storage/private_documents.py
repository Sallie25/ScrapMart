"""Private opaque objects; durable-volume backend is opt-in, never a temp fallback."""
import io
import os
from pathlib import Path
import re
import secrets
from typing import Protocol
from PIL import Image, UnidentifiedImageError
from app.core.config import Settings

MAX_DOCUMENT_BYTES = 3 * 1024 * 1024
_KEY = re.compile(r'[0-9a-f]{64}', re.ASCII)


class VerificationInfrastructureUnavailable(RuntimeError):
    def __init__(self):
        super().__init__('Verification infrastructure is unavailable')


class InvalidDocument(ValueError):
    def __init__(self):
        super().__init__('Use a valid JPEG or PNG image within the document limits')


class PrivateDocumentStorage(Protocol):
    def put(self, key: str, content: bytes) -> None: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def read(self, key: str) -> bytes: ...


def sanitize_document(content: bytes) -> bytes:
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise InvalidDocument()
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {'JPEG', 'PNG'} or image.width * image.height > 10_000_000 or max(image.size) > 8192:
                raise InvalidDocument()
            if getattr(image, 'n_frames', 1) != 1:
                raise InvalidDocument()
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            # Re-encode pixels; discard filenames, EXIF, appended payloads and
            # supplied metadata. Never serve original active/untrusted bytes.
            clean = Image.new('RGB', image.size, 'white')
            if 'A' in image.getbands():
                rgb = image.convert('RGBA')
                clean.paste(rgb, mask=rgb.getchannel('A'))
            else:
                clean.paste(image.convert('RGB'))
            output = io.BytesIO()
            clean.save(output, format='JPEG', quality=90)
            result = output.getvalue()
            if len(result) > MAX_DOCUMENT_BYTES:
                raise InvalidDocument()
            return result
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise InvalidDocument() from None


class DurableVolumeDocumentStorage:
    """Operator-managed private durable mount, not serverless ephemeral disk.

    Root must already exist with owner-only permissions, outside the source tree
    and /tmp. The operator must exclude it from all web/static/proxy routes and
    supply encrypted durable storage, backups, retention and access controls.
    """
    def __init__(self, root: str):
        path = Path(root)
        project = Path(__file__).resolve().parents[3]
        if not path.is_absolute() or path.is_symlink() or path.resolve() != path:
            raise VerificationInfrastructureUnavailable()
        if path == project or project in path.parents or path == Path('/tmp') or Path('/tmp') in path.parents:
            raise VerificationInfrastructureUnavailable()
        self._root = path
        try:
            with self._directory():
                pass
        except OSError:
            raise VerificationInfrastructureUnavailable() from None

    def _directory(self):
        # Use a directory fd and reject symlinks on every access, not just startup.
        from contextlib import contextmanager
        @contextmanager
        def directory():
            fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                stat = os.fstat(fd)
                if stat.st_uid != os.geteuid() or stat.st_mode & 0o077:
                    raise VerificationInfrastructureUnavailable()
                yield fd
            finally:
                os.close(fd)
        return directory()

    @staticmethod
    def _key(key):
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise VerificationInfrastructureUnavailable()
        return key

    def put(self, key, content):
        key = self._key(key)
        try:
            with self._directory() as directory:
                fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                try:
                    with os.fdopen(fd, 'wb') as target:
                        target.write(content)
                        target.flush()
                        os.fsync(target.fileno())
                    os.fsync(directory)
                except BaseException:
                    os.unlink(key, dir_fd=directory)
                    raise
        except OSError:
            raise VerificationInfrastructureUnavailable() from None

    def exists(self, key):
        key = self._key(key)
        try:
            with self._directory() as directory:
                try:
                    fd = os.open(key, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
                except FileNotFoundError:
                    return False
                try:
                    import stat
                    info = os.fstat(fd)
                    return stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o077 and info.st_size > 0
                finally:
                    os.close(fd)
        except OSError:
            raise VerificationInfrastructureUnavailable() from None

    def read(self, key):
        key = self._key(key)
        try:
            with self._directory() as directory:
                fd = os.open(key, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                with os.fdopen(fd, 'rb') as source:
                    import stat
                    info = os.fstat(source.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                        raise VerificationInfrastructureUnavailable()
                    content = source.read(MAX_DOCUMENT_BYTES + 1)
            return sanitize_document(content)
        except (OSError, InvalidDocument):
            raise VerificationInfrastructureUnavailable() from None

    def delete(self, key):
        key = self._key(key)
        try:
            with self._directory() as directory:
                try:
                    os.unlink(key, dir_fd=directory)
                    os.fsync(directory)
                except FileNotFoundError:
                    pass
        except OSError:
            raise VerificationInfrastructureUnavailable() from None


def get_private_document_storage(settings: Settings) -> PrivateDocumentStorage:
    if settings.private_document_storage_backend != 'durable_volume' or not settings.private_document_storage_durable or not settings.private_document_storage_root:
        raise VerificationInfrastructureUnavailable()
    return DurableVolumeDocumentStorage(settings.private_document_storage_root)
