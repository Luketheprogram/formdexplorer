from django.urls import path

from . import views

app_name = "content"

urlpatterns = [
    path("", views.article_list, name="article_list"),
    path("newsletter/subscribe/", views.newsletter_subscribe, name="newsletter_subscribe"),
    path("newsletter/unsubscribe/<str:email>/", views.newsletter_unsubscribe, name="newsletter_unsubscribe"),
    path("<slug:slug>/", views.article_detail, name="article_detail"),
]
