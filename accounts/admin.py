from django.contrib import admin
from .models import User, ReservedUsername


@admin.register(ReservedUsername)
class ReservedUsernameAdmin(admin.ModelAdmin):
    list_display = ("name", "name_ci", "protected")
    search_fields = ("name", "name_ci")
    list_filter = ("protected",)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "username",
        "first_name",
        "last_name",
        "email",
        "username_change_count",
        "username_changed_at",
    )
    search_fields = ("username", "first_name", "last_name", "email")
