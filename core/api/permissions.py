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

        return hasattr(request.user, "patient_account") and request.user.patient_account is not None
