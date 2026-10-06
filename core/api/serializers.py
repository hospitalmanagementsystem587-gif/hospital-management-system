from rest_framework import serializers
from django.utils import timezone
from django.urls import reverse

from core.models import (
    Adjustment,
    Appointment,
    Consultation,
    Department,
    HospitalFacility,
    HospitalFaq,
    HealthPackage,
    HealthContent,
    HospitalSettings,
    Invoice,
    InvoiceLine,
    Medicine,
    MedicationSchedule,
    MedicationDoseLog,
    Patient,
    PatientDocument,
    Payment,
    PaymentMethod,
    Prescription,
    PrescriptionItem,
    Refund,
    StaffProfile,
    VisitType,
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
        ]

    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


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


class HealthPackageSerializer(serializers.ModelSerializer):
    included_services = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")

    class Meta:
        model = HealthPackage
        fields = [
            "id", "code", "name", "description", "included_services", "price",
            "eligibility", "fasting_instructions", "valid_from", "valid_until",
        ]


class HealthContentSerializer(serializers.ModelSerializer):
    reviewer = serializers.SerializerMethodField()

    def get_reviewer(self, obj):
        return obj.reviewer.get_full_name() or obj.reviewer.username

    class Meta:
        model = HealthContent
        fields = ["slug", "title", "category", "summary", "body", "key_takeaways", "audience", "language", "references", "emergency_disclaimer", "version", "effective_from", "expires_on", "reviewer", "reviewed_at"]


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


class PatientInvoiceLineSerializer(serializers.ModelSerializer):
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)

    class Meta:
        model = InvoiceLine
        fields = [
            "id",
            "description",
            "quantity",
            "unit_price",
            "tax_rate",
            "discount_amount",
            "line_total",
        ]


class PatientRefundSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)

    class Meta:
        model = Refund
        fields = [
            "id",
            "amount",
            "reason",
            "status",
            "created_at",
        ]


class PatientPaymentSerializer(serializers.ModelSerializer):
    method = serializers.CharField(source="method.name", read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    receipt_url = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "receipt_number",
            "method",
            "amount",
            "reference",
            "received_at",
            "receipt_url",
        ]

    def get_receipt_url(self, obj):
        return reverse("patient_receipt_detail", kwargs={"receipt_number": obj.receipt_number})


class PatientAdjustmentSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)

    class Meta:
        model = Adjustment
        fields = [
            "id",
            "amount",
            "reason",
            "created_at",
        ]


class PatientInvoiceListSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    tax_total = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    discount_total = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    paid_total = serializers.SerializerMethodField()
    outstanding_balance = serializers.SerializerMethodField()
    currency = serializers.CharField(default="INR", read_only=True)
    is_settled = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "status",
            "issued_at",
            "created_at",
            "subtotal",
            "tax_total",
            "discount_total",
            "total",
            "paid_total",
            "outstanding_balance",
            "currency",
            "is_settled",
        ]

    def get_paid_total(self, obj):
        from decimal import Decimal
        from django.db.models import Sum
        paid = obj.payments.aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
        return f"{paid:.2f}"

    def get_outstanding_balance(self, obj):
        from core.views import _invoice_outstanding
        bal = _invoice_outstanding(obj)
        return f"{bal:.2f}"

    def get_is_settled(self, obj):
        from core.views import _invoice_outstanding
        return _invoice_outstanding(obj) <= 0


class PatientInvoiceDetailSerializer(PatientInvoiceListSerializer):
    lines = PatientInvoiceLineSerializer(many=True, read_only=True)
    payments = PatientPaymentSerializer(many=True, read_only=True)
    adjustments = PatientAdjustmentSerializer(many=True, read_only=True)

    class Meta(PatientInvoiceListSerializer.Meta):
        fields = PatientInvoiceListSerializer.Meta.fields + [
            "lines",
            "payments",
            "adjustments",
        ]


class PatientReceiptSerializer(serializers.ModelSerializer):
    method = serializers.CharField(source="method.name", read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    patient_mrn = serializers.CharField(source="invoice.patient.mrn", read_only=True)
    patient_name = serializers.CharField(source="invoice.patient.full_name", read_only=True)
    currency = serializers.CharField(default="INR", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "receipt_number",
            "invoice_number",
            "patient_mrn",
            "patient_name",
            "amount",
            "currency",
            "method",
            "reference",
            "received_at",
        ]


class PatientMedicationScheduleSerializer(serializers.ModelSerializer):
    medicine_name = serializers.SerializerMethodField()
    medicine_generic_name = serializers.CharField(source="prescription_item.medicine.generic_name", read_only=True)
    prescription_number = serializers.CharField(source="prescription_item.prescription.number", read_only=True)
    prescribing_doctor_name = serializers.SerializerMethodField()
    confirmed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = MedicationSchedule
        fields = ["id", "prescription_item", "prescription_number", "medicine_name", "medicine_generic_name", "prescribing_doctor_name", "dose_amount", "dose_unit", "target_times", "meal_relation", "start_date", "end_date", "timezone", "is_active", "confirmed_by_name", "confirmed_at", "version"]

    def get_medicine_name(self, obj):
        medicine = obj.prescription_item.medicine
        return medicine.brand_name or medicine.generic_name

    def get_prescribing_doctor_name(self, obj):
        user = obj.prescription_item.prescription.doctor.user
        return user.get_full_name() or user.username

    def get_confirmed_by_name(self, obj):
        return obj.confirmed_by.user.get_full_name() or obj.confirmed_by.user.username


class MedicationDoseLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicationDoseLog
        fields = ["id", "schedule", "scheduled_time", "action", "logged_at", "idempotency_key"]
        read_only_fields = ["id"]
