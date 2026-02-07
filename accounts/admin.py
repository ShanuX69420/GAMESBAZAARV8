from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import SellerApplication, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "role", "is_staff", "is_active", "is_email_verified")
    search_fields = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "role", "is_email_verified")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "role", "is_staff", "is_active"),
            },
        ),
    )


@admin.register(SellerApplication)
class SellerApplicationAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "status", "created_at", "reviewed_at", "reviewed_by")
    list_filter = ("status", "created_at")
    search_fields = ("user__email", "display_name")
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "user",
        "display_name",
        "experience",
        "status",
        "admin_note",
        "reviewed_by",
        "reviewed_at",
        "created_at",
        "updated_at",
    )
    actions = ("approve_applications", "reject_applications")

    @admin.action(description="Approve selected seller applications")
    def approve_applications(self, request, queryset):
        for application in queryset.select_related("user"):
            application.mark_approved(
                reviewer=request.user,
                note=application.admin_note or "Approved by admin.",
            )

    @admin.action(description="Reject selected seller applications")
    def reject_applications(self, request, queryset):
        for application in queryset.select_related("user"):
            application.mark_rejected(
                reviewer=request.user,
                note=application.admin_note or "Rejected by admin.",
            )
