from datetime import datetime, timezone, timedelta
from django.contrib.auth import authenticate, login, logout
from django.contrib.sessions.models import Session
from django.utils import timezone as tz
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django_ratelimit.decorators import ratelimit
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User, Notification
from .serializers import (
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    LoginSerializer,
    SignupSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    PasswordResetSerializer,
    NotificationSerializer,
)
from .otp_service import send_otp_email, verify_otp


def _invalidate_sessions_for_user(user: User) -> int:
    """
    Delete all server-side sessions for this user (DB backend only).
    Returns number of sessions deleted. When using Redis session backend,
    sessions are keyed by session key; consider adding Redis invalidation if needed.
    """
    from django.conf import settings
    if getattr(settings, "SESSION_ENGINE", "").endswith(".cache"):
        return 0  # Redis/cache backend: no direct user→sessions mapping
    deleted = 0
    now = tz.now()
    for session in Session.objects.filter(expire_date__gte=now):
        data = session.get_decoded()
        if str(data.get("_auth_user_id")) == str(user.pk):
            session.delete()
            deleted += 1
    return deleted


class SignupAPIView(APIView):
    """
    POST /api/auth/signup/
    Body: { "email": "...", "first_name": "...", "last_name": "...", "password": "..." }
    Creates an inactive user and sends OTP for email verification.
    """
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        first_name = serializer.validated_data["first_name"]
        last_name = serializer.validated_data["last_name"]
        password = serializer.validated_data["password"]

        # Create inactive user
        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=False,
            roles=["user"],
        )

        # Send OTP
        otp_sent = send_otp_email(email, purpose="signup")

        if not otp_sent:
            return Response(
                {"detail": "Account created but failed to send verification email. Please try requesting a new OTP."},
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {
                "detail": "Account created. Please verify your email with the OTP sent.",
                "email": email,
                "otp_sent": True,
            },
            status=status.HTTP_201_CREATED,
        )


class OTPRequestAPIView(APIView):
    """
    POST /api/auth/otp/request/
    Body: { "email": "...", "purpose": "signup" | "login" }
    Sends an OTP to the given email.
    """
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        purpose = serializer.validated_data["purpose"]

        # For signup, user should exist but be inactive
        if purpose == "signup":
            try:
                user = User.objects.get(email=email)
                if user.is_active:
                    return Response(
                        {"detail": "This email is already verified."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except User.DoesNotExist:
                return Response(
                    {"detail": "No account found with this email. Please sign up first."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        if purpose == "password_reset":
            if not User.objects.filter(email=email, is_active=True).exists():
                return Response(
                    {"detail": "No active account found with this email."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        otp_sent = send_otp_email(email, purpose=purpose)

        if not otp_sent:
            return Response(
                {"detail": "Failed to send OTP. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"detail": "OTP sent successfully.", "email": email},
            status=status.HTTP_200_OK,
        )


class OTPVerifyAPIView(APIView):
    """
    POST /api/auth/otp/verify/
    Body: { "email": "...", "otp": "123456", "purpose": "signup" | "login" }
    Verifies the OTP. For signup, activates the user account.
    """
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]
        purpose = serializer.validated_data["purpose"]

        success, message = verify_otp(email, otp, purpose=purpose)

        if not success:
            return Response(
                {"detail": message, "verified": False},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # For signup, activate user
        if purpose == "signup":
            try:
                user = User.objects.get(email=email)
                user.is_active = True
                user.save()

                expires_at = datetime.now(timezone.utc) + timedelta(days=1)

                return Response(
                    {
                        "detail": message,
                        "verified": True,
                        "user": {
                            "id": str(user.id),
                            "email": user.email,
                            "name": user.name,
                            "roles": user.roles or ["user"],
                        },
                        "accessTokenExpiresAt": expires_at.isoformat(),
                    },
                    status=status.HTTP_200_OK,
                )
            except User.DoesNotExist:
                return Response(
                    {"detail": "User not found.", "verified": False},
                    status=status.HTTP_404_NOT_FOUND,
                )

        return Response(
            {"detail": message, "verified": True},
            status=status.HTTP_200_OK,
        )


class PasswordResetAPIView(APIView):
    """
    POST /api/auth/password-reset/
    Body: { "email": "...", "otp": "123456", "new_password": "..." }
    Resets the user's password if OTP is valid.
    """
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]
        new_password = serializer.validated_data["new_password"]

        # 1. Verify OTP first
        success, message = verify_otp(email, otp, purpose="password_reset")
        if not success:
            return Response(
                {"detail": message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Reset password and invalidate all existing sessions for this user
        try:
            user = User.objects.get(email=email, is_active=True)
            user.set_password(new_password)
            user.save()
            _invalidate_sessions_for_user(user)
            return Response(
                {"detail": "Password has been reset successfully. You can now log in."},
                status=status.HTTP_200_OK,
            )
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found or inactive."},
                status=status.HTTP_404_NOT_FOUND,
            )


class LoginAPIView(APIView):
    """
    POST /api/auth/login/
    Body: { "email": "...", "password": "..." }
    Returns user data with token expiration.
    Rate limited: 5 attempts per minute per IP.
    """
    permission_classes = [AllowAny]

    @method_decorator(ratelimit(key="ip", rate="5/m", method="POST"))
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        # Try to authenticate
        user = authenticate(request, username=email, password=password)

        if user is None:
            try:
                user = User.objects.get(email=email)
                if not user.check_password(password):
                    return Response(
                        {"detail": "Invalid credentials"},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )
            except User.DoesNotExist:
                return Response(
                    {"detail": "No account found with this email. Please sign up first."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        if not user.is_active:
            return Response(
                {"detail": "Please verify your email first."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Rotate session key to prevent session fixation
        request.session.cycle_key()
        login(request, user)
        expires_at = datetime.now(timezone.utc) + timedelta(days=1)

        return Response(
            {
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "name": user.name,
                    "roles": user.roles or ["user"],
                },
                "accessTokenExpiresAt": expires_at.isoformat(),
            },
            status=status.HTTP_200_OK,
        )


class LogoutAPIView(APIView):
    """POST /api/auth/logout/"""
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        logout(request)
        return Response({"detail": "Logged out successfully"}, status=status.HTTP_200_OK)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CurrentUserAPIView(APIView):
    """
    GET /api/auth/me/ — return current authenticated user.
    AllowAny so unauthenticated requests still hit this view and get CSRF cookie set.
    """
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        if not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication credentials were not provided."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        user = request.user
        return Response({
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "roles": user.roles or ["user"],
        })


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfCookieAPIView(APIView):
    """GET /api/auth/csrf/ — ensure CSRF cookie is set for SPA."""
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        return Response({"ok": True})


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing users (admin only).
    Protected: requires authentication.
    """
    queryset = User.objects.all().order_by("-date_joined")
    permission_classes = [IsAuthenticated]  # TODO: Add IsAdminUser for admin-only

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return UserUpdateSerializer
        return UserSerializer

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Deactivate a user"""
        user = self.get_object()
        user.is_active = False
        user.save()
        return Response({"detail": "User deactivated"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate a user"""
        user = self.get_object()
        user.is_active = True
        user.save()
        return Response({"detail": "User activated"}, status=status.HTTP_200_OK)


class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user notifications.
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        """Mark all notifications as read for current user"""
        self.get_queryset().update(is_read=True)
        return Response({"detail": "All notifications marked as read"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        """Mark specific notification as read"""
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({"detail": "Notification marked as read"}, status=status.HTTP_200_OK)

