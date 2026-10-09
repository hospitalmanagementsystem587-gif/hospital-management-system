from pathlib import Path

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.models import PatientAccount, StaffProfile, Ticket, TicketAttachment, TicketMessage
from core.services.documents import inspect_patient_document_upload, open_validated_patient_document


def _patient_owns_ticket(user, ticket):
    if ticket.created_by_id == user.pk:
        return True
    return bool(
        ticket.patient_id
        and PatientAccount.objects.filter(
            user=user, patient_id=ticket.patient_id, is_verified=True
        ).exists()
    )


def _staff_profile(user):
    if not getattr(user, "is_active", False):
        return None
    return StaffProfile.objects.filter(user=user).first()


def can_access_ticket(user, ticket, *, write=False):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if _patient_owns_ticket(user, ticket):
        return True
    permission = "core.change_ticket" if write else "core.view_ticket"
    if not user.has_perm(permission):
        return False
    profile = _staff_profile(user)
    if user.is_superuser:
        return True
    if profile is None:
        return False
    if ticket.assigned_to_id:
        return ticket.assigned_to_id == profile.pk
    if ticket.assigned_team_id:
        return ticket.assigned_team_id == profile.department_id
    return True


def messages_for_user(ticket, user):
    if not can_access_ticket(user, ticket):
        raise PermissionDenied("You cannot access this ticket.")
    messages = ticket.messages.all()
    if _patient_owns_ticket(user, ticket):
        messages = messages.filter(is_internal=False)
    return messages


def add_ticket_message(*, ticket, author, body, is_internal=False):
    if not can_access_ticket(author, ticket, write=True):
        raise PermissionDenied("You cannot reply to this ticket.")
    if is_internal and _patient_owns_ticket(author, ticket):
        raise PermissionDenied("Patients cannot create internal notes.")
    body = (body or "").strip()
    if not body:
        raise ValidationError({"body": "A message body is required."})
    return TicketMessage.objects.create(
        ticket=ticket, author=author, body=body, is_internal=is_internal
    )


@transaction.atomic
def create_ticket_attachment(*, ticket, uploaded_by, upload, message=None, is_internal=False):
    if not can_access_ticket(uploaded_by, ticket, write=True):
        raise PermissionDenied("You cannot attach files to this ticket.")
    if message is not None and message.ticket_id != ticket.pk:
        raise ValidationError({"message": "The message must belong to the same ticket."})
    if message is not None and message.is_internal:
        is_internal = True
    if is_internal and _patient_owns_ticket(uploaded_by, ticket):
        raise PermissionDenied("Patients cannot create internal attachments.")

    metadata = inspect_patient_document_upload(upload)
    file_name = Path(upload.name or "attachment").name[:255]
    upload.name = file_name
    attachment = TicketAttachment(
        ticket=ticket,
        message=message,
        uploaded_by=uploaded_by,
        file=upload,
        file_name=file_name,
        content_type=metadata["content_type"],
        size_bytes=metadata["size_bytes"],
        sha256=metadata["sha256"],
        scan_status=metadata["validation_status"],
        is_internal=is_internal,
    )
    attachment.full_clean()
    attachment.save()
    return attachment


def open_ticket_attachment(*, attachment, user):
    if not can_access_ticket(user, attachment.ticket):
        raise PermissionDenied("You cannot access this attachment.")
    if attachment.is_internal and _patient_owns_ticket(user, attachment.ticket):
        raise PermissionDenied("Internal attachments are not patient-visible.")
    if attachment.scan_status != TicketAttachment.MalwareScanStatus.CLEAN:
        raise FileNotFoundError
    return open_validated_patient_document(attachment)
