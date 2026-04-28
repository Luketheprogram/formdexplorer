from django.urls import path

from . import views

app_name = "advisers"

urlpatterns = [
    path("", views.search, name="search"),
    path("search/partial/", views.search_partial, name="search_partial"),
    path("<str:crd>/", views.adviser_detail, name="detail"),
]
