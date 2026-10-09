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
        "appointments/book/",
        views.patient_appointment_book,
        name="patient_appointment_book",
    ),
    path(
        "appointments/<int:pk>/cancel/",
        views.patient_appointment_cancel,
        name="patient_appointment_cancel",
    ),
    path("", include("config.portal_urls")),
]
