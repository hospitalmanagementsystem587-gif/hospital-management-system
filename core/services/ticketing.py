from pathlib import Path

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import Invoice, PatientAccount, StaffProfile, Ticket, TicketAttachment, TicketAuditEvent, TicketMessage
from core.services.documents import inspect_patient_document_upload, open_validated_patient_document


def _patient_owns_ticket(user, ticket):
    if not ticket.patient_id:
        return False
    return PatientAccount.objects.filter(
        user=user, patient_id=ticket.patient_id, is_verified=True
    ).exists()


def _staff_profile(user):
    if not getattr(user, "is_active", False):
        return None
    return StaffProfile.objects.filter(user=user).first()


def create_patient_ticket(*, patient, user, title, description, category, priority=Ticket.Priority.NORMAL, upload=None, invoice=None, payment=None):
    """
    Safely creates a ticket for a verified patient with server-side identity derivation.
    Restricts allowed public categories, validates billing references, and sanitizes input.
    """
    allowed_categories = [
        Ticket.Category.GENERAL,
        Ticket.Category.BILLING,
        Ticket.Category.CLINICAL,
        Ticket.Category.PHARMACY,
        Ticket.Category.TECHNICAL,
    ]
    if category not in allowed_categories:
        raise ValidationError({"category": "Invalid or disallowed ticket category."})

    title = (title or "").strip()
    if not title:
        raise ValidationError({"title": "A ticket title is required."})

    description = (description or "").strip()
    if not description:
        raise ValidationError({"description": "A ticket description is required."})

    if invoice is not None:
        if invoice.patient_id != patient.pk:
            raise ValidationError({"invoice": "Referenced invoice does not belong to this patient."})
        if invoice.status == Invoice.Status.DRAFT:
            raise ValidationError({"invoice": "Draft invoices cannot be referenced in support tickets."})

    if payment is not None:
        if payment.invoice.patient_id != patient.pk:
            raise ValidationError({"payment": "Referenced payment does not belong to this patient."})

    with transaction.atomic():
        ticket = Ticket.objects.create(
            title=title,
            description=description,
            category=category,
            priority=priority,
            created_by=user,
            patient=patient,
            status=Ticket.Status.OPEN,
        )
        TicketAuditEvent.objects.create(
            ticket=ticket, actor=user, action="created", field="status",
            previous_value=None, new_value=Ticket.Status.OPEN, patient_visible=True,
        )
        if upload:
            create_ticket_attachment(
                ticket=ticket,
                uploaded_by=user,
                upload=upload,
                is_internal=False,
            )
        return ticket


def create_staff_ticket(*, user, title, description, category, priority=Ticket.Priority.NORMAL, patient=None, assigned_team=None, upload=None, invoice=None, payment=None):
    """
    Safely creates an operational/clinical support ticket from staff workflows.
    Ensures requester is active staff, attaches staff profile department if unassigned,
    validates invoice/payment references, and records optional patient context.
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        raise PermissionDenied("Authentication required to create staff tickets.")
    if not (user.is_superuser or user.has_perm("core.add_ticket")):
        raise PermissionDenied("You do not have permission to create support tickets.")

    profile = _staff_profile(user)
    if not user.is_superuser and profile is None:
        raise PermissionDenied("Only staff members can create staff tickets.")

    allowed_categories = Ticket.Category.values
    if category not in allowed_categories:
        raise ValidationError({"category": "Invalid or disallowed ticket category."})

    title = (title or "").strip()
    if not title:
        raise ValidationError({"title": "A ticket title is required."})

    description = (description or "").strip()
    if not description:
        raise ValidationError({"description": "A ticket description is required."})

    if invoice is not None and patient is not None:
        if invoice.patient_id != patient.pk:
            raise ValidationError({"invoice": "Referenced invoice does not belong to the selected patient."})

    if payment is not None:
        if invoice is not None and payment.invoice_id != invoice.pk:
            raise ValidationError({"payment": "Referenced payment does not match the invoice."})
        if patient is not None and payment.invoice.patient_id != patient.pk:
            raise ValidationError({"payment": "Referenced payment does not belong to the selected patient."})

    with transaction.atomic():
        ticket = Ticket.objects.create(
            title=title,
            description=description,
            category=category,
            priority=priority,
            created_by=user,
            patient=patient,
            assigned_team=assigned_team,
            status=Ticket.Status.OPEN,
        )
        TicketAuditEvent.objects.create(
            ticket=ticket, actor=user, action="created", field="status",
            previous_value=None, new_value=Ticket.Status.OPEN, patient_visible=patient is not None,
        )
        if upload:
            create_ticket_attachment(
                ticket=ticket,
                uploaded_by=user,
                upload=upload,
                is_internal=True,
            )
        return ticket


def staff_tickets_queryset(user, *, filter_type="all", query=None):
    """
    Returns tickets visible to a staff user based on role, department, assignment,
    or requester relationship.
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return Ticket.objects.none()
    if not (user.is_superuser or user.has_perm("core.view_ticket") or user.groups.filter(name="Administrator").exists()):
        return Ticket.objects.none()

    profile = _staff_profile(user)
    if user.is_superuser or (profile is None and user.groups.filter(name="Administrator").exists()):
        base_qs = Ticket.objects.all()
    elif profile is not None:
        dept = profile.department
        # Staff can see: tickets they created, tickets assigned to them, tickets assigned to their department,
        # or unassigned tickets (assigned_team=dept or unassigned department)
        base_qs = Ticket.objects.filter(
            Q(created_by=user)
            | Q(assigned_to=profile)
            | Q(assigned_team=dept)
            | Q(assigned_team__isnull=True, assigned_to__isnull=True)
        ).distinct()
    else:
        return Ticket.objects.none()

    if filter_type == "created_by_me":
        base_qs = base_qs.filter(created_by=user)
    elif filter_type == "assigned_to_me":
        if profile:
            base_qs = base_qs.filter(assigned_to=profile)
        else:
            base_qs = Ticket.objects.none()
    elif filter_type == "my_department":
        if profile and profile.department:
            base_qs = base_qs.filter(assigned_team=profile.department)
        else:
            base_qs = Ticket.objects.none()
    elif filter_type == "open":
        base_qs = base_qs.exclude(status__in=[Ticket.Status.RESOLVED, Ticket.Status.CLOSED])

    if query:
        query = query.strip()
        base_qs = base_qs.filter(
            Q(number__icontains=query)
            | Q(title__icontains=query)
            | Q(patient__full_name__icontains=query)
            | Q(patient__mrn__icontains=query)
        )

    return base_qs.select_related(
        "patient", "created_by", "assigned_to__user", "assigned_team", "sla_policy"
    ).order_by("-created_at")


def patient_tickets_queryset(patient, user):
    """
    Returns only tickets owned by the given verified patient and user.
    """
    return Ticket.objects.filter(
        patient=patient,
        created_by=user,
    ).prefetch_related("messages", "attachments").order_by("-created_at")



def agent_tickets_queryset(user, *, queue_filter="all", query=None):
    """
    Returns permission-scoped and department-scoped tickets for an authorized agent.
    Filters:
    - 'unassigned': Unassigned tickets matching agent's department or global
    - 'assigned_to_me': Assigned directly to agent's staff profile
    - 'high_priority': High or Urgent priority tickets in agent's scope
    - 'sla_breached': Tickets where SLA is breached
    - 'waiting_on_requester': Tickets waiting on requester
    - 'all': All tickets in agent's department or queue scope
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return Ticket.objects.none()
    if not (user.is_superuser or user.has_perm("core.view_ticket") or user.groups.filter(name="Administrator").exists()):
        return Ticket.objects.none()

    profile = _staff_profile(user)
    if user.is_superuser or (profile is None and user.groups.filter(name="Administrator").exists()):
        base_qs = Ticket.objects.all()
    elif profile is not None:
        # Agent can see: tickets assigned to themselves, or tickets assigned to their department, or unassigned tickets in their department / general (null department)
        dept = profile.department
        base_qs = Ticket.objects.filter(
            Q(assigned_to=profile)
            | Q(assigned_team=dept)
            | Q(assigned_team__isnull=True, assigned_to__isnull=True)
        )
    else:
        return Ticket.objects.none()

    now = timezone.now()
    if queue_filter == "unassigned":
        base_qs = base_qs.filter(assigned_to__isnull=True)
    elif queue_filter == "assigned_to_me":
        if profile:
            base_qs = base_qs.filter(assigned_to=profile)
        else:
            base_qs = Ticket.objects.none()
    elif queue_filter == "high_priority":
        base_qs = base_qs.filter(priority__in=[Ticket.Priority.HIGH, Ticket.Priority.URGENT])
    elif queue_filter == "sla_breached":
        base_qs = base_qs.filter(
            Q(sla_breached_at__isnull=False) | Q(sla_due_at__lt=now, resolved_at__isnull=True)
        )
    elif queue_filter == "waiting_on_requester":
        base_qs = base_qs.filter(status=Ticket.Status.WAITING_ON_REQUESTER)

    if query:
        query = query.strip()
        base_qs = base_qs.filter(
            Q(number__icontains=query)
            | Q(title__icontains=query)
            | Q(patient__full_name__icontains=query)
            | Q(patient__mrn__icontains=query)
        )

    return base_qs.select_related(
        "patient", "assigned_to__user", "assigned_team", "sla_policy"
    ).order_by("-created_at")


def can_access_ticket(user, ticket, *, write=False):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if _patient_owns_ticket(user, ticket):
        return True
    permission = "core.change_ticket" if write else "core.view_ticket"
    if not user.has_perm(permission):
        return False
    if user.is_superuser:
        return True
    if ticket.created_by_id == user.pk:
        return True
    profile = _staff_profile(user)
    if profile is None:
        return False
    if ticket.assigned_to_id:
        return ticket.assigned_to_id == profile.pk
    if ticket.assigned_team_id:
        return ticket.assigned_team_id == profile.department_id
    # Unassigned tickets (no assigned_to and no assigned_team) are accessible to support agents/staff in the queue
    return True


def messages_for_user(ticket, user):
    if not can_access_ticket(user, ticket):
        raise PermissionDenied("You cannot access this ticket.")
    messages = ticket.messages.all()
    if _patient_owns_ticket(user, ticket):
        messages = messages.filter(is_internal=False)
    return messages


def ticket_history_for_user(ticket, user):
    if not can_access_ticket(user, ticket):
        raise PermissionDenied("You cannot access this ticket history.")
    history = ticket.audit_history.select_related("actor").all()
    if _patient_owns_ticket(user, ticket):
        return history.filter(patient_visible=True)
    if not (user.is_superuser or user.has_perm("core.view_internal_ticketaudit")):
        raise PermissionDenied("You cannot access internal ticket history.")
    return history


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
