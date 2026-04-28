from django.contrib import admin

from .models import Form1AFiling


@admin.register(Form1AFiling)
class Form1AFilingAdmin(admin.ModelAdmin):
    list_display = (
        "accession_number", "issuer", "form_type", "tier", "filing_date",
        "total_offering_amount", "total_amount_sold",
    )
    list_filter = ("form_type", "tier")
    search_fields = ("accession_number", "issuer__name", "issuer__cik")
    date_hierarchy = "filing_date"
    readonly_fields = ("created_at", "updated_at", "raw_xml")
