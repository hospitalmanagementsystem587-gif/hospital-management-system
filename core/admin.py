from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import (
    Department,
    HospitalFacility,
    HospitalFaq,
    HospitalSettings,
    Medicine,
    NumberSequence,
    PaymentMethod,
    Service,
    StaffProfile,
    Supplier,
    VisitType,
)

User = get_user_model()
admin.site.unregister(User)


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


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "user", "department", "job_title")
    list_filter = ("department",)
    search_fields = ("employee_id", "user__username", "user__email")


@admin.register(HospitalSettings)
class HospitalSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not HospitalSettings.objects.exists() and super().has_add_permission(
            request
        )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NumberSequence)
class NumberSequenceAdmin(admin.ModelAdmin):
    list_display = ("code", "prefix", "next_value", "updated_at")
    search_fields = ("code", "prefix")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


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
