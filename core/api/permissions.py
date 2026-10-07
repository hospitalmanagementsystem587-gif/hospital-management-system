from rest_framework import permissions
from core.models import StaffProfile


class IsPatientUser(permissions.BasePermission):
    """
    Allows access only to authenticated users who have an associated PatientAccount
    and do NOT have a StaffProfile (to prevent staff role mixing).
    """

    message = "Patient account required."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Staff accounts cannot use patient endpoints merely because they are authenticated
        if StaffProfile.objects.filter(user=request.user).exists() or request.user.is_staff or request.user.is_superuser:
            return False

        if not request.user.is_active or not hasattr(request.user, "patient_account"):
            return False

        account = request.user.patient_account
        return account.is_verified and account.patient.archived_at is None


class IsReceptionUser(permissions.BasePermission):
    message = "Reception staff account required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.groups.filter(name="Reception").exists()
            and StaffProfile.objects.filter(user=request.user).exists()
        )
