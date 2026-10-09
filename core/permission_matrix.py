"""Auditable high-level portal admission and sensitive-domain authorization matrix.

Navigation is never an authorization control. Views must still require Django
permissions and apply object-level querysets/services.
"""

PORTAL_PERMISSION_MATRIX = {
    "admin": {
        "groups": frozenset({"Administrator"}),
        "boundary": "is_staff plus model permissions; superusers bypass",
    },
    "staff": {
        "groups": frozenset({"Administrator", "Doctor", "Reception", "Pharmacy"}),
        "boundary": "Django permissions plus patient/doctor/department object scope",
    },
    "store": {
        "groups": frozenset({"Administrator", "Pharmacy"}),
        "boundary": "pharmacy permissions; no clinical or billing access by navigation alone",
    },
    "patient": {
        "groups": frozenset(),
        "boundary": "verified PatientAccount self-access; archived accounts denied",
    },
    "agent": {
        "groups": frozenset({"Administrator", "Support Agent"}),
        "boundary": "ticket permissions plus assignment/department object scope",
    },
}

SENSITIVE_DOMAIN_CONTROLS = {
    "clinical_records": "doctor_patient_queryset / get_authorized_patient_queryset",
    "patient_documents": "authorized patient queryset and verified patient self-access before private storage open",
    "prescriptions": "doctor/patient ownership filters; pharmacy dispensing permissions",
    "pharmacy_stock": "Pharmacy or Administrator permissions and store portal admission",
    "billing": "Reception or Administrator permissions plus patient/invoice reference validation",
    "tickets": "can_access_ticket and participant/assignment/department querysets",
    "ticket_audit": "ticket_history_for_user with patient-visible filtering",
}
