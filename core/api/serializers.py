from rest_framework import serializers
from django.utils import timezone
from core.models import Patient, StaffProfile, VisitType, Appointment, HospitalSettings
from core.forms import appointment_slot_conflicts


class PatientProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = [
            "mrn",
            "full_name",
            "date_of_birth",
            "phone",
            "email",
            "emergency_contact_name",
            "emergency_contact_phone",
            "allergy_safety_notes",
        ]
        read_only_fields = fields


class DoctorSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    department_name = serializers.CharField(source="department.name", read_only=True)
    department_code = serializers.CharField(source="department.code", read_only=True)

    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "employee_id",
            "full_name",
            "department_name",
            "department_code",
            "job_title",
        ]

    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


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

