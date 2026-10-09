from django.urls import include, path

from core import views

urlpatterns = [
    path("", views.patient_dashboard, name="patient_dashboard"),
    path(
        "documents/",
        views.patient_document_list,
        name="patient_document_list",
    ),
    path(
        "documents/<uuid:public_id>/download/",
        views.patient_portal_document_download,
        name="patient_portal_document_download",
    ),
    path(
        "prescriptions/<int:pk>/print/",
        views.patient_portal_prescription_print,
        name="patient_portal_prescription_print",
    ),
    path(
        "prescriptions/",
        views.patient_prescription_history,
        name="patient_prescription_history",
    ),
    path(
        "prescriptions/<int:pk>/",
        views.patient_prescription_detail,
        name="patient_prescription_detail",
    ),
    path(
        "appointments/book/",
        views.patient_appointment_book,
        name="patient_appointment_book",
    ),
    path(
        "appointments/<int:pk>/cancel/",
        views.patient_appointment_cancel,
        name="patient_appointment_cancel",
    ),
    path(
        "doctors/",
        views.patient_doctor_directory,
        name="patient_doctor_directory",
    ),
    path(
        "invoices/",
        views.patient_invoice_list,
        name="patient_invoice_list",
    ),
    path(
        "invoices/<int:pk>/",
        views.patient_invoice_detail,
        name="patient_invoice_detail",
    ),
    path(
        "insurance/",
        views.patient_insurance_workspace,
        name="patient_insurance_workspace",
    ),
    path(
        "feedback/",
        views.patient_feedback_workspace,
        name="patient_feedback_workspace",
    ),
    path(
        "feedback/submit/",
        views.patient_feedback_submit,
        name="patient_feedback_submit",
    ),
    path("", include("config.portal_urls")),
]
