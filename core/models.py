from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone



class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Department(TimestampedModel):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)


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

    def __str__(self):
        display_name = self.user.get_full_name() or self.user.get_username()
        return f"{display_name} · {self.employee_id}"


class HospitalSettings(TimestampedModel):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    name = models.CharField(max_length=200)
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    currency_code = models.CharField(max_length=3, default="INR")
    phone = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="hospital_settings_one_row")
        ]


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


class PaymentMethod(TimestampedModel):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)


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

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="documents"
    )
    document_type = models.CharField(
        max_length=24, choices=DocumentType.choices, default=DocumentType.PRESCRIPTION
    )
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="patient_documents/%Y/%m/")
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


