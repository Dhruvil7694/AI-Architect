"""
Stub auth views for development. Accept any email/password and return a fake user.
Replace with real JWT/session auth for production.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class LoginStubAPIView(APIView):
    """
    POST /api/auth/login/
    Body: { "email": "...", "password": "..." }
    Returns 200 with { user, accessTokenExpiresAt } for any non-empty email.
    """

    def post(self, request: Request, *args, **kwargs) -> Response:
        email = (request.data.get("email") or "").strip()
        if not email:
            return Response(
                {"detail": "Email is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        return Response(
            {
                "user": {
                    "id": "1",
                    "email": email,
                    "name": email.split("@")[0],
                    "roles": ["user"],
                },
                "accessTokenExpiresAt": expires_at.isoformat(),
            },
            status=status.HTTP_200_OK,
        )
