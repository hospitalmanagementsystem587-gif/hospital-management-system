from decimal import Decimal
import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from .storage import private_patient_document_storage



class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Department(TimestampedModel):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    icon_name = models.CharField(max_length=40, default="medical_services", blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class StaffProfile(TimestampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="staff_profile",
    )
    employee_id = models.CharField(max_length=32, unique=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff",
    )
    job_title = models.CharField(max_length=120, blank=True)
    qualifications = models.CharField(max_length=200, blank=True)
    experience_years = models.PositiveSmallIntegerField(default=0)
    languages = models.CharField(max_length=120, default="Hindi, English", blank=True)
    opd_room = models.CharField(max_length=64, blank=True)
    opd_schedule = models.CharField(max_length=160, blank=True)
    consultation_fee = models.PositiveIntegerField(default=500)
    biography = models.TextField(blank=True)
    is_public = models.BooleanField(default=True)

    def __str__(self):
        display_name = self.user.get_full_name() or self.user.get_username()
        return f"{display_name} · {self.employee_id}"


class HospitalSettings(TimestampedModel):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    name = models.CharField(max_length=200)
    tagline = models.CharField(max_length=255, blank=True)
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    currency_code = models.CharField(max_length=3, default="INR")
    phone = models.CharField(max_length=32, blank=True)
    emergency_phone = models.CharField(max_length=32, default="102", blank=True)
    emergency_phone_display = models.CharField(max_length=64, default="102 / 108", blank=True)
    ambulance_phone = models.CharField(max_length=32, default="108", blank=True)
    ambulance_phone_display = models.CharField(max_length=64, default="108", blank=True)
    reception_phone = models.CharField(max_length=32, blank=True)
    reception_phone_display = models.CharField(max_length=64, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    landmark = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, default="Lucknow, Uttar Pradesh", blank=True)
    maps_query = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="hospital_settings_one_row")
        ]


class HospitalFacility(TimestampedModel):
    title = models.CharField(max_length=120)
    category = models.CharField(max_length=60, default="General")
    description = models.TextField()
    highlight = models.CharField(max_length=120, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "title"]

    def __str__(self):
        return f"{self.title} ({self.category})"


class HospitalFaq(TimestampedModel):
    question = models.CharField(max_length=255)
    answer = models.TextField()
    category = models.CharField(max_length=80, default="General Information")
    highlight_tag = models.CharField(max_length=80, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.question


class NumberSequence(TimestampedModel):
    code = models.CharField(max_length=40, unique=True)
    prefix = models.CharField(max_length=24, blank=True)
    next_value = models.PositiveBigIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(next_value__gt=0), name="number_sequence_positive"
            )
        ]


class VisitType(TimestampedModel):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Service(TimestampedModel):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=160, unique=True)
    current_charge = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(current_charge__isnull=True) | Q(current_charge__gte=0),
                name="service_charge_nonnegative",
            )
        ]


class HealthPackage(TimestampedModel):
    """A governed, publishable bundle of services with a price snapshot."""

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    included_services = models.ManyToManyField(Service, related_name="health_packages")
    price = models.DecimalField(max_digits=12, decimal_places=2)
    eligibility = models.TextField(blank=True)
    fasting_instructions = models.TextField(blank=True)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name="health_package_price_nonnegative"),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gte=models.F("valid_from")),
                name="health_package_valid_dates",
            ),
        ]

    def __str__(self):
        return self.name


class HealthContent(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        SUPERSEDED = "superseded", "Superseded"

    slug = models.SlugField(max_length=160, unique=True)
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    summary = models.TextField()
    body = models.TextField()
    key_takeaways = models.JSONField(default=list, blank=True)
    audience = models.CharField(max_length=80, default="patients")
    language = models.CharField(max_length=12, default="en")
    references = models.JSONField(default=list, blank=True)
    emergency_disclaimer = models.TextField(default="For emergency symptoms, seek emergency care immediately.")
    version = models.PositiveIntegerField(default=1)
    effective_from = models.DateField()
    expires_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="authored_health_content")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reviewed_health_content", null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    ai_provider = models.CharField(max_length=80, blank=True)
    ai_model = models.CharField(max_length=80, blank=True)
    ai_prompt_version = models.CharField(max_length=40, blank=True)

    class Meta:
        permissions = [("publish_healthcontent", "Can clinically approve and publish health content")]
        constraints = [
            models.CheckConstraint(condition=Q(expires_on__isnull=True) | Q(expires_on__gte=models.F("effective_from")), name="health_content_valid_dates"),
            models.CheckConstraint(condition=~Q(status="published") | (Q(reviewer__isnull=False) & Q(reviewed_at__isnull=False)), name="published_health_content_reviewed"),
        ]


class PaymentMethod(TimestampedModel):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)


class InsuranceProvider(TimestampedModel):
    name = models.CharField(max_length=180)
    code = models.CharField(max_length=40, unique=True)
    provider_type = models.CharField(max_length=16, choices=(("insurer", "Insurer"), ("tpa", "TPA")))
    is_active = models.BooleanField(default=True)


class InsurancePolicy(TimestampedModel):
    class Status(models.TextChoices):
        UNVERIFIED = "unverified", "Unverified"
        VERIFIED = "verified", "Verified"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"

    patient = models.ForeignKey("Patient", on_delete=models.PROTECT, related_name="insurance_policies")
    provider = models.ForeignKey(InsuranceProvider, on_delete=models.PROTECT, related_name="policies")
    member_reference = models.CharField(max_length=160)
    policy_reference = models.CharField(max_length=160)
    effective_from = models.DateField()
    effective_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UNVERIFIED)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(effective_until__isnull=True) | Q(effective_until__gte=F("effective_from")), name="insurance_policy_valid_dates")]


class InsuranceVerification(TimestampedModel):
    policy = models.ForeignKey(InsurancePolicy, on_delete=models.PROTECT, related_name="verifications")
    result = models.CharField(max_length=16, choices=(("pending", "Pending"), ("verified", "Verified"), ("rejected", "Rejected")), default="pending")
    authoritative_source = models.CharField(max_length=160, blank=True)
    authority_reference = models.CharField(max_length=160, blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    performed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=~Q(result="verified") | (Q(authoritative_source__gt="") & Q(authority_reference__gt="") & Q(performed_by__isnull=False) & Q(performed_at__isnull=False)), name="verified_insurance_has_authority")]


class AbhaIntegrationConsent(TimestampedModel):
    patient = models.ForeignKey("Patient", on_delete=models.PROTECT, related_name="abha_consents")
    consent_reference = models.CharField(max_length=160, unique=True)
    purpose = models.TextField()
    granted_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    external_link_reference = models.CharField(max_length=160, blank=True)


class Supplier(TimestampedModel):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)


class Medicine(TimestampedModel):
    code = models.CharField(max_length=40, unique=True)
    generic_name = models.CharField(max_length=160)
    brand_name = models.CharField(max_length=160, blank=True)
    strength = models.CharField(max_length=80, blank=True)
    dosage_form = models.CharField(max_length=80, blank=True)
    unit = models.CharField(max_length=40)
    barcode = models.CharField(max_length=80, unique=True, null=True, blank=True)
    is_otc = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)


class Patient(TimestampedModel):
    mrn = models.CharField(max_length=40, unique=True)
    full_name = models.CharField(max_length=200)
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    emergency_contact_name = models.CharField(max_length=160, blank=True)
    emergency_contact_phone = models.CharField(max_length=32, blank=True)
    allergy_safety_notes = models.TextField(blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.full_name} · {self.mrn}"

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = timezone.localdate()
        return (
            today.year
            - self.date_of_birth.year
            - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        )

    class Meta:
        indexes = [models.Index(fields=["full_name"], name="patient_name_idx")]
        permissions = [("view_all_patient_records", "Can view all patient records")]


class Appointment(TimestampedModel):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CHECKED_IN = "checked_in", "Checked in"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No show"

    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="appointments"
    )
    doctor = models.ForeignKey(
        StaffProfile, on_delete=models.PROTECT, related_name="appointments"
    )
    visit_type = models.ForeignKey(VisitType, on_delete=models.PROTECT)
    scheduled_at = models.DateTimeField()
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.SCHEDULED
    )
    queue_number = models.PositiveIntegerField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    no_show_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["scheduled_at", "status"], name="appt_time_status_idx"
            ),
            models.Index(
                fields=["doctor", "scheduled_at"], name="appt_doctor_time_idx"
            ),
            models.Index(
                fields=["patient", "scheduled_at"], name="appt_patient_time_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "scheduled",
                        "checked_in",
                        "in_progress",
                        "completed",
                        "cancelled",
                        "no_show",
                    ]
                ),
                name="appointment_status_valid",
            ),
            models.UniqueConstraint(
                fields=["doctor", "scheduled_at"],
                condition=Q(status__in=["scheduled", "checked_in", "in_progress"]),
                name="appointment_doctor_active_slot_unique",
            ),
        ]


class DigitalCheckInPass(TimestampedModel):
    appointment = models.ForeignKey(
        Appointment, on_delete=models.CASCADE, related_name="digital_check_in_passes"
    )
    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="digital_check_in_passes"
    )
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["patient", "expires_at"], name="qr_patient_expiry_idx")]


class Consultation(TimestampedModel):
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="consultation",
    )
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="consultations"
    )
    doctor = models.ForeignKey(
        StaffProfile, on_delete=models.PROTECT, related_name="consultations"
    )
    clinical_notes = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    follow_up_note = models.TextField(blank=True)
    patient_released_at = models.DateTimeField(null=True, blank=True)
    patient_access_revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(patient_access_revoked_at__isnull=True)
                    | Q(patient_released_at__isnull=False)
                ),
                name="consultation_revoke_after_release",
            )
        ]


class Prescription(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=40, unique=True)
    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="prescriptions",
    )
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="prescriptions"
    )
    doctor = models.ForeignKey(
        StaffProfile, on_delete=models.PROTECT, related_name="prescriptions"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["draft", "issued", "cancelled"]),
                name="prescription_status_valid",
            )
        ]


class PrescriptionItem(TimestampedModel):
    prescription = models.ForeignKey(
        Prescription, on_delete=models.PROTECT, related_name="items"
    )
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT)
    dosage = models.CharField(max_length=120, blank=True)
    frequency = models.CharField(max_length=120, blank=True)
    duration = models.CharField(max_length=120, blank=True)
    instructions = models.TextField(blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="prescription_item_qty_positive"
            )
        ]


class MedicationSchedule(TimestampedModel):
    class MealRelation(models.TextChoices):
        BEFORE_MEAL = "before_meal", "Before Meal"
        AFTER_MEAL = "after_meal", "After Meal"
        WITH_MEAL = "with_meal", "With Meal"
        NO_RELATION = "no_relation", "No Relation"

    prescription_item = models.ForeignKey(
        PrescriptionItem,
        on_delete=models.PROTECT,
        related_name="schedules",
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="medication_schedules",
    )
    dose_amount = models.CharField(max_length=60)
    dose_unit = models.CharField(max_length=40, default="tablet")
    target_times = models.JSONField(
        default=list,
        help_text="List of HH:MM strings in local 24h format, e.g. ['08:00', '20:00']"
    )
    meal_relation = models.CharField(
        max_length=20,
        choices=MealRelation.choices,
        default=MealRelation.NO_RELATION,
    )
    start_date = models.DateField()
    end_date = models.DateField()
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    is_active = models.BooleanField(default=True)
    confirmed_by = models.ForeignKey(
        StaffProfile,
        on_delete=models.PROTECT,
        related_name="confirmed_medication_schedules",
    )
    confirmed_at = models.DateTimeField(auto_now_add=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-start_date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")),
                name="medication_schedule_dates_valid",
            )
        ]

    def __str__(self):
        return f"Schedule for {self.prescription_item.medicine.brand_name or self.prescription_item.medicine.generic_name} ({self.patient.mrn})"


class MedicationDoseLog(TimestampedModel):
    class Action(models.TextChoices):
        TAKEN = "taken", "Taken"
        SKIPPED = "skipped", "Skipped"

    schedule = models.ForeignKey(
        MedicationSchedule,
        on_delete=models.CASCADE,
        related_name="dose_logs",
    )
    scheduled_time = models.DateTimeField(
        help_text="Expected scheduled dose timestamp in UTC"
    )
    action = models.CharField(max_length=16, choices=Action.choices, default=Action.TAKEN)
    logged_at = models.DateTimeField()
    idempotency_key = models.UUIDField(unique=True)

    class Meta:
        ordering = ["-scheduled_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "scheduled_time"],
                name="unique_schedule_scheduled_time_dose",
            )
        ]

    def __str__(self):
        return f"{self.action} at {self.scheduled_time} for {self.schedule_id}"



class StockReceipt(TimestampedModel):
    number = models.CharField(max_length=40, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    supplier_reference = models.CharField(max_length=100, blank=True)
    received_at = models.DateTimeField()
    received_by = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_receipts",
    )


class MedicineBatch(TimestampedModel):
    medicine = models.ForeignKey(
        Medicine, on_delete=models.PROTECT, related_name="batches"
    )
    receipt = models.ForeignKey(
        StockReceipt, on_delete=models.PROTECT, related_name="batches"
    )
    batch_number = models.CharField(max_length=80)
    expiry_date = models.DateField()
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity_received = models.DecimalField(max_digits=12, decimal_places=3)
    quantity_on_hand = models.DecimalField(max_digits=12, decimal_places=3)
    is_quarantined = models.BooleanField(default=False)

    class Meta:
        permissions = [("adjust_stock", "Can adjust medicine stock")]
        constraints = [
            models.UniqueConstraint(
                fields=["medicine", "batch_number"], name="medicine_batch_unique"
            ),
            models.CheckConstraint(
                condition=Q(purchase_price__gte=0), name="batch_purchase_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(sale_price__gte=0), name="batch_sale_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(quantity_received__gt=0), name="batch_received_positive"
            ),
            models.CheckConstraint(
                condition=Q(quantity_on_hand__gte=0),
                name="batch_on_hand_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["medicine", "expiry_date"], name="batch_fefo_idx")
        ]


class StockMovement(models.Model):
    class Kind(models.TextChoices):
        RECEIPT = "receipt", "Receipt"
        DISPENSE = "dispense", "Dispense"
        SALE = "sale", "Sale"
        RETURN = "return", "Return"
        EXPIRY = "expiry", "Expiry"
        QUARANTINE = "quarantine", "Quarantine"
        ADJUSTMENT = "adjustment", "Adjustment"

    batch = models.ForeignKey(
        MedicineBatch, on_delete=models.PROTECT, related_name="movements"
    )
    kind = models.CharField(max_length=12, choices=Kind.choices)
    quantity_delta = models.DecimalField(max_digits=12, decimal_places=3)
    quantity_before = models.DecimalField(max_digits=12, decimal_places=3)
    quantity_after = models.DecimalField(max_digits=12, decimal_places=3)
    reference_type = models.CharField(max_length=40, blank=True)
    reference_id = models.CharField(max_length=40, blank=True)
    request_key = models.UUIDField(null=True, blank=True, unique=True)
    actor = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(quantity_delta=0), name="stock_movement_nonzero"
            ),
            models.CheckConstraint(
                condition=Q(quantity_before__gte=0) & Q(quantity_after__gte=0),
                name="stock_movement_quantities_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(quantity_after=F("quantity_before") + F("quantity_delta")),
                name="stock_movement_balances",
            ),
        ]
        indexes = [
            models.Index(
                fields=["batch", "created_at"], name="stock_move_batch_time_idx"
            )
        ]


class PharmacySale(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        VOIDED = "voided", "Voided"

    number = models.CharField(max_length=40, unique=True)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pharmacy_sales",
    )
    invoice = models.OneToOneField(
        "Invoice",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pharmacy_sale",
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    sold_at = models.DateTimeField(null=True, blank=True)
    sold_by = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pharmacy_sales",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["draft", "issued", "voided"]),
                name="pharmacy_sale_status_valid",
            )
        ]


class PharmacySaleLine(models.Model):
    sale = models.ForeignKey(
        PharmacySale, on_delete=models.PROTECT, related_name="lines"
    )
    batch = models.ForeignKey(MedicineBatch, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="pharmacy_sale_qty_positive"
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0) & Q(line_total__gte=0),
                name="pharmacy_sale_amounts_nonnegative",
            ),
        ]


class Dispensing(TimestampedModel):
    class Status(models.TextChoices):
        PARTIAL = "partial", "Partial"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=40, unique=True)
    prescription = models.ForeignKey(
        Prescription, on_delete=models.PROTECT, related_name="dispensings"
    )
    invoice = models.OneToOneField(
        "Invoice",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dispensing",
    )
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="dispensings"
    )
    dispensed_by = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dispensings",
    )
    status = models.CharField(max_length=12, choices=Status.choices)
    dispensed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["partial", "completed", "cancelled"]),
                name="dispensing_status_valid",
            )
        ]


class DispensingLine(models.Model):
    dispensing = models.ForeignKey(
        Dispensing, on_delete=models.PROTECT, related_name="lines"
    )
    prescription_item = models.ForeignKey(PrescriptionItem, on_delete=models.PROTECT)
    batch = models.ForeignKey(MedicineBatch, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="dispensing_qty_positive"
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0), name="dispensing_price_nonnegative"
            ),
        ]


class PharmacyReturn(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    number = models.CharField(max_length=40, unique=True)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pharmacy_returns",
    )
    reason = models.TextField()
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    created_by = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pharmacy_returns_created",
    )
    request_key = models.UUIDField(unique=True, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["pending", "approved", "rejected"]),
                name="pharmacy_return_status_valid",
            )
        ]


class ReturnLine(models.Model):
    pharmacy_return = models.ForeignKey(
        PharmacyReturn, on_delete=models.PROTECT, related_name="lines"
    )
    sale_line = models.ForeignKey(
        PharmacySaleLine,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="return_lines",
    )
    dispensing_line = models.ForeignKey(
        DispensingLine,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="return_lines",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0) & Q(refund_amount__gte=0),
                name="return_line_amounts_valid",
            ),
            models.CheckConstraint(
                condition=(Q(sale_line__isnull=True) & Q(dispensing_line__isnull=False))
                | (Q(sale_line__isnull=False) & Q(dispensing_line__isnull=True)),
                name="return_line_one_source",
            ),
        ]


class Invoice(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        VOIDED = "voided", "Voided"

    number = models.CharField(max_length=40, unique=True)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices",
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    issued_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices_created",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(subtotal__gte=0)
                & Q(tax_total__gte=0)
                & Q(discount_total__gte=0)
                & Q(total__gte=0),
                name="invoice_totals_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["draft", "issued", "voided"]),
                name="invoice_status_valid",
            ),
        ]
        permissions = [("void_invoice", "Can void an issued invoice")]


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="lines")
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT, null=True, blank=True
    )
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="invoice_line_qty_positive"
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0)
                & (Q(tax_rate__isnull=True) | Q(tax_rate__gte=0))
                & Q(discount_amount__gte=0)
                & Q(line_total__gte=0),
                name="invoice_line_amounts_nonnegative",
            ),
        ]


class Payment(TimestampedModel):
    receipt_number = models.CharField(max_length=40, unique=True)
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="payments"
    )
    method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True)
    received_by = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments_received",
    )
    received_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="payment_amount_positive"
            )
        ]


class Refund(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        ISSUED = "issued", "Issued"

    payment = models.ForeignKey(
        Payment, on_delete=models.PROTECT, related_name="refunds"
    )
    pharmacy_return = models.OneToOneField(
        PharmacyReturn,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="refund",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    requested_by = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_requested",
    )
    approved_by = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_approved",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="refund_amount_positive"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "approved", "rejected", "issued"]),
                name="refund_status_valid",
            ),
        ]
        permissions = [("approve_refund", "Can approve a refund")]


class Adjustment(TimestampedModel):
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="adjustments"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    approved_by = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adjustments_approved",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(amount=0), name="adjustment_amount_nonzero"
            )
        ]
        permissions = [("approve_adjustment", "Can approve a financial adjustment")]


class AuditEvent(models.Model):
    actor = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=80)
    target_id = models.CharField(max_length=80)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class PatientDocument(TimestampedModel):
    class DocumentType(models.TextChoices):
        PRESCRIPTION = "prescription", "Scanned Prescription"
        LAB_REPORT = "lab_report", "Lab / Pathology Report"
        RADIOLOGY = "radiology", "Radiology / X-Ray / Scan"
        DISCHARGE_SUMMARY = "discharge", "Discharge Summary"
        OTHER = "other", "Other Clinical Document"

    class ValidationStatus(models.TextChoices):
        PENDING = "pending", "Pending malware scan"
        CLEAN = "clean", "Validated clean"
        REJECTED = "rejected", "Rejected"

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="documents"
    )
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    document_type = models.CharField(
        max_length=24, choices=DocumentType.choices, default=DocumentType.PRESCRIPTION
    )
    title = models.CharField(max_length=200)
    file = models.FileField(
        upload_to="patient_documents/%Y/%m/",
        storage=private_patient_document_storage,
    )
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    validation_status = models.CharField(
        max_length=12,
        choices=ValidationStatus.choices,
        default=ValidationStatus.PENDING,
    )
    patient_released_at = models.DateTimeField(null=True, blank=True)
    patient_access_revoked_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_documents",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(validation_status__in=["pending", "clean", "rejected"]),
                name="patient_document_validation_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(patient_released_at__isnull=True)
                    | Q(validation_status="clean")
                ),
                name="patient_document_release_clean",
            ),
            models.CheckConstraint(
                condition=(
                    Q(patient_access_revoked_at__isnull=True)
                    | Q(patient_released_at__isnull=False)
                ),
                name="patient_document_revoke_after_release",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_document_type_display()}) - {self.patient.mrn}"


class Ward(TimestampedModel):
    class Category(models.TextChoices):
        GENERAL = "general", "General Ward"
        SEMI_PRIVATE = "semi_private", "Semi-Private Ward"
        PRIVATE = "private", "Private Deluxe Room"
        ICU = "icu", "Intensive Care Unit (ICU)"
        CCU = "ccu", "Critical Care Unit (CCU)"
        EMERGENCY = "emergency", "Emergency / Trauma Ward"

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120, unique=True)
    category = models.CharField(
        max_length=24, choices=Category.choices, default=Category.GENERAL
    )
    floor = models.CharField(max_length=40, blank=True)
    daily_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class Bed(TimestampedModel):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        OCCUPIED = "occupied", "Occupied"
        MAINTENANCE = "maintenance", "Under Cleaning / Maintenance"

    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="beds")
    bed_number = models.CharField(max_length=32)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.AVAILABLE
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ("ward", "bed_number")

    def __str__(self):
        return f"{self.ward.name} · Bed {self.bed_number} ({self.get_status_display()})"


class Admission(TimestampedModel):
    class Status(models.TextChoices):
        ADMITTED = "admitted", "Currently Admitted"
        DISCHARGED = "discharged", "Discharged"
        TRANSFERRED = "transferred", "Transferred"
        LAMA = "lama", "Left Against Medical Advice (LAMA)"

    admission_number = models.CharField(max_length=40, unique=True)
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="admissions"
    )
    bed = models.ForeignKey(
        Bed, on_delete=models.PROTECT, related_name="admissions"
    )
    admitting_doctor = models.ForeignKey(
        StaffProfile, on_delete=models.PROTECT, related_name="admissions_handled"
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ADMITTED
    )
    admission_reason = models.TextField()
    is_mlc = models.BooleanField(
        default=False, verbose_name="Medico-Legal Case (MLC)"
    )
    admitted_at = models.DateTimeField(default=timezone.now)
    discharged_at = models.DateTimeField(null=True, blank=True)
    discharge_summary = models.TextField(blank=True)
    discharge_condition = models.CharField(max_length=120, blank=True)
    admitted_by = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admissions_recorded",
    )

    class Meta:
        ordering = ["-admitted_at"]

    def __str__(self):
        return f"IPD {self.admission_number} · {self.patient.full_name} ({self.bed.bed_number})"

    @property
    def total_advance_deposited(self):
        return self.deposits.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

    @property
    def total_days_stayed(self):
        end_time = self.discharged_at or timezone.now()
        duration = end_time - self.admitted_at
        days = duration.days
        if duration.seconds > 0 or days == 0:
            days += 1
        return days

    @property
    def estimated_bed_charges(self):
        return Decimal(self.total_days_stayed) * self.bed.ward.daily_rate

    @property
    def net_balance(self):
        return self.total_advance_deposited - self.estimated_bed_charges


class InpatientDeposit(TimestampedModel):
    receipt_number = models.CharField(max_length=40, unique=True)
    admission = models.ForeignKey(
        Admission, on_delete=models.PROTECT, related_name="deposits"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.ForeignKey(
        PaymentMethod, on_delete=models.PROTECT
    )
    transaction_reference = models.CharField(
        max_length=100, blank=True, help_text="Bank/UPI UTR or Card Auth Code"
    )
    deposited_by_name = models.CharField(
        max_length=160, blank=True, help_text="Family / Attendant name"
    )
    deposited_by_phone = models.CharField(max_length=32, blank=True)
    received_by = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inpatient_deposits_collected",
    )
    received_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.receipt_number} · {self.amount} for {self.admission.admission_number}"


class PatientAccount(TimestampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="patient_account",
    )
    patient = models.OneToOneField(
        Patient,
        on_delete=models.PROTECT,
        related_name="account",
    )
    is_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    identity_provider = models.CharField(max_length=64, blank=True)
    id_document_reference = models.CharField(max_length=128, blank=True)
    terms_version_accepted = models.CharField(max_length=32, blank=True)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Account for {self.patient.full_name} ({self.user.username})"


class PatientVerificationChallenge(TimestampedModel):
    class Purpose(models.TextChoices):
        REGISTRATION = "registration", "Registration"
        CLAIM_PATIENT = "claim_patient", "Claim Patient"
        PASSWORD_RESET = "password_reset", "Password Reset"

    contact = models.CharField(max_length=120)  # Phone or email
    purpose = models.CharField(max_length=32, choices=Purpose.choices)
    salt = models.CharField(max_length=64, blank=True)
    code_hash = models.CharField(max_length=128)  # Salted hash of OTP code
    expires_at = models.DateTimeField()
    attempts_count = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    matched_patient = models.ForeignKey(
        Patient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verification_challenges",
    )

    class Meta:
        indexes = [
            models.Index(fields=["contact", "purpose", "is_used"], name="chal_contact_purp_idx"),
        ]


class PatientFeedback(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending Moderation"
        PUBLISHED = "published", "Published"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn by Patient"

    class Category(models.TextChoices):
        DOCTOR_CONSULTATION = "doctor_consultation", "Doctor Consultation"
        NURSING_CARE = "nursing_care", "Nursing & In-Patient"
        EMERGENCY_CARE = "emergency_care", "Emergency Care"
        PHARMACY_LAB = "pharmacy_lab", "Pharmacy & Lab"
        OVERALL_EXPERIENCE = "overall_experience", "Overall Experience"

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="feedbacks",
    )
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name="patient_feedback",
    )
    doctor = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doctor_feedbacks",
    )
    rating = models.PositiveSmallIntegerField()  # 1 to 5
    category = models.CharField(
        max_length=32,
        choices=Category.choices,
        default=Category.DOCTOR_CONSULTATION,
    )
    comment = models.TextField(blank=True, max_length=2000)
    is_anonymous_public = models.BooleanField(
        default=True,
        help_text="If published, do not expose patient name publicly.",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderated_feedbacks",
    )
    moderated_at = models.DateTimeField(null=True, blank=True)
    moderation_notes = models.TextField(blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "doctor"], name="feedback_status_doc_idx"),
            models.Index(fields=["patient", "status"], name="feedback_patient_status_idx"),
            models.Index(fields=["created_at"], name="feedback_created_idx"),
        ]
        permissions = [
            ("can_moderate_feedback", "Can moderate patient feedback"),
        ]

    def __str__(self):
        return f"Feedback #{self.pk} by {self.patient.full_name} ({self.rating}★ - {self.status})"

    def clean(self):
        super().clean()
        if self.rating < 1 or self.rating > 5:
            from django.core.exceptions import ValidationError
            raise ValidationError({"rating": "Rating must be between 1 and 5."})
