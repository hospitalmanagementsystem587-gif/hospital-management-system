from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivatePatientDocumentStorage(FileSystemStorage):
    """Filesystem storage without a public URL for clinical documents."""

    def __init__(self):
        super().__init__(
            location=settings.PRIVATE_PATIENT_DOCUMENT_ROOT,
            base_url=None,
            file_permissions_mode=0o600,
            directory_permissions_mode=0o700,
        )


private_patient_document_storage = PrivatePatientDocumentStorage()
