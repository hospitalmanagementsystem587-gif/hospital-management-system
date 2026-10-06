from django import forms
from datetime import timedelta
from django.forms import inlineformset_factory
from django.utils import timezone

from .models import (
    Admission,
    Appointment,
    Bed,
    Consultation,
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

