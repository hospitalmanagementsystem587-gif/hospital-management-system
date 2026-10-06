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
    # Auth endpoints
    path("auth/token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", ThrottledTokenRefreshView.as_view(), name="token_refresh"),

    # Patient profile
    path("me/", views.PatientProfileView.as_view(), name="patient_profile"),

    # Catalog endpoints
    path("doctors/", views.DoctorListView.as_view(), name="doctor_list"),
    path("visit-types/", views.VisitTypeListView.as_view(), name="visit_type_list"),

    # Appointment endpoints
    path("appointments/", views.AppointmentListCreateView.as_view(), name="appointment_list_create"),
    path("appointments/<int:pk>/", views.AppointmentDetailView.as_view(), name="appointment_detail"),
    path("appointments/<int:pk>/cancel/", views.AppointmentCancelView.as_view(), name="appointment_cancel"),
]
