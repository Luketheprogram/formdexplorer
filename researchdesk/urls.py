from django.urls import path
from . import views
from . import learning

app_name = "researchdesk"
urlpatterns = [
    path("research/calendar/", views.coverage_calendar, name="calendar"),
    path("research/fields/", learning.fields, name="fields"),
    path("research/exports/", views.exports, name="exports"),
    path("research/exports/<int:pk>/", views.export_status, name="export_status"),
    path(
        "research/exports/<int:pk>/download/",
        views.export_download,
        name="export_download",
    ),
    path("research/workbench/", views.index, name="index"),
    path("research/analysis/<slug:slug>/", views.report, name="report"),
    path("research/download/<slug:slug>.<str:format>", views.download, name="download"),
    path("research/disclosures/", views.disclosures, name="disclosures"),
    path(
        "research/evidence/<str:dataset>/<str:accession>/",
        views.evidence,
        name="evidence",
    ),
    path(
        "research/source/<str:dataset>/<str:accession>/",
        views.source_download,
        name="source",
    ),
    path("research/brief/<str:cik>/", views.brief, name="brief"),
    path("research/compare-issuers/", views.compare_issuers, name="compare_issuers"),
    path("research/collections/", views.collections, name="collections"),
    path("research/collections/<int:pk>/", views.collection, name="collection"),
    path(
        "research/collections/<int:pk>/delete/",
        views.delete_collection,
        name="delete_collection",
    ),
    path("research/items/<int:pk>/delete/", views.delete_item, name="delete_item"),
    path("research/feedback/", views.feedback, name="feedback"),
    path("research/editions/", views.editions, name="editions"),
    path("research/editions/<int:pk>/", views.edition, name="edition"),
    path("research/authors/<slug:slug>/", views.contributor, name="contributor"),
    path("research/operations/", views.operations, name="operations"),
    path("research/operations/queue/", views.queue_operation, name="queue_operation"),
    path("research/glossary/", learning.glossary, name="glossary"),
    path("research/walkthrough/", learning.walkthrough, name="walkthrough"),
    path("research/exercises/", learning.exercises, name="exercises"),
]
