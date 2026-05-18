from django.urls import path

from . import views

app_name = "advisers"

urlpatterns = [
    path("", views.search, name="search"),
    path("search/partial/", views.search_partial, name="search_partial"),
    path("export/xlsx/", views.export_xlsx, name="export_xlsx"),
    path("<str:crd>/", views.adviser_detail, name="detail"),
]
