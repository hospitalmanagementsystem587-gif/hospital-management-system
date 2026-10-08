from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Sum
from django.shortcuts import redirect
from django.utils import timezone

from .forms import (
    DepartmentForm,
    DiagnosticTestForm,
    DoctorScheduleForm,
    HealthContentForm,
    HealthPackageForm,
    HospitalFacilityForm,
    HospitalFaqForm,
    HospitalSettingsForm,
    ServiceForm,
    SpecialtyForm,
    StaffProfileForm,
)
from .models import (
    Admission,
    Appointment,
    AuditEvent,
    Bed,
    Department,
    DiagnosticTest,
    DoctorSchedule,
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


class DoctorScheduleInline(admin.TabularInline):
    model = DoctorSchedule
    form = DoctorScheduleForm
    extra = 1
    fields = (
        "weekday",
        "start_time",
        "end_time",
        "opd_room",
        "slot_duration_minutes",
        "max_patients",
        "is_active",
    )


@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(admin.ModelAdmin):
    form = DoctorScheduleForm
    list_display = (
        "doctor",
        "weekday_name",
        "start_time",
        "end_time",
        "opd_room",
        "slot_duration_minutes",
        "max_patients",
        "is_active",
        "updated_at",
    )
    list_editable = ("is_active",)
    list_filter = ("is_active", "weekday", "doctor__department")
    search_fields = (
        "doctor__employee_id",
        "doctor__user__first_name",
        "doctor__user__last_name",
        "opd_room",
    )
    ordering = ("weekday", "start_time")

    def weekday_name(self, obj):
        return obj.get_weekday_display()
    weekday_name.short_description = "Day of Week"
    weekday_name.admin_order_field = "weekday"


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
    inlines = [DoctorSpecialtyInline, DoctorScheduleInline]
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
    form = ServiceForm
    list_display = ("code", "name", "current_charge", "is_active", "updated_at")
    list_editable = ("current_charge", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    ordering = ("name",)

    fieldsets = (
        (
            "Service Identification",
            {
                "fields": ("code", "name"),
                "description": "Unique institutional service code and standard description.",
            },
        ),
        (
            "Billing & Availability",
            {
                "fields": ("current_charge", "is_active"),
                "description": "Current charge and availability for billing. Changing current_charge does not alter historical invoice records.",
            },
        ),
    )

    def has_delete_permission(self, request, obj=None):
        if obj is not None:
            # Prevent deletion if referenced in any invoice lines or health packages
            if obj.invoiceline_set.exists() or obj.health_packages.exists():
                return False
        return super().has_delete_permission(request, obj)


@admin.register(DiagnosticTest)
class DiagnosticTestAdmin(admin.ModelAdmin):
    form = DiagnosticTestForm
    list_display = (
        "code",
        "name",
        "category",
        "department",
        "sample_type",
        "turnaround_time",
        "display_order",
        "is_active",
        "updated_at",
    )
    list_editable = ("display_order", "is_active")
    list_filter = ("is_active", "category", "department")
    search_fields = ("code", "name", "description", "sample_type")
    ordering = ("category", "display_order", "name")

    fieldsets = (
        (
            "Test Identification",
            {
                "fields": ("code", "name", "category", "department", "description"),
                "description": "Clinical identification, specialty category, and assigned laboratory department.",
            },
        ),
        (
            "Clinical Protocol & Patient Instructions",
            {
                "fields": (
                    "sample_type",
                    "preparation_instructions",
                    "turnaround_time",
                ),
                "description": "Specimen handling, fasting/prep requirements, and expected turnaround duration.",
            },
        ),
        (
            "Display & Catalog Availability",
            {
                "fields": ("display_order", "is_active"),
                "description": "Listing sequence and active ordering status across public and staff portals.",
            },
        ),
    )


@admin.register(HealthPackage)
class HealthPackageAdmin(admin.ModelAdmin):
    form = HealthPackageForm
    list_display = (
        "code",
        "name",
        "price",
        "services_count",
        "valid_from",
        "valid_until",
        "is_published",
        "updated_at",
    )
    list_editable = ("price", "is_published")
    list_filter = ("is_published", "valid_from", "valid_until")
    search_fields = ("code", "name", "description", "eligibility")
    filter_horizontal = ("included_services",)
    ordering = ("name",)

    fieldsets = (
        (
            "Package Identity & Pricing",
            {
                "fields": ("code", "name", "price", "is_published"),
                "description": "Standard identifier, public marketing title, and discounted composite package price.",
            },
        ),
        (
            "Clinical Scope & Included Services",
            {
                "fields": ("description", "included_services", "eligibility", "fasting_instructions"),
                "description": "Covered clinical services, target demographic eligibility, and patient prep requirements.",
            },
        ),
        (
            "Validity & Campaign Schedule",
            {
                "fields": ("valid_from", "valid_until"),
                "description": "Optional promotion start and expiry dates for seasonal health packages.",
            },
        ),
    )

    def services_count(self, obj):
        return obj.included_services.count()
    services_count.short_description = "Included Services"

    def save_model(self, request, obj, form, change):
        previous_published = None
        if change and obj.pk:
            previous = HealthPackage.objects.filter(pk=obj.pk).values("is_published").first()
            if previous:
                previous_published = previous["is_published"]

        super().save_model(request, obj, form, change)

        actor_profile = StaffProfile.objects.filter(user=request.user).first()
        if not change:
            AuditEvent.objects.create(
                actor=actor_profile,
                action="healthpackage.created",
                target_type="healthpackage",
                target_id=str(obj.pk),
                details={"code": obj.code, "is_published": obj.is_published, "name": obj.name},
            )
        elif previous_published != obj.is_published:
            action_name = "healthpackage.published" if obj.is_published else "healthpackage.unpublished"
            AuditEvent.objects.create(
                actor=actor_profile,
                action=action_name,
                target_type="healthpackage",
                target_id=str(obj.pk),
                details={"code": obj.code, "is_published": obj.is_published, "name": obj.name},
            )


@admin.register(HealthContent)
class HealthContentAdmin(admin.ModelAdmin):
    form = HealthContentForm
    list_display = (
        "title",
        "slug",
        "category",
        "version",
        "status",
        "author",
        "reviewer",
        "effective_from",
        "expires_on",
    )
    list_filter = ("status", "category", "language", "audience", "effective_from")
    search_fields = ("title", "slug", "summary", "body", "category")
    readonly_fields = ("reviewed_at",)
    ordering = ("-effective_from", "title")

    fieldsets = (
        (
            "Article Identity & SEO",
            {
                "fields": ("slug", "title", "category", "audience", "language", "version"),
                "description": "Unique URL identifier, publication headline, demographic audience, and versioning.",
            },
        ),
        (
            "Educational Body & Clinical Guidance",
            {
                "fields": ("summary", "body", "key_takeaways", "references", "emergency_disclaimer"),
                "description": "Patient-facing summary, rich educational copy, evidence references, and emergency caution disclaimers.",
            },
        ),
        (
            "Governance & Clinical Approval Workflow",
            {
                "fields": ("status", "effective_from", "expires_on", "author", "reviewer", "reviewed_at"),
                "description": "Publishing lifecycle. Only clinicians with publishing permission can transition status to Published.",
            },
        ),
        (
            "AI Provenance & Audit Metadata",
            {
                "fields": ("ai_provider", "ai_model", "ai_prompt_version"),
                "classes": ("collapse",),
                "description": "Optional audit logs for content assisted by approved medical LLM pipelines.",
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        previous_status = None
        if change and obj.pk:
            previous = HealthContent.objects.filter(pk=obj.pk).values("status").first()
            if previous:
                previous_status = previous["status"]

        if obj.status == HealthContent.Status.PUBLISHED:
            if not request.user.has_perm("core.publish_healthcontent"):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied("Clinical publishing permission is required.")
            if not obj.reviewer:
                obj.reviewer = request.user
            obj.reviewed_at = timezone.now()

        super().save_model(request, obj, form, change)

        actor_profile = StaffProfile.objects.filter(user=request.user).first()
        if not change:
            AuditEvent.objects.create(
                actor=actor_profile,
                action="content.created",
                target_type="healthcontent",
                target_id=str(obj.pk),
                details={"slug": obj.slug, "status": obj.status, "title": obj.title},
            )
        elif previous_status != obj.status:
            action_name = "content.published" if obj.status == HealthContent.Status.PUBLISHED else (
                "content.unpublished" if previous_status == HealthContent.Status.PUBLISHED else "content.status_changed"
            )
            AuditEvent.objects.create(
                actor=actor_profile,
                action=action_name,
                target_type="healthcontent",
                target_id=str(obj.pk),
                details={
                    "slug": obj.slug,
                    "previous_status": previous_status,
                    "new_status": obj.status,
                    "reviewer": obj.reviewer.username if obj.reviewer else None,
                },
            )


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
    form = HospitalFacilityForm
    list_display = (
        "title",
        "category",
        "highlight",
        "display_order",
        "is_active",
        "updated_at",
    )
    list_editable = ("display_order", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("title", "category", "description", "highlight")
    ordering = ("display_order", "title")

    fieldsets = (
        (
            "Facility Identity & Placement",
            {
                "fields": ("title", "category", "display_order", "is_active"),
                "description": "Facility name, medical category, display sequence on website, and visibility toggle.",
            },
        ),
        (
            "Overview & Accreditations",
            {
                "fields": ("highlight", "description"),
                "description": "Badge/highlight tags and detailed description for patient-facing directory.",
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        previous_active = None
        if change and obj.pk:
            previous = HospitalFacility.objects.filter(pk=obj.pk).values("is_active").first()
            if previous:
                previous_active = previous["is_active"]

        super().save_model(request, obj, form, change)

        actor_profile = StaffProfile.objects.filter(user=request.user).first()
        if not change:
            AuditEvent.objects.create(
                actor=actor_profile,
                action="facility.created",
                target_type="hospitalfacility",
                target_id=str(obj.pk),
                details={"title": obj.title, "is_active": obj.is_active},
            )
        elif previous_active != obj.is_active:
            action_name = "facility.activated" if obj.is_active else "facility.deactivated"
            AuditEvent.objects.create(
                actor=actor_profile,
                action=action_name,
                target_type="hospitalfacility",
                target_id=str(obj.pk),
                details={"title": obj.title, "is_active": obj.is_active},
            )


@admin.register(HospitalFaq)
class HospitalFaqAdmin(admin.ModelAdmin):
    form = HospitalFaqForm
    list_display = (
        "question",
        "category",
        "highlight_tag",
        "display_order",
        "is_active",
        "updated_at",
    )
    list_editable = ("display_order", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("question", "answer", "category", "highlight_tag")
    ordering = ("display_order", "id")

    fieldsets = (
        (
            "FAQ Classification & Visibility",
            {
                "fields": ("category", "highlight_tag", "display_order", "is_active"),
                "description": "FAQ topic category, quick filter tags, priority sort order, and active status.",
            },
        ),
        (
            "Question & Clinical/Administrative Answer",
            {
                "fields": ("question", "answer"),
                "description": "Clear inquiry heading and comprehensive public answer.",
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        previous_active = None
        if change and obj.pk:
            previous = HospitalFaq.objects.filter(pk=obj.pk).values("is_active").first()
            if previous:
                previous_active = previous["is_active"]

        super().save_model(request, obj, form, change)

        actor_profile = StaffProfile.objects.filter(user=request.user).first()
        if not change:
            AuditEvent.objects.create(
                actor=actor_profile,
                action="faq.created",
                target_type="hospitalfaq",
                target_id=str(obj.pk),
                details={"question": obj.question, "is_active": obj.is_active},
            )
        elif previous_active != obj.is_active:
            action_name = "faq.activated" if obj.is_active else "faq.deactivated"
            AuditEvent.objects.create(
                actor=actor_profile,
                action=action_name,
                target_type="hospitalfaq",
                target_id=str(obj.pk),
                details={"question": obj.question, "is_active": obj.is_active},
            )


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
