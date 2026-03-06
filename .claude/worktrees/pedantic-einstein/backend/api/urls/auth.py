from __future__ import annotations

from django.urls import path

from api.views.auth import LoginStubAPIView

urlpatterns = [
    path("login/", LoginStubAPIView.as_view(), name="auth-login"),
]
