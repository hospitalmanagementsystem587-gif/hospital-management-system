from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from core import views

urlpatterns = [
    path("api/v1/", include("core.api.urls")),
    path("", views.home, name="home"),
    path("health/", views.health, name="health"),
    path("accounts/login/", views.HospitalLoginView.as_view(), name="login"),
    path("patients/", views.patient_list, name="patient_list"),
    path("patients/register/", views.patient_create, name="patient_create"),
    path("patients/<int:pk>/", views.patient_detail, name="patient_detail"),
    path("patients/<int:pk>/edit/", views.patient_update, name="patient_update"),
    path(
        "patients/<int:pk>/documents/upload/",
        views.patient_document_upload,
        name="patient_document_upload",
    ),
    path(
        "patients/<int:patient_pk>/documents/<uuid:public_id>/download/",
        views.patient_document_download,
        name="staff_patient_document_download",
    ),
    path("ipd/admissions/", views.admission_list, name="admission_list"),
    path("ipd/admissions/create/", views.admission_create, name="admission_create"),
    path(
        "ipd/admissions/<int:pk>/",
        views.admission_detail,
        name="admission_detail",
    ),
    path(
        "ipd/admissions/<int:admission_id>/deposits/create/",
        views.inpatient_deposit_create,
        name="inpatient_deposit_create",
    ),
    path(
        "ipd/admissions/<int:pk>/discharge/",
        views.admission_discharge,
        name="admission_discharge",
    ),
    path("invoices/create/", views.invoice_create, name="invoice_create"),
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("invoices/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("invoices/<int:pk>/payment/", views.payment_create, name="payment_create"),
    path(
        "invoices/<int:pk>/adjustments/",
        views.invoice_adjustment,
        name="invoice_adjustment",
    ),
    path("invoices/<int:pk>/refunds/", views.invoice_refund, name="invoice_refund"),
    path("invoices/<int:pk>/void/", views.invoice_void, name="invoice_void"),
    path("appointments/", views.appointment_list, name="appointment_list"),
    path("appointments/create/", views.appointment_create, name="appointment_create"),
    path(
        "appointments/<int:pk>/reschedule/",
        views.appointment_reschedule,
        name="appointment_reschedule",
    ),
    path(
        "appointments/<int:pk>/transition/",
        views.appointment_transition,
        name="appointment_transition",
    ),
    path(
        "clinical/patients/<int:patient_id>/",
        views.clinical_history,
        name="clinical_history",
    ),
    path(
        "consultations/appointment/<int:appointment_id>/",
        views.consultation_create,
        name="consultation_create",
    ),
    path(
        "consultations/<int:pk>/",
        views.consultation_detail,
        name="consultation_detail",
    ),
    path(
        "prescriptions/<int:pk>/print/",
        views.prescription_print,
        name="prescription_print",
    ),
    path(
        "pharmacy/stock-receipts/create/",
        views.stock_receipt_create,
        name="stock_receipt_create",
    ),
    path(
        "pharmacy/sales/create/",
        views.pharmacy_sale_create,
        name="pharmacy_sale_create",
    ),
    path(
        "pharmacy/sales/<int:pk>/",
        views.pharmacy_sale_detail,
        name="pharmacy_sale_detail",
    ),
    path(
        "pharmacy/returns/create/",
        views.pharmacy_return_create,
        name="pharmacy_return_create",
    ),
    path(
        "pharmacy/returns/<int:pk>/reject/",
        views.pharmacy_return_reject,
        name="pharmacy_return_reject",
    ),
    path(
        "pharmacy/batches/<int:pk>/adjust/",
        views.stock_adjustment,
        name="stock_adjustment",
    ),
    path(
        "pharmacy/batches/<int:pk>/quarantine/",
        views.batch_quarantine,
        name="batch_quarantine",
    ),
    path(
        "prescriptions/<int:prescription_id>/dispense/",
        views.dispense_prescription,
        name="dispense_prescription",
    ),
    path(
        "pharmacy/prescriptions/",
        views.pharmacy_prescription_list,
        name="pharmacy_prescription_list",
    ),
    path("accounts/", include("django.contrib.auth.urls")),
]

urlpatterns += staticfiles_urlpatterns()
