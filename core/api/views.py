from django.db import transaction, IntegrityError
from django.utils import timezone
from django.http import Http404
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from core.models import StaffProfile, VisitType, Appointment, AuditEvent
from core.forms import appointment_slot_conflicts
from core.views import _audit_appointment_change
from core.api.permissions import IsPatientUser
from core.api.throttling import AppointmentWriteRateThrottle
from core.api.serializers import (
    PatientProfileSerializer,
    DoctorSerializer,
    VisitTypeSerializer,
    AppointmentListSerializer,
    AppointmentDetailSerializer,
    AppointmentBookingSerializer,
)


class PatientProfileView(APIView):
    permission_classes = [IsPatientUser]

    def get(self, request):
        patient = request.user.patient_account.patient
        serializer = PatientProfileSerializer(patient)
        return Response(serializer.data)


class DoctorListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DoctorSerializer

    def get_queryset(self):
        return (
            StaffProfile.objects.filter(
                user__groups__name="Doctor",
                user__is_active=True,
                department__is_active=True,
            )
            .select_related("user", "department")
            .order_by("user__first_name", "user__last_name", "pk")
        )


class VisitTypeListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = VisitTypeSerializer

    def get_queryset(self):
        return VisitType.objects.filter(is_active=True).order_by("name")


class AppointmentListCreateView(APIView):
    permission_classes = [IsPatientUser]

    def get_throttles(self):
        if self.request.method == "POST":
            return [AppointmentWriteRateThrottle()]
        return super().get_throttles()

    def get(self, request):
        patient = request.user.patient_account.patient
        appointments = (
            Appointment.objects.filter(patient=patient)
            .select_related("doctor__user", "doctor__department", "visit_type")
            .order_by("-scheduled_at", "-id")
        )
        serializer = AppointmentListSerializer(appointments, many=True)
        return Response(serializer.data)

    def post(self, request):
        patient = request.user.patient_account.patient
        serializer = AppointmentBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        doctor = serializer.validated_data["doctor"]
        visit_type = serializer.validated_data["visit_type"]
        scheduled_at = serializer.validated_data["scheduled_at"]

        try:
            with transaction.atomic():
                # Lock the doctor record to serialize slot checks
                StaffProfile.objects.select_for_update().get(pk=doctor.pk)
                if appointment_slot_conflicts(doctor, scheduled_at):
                    return Response(
                        {
                            "error": {
                                "status_code": status.HTTP_409_CONFLICT,
                                "message": "This doctor already has an overlapping active appointment.",
                                "details": {"scheduled_at": ["Slot conflict"]},
                            }
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                appointment = Appointment.objects.create(
                    patient=patient,
                    doctor=doctor,
                    visit_type=visit_type,
                    scheduled_at=scheduled_at,
                    status=Appointment.Status.SCHEDULED,
                )

                _audit_appointment_change(
                    request,
                    appointment,
                    "appointment.created",
                    {"status": appointment.status, "source": "patient_api"},
                )

        except IntegrityError:
            return Response(
                {
                    "error": {
                        "status_code": status.HTTP_409_CONFLICT,
                        "message": "This doctor already has an overlapping active appointment.",
                        "details": {"scheduled_at": ["Slot conflict"]},
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        detail_serializer = AppointmentDetailSerializer(appointment)
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)


class AppointmentDetailView(APIView):
    permission_classes = [IsPatientUser]

    def get(self, request, pk):
        patient = request.user.patient_account.patient
        try:
            appointment = (
                Appointment.objects.select_related(
                    "patient", "doctor__user", "doctor__department", "visit_type"
                ).get(pk=pk, patient=patient)
            )
        except Appointment.DoesNotExist:
            raise Http404("Appointment not found")

        serializer = AppointmentDetailSerializer(appointment)
        return Response(serializer.data)


class AppointmentCancelView(APIView):
    permission_classes = [IsPatientUser]
    throttle_classes = [AppointmentWriteRateThrottle]

    def post(self, request, pk):
        patient = request.user.patient_account.patient
        try:
            appointment = Appointment.objects.get(pk=pk, patient=patient)
        except Appointment.DoesNotExist:
            raise Http404("Appointment not found")

        with transaction.atomic():
            appointment = (
                Appointment.objects.select_for_update().get(pk=appointment.pk)
            )

            # Idempotent or allowable check
            if appointment.status == Appointment.Status.CANCELLED:
                serializer = AppointmentDetailSerializer(appointment)
                return Response(serializer.data, status=status.HTTP_200_OK)

            if appointment.status != Appointment.Status.SCHEDULED:
                return Response(
                    {
                        "error": {
                            "status_code": status.HTTP_409_CONFLICT,
                            "message": f"Appointment in '{appointment.get_status_display()}' status cannot be cancelled.",
                            "details": {},
                        }
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            appointment.status = Appointment.Status.CANCELLED
            appointment.cancelled_at = timezone.now()
            appointment.save(update_fields=["status", "cancelled_at", "updated_at"])

            _audit_appointment_change(
                request,
                appointment,
                "appointment.cancelled",
                {"source": "patient_api"},
            )

        serializer = AppointmentDetailSerializer(appointment)
        return Response(serializer.data, status=status.HTTP_200_OK)
