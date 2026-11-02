from django.contrib import admin
from .models import (
    Collection,
    Contributor,
    CoverageDay,
    DisclosureEvidence,
    EditorialReview,
    OfferingLink,
    ReaderRequest,
    ResearchEdition,
    ResearchItem,
    ResearchJob,
    UsabilitySession,
)


@admin.register(DisclosureEvidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ["dataset", "accession", "cik", "extracted_at"]
    list_filter = ["dataset"]
    search_fields = ["accession", "cik"]
    readonly_fields = [f.name for f in DisclosureEvidence._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ResearchEdition)
class EditionAdmin(admin.ModelAdmin):
    list_display = ["title", "period_end", "version", "status", "published_at"]
    list_filter = ["status", "series"]

    def get_readonly_fields(self, request, obj=None):
        return (
            [f.name for f in ResearchEdition._meta.fields]
            if obj and obj.status == "published"
            else ["created_at"]
        )


@admin.register(ReaderRequest)
class RequestAdmin(admin.ModelAdmin):
    list_display = ["kind", "dataset", "reference", "status", "created_at"]
    list_filter = ["kind", "status"]


for model in [
    Contributor,
    CoverageDay,
    EditorialReview,
    OfferingLink,
    Collection,
    ResearchItem,
    ResearchJob,
    UsabilitySession,
]:
    admin.site.register(model)
