import zoneinfo

from django import forms
from datetime import timedelta
from django.forms import inlineformset_factory
from django.utils import timezone

from .models import (
    Admission,
    Appointment,
    Bed,
    Consultation,
    Department,
    HospitalSettings,
    InpatientDeposit,
    Patient,
    PatientDocument,
    PaymentMethod,
    Prescription,
    PrescriptionItem,
    StaffProfile,
    VisitType,
)
from .services.documents import inspect_patient_document_upload

APPOINTMENT_DURATION = timedelta(minutes=30)


def appointment_slot_conflicts(doctor, scheduled_at, exclude_pk=None):
    conflicts = Appointment.objects.filter(
        doctor=doctor,
        scheduled_at__gt=scheduled_at - APPOINTMENT_DURATION,
        scheduled_at__lt=scheduled_at + APPOINTMENT_DURATION,
        status__in=(
            Appointment.Status.SCHEDULED,
            Appointment.Status.CHECKED_IN,
            Appointment.Status.IN_PROGRESS,
        ),
    )
    if exclude_pk:
        conflicts = conflicts.exclude(pk=exclude_pk)
    return conflicts.exists()


class PatientForm(forms.ModelForm):
    age = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=130,
        label="Age (Years)",
        widget=forms.NumberInput(attrs={"placeholder": "e.g. 35", "min": "0", "max": "130"}),
    )
    date_of_birth = forms.DateField(
        required=False,
        input_formats=["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"],
        label="Date of Birth",
        widget=forms.DateInput(
            format="%d/%m/%Y",
            attrs={
                "type": "text",
                "placeholder": "DD/MM/YYYY",
                "pattern": r"\d{2}/\d{2}/\d{4}",
                "maxlength": "10",
                "autocomplete": "off",
                "inputmode": "numeric",
            },
        ),
    )

    class Meta:
        model = Patient
        fields = (
            "full_name",
            "date_of_birth",
            "phone",
            "email",
            "address",
            "emergency_contact_name",
            "emergency_contact_phone",
        )
        widgets = {
            "email": forms.EmailInput(attrs={"placeholder": "patient@example.com"}),
        }


    def clean_date_of_birth(self):
        date_of_birth = self.cleaned_data.get("date_of_birth")
        if date_of_birth and date_of_birth > timezone.localdate():
            raise forms.ValidationError("Date of birth cannot be in the future.")
        return date_of_birth

    def clean(self):
        cleaned_data = super().clean()
        dob = cleaned_data.get("date_of_birth")
        age = cleaned_data.get("age")

        # If age is entered without DOB, derive an approximate DOB (Jan 1 of birth year)
        if not dob and age is not None:
            today = timezone.localdate()
            cleaned_data["date_of_birth"] = today.replace(year=today.year - age, month=1, day=1)

        return cleaned_data


class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ("patient", "doctor", "visit_type", "scheduled_at")
        widgets = {
            "scheduled_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={
                    "type": "datetime-local",
                    "class": "appointment-control",
                },
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = Patient.objects.filter(
            archived_at__isnull=True
        )
        self.fields["doctor"].queryset = (
            StaffProfile.objects.filter(
                user__groups__name="Doctor", user__is_active=True
            )
            .select_related("user")
            .distinct()
        )
        self.fields["visit_type"].queryset = VisitType.objects.filter(is_active=True)
        self.fields["patient"].empty_label = "Select a registered patient"
        self.fields["doctor"].empty_label = "Select an attending doctor"
        self.fields["visit_type"].empty_label = "Select a visit type"
        for field_name in ("patient", "doctor", "visit_type"):
            self.fields[field_name].widget.attrs.update(
                {"class": "appointment-control"}
            )

    def clean(self):
        cleaned_data = super().clean()
        doctor = cleaned_data.get("doctor")
        scheduled_at = cleaned_data.get("scheduled_at")
        if doctor and scheduled_at:
            if appointment_slot_conflicts(doctor, scheduled_at, self.instance.pk):
                self.add_error(
                    "scheduled_at",
                    "This doctor already has an overlapping active appointment.",
                )
        return cleaned_data


class ConsultationForm(forms.ModelForm):
    class Meta:
        model = Consultation
        fields = ("clinical_notes", "diagnosis", "follow_up_date", "follow_up_note")
        widgets = {
            "clinical_notes": forms.Textarea(attrs={"rows": 6}),
            "diagnosis": forms.Textarea(attrs={"rows": 3}),
            "follow_up_date": forms.DateInput(attrs={"type": "date"}),
            "follow_up_note": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("clinical_notes") and not cleaned_data.get("diagnosis"):
            raise forms.ValidationError("Enter clinical notes or a diagnosis.")
        return cleaned_data


class PrescriptionItemForm(forms.ModelForm):
    class Meta:
        model = PrescriptionItem
        fields = (
            "medicine",
            "dosage",
            "frequency",
            "duration",
            "instructions",
            "quantity",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["medicine"].queryset = self.fields["medicine"].queryset.filter(
            is_active=True
        )


PrescriptionItemFormSet = inlineformset_factory(
    Prescription,
    PrescriptionItem,
    form=PrescriptionItemForm,
    extra=1,
    can_delete=False,
)


class PatientDocumentForm(forms.ModelForm):
    class Meta:
        model = PatientDocument
        fields = ("document_type", "title", "file", "notes")
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": "e.g. Scanned Prescription - Dr. Sharma OPD",
                    "class": "clinical-input",
                }
            ),
            "document_type": forms.Select(attrs={"class": "clinical-input"}),
            "file": forms.FileInput(
                attrs={
                    "class": "clinical-input",
                    "accept": ".pdf,.jpg,.jpeg,.png,.webp",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Any remarks or notes about this document...",
                    "class": "clinical-input",
                }
            ),
        }

    def clean_file(self):
        upload = self.cleaned_data["file"]
        self._document_metadata = inspect_patient_document_upload(upload)
        return upload

    def save(self, commit=True):
        document = super().save(commit=False)
        metadata = getattr(self, "_document_metadata", None)
        if metadata:
            document.content_type = metadata["content_type"]
            document.size_bytes = metadata["size_bytes"]
            document.sha256 = metadata["sha256"]
            document.validation_status = metadata["validation_status"]
        if commit:
            document.save()
            self.save_m2m()
        return document


class AdmissionForm(forms.ModelForm):
    class Meta:
        model = Admission
        fields = (
            "patient",
            "bed",
            "admitting_doctor",
            "admission_reason",
            "is_mlc",
        )
        widgets = {
            "patient": forms.Select(attrs={"class": "clinical-input"}),
            "bed": forms.Select(attrs={"class": "clinical-input"}),
            "admitting_doctor": forms.Select(attrs={"class": "clinical-input"}),
            "admission_reason": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Clinical diagnosis, provisional findings, and indication for hospitalization...",
                    "class": "clinical-input",
                }
            ),
            "is_mlc": forms.CheckboxInput(attrs={"style": "width: 18px; height: 18px;"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = Patient.objects.filter(
            archived_at__isnull=True
        ).order_by("full_name")
        self.fields["bed"].queryset = Bed.objects.filter(
            status=Bed.Status.AVAILABLE
        ).select_related("ward").order_by("ward__name", "bed_number")
        self.fields["admitting_doctor"].queryset = (
            StaffProfile.objects.filter(
                user__groups__name="Doctor",
                user__is_active=True,
            )
            .select_related("user", "department")
            .order_by("user__first_name", "user__username")
        )


class InpatientDepositForm(forms.ModelForm):
    class Meta:
        model = InpatientDeposit
        fields = (
            "amount",
            "payment_method",
            "transaction_reference",
            "deposited_by_name",
            "deposited_by_phone",
            "notes",
        )
        widgets = {
            "amount": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "1.00",
                    "placeholder": "e.g. 20000.00",
                    "class": "clinical-input",
                }
            ),
            "payment_method": forms.Select(attrs={"class": "clinical-input"}),
            "transaction_reference": forms.TextInput(
                attrs={
                    "placeholder": "Bank / UPI UTR / Card Auth Code",
                    "class": "clinical-input",
                }
            ),
            "deposited_by_name": forms.TextInput(
                attrs={
                    "placeholder": "Name of family member / attendant",
                    "class": "clinical-input",
                }
            ),
            "deposited_by_phone": forms.TextInput(
                attrs={
                    "placeholder": "Attendant phone number",
                    "class": "clinical-input",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Advance deposit remarks...",
                    "class": "clinical-input",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_method"].queryset = PaymentMethod.objects.filter(
            is_active=True
        )


class DischargeForm(forms.ModelForm):
    class Meta:
        model = Admission
        fields = (
            "discharge_condition",
            "discharge_summary",
            "status",
        )
        widgets = {
            "discharge_condition": forms.TextInput(
                attrs={
                    "placeholder": "e.g. Stable / Hemodynamically Normal / Cured",
                    "class": "clinical-input",
                }
            ),
            "discharge_summary": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Summary of hospital course, investigations performed, and discharge medications...",
                    "class": "clinical-input",
                }
            ),
            "status": forms.Select(
                choices=[
                    (Admission.Status.DISCHARGED, "Normal Medical Discharge"),
                    (Admission.Status.LAMA, "Left Against Medical Advice (LAMA)"),
                    (Admission.Status.TRANSFERRED, "Transferred to Higher Facility"),
                ],
                attrs={"class": "clinical-input"},
            ),
        }


class HospitalSettingsForm(forms.ModelForm):
    """Administrator CMS form for managing the canonical hospital profile and settings."""

    class Meta:
        model = HospitalSettings
        fields = (
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
        )
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Vedant Hospital", "class": "vTextField"}),
            "tagline": forms.TextInput(attrs={"placeholder": "e.g. Multi-Speciality Care & 24x7 Emergency", "class": "vTextField"}),
            "timezone": forms.TextInput(attrs={"placeholder": "Asia/Kolkata", "class": "vTextField"}),
            "currency_code": forms.TextInput(attrs={"placeholder": "INR", "maxlength": "3", "class": "vTextField"}),
            "phone": forms.TextInput(attrs={"placeholder": "+91 94150 12345", "class": "vTextField"}),
            "emergency_phone": forms.TextInput(attrs={"placeholder": "102", "class": "vTextField"}),
            "emergency_phone_display": forms.TextInput(attrs={"placeholder": "102 / 108", "class": "vTextField"}),
            "ambulance_phone": forms.TextInput(attrs={"placeholder": "108", "class": "vTextField"}),
            "ambulance_phone_display": forms.TextInput(attrs={"placeholder": "108", "class": "vTextField"}),
            "reception_phone": forms.TextInput(attrs={"placeholder": "+91 522 2418900", "class": "vTextField"}),
            "reception_phone_display": forms.TextInput(attrs={"placeholder": "+91 (0522) 2418900", "class": "vTextField"}),
            "email": forms.EmailInput(attrs={"placeholder": "contact@hospital.com", "class": "vTextField"}),
            "address": forms.Textarea(attrs={"rows": 3, "placeholder": "Hospital street address...", "class": "vLargeTextField"}),
            "landmark": forms.TextInput(attrs={"placeholder": "e.g. Near Kanpur Ring Road", "class": "vTextField"}),
            "city": forms.TextInput(attrs={"placeholder": "e.g. Lucknow, Uttar Pradesh", "class": "vTextField"}),
            "maps_query": forms.TextInput(attrs={"placeholder": "e.g. Vedant Hospital, Hardoi Road, Lucknow", "class": "vTextField"}),
        }

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("This field is required.")
        return name

    def clean_timezone(self):
        tz = (self.cleaned_data.get("timezone") or "").strip()
        if tz:
            try:
                zoneinfo.ZoneInfo(tz)
            except (zoneinfo.ZoneInfoNotFoundError, ValueError):
                raise forms.ValidationError(f"'{tz}' is not a valid IANA time zone identifier (e.g. Asia/Kolkata).")
        return tz

    def clean_currency_code(self):
        curr = (self.cleaned_data.get("currency_code") or "").strip().upper()
        if not curr:
            return "INR"
        if len(curr) != 3 or not curr.isalpha():
            raise forms.ValidationError("Currency code must be a 3-letter ISO code (e.g. INR, USD).")
        return curr

    def clean_phone(self):
        return (self.cleaned_data.get("phone") or "").strip()

    def clean_emergency_phone(self):
        return (self.cleaned_data.get("emergency_phone") or "").strip()

    def clean_ambulance_phone(self):
        return (self.cleaned_data.get("ambulance_phone") or "").strip()

    def clean_reception_phone(self):
        return (self.cleaned_data.get("reception_phone") or "").strip()

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip()


class DepartmentForm(forms.ModelForm):
    """Administrator CMS form for creating and managing hospital departments."""

    class Meta:
        model = Department
        fields = (
            "code",
            "name",
            "description",
            "icon_name",
            "display_order",
            "is_active",
        )
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "e.g. CARDIO", "class": "vTextField"}),
            "name": forms.TextInput(attrs={"placeholder": "e.g. Cardiology", "class": "vTextField"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Clinical services and department scope...", "class": "vLargeTextField"}),
            "icon_name": forms.TextInput(attrs={"placeholder": "e.g. medical_services", "class": "vTextField"}),
            "display_order": forms.NumberInput(attrs={"class": "vIntegerField"}),
        }
        help_texts = {
            "code": "Unique alphanumeric system code (uppercase recommended, e.g. CARDIO, ORTHO).",
            "name": "Public and clinical display name of the department.",
            "description": "Optional clinical description shown on public directories and patient scheduling.",
            "icon_name": "Material / UI icon identifier for portal navigation.",
            "display_order": "Sorting priority across navigation listings and directories (lower numbers appear first).",
            "is_active": "Controls whether this department is available for new clinical appointments and public visibility. Inactive departments retain all historical staff, patient, and billing records.",
        }

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code:
            raise forms.ValidationError("Department code is required.")
        qs = Department.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Department with code '{code}' already exists.")
        return code

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Department name is required.")
        qs = Department.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Department with name '{name}' already exists.")
        return name

    def clean_icon_name(self):
        icon = (self.cleaned_data.get("icon_name") or "").strip()
        return icon or "medical_services"
