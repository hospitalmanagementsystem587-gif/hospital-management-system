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
    DiagnosticTest,
    HealthContent,
    HealthPackage,
    HospitalFacility,
    HospitalFaq,
    HospitalSettings,
    InpatientDeposit,
    Medicine,
    Patient,
    PatientDocument,
    PaymentMethod,
    Prescription,
    PrescriptionItem,
    Price,
    Service,
    Specialty,
    StaffProfile,
    DoctorSchedule,
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


class SpecialtyForm(forms.ModelForm):
    """Administrator CMS form for creating and managing medical specialties."""

    class Meta:
        model = Specialty
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
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Clinical focus and sub-specialty scope...", "class": "vLargeTextField"}),
            "icon_name": forms.TextInput(attrs={"placeholder": "e.g. medical_services", "class": "vTextField"}),
            "display_order": forms.NumberInput(attrs={"class": "vIntegerField"}),
        }
        help_texts = {
            "code": "Unique alphanumeric system code (uppercase recommended, e.g. CARDIO, NEURO).",
            "name": "Public and clinical display name of the medical specialty.",
            "description": "Optional clinical description shown on public directories and doctor profiles.",
            "icon_name": "Material / UI icon identifier for portal navigation.",
            "display_order": "Sorting priority across navigation listings and directories (lower numbers appear first).",
            "is_active": "Controls whether this specialty is active for doctor assignments and public visibility.",
        }

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code:
            raise forms.ValidationError("Specialty code is required.")
        qs = Specialty.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Specialty with code '{code}' already exists.")
        return code

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Specialty name is required.")
        qs = Specialty.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Specialty with name '{name}' already exists.")
        return name

    def clean_icon_name(self):
        icon = (self.cleaned_data.get("icon_name") or "").strip()
        return icon or "medical_services"


class StaffProfileForm(forms.ModelForm):
    """Administrator CMS form for managing staff and doctor profiles."""

    class Meta:
        model = StaffProfile
        fields = (
            "user",
            "employee_id",
            "department",
            "job_title",
            "qualifications",
            "experience_years",
            "languages",
            "opd_room",
            "opd_schedule",
            "consultation_fee",
            "biography",
            "is_public",
        )
        widgets = {
            "employee_id": forms.TextInput(attrs={"placeholder": "e.g. DOC-001 or EMP-101", "class": "vTextField"}),
            "job_title": forms.TextInput(attrs={"placeholder": "e.g. Senior Consultant Cardiologist", "class": "vTextField"}),
            "qualifications": forms.TextInput(attrs={"placeholder": "e.g. MBBS, MD (Cardiology), FACC", "class": "vTextField"}),
            "experience_years": forms.NumberInput(attrs={"class": "vIntegerField", "min": 0}),
            "languages": forms.TextInput(attrs={"placeholder": "e.g. Hindi, English", "class": "vTextField"}),
            "opd_room": forms.TextInput(attrs={"placeholder": "e.g. OPD Room 102", "class": "vTextField"}),
            "opd_schedule": forms.TextInput(attrs={"placeholder": "e.g. Mon-Sat: 10:00 AM - 2:00 PM", "class": "vTextField"}),
            "consultation_fee": forms.NumberInput(attrs={"class": "vIntegerField", "min": 0}),
            "biography": forms.Textarea(attrs={"rows": 4, "placeholder": "Clinical background, specialties, and bio...", "class": "vLargeTextField"}),
        }
        help_texts = {
            "user": "Linked hospital system user account. Reuses existing staff authentication credentials.",
            "employee_id": "Unique internal staff/practitioner identifier.",
            "department": "Primary clinical department.",
            "job_title": "Professional title or clinical role.",
            "qualifications": "Academic degrees, medical certifications, and fellowships.",
            "experience_years": "Years of clinical practice.",
            "languages": "Spoken languages for patient consultations.",
            "opd_room": "Consultation room or outpatient clinic number.",
            "opd_schedule": "Clinic hours displayed on public and patient portals.",
            "consultation_fee": "Default consultation charge in standard hospital currency.",
            "biography": "Public clinical overview shown on website and mobile doctor directory.",
            "is_public": "Whether this profile is listed publicly in directory searches and patient booking.",
        }

    def clean_employee_id(self):
        emp_id = (self.cleaned_data.get("employee_id") or "").strip().upper()
        if not emp_id:
            raise forms.ValidationError("Employee ID is required.")
        qs = StaffProfile.objects.filter(employee_id__iexact=emp_id)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Staff profile with Employee ID '{emp_id}' already exists.")
        return emp_id


class DoctorScheduleForm(forms.ModelForm):
    """Administrator CMS form for managing recurring doctor OPD schedules."""

    class Meta:
        model = DoctorSchedule
        fields = (
            "doctor",
            "weekday",
            "start_time",
            "end_time",
            "opd_room",
            "slot_duration_minutes",
            "max_patients",
            "is_active",
        )
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time", "class": "vTimeField"}),
            "end_time": forms.TimeInput(attrs={"type": "time", "class": "vTimeField"}),
            "opd_room": forms.TextInput(attrs={"placeholder": "e.g. OPD Room 204", "class": "vTextField"}),
            "slot_duration_minutes": forms.NumberInput(attrs={"class": "vIntegerField", "min": 5, "max": 120}),
            "max_patients": forms.NumberInput(attrs={"class": "vIntegerField", "min": 1, "max": 200}),
        }

    def clean(self):
        cleaned_data = super().clean()
        doctor = cleaned_data.get("doctor")
        weekday = cleaned_data.get("weekday")
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        is_active = cleaned_data.get("is_active", True)

        if start_time and end_time:
            if start_time >= end_time:
                raise forms.ValidationError({"end_time": "Session end time must be strictly after start time."})

            if doctor and weekday is not None and is_active:
                # Check for overlapping active schedules for the same doctor on the same weekday
                conflicts = DoctorSchedule.objects.filter(
                    doctor=doctor,
                    weekday=weekday,
                    is_active=True,
                )
                if self.instance.pk:
                    conflicts = conflicts.exclude(pk=self.instance.pk)

                # Overlap condition: start_time < existing.end_time and end_time > existing.start_time
                for conflict in conflicts:
                    if start_time < conflict.end_time and end_time > conflict.start_time:
                        raise forms.ValidationError(
                            f"Schedule conflict: Doctor already has an active session on {conflict.get_weekday_display()} "
                            f"from {conflict.start_time.strftime('%H:%M')} to {conflict.end_time.strftime('%H:%M')}."
                        )
        return cleaned_data


class ServiceForm(forms.ModelForm):
    """Administrator CMS form for managing clinical and hospital service master data."""

    class Meta:
        model = Service
        fields = (
            "code",
            "name",
            "current_charge",
            "is_active",
        )
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "e.g. CONSULT_OPD or LAB_CBC", "class": "vTextField"}),
            "name": forms.TextInput(attrs={"placeholder": "e.g. Outpatient Specialist Consultation", "class": "vTextField"}),
            "current_charge": forms.NumberInput(attrs={"class": "vIntegerField", "min": 0, "step": "0.01"}),
        }
        help_texts = {
            "code": "Unique alphanumeric service code used across billing, orders, and diagnostic packages.",
            "name": "Clinical and billing service title displayed on invoices and patient portals.",
            "current_charge": "Current default base price for this service. Modifying this does not rewrite historical invoice lines.",
            "is_active": "Controls whether this service is active and orderable. Deactivated services preserve all historical billing lines.",
        }

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code:
            raise forms.ValidationError("Service code is required.")
        qs = Service.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Service with code '{code}' already exists.")
        return code

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Service name is required.")
        qs = Service.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Service with name '{name}' already exists.")
        return name

    def clean_current_charge(self):
        charge = self.cleaned_data.get("current_charge")
        if charge is not None and charge < 0:
            raise forms.ValidationError("Current charge cannot be negative.")
        return charge


class DiagnosticTestForm(forms.ModelForm):
    """Administrator CMS form for managing diagnostic laboratory and imaging tests."""

    class Meta:
        model = DiagnosticTest
        fields = (
            "code",
            "name",
            "category",
            "department",
            "description",
            "preparation_instructions",
            "sample_type",
            "turnaround_time",
            "display_order",
            "is_active",
        )
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "e.g. CBC or MRI_BRAIN", "class": "vTextField"}),
            "name": forms.TextInput(attrs={"placeholder": "e.g. Complete Blood Count", "class": "vTextField"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Clinical purpose and test parameters...", "class": "vLargeTextField"}),
            "preparation_instructions": forms.Textarea(attrs={"rows": 2, "placeholder": "e.g. 10-12 hours fasting required...", "class": "vLargeTextField"}),
            "sample_type": forms.TextInput(attrs={"placeholder": "e.g. EDTA Whole Blood, 3ml", "class": "vTextField"}),
            "turnaround_time": forms.TextInput(attrs={"placeholder": "e.g. 4 hours or Same Day", "class": "vTextField"}),
            "display_order": forms.NumberInput(attrs={"class": "vIntegerField"}),
        }

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code:
            raise forms.ValidationError("Diagnostic test code is required.")
        qs = DiagnosticTest.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Diagnostic test with code '{code}' already exists.")
        return code

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Diagnostic test name is required.")
        qs = DiagnosticTest.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Diagnostic test with name '{name}' already exists.")
        return name


class HealthPackageForm(forms.ModelForm):
    """Administrator CMS form for managing health packages and checkup bundles."""

    class Meta:
        model = HealthPackage
        fields = (
            "code",
            "name",
            "description",
            "included_services",
            "price",
            "eligibility",
            "fasting_instructions",
            "valid_from",
            "valid_until",
            "is_published",
        )
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "e.g. EXEC_HEALTH_MEN", "class": "vTextField"}),
            "name": forms.TextInput(attrs={"placeholder": "e.g. Executive Comprehensive Health Checkup", "class": "vTextField"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Clinical overview and scope of the package...", "class": "vLargeTextField"}),
            "price": forms.NumberInput(attrs={"class": "vIntegerField", "min": 0, "step": "0.01"}),
            "eligibility": forms.TextInput(attrs={"placeholder": "e.g. Adults aged 18-65 years", "class": "vTextField"}),
            "fasting_instructions": forms.TextInput(attrs={"placeholder": "e.g. 10-12 hours overnight fasting required", "class": "vTextField"}),
            "valid_from": forms.DateInput(attrs={"type": "date", "class": "vDateField"}),
            "valid_until": forms.DateInput(attrs={"type": "date", "class": "vDateField"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "included_services" in self.fields:
            self.fields["included_services"].required = False

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code:
            raise forms.ValidationError("Package code is required.")
        qs = HealthPackage.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Health package with code '{code}' already exists.")
        return code

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Package name is required.")
        qs = HealthPackage.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Health package with name '{name}' already exists.")
        return name

    def clean_price(self):
        price = self.cleaned_data.get("price")
        if price is not None and price < 0:
            raise forms.ValidationError("Package price cannot be negative.")
        return price

    def clean(self):
        cleaned_data = super().clean()
        valid_from = cleaned_data.get("valid_from")
        valid_until = cleaned_data.get("valid_until")
        if valid_from and valid_until and valid_until < valid_from:
            raise forms.ValidationError({"valid_until": "Validity end date must be on or after valid from date."})
        return cleaned_data


class HealthContentForm(forms.ModelForm):
    """Administrator / Clinical CMS form for authoring and managing structured educational articles."""

    class Meta:
        model = HealthContent
        fields = (
            "slug",
            "title",
            "category",
            "summary",
            "body",
            "key_takeaways",
            "audience",
            "language",
            "references",
            "emergency_disclaimer",
            "version",
            "effective_from",
            "expires_on",
            "status",
            "author",
            "reviewer",
            "reviewed_at",
            "ai_provider",
            "ai_model",
            "ai_prompt_version",
        )
        widgets = {
            "slug": forms.TextInput(attrs={"placeholder": "e.g. managing-type-2-diabetes", "class": "vTextField"}),
            "title": forms.TextInput(attrs={"placeholder": "e.g. Managing Type 2 Diabetes: Daily Care & Nutrition", "class": "vTextField"}),
            "category": forms.TextInput(attrs={"placeholder": "e.g. Endocrinology & Chronic Care", "class": "vTextField"}),
            "summary": forms.Textarea(attrs={"rows": 3, "placeholder": "Executive summary for patients and website cards...", "class": "vLargeTextField"}),
            "body": forms.Textarea(attrs={"rows": 10, "placeholder": "Full educational content body...", "class": "vLargeTextField"}),
            "emergency_disclaimer": forms.Textarea(attrs={"rows": 2, "class": "vLargeTextField"}),
            "effective_from": forms.DateInput(attrs={"type": "date", "class": "vDateField"}),
            "expires_on": forms.DateInput(attrs={"type": "date", "class": "vDateField"}),
        }

    def clean_slug(self):
        slug = (self.cleaned_data.get("slug") or "").strip().lower()
        if not slug:
            raise forms.ValidationError("Slug is required.")
        qs = HealthContent.objects.filter(slug__iexact=slug)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Health content with slug '{slug}' already exists.")
        return slug

    def clean(self):
        cleaned_data = super().clean()
        effective_from = cleaned_data.get("effective_from")
        expires_on = cleaned_data.get("expires_on")
        if effective_from and expires_on and expires_on < effective_from:
            raise forms.ValidationError({"expires_on": "Expiry date must be on or after effective from date."})
        return cleaned_data


class HospitalFacilityForm(forms.ModelForm):
    """Administrator CMS form for hospital physical and clinical facilities."""

    class Meta:
        model = HospitalFacility
        fields = (
            "title",
            "category",
            "description",
            "highlight",
            "display_order",
            "is_active",
        )
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. 24x7 Emergency Trauma Center", "class": "vTextField"}),
            "category": forms.TextInput(attrs={"placeholder": "e.g. Critical Care, Diagnostics, Amenities", "class": "vTextField"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Detailed description of facility capabilities...", "class": "vLargeTextField"}),
            "highlight": forms.TextInput(attrs={"placeholder": "e.g. Level-1 Trauma Certified, 128-Slice CT", "class": "vTextField"}),
            "display_order": forms.NumberInput(attrs={"class": "vIntegerField", "min": 0}),
        }

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise forms.ValidationError("Facility title is required.")
        qs = HospitalFacility.objects.filter(title__iexact=title)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Facility with title '{title}' already exists.")
        return title

    def clean_display_order(self):
        order = self.cleaned_data.get("display_order")
        if order is not None and order < 0:
            raise forms.ValidationError("Display order cannot be negative.")
        return order


class HospitalFaqForm(forms.ModelForm):
    """Administrator CMS form for patient questions and knowledge base answers."""

    class Meta:
        model = HospitalFaq
        fields = (
            "question",
            "answer",
            "category",
            "highlight_tag",
            "display_order",
            "is_active",
        )
        widgets = {
            "question": forms.TextInput(attrs={"placeholder": "e.g. What are the hospital visiting hours?", "class": "vTextField"}),
            "answer": forms.Textarea(attrs={"rows": 4, "placeholder": "Clear and concise response for patients...", "class": "vLargeTextField"}),
            "category": forms.TextInput(attrs={"placeholder": "e.g. OPD & Appointments, Billing & Insurance", "class": "vTextField"}),
            "highlight_tag": forms.TextInput(attrs={"placeholder": "e.g. OPD Timings, Insurance", "class": "vTextField"}),
            "display_order": forms.NumberInput(attrs={"class": "vIntegerField", "min": 0}),
        }

    def clean_question(self):
        question = (self.cleaned_data.get("question") or "").strip()
        if not question:
            raise forms.ValidationError("Question is required.")
        qs = HospitalFaq.objects.filter(question__iexact=question)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("FAQ with this question already exists.")
        return question

    def clean_display_order(self):
        order = self.cleaned_data.get("display_order")
        if order is not None and order < 0:
            raise forms.ValidationError("Display order cannot be negative.")
        return order


class PriceForm(forms.ModelForm):
    """Administrator CMS form for canonical price creation and modifications."""

    class Meta:
        model = Price
        fields = (
            "price_type",
            "content_type",
            "object_id",
            "scope",
            "amount",
            "currency",
            "effective_from",
            "effective_until",
            "status",
            "is_active",
            "version",
            "notes",
        )
        widgets = {
            "scope": forms.TextInput(attrs={"placeholder": "e.g. standard, initial, follow_up", "class": "vTextField"}),
            "amount": forms.NumberInput(attrs={"class": "vIntegerField", "min": 0, "step": "0.01"}),
            "currency": forms.TextInput(attrs={"maxlength": 3, "class": "vTextField"}),
            "effective_from": forms.DateInput(attrs={"type": "date", "class": "vDateField"}),
            "effective_until": forms.DateInput(attrs={"type": "date", "class": "vDateField"}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Pricing rationale or revision details...", "class": "vLargeTextField"}),
        }

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is not None and amount < 0:
            raise forms.ValidationError("Price amount cannot be negative.")
        return amount

    def clean(self):
        cleaned_data = super().clean()
        effective_from = cleaned_data.get("effective_from")
        effective_until = cleaned_data.get("effective_until")
        if effective_from and effective_until and effective_until < effective_from:
            raise forms.ValidationError({"effective_until": "Effective until date must be on or after effective from date."})
        return cleaned_data


class MedicineForm(forms.ModelForm):
    class Meta:
        model = Medicine
        fields = (
            "code",
            "generic_name",
            "brand_name",
            "strength",
            "dosage_form",
            "unit",
            "barcode",
            "is_otc",
            "is_active",
        )
        widgets = {
            "code": forms.TextInput(attrs={"class": "clinical-input", "placeholder": "e.g. MED-PARA-500"}),
            "generic_name": forms.TextInput(attrs={"class": "clinical-input", "placeholder": "e.g. Paracetamol"}),
            "brand_name": forms.TextInput(attrs={"class": "clinical-input", "placeholder": "e.g. Crocin"}),
            "strength": forms.TextInput(attrs={"class": "clinical-input", "placeholder": "e.g. 500 mg"}),
            "dosage_form": forms.TextInput(attrs={"class": "clinical-input", "placeholder": "e.g. Tablet, Syrup, Injection"}),
            "unit": forms.TextInput(attrs={"class": "clinical-input", "placeholder": "e.g. strip, bottle, vial"}),
            "barcode": forms.TextInput(attrs={"class": "clinical-input", "placeholder": "Optional barcode / GTIN"}),
            "is_otc": forms.CheckboxInput(attrs={"class": "hms-checkbox"}),
            "is_active": forms.CheckboxInput(attrs={"class": "hms-checkbox"}),
        }

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not code:
            raise forms.ValidationError("Medicine code is required.")
        qs = Medicine.objects.filter(code__iexact=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A medicine with this code already exists.")
        return code

    def clean_generic_name(self):
        name = (self.cleaned_data.get("generic_name") or "").strip()
        if not name:
            raise forms.ValidationError("Generic name is required.")
        return name

    def clean_unit(self):
        unit = (self.cleaned_data.get("unit") or "").strip()
        if not unit:
            raise forms.ValidationError("Dispensing unit is required.")
        return unit

    def clean_barcode(self):
        barcode = (self.cleaned_data.get("barcode") or "").strip()
        if not barcode:
            return None
        qs = Medicine.objects.filter(barcode__iexact=barcode)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A medicine with this barcode already exists.")
        return barcode
