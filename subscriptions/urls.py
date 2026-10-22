from django.urls import path

from . import views

app_name = "subscriptions"

urlpatterns = [
    path("pricing/", views.pricing, name="pricing"),
    path("checkout/success/", views.checkout_success, name="checkout_success"),
    path("checkout/cancel/", views.checkout_cancel, name="checkout_cancel"),
    path("checkout/<str:plan_key>/", views.checkout, name="checkout"),
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
]
