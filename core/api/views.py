from django.conf import settings
import hashlib
import secrets
from datetime import timedelta
from django.db import transaction, IntegrityError, OperationalError
from django.db.models import Count, Prefetch
from django.utils import timezone
from django.http import FileResponse, Http404
from django.utils.cache import patch_vary_headers
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from core.models import (
    Adjustment,
    Appointment,
    AuditEvent,
    Consultation,
    Department,
    DigitalCheckInPass,
    HospitalFacility,
    HospitalFaq,
    HealthPackage,
    HealthContent,
    Ward,
    Bed,
    HospitalSettings,
    Invoice,
    InvoiceLine,
    PatientDocument,
    Payment,
    Prescription,
    Refund,
    MedicationSchedule,
    MedicationDoseLog,
    StaffProfile,
    VisitType,
)
from core.forms import appointment_slot_conflicts
from core.views import _audit_appointment_change
from core.api.permissions import IsPatientUser, IsReceptionUser
from core.api.throttling import AppointmentWriteRateThrottle
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from core.models import Patient, PatientAccount, PatientVerificationChallenge
from core.services.numbering import next_number
from core.services.verification import VerificationProvider
from core.views import _audit_patient_change
from core.api.throttling import AuthAnonRateThrottle
from core.api.serializers import (
    PatientProfileSerializer,
    PatientProfileUpdateSerializer,
    OnboardingRequestOtpSerializer,
    OnboardingRegisterSerializer,
    OnboardingClaimPatientSerializer,
    DoctorSerializer,
    DepartmentDetailSerializer,
    HospitalInfoSerializer,
    HospitalFacilitySerializer,
    HospitalFaqSerializer,
    HealthPackageSerializer,
    HealthContentSerializer,
    VisitTypeSerializer,
    AppointmentListSerializer,
    AppointmentDetailSerializer,
    AppointmentBookingSerializer,
    HealthRecordDetailSerializer,
    HealthRecordListSerializer,
    PatientDocumentSerializer,
    PrescriptionDetailSerializer,
    PrescriptionListSerializer,
    PatientInvoiceListSerializer,
    PatientInvoiceDetailSerializer,
    PatientReceiptSerializer,
    PatientMedicationScheduleSerializer,
    MedicationDoseLogSerializer,
)
from core.services.documents import (
    open_validated_patient_document,
    patient_document_download_name,
)

User = get_user_model()


class PatientProfileView(APIView):
    permission_classes = [IsPatientUser]

    def get(self, request):
        patient = request.user.patient_account.patient
        serializer = PatientProfileSerializer(patient)
        return Response(serializer.data)

    def patch(self, request):
        patient = request.user.patient_account.patient
        serializer = PatientProfileUpdateSerializer(patient, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        changed_fields = list(serializer.validated_data.keys())
        with transaction.atomic():
            serializer.save()
            _audit_patient_change(
                request,
                patient,
                "patient.demographics_updated",
                changed_fields,
            )

        full_serializer = PatientProfileSerializer(patient)
        return Response(full_serializer.data)


class OnboardingRequestOtpView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthAnonRateThrottle]

    def post(self, request):
        serializer = OnboardingRequestOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        contact = serializer.validated_data["contact"].strip().lower()
        purpose = serializer.validated_data["purpose"]

        # Create challenge without exposing if contact exists or not
        challenge, code = VerificationProvider.create_challenge(
            contact=contact,
            purpose=purpose,
        )

        response_data = {
            "message": "If the contact is valid, a verification code has been dispatched.",
            "expires_in_minutes": 10,
        }
        # In test / debug environment, attach the code for testing
        if getattr(settings, "DEBUG", False):
            response_data["_debug_code"] = code

        return Response(response_data, status=status.HTTP_200_OK)


class OnboardingRegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthAnonRateThrottle]

    def post(self, request):
        serializer = OnboardingRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        contact = serializer.validated_data["contact"].strip().lower()
        code = serializer.validated_data["code"].strip()
        full_name = serializer.validated_data["full_name"].strip()
        password = serializer.validated_data["password"]
        dob = serializer.validated_data.get("date_of_birth")
        terms_version = serializer.validated_data["terms_version"]

        is_valid, msg, challenge = VerificationProvider.verify_challenge(
            contact=contact,
            purpose=PatientVerificationChallenge.Purpose.REGISTRATION,
            code=code,
        )
        if not is_valid:
            return Response(
                {
                    "error": {
                        "status_code": status.HTTP_400_BAD_REQUEST,
                        "message": msg,
                        "details": {"code": [msg]},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check username / user conflict
        username = contact
        if User.objects.filter(username=username).exists():
            return Response(
                {
                    "error": {
                        "status_code": status.HTTP_409_CONFLICT,
                        "message": "An account already exists for this contact.",
                        "details": {},
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            # Server-issued MRN via NumberSequence
            server_mrn = next_number("PATIENT")
            is_email = "@" in contact
            patient = Patient.objects.create(
                mrn=server_mrn,
                full_name=full_name,
                phone="" if is_email else contact,
                email=contact if is_email else "",
                date_of_birth=dob,
            )

            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=full_name.split()[0] if full_name else "",
            )

            account = PatientAccount.objects.create(
                user=user,
                patient=patient,
                is_verified=True,
                phone_verified=not is_email,
                email_verified=is_email,
                terms_version_accepted=terms_version,
                terms_accepted_at=timezone.now(),
            )

        # Generate JWT session
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "patient": PatientProfileSerializer(patient).data,
            },
            status=status.HTTP_201_CREATED,
        )


class OnboardingClaimPatientView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthAnonRateThrottle]

    def post(self, request):
        serializer = OnboardingClaimPatientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        mrn = serializer.validated_data["mrn"].strip()
        contact = serializer.validated_data["contact"].strip().lower()
        code = serializer.validated_data["code"].strip()
        password = serializer.validated_data["password"]
        terms_version = serializer.validated_data["terms_version"]

        is_valid, msg, challenge = VerificationProvider.verify_challenge(
            contact=contact,
            purpose=PatientVerificationChallenge.Purpose.CLAIM_PATIENT,
            code=code,
        )
        if not is_valid:
            return Response(
                {
                    "error": {
                        "status_code": status.HTTP_400_BAD_REQUEST,
                        "message": msg,
                        "details": {"code": [msg]},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        patient = Patient.objects.filter(mrn=mrn).first()
        patient_phone = (patient.phone or "").strip().lower() if patient else ""
        patient_email = (patient.email or "").strip().lower() if patient else ""

        # Uniform error response for nonexistent MRN or non-matching contact to prevent MRN enumeration
        if not patient or (contact != patient_phone and contact != patient_email):
            return Response(
                {
                    "error": {
                        "status_code": status.HTTP_404_NOT_FOUND,
                        "message": "Patient record with provided MRN and verified contact could not be verified. Please contact hospital reception.",
                        "details": {},
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Ensure patient does not already have an active linked account
        if hasattr(patient, "account") and patient.account is not None:
            return Response(
                {
                    "error": {
                        "status_code": status.HTTP_409_CONFLICT,
                        "message": "This patient record is already linked to an active mobile account.",
                        "details": {},
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        username = contact
        if User.objects.filter(username=username).exists():
            return Response(
                {
                    "error": {
                        "status_code": status.HTTP_409_CONFLICT,
                        "message": "An account with this contact already exists.",
                        "details": {},
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=patient.full_name.split()[0] if patient.full_name else "",
            )
            is_email = "@" in contact
            account = PatientAccount.objects.create(
                user=user,
                patient=patient,
                is_verified=True,
                phone_verified=not is_email,
                email_verified=is_email,
                terms_version_accepted=terms_version,
                terms_accepted_at=timezone.now(),
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "patient": PatientProfileSerializer(patient).data,
            },
            status=status.HTTP_200_OK,
        )



class DoctorListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = DoctorSerializer

    def get_queryset(self):
        qs = (
            StaffProfile.objects.filter(
                user__groups__name="Doctor",
                user__is_active=True,
                department__is_active=True,
                is_public=True,
            )
            .select_related("user", "department")
            .order_by("user__first_name", "user__last_name", "pk")
        )
        dept = self.request.query_params.get("department")
        if dept:
            qs = qs.filter(department__code__iexact=dept) | qs.filter(department__name__iexact=dept)
        search = self.request.query_params.get("search")
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(department__name__icontains=search)
                | Q(qualifications__icontains=search)
                | Q(biography__icontains=search)
            )
        return qs


class DoctorDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = DoctorSerializer

    def get_queryset(self):
        return (
            StaffProfile.objects.filter(
                user__groups__name="Doctor",
                user__is_active=True,
                department__is_active=True,
                is_public=True,
            )
            .select_related("user", "department")
        )


class DepartmentListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = DepartmentDetailSerializer

    def get_queryset(self):
        return Department.objects.filter(is_active=True).order_by("display_order", "name")


class HospitalInfoView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        hospital = HospitalSettings.objects.filter(pk=1).first()
        if not hospital:
            hospital = HospitalSettings.objects.create(
                pk=1,
                name="Vedant Hospital",
                tagline="Multi-Speciality Care, Advanced Surgery & 24x7 Emergency",
                phone="+919415012345",
                emergency_phone="102",
                emergency_phone_display="+91 94150 12345 / 102",
                ambulance_phone="108",
                ambulance_phone_display="+91 94150 12346 / 108",
                reception_phone="+915222418900",
                reception_phone_display="+91 (0522) 2418900",
                email="contact@vedanthospitallucknow.com",
                address="Hardoi Road, Near Raj State, Kanpur Ring Road, Rajaji Puram, Lucknow-226017, Uttar Pradesh",
                landmark="Near Raj State, Kanpur Ring Road Intersection",
                city="Lucknow, Uttar Pradesh - 226017",
                maps_query="Vedant Hospital, Hardoi Road, Rajajipuram, Lucknow",
            )
        serializer = HospitalInfoSerializer(hospital)
        return Response(serializer.data)


class HospitalFacilityListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = HospitalFacilitySerializer

    def get_queryset(self):
        qs = HospitalFacility.objects.filter(is_active=True).order_by("display_order", "id")
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__iexact=category)
        return qs


class HospitalFaqListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = HospitalFaqSerializer

    def get_queryset(self):
        qs = HospitalFaq.objects.filter(is_active=True).order_by("display_order", "id")
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__iexact=category)
        search = self.request.query_params.get("search")
        if search:
            from django.db.models import Q
            qs = qs.filter(Q(question__icontains=search) | Q(answer__icontains=search))
        return qs


class BedAvailabilityView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        from django.db.models import Count, Q
        from django.utils import timezone

        generated_at = timezone.now()
        wards = (
            Ward.objects.filter(is_active=True)
            .values("category")
            .annotate(
                total=Count("beds"),
                available=Count("beds", filter=Q(beds__status=Bed.Status.AVAILABLE)),
                occupied=Count("beds", filter=Q(beds__status=Bed.Status.OCCUPIED)),
                maintenance=Count("beds", filter=Q(beds__status=Bed.Status.MAINTENANCE)),
            )
            .order_by("category")
        )
        labels = dict(Ward.Category.choices)
        categories = [
            {
                "category": row["category"],
                "label": labels[row["category"]],
                "total": row["total"],
                "available": row["available"],
                "occupied": row["occupied"],
                "maintenance": row["maintenance"],
            }
            for row in wards
            if row["total"] > 0
        ]
        response = Response({
            "generated_at": generated_at,
            "fresh_for_seconds": 60,
            "disclaimer": "Availability is indicative and subject to confirmation during admission.",
            "categories": categories,
        })
        response["Cache-Control"] = "public, max-age=30, stale-if-error=300"
        return response


class HealthPackageListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = HealthPackageSerializer

    def get_queryset(self):
        from django.db.models import Q
        from django.utils import timezone

        today = timezone.localdate()
        return (
            HealthPackage.objects.filter(is_published=True, valid_from__lte=today)
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today))
            .prefetch_related("included_services")
            .order_by("name", "id")
        )


class OpdHistoricalMetricsView(APIView):
    permission_classes = [AllowAny]
    minimum_bucket_size = 5

    def get(self, request):
        from collections import defaultdict
        from datetime import timedelta
        from django.utils import timezone

        try:
            weekday = int(request.query_params.get("weekday", timezone.localdate().weekday()))
        except ValueError:
            return Response({"detail": "weekday must be an integer from 0 to 6."}, status=400)
        if weekday not in range(7):
            return Response({"detail": "weekday must be an integer from 0 to 6."}, status=400)

        end_date = timezone.localdate()
        start_date = end_date - timedelta(days=28)
        queryset = Appointment.objects.filter(
            scheduled_at__date__gte=start_date,
            scheduled_at__date__lt=end_date,
        ).select_related("doctor__department")
        department = request.query_params.get("department", "").strip()
        if department:
            queryset = queryset.filter(doctor__department__code__iexact=department)

        buckets = defaultdict(lambda: {
            "booked": 0, "check_ins": 0, "completed": 0, "no_shows": 0,
            "wait_minutes": [], "duration_minutes": [],
        })
        complete_waits = 0
        for appointment in queryset.iterator():
            local_scheduled = timezone.localtime(appointment.scheduled_at)
            if local_scheduled.weekday() != weekday:
                continue
            bucket = buckets[local_scheduled.hour]
            bucket["booked"] += 1
            if appointment.checked_in_at:
                bucket["check_ins"] += 1
            if appointment.status == Appointment.Status.COMPLETED:
                bucket["completed"] += 1
            if appointment.status == Appointment.Status.NO_SHOW:
                bucket["no_shows"] += 1
            if appointment.checked_in_at and appointment.started_at and appointment.started_at >= appointment.checked_in_at:
                bucket["wait_minutes"].append((appointment.started_at - appointment.checked_in_at).total_seconds() / 60)
                complete_waits += 1
            if appointment.started_at and appointment.completed_at and appointment.completed_at >= appointment.started_at:
                bucket["duration_minutes"].append((appointment.completed_at - appointment.started_at).total_seconds() / 60)

        hourly = []
        total_records = sum(bucket["booked"] for bucket in buckets.values())
        for hour, bucket in sorted(buckets.items()):
            if bucket["booked"] < self.minimum_bucket_size:
                continue
            waits = bucket.pop("wait_minutes")
            durations = bucket.pop("duration_minutes")
            hourly.append({
                "hour": hour,
                **bucket,
                "sample_size": bucket["booked"],
                "average_wait_minutes": round(sum(waits) / len(waits)) if waits else None,
                "average_consultation_minutes": round(sum(durations) / len(durations)) if durations else None,
            })

        return Response({
            "kind": "historical",
            "generated_at": timezone.now(),
            "date_range": {"start": start_date, "end_exclusive": end_date},
            "weekday": weekday,
            "department": department or None,
            "minimum_bucket_size": self.minimum_bucket_size,
            "data_quality": {
                "records": total_records,
                "complete_wait_samples": complete_waits,
                "forecast_available": False,
                "message": "Forecasting is disabled until sufficient lifecycle data is back-tested and approved.",
            },
            "definitions": {
                "booked": "Appointments scheduled in the hour, including later no-shows or cancellations.",
                "average_wait_minutes": "Mean elapsed time from recorded check-in to consultation start.",
            },
            "hourly": hourly,
        })


class HealthContentListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = HealthContentSerializer

    def get_queryset(self):
        from django.db.models import Q
        today = timezone.localdate()
        return HealthContent.objects.filter(status=HealthContent.Status.PUBLISHED, effective_from__lte=today).filter(Q(expires_on__isnull=True) | Q(expires_on__gte=today)).select_related("reviewer").order_by("category", "title")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response["Cache-Control"] = "public, max-age=300, stale-if-error=86400"
        return response


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

        except (IntegrityError, OperationalError):
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


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": {"status_code": 400, "message": "Refresh token is required.", "details": {}}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            from rest_framework_simplejwt.tokens import RefreshToken
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"message": "Successfully logged out."}, status=status.HTTP_200_OK)
        except Exception:
            return Response(
                {"error": {"status_code": 400, "message": "Invalid or expired token.", "details": {}}},
                status=status.HTTP_400_BAD_REQUEST,
            )


class LogoutAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        tokens = OutstandingToken.objects.filter(user=request.user)
        for token in tokens:
            BlacklistedToken.objects.get_or_create(token=token)
        return Response({"message": "Successfully logged out from all devices."}, status=status.HTTP_200_OK)


def _released_health_records(patient):
    visible_prescriptions = Prescription.objects.filter(
        patient=patient,
        status=Prescription.Status.ISSUED,
        issued_at__isnull=False,
    ).only("id", "consultation_id")
    return (
        Consultation.objects.filter(
            patient=patient,
            patient_released_at__isnull=False,
            patient_access_revoked_at__isnull=True,
        )
        .select_related("appointment", "doctor__user", "doctor__department")
        .prefetch_related(
            Prefetch(
                "prescriptions",
                queryset=visible_prescriptions,
                to_attr="visible_prescriptions",
            )
        )
        .order_by("-created_at", "-id")
    )


def _issued_prescriptions(patient):
    return (
        Prescription.objects.filter(
            patient=patient,
            status=Prescription.Status.ISSUED,
            issued_at__isnull=False,
        )
        .select_related("doctor__user", "doctor__department")
        .annotate(item_count=Count("items"))
        .order_by("-issued_at", "-id")
    )


def _released_documents(patient):
    return PatientDocument.objects.filter(
        patient=patient,
        validation_status=PatientDocument.ValidationStatus.CLEAN,
        patient_released_at__isnull=False,
        patient_access_revoked_at__isnull=True,
        content_type__in=("application/pdf", "image/jpeg", "image/png", "image/webp"),
        size_bytes__gt=0,
        size_bytes__lte=settings.PATIENT_DOCUMENT_MAX_BYTES,
    ).order_by("-created_at", "-id")


def _clinical_response(data):
    response = Response(data)
    response["Cache-Control"] = "private, no-store"
    response["Pragma"] = "no-cache"
    patch_vary_headers(response, ("Authorization",))
    return response


class PatientClinicalAPIView(APIView):
    permission_classes = [IsPatientUser]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["Pragma"] = "no-cache"
        patch_vary_headers(response, ("Authorization",))
        return response


class HealthRecordListView(PatientClinicalAPIView):
    permission_classes = [IsPatientUser]

    def get(self, request):
        patient = request.user.patient_account.patient
        return _clinical_response(
            HealthRecordListSerializer(
                _released_health_records(patient), many=True
            ).data
        )


class HealthRecordDetailView(PatientClinicalAPIView):
    permission_classes = [IsPatientUser]

    def get(self, request, pk):
        patient = request.user.patient_account.patient
        try:
            record = _released_health_records(patient).get(pk=pk)
        except Consultation.DoesNotExist:
            raise Http404("Health record not found")
        return _clinical_response(HealthRecordDetailSerializer(record).data)


class PrescriptionListView(PatientClinicalAPIView):
    permission_classes = [IsPatientUser]

    def get(self, request):
        patient = request.user.patient_account.patient
        return _clinical_response(
            PrescriptionListSerializer(_issued_prescriptions(patient), many=True).data
        )


class PrescriptionDetailView(PatientClinicalAPIView):
    permission_classes = [IsPatientUser]

    def get(self, request, pk):
        patient = request.user.patient_account.patient
        try:
            prescription = _issued_prescriptions(patient).prefetch_related(
                "items__medicine"
            ).get(pk=pk)
        except Prescription.DoesNotExist:
            raise Http404("Prescription not found")
        return _clinical_response(PrescriptionDetailSerializer(prescription).data)


class PatientDocumentListView(PatientClinicalAPIView):
    permission_classes = [IsPatientUser]

    def get(self, request):
        patient = request.user.patient_account.patient
        return _clinical_response(
            PatientDocumentSerializer(_released_documents(patient), many=True).data
        )


class PatientDocumentDownloadView(PatientClinicalAPIView):
    permission_classes = [IsPatientUser]

    def get(self, request, public_id):
        patient = request.user.patient_account.patient
        try:
            document = _released_documents(patient).get(public_id=public_id)
            file_handle = open_validated_patient_document(document)
        except (PatientDocument.DoesNotExist, FileNotFoundError):
            raise Http404("Document not found")

        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=patient_document_download_name(document),
            content_type=document.content_type,
        )
        response["Content-Length"] = str(document.size_bytes)
        response["Cache-Control"] = "private, no-store"
        response["Pragma"] = "no-cache"
        response["X-Content-Type-Options"] = "nosniff"
        patch_vary_headers(response, ("Authorization",))
        return response


class PatientInvoiceListView(APIView):
    permission_classes = [IsPatientUser]

    def get(self, request):
        patient = request.user.patient_account.patient
        # Only show issued or voided invoices belonging to the patient (exclude drafts)
        invoices = (
            Invoice.objects.filter(patient=patient, status__in=[Invoice.Status.ISSUED, Invoice.Status.VOIDED])
            .prefetch_related("payments", "adjustments")
            .order_by("-created_at")
        )
        serializer = PatientInvoiceListSerializer(invoices, many=True)
        return Response(serializer.data)


class PatientInvoiceDetailView(APIView):
    permission_classes = [IsPatientUser]

    def get(self, request, pk):
        patient = request.user.patient_account.patient
        try:
            invoice = (
                Invoice.objects.filter(patient=patient, status__in=[Invoice.Status.ISSUED, Invoice.Status.VOIDED])
                .prefetch_related("lines", "payments__method", "adjustments")
                .get(pk=pk)
            )
        except Invoice.DoesNotExist:
            raise Http404("Invoice not found")
        serializer = PatientInvoiceDetailSerializer(invoice)
        return Response(serializer.data)


class PatientReceiptDetailView(APIView):
    permission_classes = [IsPatientUser]

    def get(self, request, receipt_number):
        patient = request.user.patient_account.patient
        try:
            payment = (
                Payment.objects.select_related("invoice", "invoice__patient", "method")
                .filter(invoice__patient=patient)
                .get(receipt_number=receipt_number)
            )
        except Payment.DoesNotExist:
            raise Http404("Receipt not found")
        serializer = PatientReceiptSerializer(payment)
        return Response(serializer.data)


class PatientPaymentInitiateView(APIView):
    permission_classes = [IsPatientUser]

    def post(self, request, pk):
        # Online payment gateway has not been configured by owner yet
        return Response(
            {
                "detail": "Online payments are currently disabled pending payment gateway credentials configuration. Please settle bills at the hospital billing desk.",
                "enabled": False,
                "supported_offline_methods": ["Cash at Counter", "Card / POS Terminal", "Hospital Desk UPI"],
            },
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

class DigitalCheckInPassIssueView(PatientClinicalAPIView):
    permission_classes = [IsPatientUser]

    def post(self, request):
        patient = request.user.patient_account.patient
        candidates = Appointment.objects.filter(
            patient=patient,
            status=Appointment.Status.SCHEDULED,
            scheduled_at__date=timezone.localdate(),
        )
        appointment_id = request.data.get("appointment_id")
        if appointment_id:
            candidates = candidates.filter(pk=appointment_id)
        if candidates.count() != 1:
            return Response({"detail": "Select one eligible appointment."}, status=409)
        appointment = candidates.get()
        raw_token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = timezone.now() + timedelta(minutes=5)
        with transaction.atomic():
            DigitalCheckInPass.objects.filter(
                patient=patient, consumed_at__isnull=True, revoked_at__isnull=True
            ).update(revoked_at=timezone.now())
            DigitalCheckInPass.objects.create(
                appointment=appointment, patient=patient,
                token_digest=digest, expires_at=expires_at,
            )
        return _clinical_response({
            "token": raw_token,
            "expires_at": expires_at,
            "appointment_id": appointment.pk,
        })


class DigitalCheckInConsumeView(APIView):
    permission_classes = [IsReceptionUser]

    def post(self, request):
        raw_token = request.data.get("token", "")
        digest = hashlib.sha256(raw_token.encode()).hexdigest()
        with transaction.atomic():
            try:
                qr_pass = DigitalCheckInPass.objects.select_for_update().select_related("appointment").get(
                    token_digest=digest
                )
            except DigitalCheckInPass.DoesNotExist:
                raise Http404("Pass not found")
            appointment = Appointment.objects.select_for_update().get(pk=qr_pass.appointment_id)
            if qr_pass.revoked_at or qr_pass.expires_at <= timezone.now():
                raise Http404("Pass not found")
            if qr_pass.consumed_at:
                return Response({"detail": "Pass has already been consumed."}, status=409)
            if appointment.status != Appointment.Status.SCHEDULED:
                return Response({"detail": "Appointment is not eligible for check-in."}, status=409)
            now = timezone.now()
            appointment.status = Appointment.Status.CHECKED_IN
            appointment.checked_in_at = now
            appointment.save(update_fields=["status", "checked_in_at", "updated_at"])
            qr_pass.consumed_at = now
            qr_pass.save(update_fields=["consumed_at", "updated_at"])
            actor = StaffProfile.objects.get(user=request.user)
            AuditEvent.objects.create(
                actor=actor, action="appointment.qr_checked_in",
                target_type="appointment", target_id=str(appointment.pk),
                details={"source": "qr"},
            )
        return Response({"appointment_id": appointment.pk, "status": "checked_in", "replayed": False})


class PatientMedicationScheduleListView(PatientClinicalAPIView):
    permission_classes = [IsPatientUser]

    def get(self, request):
        patient = request.user.patient_account.patient
        schedules = MedicationSchedule.objects.filter(patient=patient, is_active=True, prescription_item__prescription__status=Prescription.Status.ISSUED).select_related("prescription_item__medicine", "prescription_item__prescription__doctor", "confirmed_by").order_by("-start_date", "-id")
        return _clinical_response(PatientMedicationScheduleSerializer(schedules, many=True).data)


class PatientMedicationScheduleDetailView(PatientClinicalAPIView):
    permission_classes = [IsPatientUser]

    def get(self, request, pk):
        patient = request.user.patient_account.patient
        try:
            schedule = MedicationSchedule.objects.filter(patient=patient, prescription_item__prescription__status=Prescription.Status.ISSUED).select_related("prescription_item__medicine", "prescription_item__prescription__doctor", "confirmed_by").get(pk=pk)
        except MedicationSchedule.DoesNotExist:
            raise Http404("Medication schedule not found")
        return _clinical_response(PatientMedicationScheduleSerializer(schedule).data)


class PatientMedicationDoseLogCreateView(APIView):
    permission_classes = [IsPatientUser]

    def post(self, request):
        patient = request.user.patient_account.patient
        raw_key = request.data.get("idempotency_key")
        if raw_key:
            existing = MedicationDoseLog.objects.filter(idempotency_key=raw_key, schedule__patient=patient).first()
            if existing:
                return Response(MedicationDoseLogSerializer(existing).data)
        serializer = MedicationDoseLogSerializer(data=request.data)
        if not serializer.is_valid():
            existing_slot = MedicationDoseLog.objects.filter(schedule_id=request.data.get("schedule"), schedule__patient=patient, scheduled_time=request.data.get("scheduled_time")).first()
            if existing_slot:
                return Response(MedicationDoseLogSerializer(existing_slot).data)
            serializer.is_valid(raise_exception=True)
        if serializer.validated_data["schedule"].patient_id != patient.id:
            raise Http404("Medication schedule not found")
        dose_log = serializer.save()
        return Response(MedicationDoseLogSerializer(dose_log).data, status=status.HTTP_201_CREATED)
