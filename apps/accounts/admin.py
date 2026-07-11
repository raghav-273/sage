# apps/accounts/admin.py
from django.contrib import admin

from .models import AuditLog, Role, UserProfile


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("display_name", "name", "is_system_role", "created_at")
    readonly_fields = ("created_at",)

    def has_delete_permission(self, request, obj=None) -> bool:
        if obj and obj.is_system_role:
            return False
        return super().has_delete_permission(request, obj)


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    extra = 0
    fields = ("role", "department", "designation", "employee_id", "requires_password_reset")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "department", "requires_password_reset", "created_at")
    list_filter = ("role", "requires_password_reset")
    search_fields = ("user__username", "user__email", "department", "employee_id")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("user",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "event_type", "severity", "actor_username", "target_label", "ip_address")
    list_filter = ("event_type", "severity")
    search_fields = ("actor_username", "target_label", "ip_address")
    readonly_fields = (
        "id", "event_type", "severity", "actor_id", "actor_username",
        "target_type", "target_id", "target_label",
        "ip_address", "user_agent", "detail", "timestamp",
    )
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False