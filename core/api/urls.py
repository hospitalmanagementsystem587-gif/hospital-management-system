from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from core.api.throttling import AuthAnonRateThrottle
from core.api import views


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [AuthAnonRateThrottle]


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [AuthAnonRateThrottle]


urlpatterns = [
    # Auth & Onboarding endpoints
    path("auth/token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", ThrottledTokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth_logout"),
    path("auth/logout-all/", views.LogoutAllView.as_view(), name="auth_logout_all"),
    path("auth/otp/request/", views.OnboardingRequestOtpView.as_view(), name="onboarding_request_otp"),
    path("auth/register/", views.OnboardingRegisterView.as_view(), name="onboarding_register"),
    path("auth/claim-patient/", views.OnboardingClaimPatientView.as_view(), name="onboarding_claim_patient"),

    # Patient profile
    path("me/", views.PatientProfileView.as_view(), name="patient_profile"),

    # Catalog & Public content endpoints
    path("doctors/", views.DoctorListView.as_view(), name="doctor_list"),
    path("doctors/<int:pk>/", views.DoctorDetailView.as_view(), name="doctor_detail"),
    path("departments/", views.DepartmentListView.as_view(), name="department_list"),
    path("hospital-info/", views.HospitalInfoView.as_view(), name="hospital_info"),
    path("facilities/", views.HospitalFacilityListView.as_view(), name="facility_list"),
    path("bed-availability/", views.BedAvailabilityView.as_view(), name="bed_availability"),
    path("health-packages/", views.HealthPackageListView.as_view(), name="health_package_list"),
    path("opd/historical-metrics/", views.OpdHistoricalMetricsView.as_view(), name="opd_historical_metrics"),
    path("health-content/", views.HealthContentListView.as_view(), name="health_content_list"),
    path("faqs/", views.HospitalFaqListView.as_view(), name="faq_list"),
    path("visit-types/", views.VisitTypeListView.as_view(), name="visit_type_list"),

    # Appointment endpoints
    path("appointments/", views.AppointmentListCreateView.as_view(), name="appointment_list_create"),
    path("appointments/<int:pk>/", views.AppointmentDetailView.as_view(), name="appointment_detail"),
    path("appointments/<int:pk>/cancel/", views.AppointmentCancelView.as_view(), name="appointment_cancel"),

    # Patient-owned clinical records (read-only)
    path("me/health-records/", views.HealthRecordListView.as_view(), name="health_record_list"),
    path("me/health-records/<int:pk>/", views.HealthRecordDetailView.as_view(), name="health_record_detail"),
    path("me/prescriptions/", views.PrescriptionListView.as_view(), name="patient_prescription_list"),
    path("me/prescriptions/<int:pk>/", views.PrescriptionDetailView.as_view(), name="patient_prescription_detail"),
    path("me/documents/", views.PatientDocumentListView.as_view(), name="patient_document_list"),
    path("me/documents/<uuid:public_id>/download/", views.PatientDocumentDownloadView.as_view(), name="patient_document_download"),

    # Patient-owned billing and receipts (read-only)
    path("me/invoices/", views.PatientInvoiceListView.as_view(), name="patient_invoice_list"),
    path("me/invoices/<int:pk>/", views.PatientInvoiceDetailView.as_view(), name="patient_invoice_detail"),
    path("me/invoices/<int:pk>/pay/", views.PatientPaymentInitiateView.as_view(), name="patient_payment_initiate"),
    path("me/receipts/<str:receipt_number>/", views.PatientReceiptDetailView.as_view(), name="patient_receipt_detail"),
]
