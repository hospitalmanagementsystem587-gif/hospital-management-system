import hashlib
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.module_loading import import_string


ALLOWED_DOCUMENT_TYPES = {
    "application/pdf": {".pdf"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
}

DOCUMENT_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

_EICAR_SIGNATURE = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"


def _detected_content_type(content):
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def inspect_patient_document_upload(upload):
    """Validate file structure and return trusted metadata.

    Malware scanning is deliberately fail-closed. A deployment may configure a
    callable via PATIENT_DOCUMENT_MALWARE_SCAN_CALLBACK. Without one, a valid
    upload remains pending and cannot be released or downloaded.
    """

    max_bytes = settings.PATIENT_DOCUMENT_MAX_BYTES
    size_bytes = getattr(upload, "size", None)
    if size_bytes is None or size_bytes <= 0:
        raise ValidationError("The document is empty.")
    if size_bytes > max_bytes:
        raise ValidationError(
            f"The document exceeds the {max_bytes // (1024 * 1024)} MiB limit."
        )

    original_position = upload.tell() if hasattr(upload, "tell") else 0
    upload.seek(0)
    content = upload.read(max_bytes + 1)
    upload.seek(original_position)
    if len(content) != size_bytes:
        raise ValidationError("The document size could not be verified.")

    content_type = _detected_content_type(content)
    if content_type is None:
        raise ValidationError("Only valid PDF, JPEG, PNG, or WebP documents are allowed.")

    suffix = Path(upload.name or "").suffix.lower()
    if suffix not in ALLOWED_DOCUMENT_TYPES[content_type]:
        raise ValidationError("The document extension does not match its contents.")

    if _EICAR_SIGNATURE in content:
        raise ValidationError("The document failed malware validation.")

    validation_status = "pending"
    scanner_path = getattr(settings, "PATIENT_DOCUMENT_MALWARE_SCAN_CALLBACK", "")
    if scanner_path:
        scanner = import_string(scanner_path)
        upload.seek(0)
        try:
            scan_is_clean = scanner(upload)
        finally:
            upload.seek(original_position)
        if scan_is_clean is not True:
            raise ValidationError("The document failed malware validation.")
        validation_status = "clean"

    return {
        "content_type": content_type,
        "size_bytes": size_bytes,
        "sha256": hashlib.sha256(content).hexdigest(),
        "validation_status": validation_status,
    }


def open_validated_patient_document(document):
    """Open a clean document after verifying current storage metadata and digest."""

    if document.content_type not in ALLOWED_DOCUMENT_TYPES:
        raise FileNotFoundError
    if document.size_bytes <= 0 or document.size_bytes > settings.PATIENT_DOCUMENT_MAX_BYTES:
        raise FileNotFoundError
    if not document.sha256 or len(document.sha256) != 64:
        raise FileNotFoundError

    try:
        file_handle = document.file.open("rb")
        digest = hashlib.sha256()
        actual_size = 0
        while True:
            chunk = file_handle.read(64 * 1024)
            if not chunk:
                break
            actual_size += len(chunk)
            if actual_size > settings.PATIENT_DOCUMENT_MAX_BYTES:
                raise FileNotFoundError
            digest.update(chunk)
        if actual_size != document.size_bytes or digest.hexdigest() != document.sha256:
            raise FileNotFoundError
        file_handle.seek(0)
        return file_handle
    except Exception:
        try:
            file_handle.close()
        except (AttributeError, OSError):
            pass
        raise FileNotFoundError


def patient_document_download_name(document):
    stem = "".join(
        character.lower() if character.isalnum() else "-"
        for character in document.title
    )
    stem = "-".join(part for part in stem.split("-") if part)[:80]
    if not stem:
        stem = "clinical-document"
    return f"{stem}-{document.public_id}{DOCUMENT_TYPE_EXTENSIONS[document.content_type]}"
