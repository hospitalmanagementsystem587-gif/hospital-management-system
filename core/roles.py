ROLE_PERMISSIONS = {
    "Reception": (
        "core.add_patient",
        "core.change_patient",
        "core.view_patient",
        "core.add_appointment",
        "core.change_appointment",
        "core.view_appointment",
        "core.view_department",
        "core.view_staffprofile",
        "core.view_visittype",
        "core.view_service",
        "core.add_invoice",
        "core.view_invoice",
        "core.add_invoiceline",
        "core.view_invoiceline",
        "core.add_payment",
        "core.view_payment",
        "core.view_paymentmethod",
        "core.view_adjustment",
        "core.view_refund",
        "core.add_patientdocument",
        "core.view_patientdocument",
        "core.view_ward",
        "core.view_bed",
        "core.add_admission",
        "core.change_admission",
        "core.view_admission",
        "core.add_inpatientdeposit",
        "core.view_inpatientdeposit",
    ),
    "Pharmacy": (
        "core.view_patient",
        "core.view_prescription",
        "core.view_prescriptionitem",
        "core.view_medicine",
        "core.add_medicine",
        "core.change_medicine",
        "core.view_supplier",
        "core.add_supplier",
        "core.change_supplier",
        "core.view_stockreceipt",
        "core.add_stockreceipt",
        "core.view_medicinebatch",
        "core.add_medicinebatch",
        "core.change_medicinebatch",
        "core.adjust_stock",
        "core.view_stockmovement",
        "core.add_stockmovement",
        "core.view_pharmacysale",
        "core.add_pharmacysale",
        "core.view_pharmacysaleline",
        "core.add_pharmacysaleline",
        "core.view_dispensing",
        "core.add_dispensing",
        "core.view_dispensingline",
        "core.add_dispensingline",
        "core.view_pharmacyreturn",
        "core.add_pharmacyreturn",
        "core.view_returnline",
        "core.add_returnline",
        "core.view_paymentmethod",
    ),
    "Doctor": (
        "core.view_patient",
        "core.view_appointment",
        "core.change_appointment",
        "core.view_department",
        "core.view_visittype",
        "core.view_medicine",
        "core.view_consultation",
        "core.add_consultation",
        "core.change_consultation",
        "core.view_prescription",
        "core.add_prescription",
        "core.change_prescription",
        "core.view_prescriptionitem",
        "core.add_prescriptionitem",
        "core.change_prescriptionitem",
        "core.view_patientdocument",
        "core.add_patientdocument",
        "core.view_ward",
        "core.view_bed",
        "core.view_admission",
        "core.change_admission",
    ),
    "Administrator": (
        "auth.view_user",
        "auth.add_user",
        "auth.change_user",
        "auth.view_group",
        "core.view_staffprofile",
        "core.add_staffprofile",
        "core.change_staffprofile",
        "core.view_hospitalsettings",
        "core.change_hospitalsettings",
        "core.view_numbersequence",
        "core.change_numbersequence",
        "core.view_department",
        "core.add_department",
        "core.change_department",
        "core.delete_department",
        "core.view_specialty",
        "core.add_specialty",
        "core.change_specialty",
        "core.delete_specialty",
        "core.view_doctorspecialty",
        "core.add_doctorspecialty",
        "core.change_doctorspecialty",
        "core.delete_doctorspecialty",
        "core.view_visittype",
        "core.add_visittype",
        "core.change_visittype",
        "core.view_service",
        "core.add_service",
        "core.change_service",
        "core.view_paymentmethod",
        "core.add_paymentmethod",
        "core.change_paymentmethod",
        "core.add_invoice",
        "core.view_invoice",
        "core.view_invoiceline",
        "core.view_payment",
        "core.add_adjustment",
        "core.view_adjustment",
        "core.add_refund",
        "core.view_refund",
        "core.approve_refund",
        "core.void_invoice",
        "core.view_supplier",
        "core.add_supplier",
        "core.change_supplier",
        "core.view_medicine",
        "core.add_medicine",
        "core.change_medicine",
        "core.view_patientdocument",
        "core.add_patientdocument",
        "core.change_patientdocument",
        "core.delete_patientdocument",
        "core.view_ward",
        "core.add_ward",
        "core.change_ward",
        "core.view_bed",
        "core.add_bed",
        "core.change_bed",
        "core.view_admission",
        "core.add_admission",
        "core.change_admission",
        "core.view_inpatientdeposit",
        "core.add_inpatientdeposit",
    ),
}



def configure_role_permissions():
    from django.contrib.auth.models import Group, Permission

    requested = {
        (app_label, codename)
        for permissions in ROLE_PERMISSIONS.values()
        for app_label, codename in (
            permission.split(".", 1) for permission in permissions
        )
    }
    app_labels = {app_label for app_label, _ in requested}
    codenames = {codename for _, codename in requested}
    available = {
        (permission.content_type.app_label, permission.codename): permission
        for permission in Permission.objects.filter(
            content_type__app_label__in=app_labels,
            codename__in=codenames,
        ).select_related("content_type")
    }
    missing = requested - available.keys()
    if missing:
        raise RuntimeError(f"Missing Django permissions: {sorted(missing)}")

    for role, permission_names in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=role)
        group.permissions.set(
            [
                available[tuple(permission.split(".", 1))]
                for permission in permission_names
            ]
        )
