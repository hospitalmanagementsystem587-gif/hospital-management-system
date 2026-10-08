"""Portal-aware authorization helpers and querysets.

Enforces server-side coarse admission and resource/object-level scopes across
the hospital management system browser portals and applications.
"""

from django.db.models import Q

from core.models import Appointment, Patient, StaffProfile

PORTAL_ALLOWED_GROUPS = {
    "admin": frozenset(),
    "staff": frozenset({"Administrator", "Doctor", "Reception", "Pharmacy"}),
    "store": frozenset({"Administrator", "Pharmacy"}),
    "patient": frozenset(),
    # Agent portal remains administrator-only until dedicated support-agent role is introduced
    "agent": frozenset({"Administrator"}),
}


def user_can_access_portal(user, portal):
    """Determine whether a Django user is authorized to enter a given portal host."""
    if not user or not user.is_authenticated or not user.is_active:
        return False

    if user.is_superuser:
        return True

    if portal not in PORTAL_ALLOWED_GROUPS:
        return False

    if portal == "admin":
        return user.is_staff

    if portal == "patient":
        account = getattr(user, "patient_account", None)
        return bool(
            account
            and account.is_verified
            and account.patient.archived_at is None
        )

    allowed_groups = PORTAL_ALLOWED_GROUPS[portal]
    return user.groups.filter(name__in=allowed_groups).exists()


def doctor_patient_queryset(user):
    """Return patient records assigned to a doctor through appointments or consultations."""
    if (
        not user.is_authenticated
        or not user.is_active
        or not user.groups.filter(name="Doctor").exists()
    ):
        return Patient.objects.none()

    if user.has_perm("core.view_all_patient_records"):
        return Patient.objects.all()

    profile = StaffProfile.objects.filter(user=user).first()
    if profile is None:
        return Patient.objects.none()

    return Patient.objects.filter(
        Q(appointments__doctor=profile) | Q(consultations__doctor=profile)
    ).distinct()


def get_authorized_patient_queryset(user):
    """Return non-archived patient queryset accessible by the user based on staff role."""
    if not user.is_authenticated or not user.is_active:
        return Patient.objects.none()

    if user.is_superuser:
        return Patient.objects.filter(archived_at__isnull=True)

    has_staff_profile = StaffProfile.objects.filter(user=user).exists()
    if not has_staff_profile:
        return Patient.objects.none()

    groups = set(user.groups.values_list("name", flat=True))
    if "Reception" in groups:
        return Patient.objects.filter(archived_at__isnull=True)

    if "Doctor" in groups:
        return doctor_patient_queryset(user).filter(archived_at__isnull=True)

    return Patient.objects.none()


def get_authorized_appointment_queryset(user):
    """Return appointment queryset accessible by the user based on staff role."""
    if not user.is_authenticated or not user.is_active:
        return Appointment.objects.none()

    if user.is_superuser:
        return Appointment.objects.all()

    has_staff_profile = StaffProfile.objects.filter(user=user).exists()
    if not has_staff_profile:
        return Appointment.objects.none()

    groups = set(user.groups.values_list("name", flat=True))
    if "Reception" in groups:
        return Appointment.objects.all()

    if "Doctor" in groups:
        return Appointment.objects.filter(doctor__user=user)

    return Appointment.objects.none()
