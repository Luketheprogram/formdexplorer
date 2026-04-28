from django.urls import path

from . import views

app_name = "crowdfunding"

urlpatterns = [
    path("", views.search, name="search"),
    path("search/partial/", views.search_partial, name="search_partial"),
    path("<str:accession_number>/", views.detail, name="detail"),
]
