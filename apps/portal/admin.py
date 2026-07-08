# apps/portal/admin.py
from django.contrib import admin

from .models import LoginAttempt


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "ip_address", "username_attempted", "success", "failure_reason")
    list_filter = ("success", "failure_reason")
    search_fields = ("ip_address", "username_attempted")
    readonly_fields = ("ip_address", "username_attempted", "success", "failure_reason",
                       "user_agent", "timestamp")
    ordering = ("-timestamp",)
    date_hierarchy = "timestamp"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False