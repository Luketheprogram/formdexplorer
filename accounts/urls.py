from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import EmailAuthenticationForm
from .throttle import rate_limit

_login_view = auth_views.LoginView.as_view(
    template_name="accounts/login.html",
    authentication_form=EmailAuthenticationForm,
    extra_context={"page_title": "Log in — Form D Explorer", "robots": "noindex"},
)

app_name = "accounts"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("login/", rate_limit(name="login", max_hits=10, window_seconds=300)(_login_view), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("account/", views.account, name="account"),
    path("account/api-keys/", views.api_keys, name="api_keys"),
    path("account/api-keys/create/", views.api_key_create, name="api_key_create"),
    path("account/api-keys/<int:pk>/revoke/", views.api_key_revoke, name="api_key_revoke"),
]
