from django.contrib import admin

from .models import Filing, Issuer, RelatedPerson, SavedSearch


@admin.register(Issuer)
class IssuerAdmin(admin.ModelAdmin):
    list_display = ("name", "cik", "state", "entity_type", "updated_at")
    list_filter = ("state", "entity_type")
    search_fields = ("name", "cik")
    prepopulated_fields = {"name_slug": ("name",)}


class RelatedPersonInline(admin.TabularInline):
    model = RelatedPerson
    extra = 0


@admin.register(Filing)
class FilingAdmin(admin.ModelAdmin):
    list_display = ("accession_number", "issuer", "filing_date", "form_type", "industry_group", "total_offering_amount")
    list_filter = ("form_type", "industry_group")
    search_fields = ("accession_number", "issuer__name", "issuer__cik")
    date_hierarchy = "filing_date"
    inlines = [RelatedPersonInline]


@admin.register(RelatedPerson)
class RelatedPersonAdmin(admin.ModelAdmin):
    list_display = ("name", "relationship", "filing", "state")
    search_fields = ("name",)


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "created_at", "last_checked_at")
    search_fields = ("name", "user__email")
