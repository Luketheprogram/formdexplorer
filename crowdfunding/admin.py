from django.contrib import admin

from .models import CrowdfundingFiling


@admin.register(CrowdfundingFiling)
class CrowdfundingFilingAdmin(admin.ModelAdmin):
    list_display = (
        "accession_number", "issuer", "form_type", "filing_date",
        "intermediary_name", "maximum_offering_amount",
    )
    list_filter = ("form_type",)
    search_fields = ("accession_number", "issuer__name", "issuer__cik", "intermediary_name")
    date_hierarchy = "filing_date"
    readonly_fields = ("created_at", "updated_at", "raw_xml")
