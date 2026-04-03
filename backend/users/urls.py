from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LoginAPIView,
    LogoutAPIView,
    CurrentUserAPIView,
    CsrfCookieAPIView,
    SignupAPIView,
    OTPRequestAPIView,
    OTPVerifyAPIView,
    PasswordResetAPIView,
    UserViewSet,
    NotificationViewSet,
)

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"notifications", NotificationViewSet, basename="notification")

urlpatterns = [
    # Auth endpoints
    path("auth/login/", LoginAPIView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutAPIView.as_view(), name="auth-logout"),
    path("auth/me/", CurrentUserAPIView.as_view(), name="auth-me"),
    path("auth/csrf/", CsrfCookieAPIView.as_view(), name="auth-csrf"),
    path("auth/signup/", SignupAPIView.as_view(), name="auth-signup"),
    path("auth/otp/request/", OTPRequestAPIView.as_view(), name="auth-otp-request"),
    path("auth/otp/verify/", OTPVerifyAPIView.as_view(), name="auth-otp-verify"),
    path("auth/password-reset/", PasswordResetAPIView.as_view(), name="auth-password-reset"),

    # Admin user management
    path("admin/", include(router.urls)),
]
