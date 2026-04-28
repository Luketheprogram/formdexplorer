from django.contrib import admin

from .models import Adviser


@admin.register(Adviser)
class AdviserAdmin(admin.ModelAdmin):
    list_display = ("name", "crd", "sec_file_number", "state", "regulatory_aum", "num_employees", "registration_status")
    list_filter = ("state", "registration_status", "has_disciplinary")
    search_fields = ("name", "crd", "sec_file_number")
    readonly_fields = ("created_at", "updated_at", "raw_data")
