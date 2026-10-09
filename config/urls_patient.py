from django.urls import include, path

from core import views

urlpatterns = [
    path("", views.patient_dashboard, name="patient_dashboard"),
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
    path("", include("config.portal_urls")),
]
