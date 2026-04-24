from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("v1/filings/", views.filings_list, name="filings_list"),
    path("v1/filings/<str:accession_number>/", views.filing_detail, name="filing_detail"),
    path("v1/issuers/<str:cik>/", views.issuer_detail, name="issuer_detail"),
]
