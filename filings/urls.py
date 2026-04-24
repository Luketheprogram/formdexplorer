from django.urls import path

from . import views

app_name = "filings"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("search/partial/", views.search_partial, name="search_partial"),
    path("recent/", views.recent, name="recent"),
    path("export/csv/", views.export_csv, name="export_csv"),
    path("saved-searches/", views.saved_search_list, name="saved_search_list"),
    path("saved-searches/new/", views.saved_search_create, name="saved_search_create"),
    path("saved-searches/<int:pk>/delete/", views.saved_search_delete, name="saved_search_delete"),
    path("issuer/<slug:slug_cik>/", views.issuer_detail, name="issuer_detail"),
    path("filing/<str:accession_number>/", views.filing_detail, name="filing_detail"),
    path("industry/<slug:slug>/", views.industry_detail, name="industry_detail"),
    path("state/<str:state>/", views.state_detail, name="state_detail"),
]
