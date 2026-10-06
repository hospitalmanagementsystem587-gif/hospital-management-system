from rest_framework import serializers
from django.utils import timezone
from django.urls import reverse

from core.models import (
    Appointment,
    Consultation,
    Department,
    HospitalFacility,
    HospitalFaq,
    HospitalSettings,
    Medicine,
    Patient,
    PatientDocument,
    Prescription,
    PrescriptionItem,
    StaffProfile,
    VisitType,
    PatientFeedback,
)
from core.forms import appointment_slot_conflicts


class PatientProfileSerializer(serializers.ModelSerializer):
    phone_verified = serializers.BooleanField(source="account.phone_verified", read_only=True)
    email_verified = serializers.BooleanField(source="account.email_verified", read_only=True)

    class Meta:
        model = Patient
        fields = [
            "mrn",
            "full_name",
            "date_of_birth",
            "phone",
            "phone_verified",
            "email",
            "email_verified",
            "emergency_contact_name",
            "emergency_contact_phone",
            "allergy_safety_notes",
        ]
        read_only_fields = [
            "mrn",
            "phone_verified",
            "email_verified",
            "allergy_safety_notes",
        ]


class PatientProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = [
            "email",
            "address",
            "emergency_contact_name",
            "emergency_contact_phone",
        ]


class OnboardingRequestOtpSerializer(serializers.Serializer):
    contact = serializers.CharField(max_length=120)
    purpose = serializers.ChoiceField(
        choices=["registration", "claim_patient", "password_reset"]
    )
    terms_version = serializers.CharField(max_length=32, required=False, default="1.0")


class OnboardingRegisterSerializer(serializers.Serializer):
    contact = serializers.CharField(max_length=120)
    code = serializers.CharField(max_length=16)
    full_name = serializers.CharField(max_length=200)
    password = serializers.CharField(min_length=8, write_only=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    terms_version = serializers.CharField(max_length=32, default="1.0")


class OnboardingClaimPatientSerializer(serializers.Serializer):
    mrn = serializers.CharField(max_length=40)
    contact = serializers.CharField(max_length=120)
    code = serializers.CharField(max_length=16)
    password = serializers.CharField(min_length=8, write_only=True)
    terms_version = serializers.CharField(max_length=32, default="1.0")



class DoctorSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    department_name = serializers.CharField(source="department.name", read_only=True)
    department_code = serializers.CharField(source="department.code", read_only=True)
    consultation_fee = serializers.IntegerField(read_only=True)
    rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "employee_id",
            "full_name",
            "department_name",
            "department_code",
            "job_title",
            "qualifications",
            "experience_years",
            "languages",
            "opd_room",
            "opd_schedule",
            "consultation_fee",
            "biography",
            "rating",
            "review_count",
        ]

    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_rating(self, obj):
        from django.db.models import Avg
        MIN_REVIEWS_THRESHOLD = 3
        published = obj.doctor_feedbacks.filter(status=PatientFeedback.Status.PUBLISHED)
        count = published.count()
        if count < MIN_REVIEWS_THRESHOLD:
            return 0.0
        avg_val = published.aggregate(avg=Avg("rating"))["avg"]
        return round(float(avg_val), 1) if avg_val is not None else 0.0

    def get_review_count(self, obj):
        return obj.doctor_feedbacks.filter(status=PatientFeedback.Status.PUBLISHED).count()


class DepartmentDetailSerializer(serializers.ModelSerializer):
    doctor_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = [
            "id",
            "code",
            "name",
            "description",
            "icon_name",
            "display_order",
            "doctor_count",
        ]

    def get_doctor_count(self, obj):
        return obj.staff.filter(
            user__groups__name="Doctor",
            user__is_active=True,
            is_public=True,
        ).count()


class HospitalInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = HospitalSettings
        fields = [
            "name",
            "tagline",
            "timezone",
            "currency_code",
            "phone",
            "emergency_phone",
            "emergency_phone_display",
            "ambulance_phone",
            "ambulance_phone_display",
            "reception_phone",
            "reception_phone_display",
            "email",
            "address",
            "landmark",
            "city",
            "maps_query",
        ]


class HospitalFacilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = HospitalFacility
        fields = [
            "id",
            "title",
            "category",
            "description",
            "highlight",
            "display_order",
        ]


class HospitalFaqSerializer(serializers.ModelSerializer):
    class Meta:
        model = HospitalFaq
        fields = [
            "id",
            "question",
            "answer",
            "category",
            "highlight_tag",
            "display_order",
        ]


class VisitTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitType
        fields = [
            "id",
            "code",
            "name",
        ]


class AppointmentListSerializer(serializers.ModelSerializer):
    doctor_name = serializers.SerializerMethodField()
    doctor_department = serializers.CharField(source="doctor.department.name", read_only=True)
    visit_type_name = serializers.CharField(source="visit_type.name", read_only=True)

    class Meta:
        model = Appointment
        fields = [
            "id",
            "doctor",
            "doctor_name",
            "doctor_department",
            "visit_type",
            "visit_type_name",
            "scheduled_at",
            "status",
            "queue_number",
            "created_at",
        ]

    def get_doctor_name(self, obj):
        return obj.doctor.user.get_full_name() or obj.doctor.user.username


class AppointmentDetailSerializer(serializers.ModelSerializer):
    doctor_name = serializers.SerializerMethodField()
    doctor_department = serializers.CharField(source="doctor.department.name", read_only=True)
    visit_type_name = serializers.CharField(source="visit_type.name", read_only=True)
    patient_mrn = serializers.CharField(source="patient.mrn", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    patient_phone = serializers.CharField(source="patient.phone", read_only=True)
    hospital_name = serializers.SerializerMethodField()
    hospital_phone = serializers.SerializerMethodField()
    hospital_address = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            "id",
            "patient_mrn",
            "patient_name",
            "patient_phone",
            "doctor",
            "doctor_name",
            "doctor_department",
            "visit_type",
            "visit_type_name",
            "scheduled_at",
            "status",
            "queue_number",
            "checked_in_at",
            "started_at",
            "completed_at",
            "cancelled_at",
            "created_at",
            "hospital_name",
            "hospital_phone",
            "hospital_address",
        ]

    def get_doctor_name(self, obj):
        return obj.doctor.user.get_full_name() or obj.doctor.user.username

    def get_hospital_name(self, obj):
        settings_obj = HospitalSettings.objects.first()
        return settings_obj.name if settings_obj else "Vedant Hospital"

    def get_hospital_phone(self, obj):
        settings_obj = HospitalSettings.objects.first()
        return settings_obj.phone if settings_obj else ""

    def get_hospital_address(self, obj):
        settings_obj = HospitalSettings.objects.first()
        return settings_obj.address if settings_obj else ""


class AppointmentBookingSerializer(serializers.Serializer):
    doctor = serializers.PrimaryKeyRelatedField(
        queryset=StaffProfile.objects.filter(
            user__groups__name="Doctor",
            user__is_active=True,
            department__is_active=True,
        )
    )
    visit_type = serializers.PrimaryKeyRelatedField(
        queryset=VisitType.objects.filter(is_active=True)
    )
    scheduled_at = serializers.DateTimeField()

    def validate_doctor(self, value):
        if not value.user.is_active:
            raise serializers.ValidationError("Doctor is inactive.")
        if not value.department or not value.department.is_active:
            raise serializers.ValidationError("Doctor is not associated with an active department.")
        return value

    def validate_scheduled_at(self, value):
        if value < timezone.now():
            raise serializers.ValidationError("Appointment time must be in the future.")
        return value

    def validate(self, attrs):
        return attrs


class PatientFacingDoctorSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()

    def get_name(self, obj):
        return obj.user.get_full_name() or obj.user.get_username()

    def get_department(self, obj):
        return obj.department.name if obj.department else ""


class HealthRecordListSerializer(serializers.ModelSerializer):
    appointment_id = serializers.IntegerField(read_only=True, allow_null=True)
    doctor = PatientFacingDoctorSerializer(read_only=True)
    encounter_at = serializers.SerializerMethodField()
    released_at = serializers.DateTimeField(source="patient_released_at", read_only=True)

    class Meta:
        model = Consultation
        fields = [
            "id",
            "appointment_id",
            "doctor",
            "encounter_at",
            "released_at",
            "follow_up_date",
        ]

    def get_encounter_at(self, obj):
        if obj.appointment_id and obj.appointment.completed_at:
            return obj.appointment.completed_at
        return obj.created_at


class HealthRecordDetailSerializer(HealthRecordListSerializer):
    prescription_ids = serializers.SerializerMethodField()

    class Meta(HealthRecordListSerializer.Meta):
        fields = HealthRecordListSerializer.Meta.fields + [
            "follow_up_note",
            "prescription_ids",
        ]

    def get_prescription_ids(self, obj):
        return [prescription.id for prescription in obj.visible_prescriptions]


class PrescriptionListSerializer(serializers.ModelSerializer):
    consultation_id = serializers.IntegerField(read_only=True, allow_null=True)
    doctor = PatientFacingDoctorSerializer(read_only=True)
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Prescription
        fields = [
            "id",
            "number",
            "consultation_id",
            "doctor",
            "issued_at",
            "item_count",
        ]


class PatientMedicineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medicine
        fields = [
            "id",
            "generic_name",
            "brand_name",
            "strength",
            "dosage_form",
            "unit",
        ]


class PatientPrescriptionItemSerializer(serializers.ModelSerializer):
    medicine = PatientMedicineSerializer(read_only=True)

    class Meta:
        model = PrescriptionItem
        fields = [
            "id",
            "medicine",
            "dosage",
            "frequency",
            "duration",
            "instructions",
            "quantity",
        ]


class PrescriptionDetailSerializer(PrescriptionListSerializer):
    items = PatientPrescriptionItemSerializer(many=True, read_only=True)

    class Meta(PrescriptionListSerializer.Meta):
        fields = PrescriptionListSerializer.Meta.fields + ["items"]


class PatientDocumentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    document_type_label = serializers.CharField(
        source="get_document_type_display", read_only=True
    )
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = PatientDocument
        fields = [
            "id",
            "document_type",
            "document_type_label",
            "title",
            "created_at",
            "content_type",
            "size_bytes",
            "download_url",
        ]

    def get_download_url(self, obj):
        return reverse("patient_document_download", kwargs={"public_id": obj.public_id})


class FeedbackSubmitSerializer(serializers.ModelSerializer):
    appointment_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = PatientFeedback
        fields = [
            "id",
            "appointment_id",
            "rating",
            "category",
            "comment",
            "is_anonymous_public",
            "created_at",
            "status",
        ]
        read_only_fields = ["id", "created_at", "status"]

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate_comment(self, value):
        # Basic abuse / HTML tag strip check
        if "<script" in value.lower() or "</script>" in value.lower():
            raise serializers.ValidationError("Invalid characters or script tags in comment.")
        return value


class PatientFeedbackDetailSerializer(serializers.ModelSerializer):
    appointment_id = serializers.IntegerField(source="appointment.id", read_only=True)
    doctor_name = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    is_editable = serializers.SerializerMethodField()

    class Meta:
        model = PatientFeedback
        fields = [
            "id",
            "appointment_id",
            "doctor_name",
            "department_name",
            "rating",
            "category",
            "comment",
            "is_anonymous_public",
            "status",
            "is_editable",
            "created_at",
            "updated_at",
            "withdrawn_at",
        ]

    def get_doctor_name(self, obj):
        if obj.doctor and obj.doctor.user:
            return obj.doctor.user.get_full_name() or obj.doctor.user.username
        return ""

    def get_department_name(self, obj):
        if obj.doctor and obj.doctor.department:
            return obj.doctor.department.name
        return ""

    def get_is_editable(self, obj):
        if obj.status in [PatientFeedback.Status.WITHDRAWN, PatientFeedback.Status.REJECTED]:
            return False
        # 48-hour edit/withdrawal window
        return timezone.now() - obj.created_at <= timezone.timedelta(hours=48)


class PublicFeedbackReviewSerializer(serializers.ModelSerializer):
    patient_display_name = serializers.SerializerMethodField()
    doctor_name = serializers.SerializerMethodField()
    date_str = serializers.SerializerMethodField()

    class Meta:
        model = PatientFeedback
        fields = [
            "id",
            "patient_display_name",
            "doctor_name",
            "rating",
            "category",
            "comment",
            "date_str",
            "created_at",
        ]

    def get_patient_display_name(self, obj):
        if obj.is_anonymous_public:
            return "Verified Patient"
        # Hide full MRN or sensitive identifiers; e.g. "S*** G***" or "Verified Patient"
        name_parts = obj.patient.full_name.split()
        if len(name_parts) >= 2:
            return f"{name_parts[0][0]}*** {name_parts[-1][0]}***"
        elif name_parts:
            return f"{name_parts[0][0]}***"
        return "Verified Patient"

    def get_doctor_name(self, obj):
        if obj.doctor and obj.doctor.user:
            return obj.doctor.user.get_full_name() or obj.doctor.user.username
        return ""

    def get_date_str(self, obj):
        return obj.created_at.strftime("%d %b %Y")


class StaffFeedbackModerationSerializer(serializers.ModelSerializer):
    patient_mrn = serializers.CharField(source="patient.mrn", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    doctor_name = serializers.SerializerMethodField()

    class Meta:
        model = PatientFeedback
        fields = [
            "id",
            "patient_mrn",
            "patient_name",
            "doctor_name",
            "appointment_id",
            "rating",
            "category",
            "comment",
            "is_anonymous_public",
            "status",
            "moderation_notes",
            "moderated_by",
            "moderated_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "patient_mrn",
            "patient_name",
            "doctor_name",
            "appointment_id",
            "rating",
            "category",
            "comment",
            "is_anonymous_public",
            "moderated_by",
            "moderated_at",
            "created_at",
        ]

    def get_doctor_name(self, obj):
        if obj.doctor and obj.doctor.user:
            return obj.doctor.user.get_full_name() or obj.doctor.user.username
        return ""
