from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Sum
from django.shortcuts import redirect
from django.utils import timezone

from .forms import DepartmentForm, HospitalSettingsForm, SpecialtyForm, StaffProfileForm
from .models import (
    Admission,
    Appointment,
    Bed,
    Department,
    DoctorSpecialty,
    HospitalFacility,
    HospitalFaq,
    HealthPackage,
    HealthContent,
    HospitalSettings,
    Invoice,
    Medicine,
    MedicineBatch,
    NumberSequence,
    Patient,
    PatientFeedback,
    Payment,
    PaymentMethod,
    Prescription,
    Refund,
    Service,
    Specialty,
    StaffProfile,
    Supplier,
    VisitType,
)

User = get_user_model()
admin.site.unregister(User)

# Customize AdminSite index view with executive management dashboard metrics
_orig_admin_index = admin.site.index


def _admin_management_dashboard_index(request, extra_context=None):
    today = timezone.localdate()
    kpis = {
        "total_patients": Patient.objects.filter(archived_at__isnull=True).count(),
        "today_appointments": Appointment.objects.filter(scheduled_at__date=today).count(),
        "today_collections": Payment.objects.filter(received_at__date=today).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00"),
        "today_refunds": Refund.objects.filter(
            created_at__date=today, status=Refund.Status.ISSUED
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
        "unsettled_invoices": Invoice.objects.filter(status=Invoice.Status.ISSUED).count(),
        "active_admissions": Admission.objects.filter(status=Admission.Status.ADMITTED).count(),
        "occupied_beds": Bed.objects.filter(status=Bed.Status.OCCUPIED).count(),
        "available_beds": Bed.objects.filter(status=Bed.Status.AVAILABLE).count(),
        "total_beds": Bed.objects.count(),
        "low_stock_batches": MedicineBatch.objects.filter(
            quantity_on_hand__lt=10, is_quarantined=False
        ).count(),
        "expired_batches": MedicineBatch.objects.filter(expiry_date__lt=today).count(),
        "issued_prescriptions": Prescription.objects.filter(
            status=Prescription.Status.ISSUED
        ).count(),
        "pending_feedback": PatientFeedback.objects.filter(
            status=PatientFeedback.Status.PENDING
        ).count(),
        "total_staff": StaffProfile.objects.count(),
    }
    dashboard_context = {
        "kpis": kpis,
        "today": today,
        **(extra_context or {}),
    }
    return _orig_admin_index(request, extra_context=dashboard_context)


admin.site.index = _admin_management_dashboard_index



@admin.register(User)
class StaffUserAdmin(UserAdmin):
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets

        restricted = {"is_staff", "is_superuser", "user_permissions"}
        return [
            (
                name,
                {
                    **options,
                    "fields": tuple(
                        f for f in options["fields"] if f not in restricted
                    ),
                },
            )
            for name, options in fieldsets
            if any(field not in restricted for field in options["fields"])
        ]

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if (
            obj is not None
            and obj.pk == request.user.pk
            and not request.user.is_superuser
        ):
            fields.append("groups")
        return fields

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not request.user.is_superuser:
            queryset = queryset.filter(is_superuser=False)
        return queryset

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            obj.is_superuser = False
        super().save_model(request, obj, form, change)
        if not request.user.is_superuser:
            obj.user_permissions.clear()

    def has_delete_permission(self, request, obj=None):
        return False


class DoctorSpecialtyInline(admin.TabularInline):
    model = DoctorSpecialty
    extra = 1
    autocomplete_fields = ("specialty",)
    fields = ("specialty", "is_primary")


@admin.register(DoctorSpecialty)
class DoctorSpecialtyAdmin(admin.ModelAdmin):
    list_display = ("doctor", "specialty", "is_primary", "updated_at")
    list_filter = ("is_primary", "specialty")
    search_fields = (
        "doctor__employee_id",
        "doctor__user__first_name",
        "doctor__user__last_name",
        "specialty__name",
        "specialty__code",
    )
    autocomplete_fields = ("specialty",)


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    form = StaffProfileForm
    inlines = [DoctorSpecialtyInline]
    list_display = (
        "employee_id",
        "user_full_name",
        "department",
        "job_title",
        "is_doctor_role",
        "is_public",
        "consultation_fee",
        "updated_at",
    )
    list_editable = ("is_public",)
    list_filter = ("is_public", "department", "user__is_active", "user__groups")
    search_fields = (
        "employee_id",
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "job_title",
        "qualifications",
    )
    raw_id_fields = ("user",)
    ordering = ("employee_id",)

    fieldsets = (
        (
            "Account & Internal Identity",
            {
                "fields": ("user", "employee_id", "department", "job_title"),
                "description": "Internal institutional credentials, employment identity, and department placement.",
            },
        ),
        (
            "Public Profile & Clinical Credentials",
            {
                "fields": (
                    "qualifications",
                    "experience_years",
                    "languages",
                    "biography",
                    "is_public",
                ),
                "description": "Public doctor details displayed on patient portals, directories, and website doctor profiles.",
            },
        ),
        (
            "OPD & Outpatient Practice",
            {
                "fields": (
                    "opd_room",
                    "opd_schedule",
                    "consultation_fee",
                ),
                "description": "Clinic scheduling and consultation fee settings for patient appointments.",
            },
        ),
    )

    def user_full_name(self, obj):
        name = obj.user.get_full_name()
        return name if name else obj.user.get_username()
    user_full_name.short_description = "Staff / Doctor Name"
    user_full_name.admin_order_field = "user__first_name"

    def is_doctor_role(self, obj):
        return obj.user.groups.filter(name="Doctor").exists()
    is_doctor_role.boolean = True
    is_doctor_role.short_description = "Doctor Role"


@admin.register(HospitalSettings)
class HospitalSettingsAdmin(admin.ModelAdmin):
    form = HospitalSettingsForm
    list_display = ("name", "city", "phone", "emergency_phone_display", "email", "updated_at")

    fieldsets = (
        (
            "Hospital Identity",
            {
                "fields": ("name", "tagline"),
                "description": "Primary organizational identity displayed across portal navigation, branding banners, and patient records.",
            },
        ),
        (
            "Localization & Regional Settings",
            {
                "fields": ("timezone", "currency_code"),
                "description": "Standard IANA timezone (e.g. Asia/Kolkata) and 3-letter currency code (e.g. INR) for clinical scheduling and revenue operations.",
            },
        ),
        (
            "Emergency & Clinical Contacts",
            {
                "fields": (
                    "emergency_phone",
                    "emergency_phone_display",
                    "ambulance_phone",
                    "ambulance_phone_display",
                    "reception_phone",
                    "reception_phone_display",
                ),
                "description": "Critical emergency numbers for public banners, mobile emergency dialers, and triage intake.",
            },
        ),
        (
            "General Communications & Location",
            {
                "fields": ("phone", "email", "address", "landmark", "city", "maps_query"),
                "description": "Hospital physical address, primary public telephone, inquiries email, and map location query.",
            },
        ),
    )

    def changelist_view(self, request, extra_context=None):
        """Redirect directly to the canonical singleton profile change form."""
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        obj = HospitalSettings.objects.filter(pk=1).first()
        if obj:
            return redirect("admin:core_hospitalsettings_change", obj.pk)
        return redirect("admin:core_hospitalsettings_add")

    def has_add_permission(self, request):
        return not HospitalSettings.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NumberSequence)
class NumberSequenceAdmin(admin.ModelAdmin):
    list_display = ("code", "prefix", "next_value", "updated_at")
    search_fields = ("code", "prefix")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    form = DepartmentForm
    list_display = ("code", "name", "display_order", "is_active", "staff_count", "updated_at")
    list_editable = ("display_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "description")
    ordering = ("display_order", "name")

    fieldsets = (
        (
            "Department Information",
            {
                "fields": ("code", "name", "description"),
                "description": "Core departmental identification. Code is used for internal routing and reporting.",
            },
        ),
        (
            "Display & Navigation",
            {
                "fields": ("icon_name", "display_order", "is_active"),
                "description": "Controls sorting order and public/clinical availability.",
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(models_staff_count=models.Count("staff", distinct=True))

    def staff_count(self, obj):
        return getattr(obj, "models_staff_count", obj.staff.count())
    staff_count.short_description = "Assigned Staff"
    staff_count.admin_order_field = "models_staff_count"

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.staff.exists():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Specialty)
class SpecialtyAdmin(admin.ModelAdmin):
    form = SpecialtyForm
    list_display = ("code", "name", "display_order", "is_active", "updated_at")
    list_editable = ("display_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "description")
    ordering = ("display_order", "name")

    fieldsets = (
        (
            "Specialty Information",
            {
                "fields": ("code", "name", "description"),
                "description": "Medical specialty identity. Code is used for routing, reporting, and doctor specialization.",
            },
        ),
        (
            "Display & Availability",
            {
                "fields": ("icon_name", "display_order", "is_active"),
                "description": "Controls display order and availability for doctor profiles and directory publishing.",
            },
        ),
    )


@admin.register(VisitType)
class VisitTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "current_charge", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(HealthPackage)
class HealthPackageAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "price", "valid_from", "valid_until", "is_published")
    list_filter = ("is_published", "valid_from", "valid_until")
    search_fields = ("code", "name", "description")
    filter_horizontal = ("included_services",)


@admin.register(HealthContent)
class HealthContentAdmin(admin.ModelAdmin):
    list_display = ("title", "version", "status", "reviewer", "effective_from", "expires_on")
    list_filter = ("status", "language", "audience")
    search_fields = ("title", "summary", "body")
    readonly_fields = ("reviewed_at",)

    def save_model(self, request, obj, form, change):
        if obj.status == HealthContent.Status.PUBLISHED:
            if not request.user.has_perm("core.publish_healthcontent"):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied("Clinical publishing permission is required.")
            obj.reviewer = request.user
            obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "phone", "email", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "phone", "email")


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ("code", "generic_name", "brand_name", "unit", "is_otc", "is_active")
    list_filter = ("is_active", "is_otc", "dosage_form")
    search_fields = ("code", "generic_name", "brand_name", "barcode")


@admin.register(HospitalFacility)
class HospitalFacilityAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "highlight", "display_order", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("title", "category", "description")


@admin.register(HospitalFaq)
class HospitalFaqAdmin(admin.ModelAdmin):
    list_display = ("question", "category", "highlight_tag", "display_order", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("question", "answer", "category")


@admin.register(PatientFeedback)
class PatientFeedbackAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient",
        "appointment",
        "doctor",
        "rating",
        "category",
        "status",
        "is_anonymous_public",
        "created_at",
    )
    list_filter = ("status", "rating", "category", "is_anonymous_public")
    search_fields = (
        "patient__full_name",
        "patient__mrn",
        "doctor__user__first_name",
        "doctor__user__last_name",
        "comment",
        "moderation_notes",
    )
    readonly_fields = ("patient", "appointment", "doctor", "created_at", "updated_at")
