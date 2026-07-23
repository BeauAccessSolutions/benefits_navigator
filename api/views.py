"""
Mobile API Views - JWT Authentication and User Info

Provides endpoints for mobile app authentication:
- /api/v1/auth/token/ - Obtain access and refresh tokens
- /api/v1/auth/token/refresh/ - Refresh access token
- /api/v1/auth/token/verify/ - Verify token validity
- /api/v1/auth/me/ - Get current user info
"""

import logging

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.models import AuditLog

logger = logging.getLogger(__name__)

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom token serializer that includes user info in the response.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token["email"] = user.email
        token["is_premium"] = user.is_premium

        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        # Add user info to response
        data["user"] = {
            "id": self.user.id,
            "email": self.user.email,
            "full_name": self.user.full_name,
            "is_premium": self.user.is_premium,
            "is_verified": self.user.is_verified,
        }

        # Audit log the login
        try:
            AuditLog.objects.create(
                user=self.user,
                action="api_login",
                resource_type="User",
                resource_id=self.user.id,
                details={"method": "jwt"},
                success=True,
            )
        except Exception:
            # Don't fail login if audit logging fails, but a failure here
            # is a security-relevant blind spot — it must not be silent.
            logger.exception("Failed to write audit log for api_login")

        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom token obtain view that uses our custom serializer.

    POST /api/v1/auth/token/
    {
        "email": "user@example.com",
        "password": "password123"
    }

    Response:
    {
        "access": "eyJ...",
        "refresh": "eyJ...",
        "user": {
            "id": 1,
            "email": "user@example.com",
            "full_name": "John Doe",
            "is_premium": true,
            "is_verified": true
        }
    }
    """

    serializer_class = CustomTokenObtainPairSerializer


class CustomTokenRefreshView(TokenRefreshView):
    """
    Refresh access token using refresh token.

    POST /api/v1/auth/token/refresh/
    {
        "refresh": "eyJ..."
    }

    Response:
    {
        "access": "eyJ...",
        "refresh": "eyJ..."  # New refresh token (rotation enabled)
    }
    """

    pass


class CustomTokenVerifyView(TokenVerifyView):
    """
    Verify a token is valid.

    POST /api/v1/auth/token/verify/
    {
        "token": "eyJ..."
    }

    Response: 200 OK if valid, 401 if invalid
    """

    pass


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """
    Get current authenticated user info.

    GET /api/v1/auth/me/
    Authorization: Bearer <access_token>

    Response:
    {
        "id": 1,
        "email": "user@example.com",
        "full_name": "John Doe",
        "is_premium": true,
        "is_verified": true,
        "profile": {
            "branch_of_service": "Army",
            "disability_rating": 70
        },
        "subscription": {
            "plan_type": "premium",
            "status": "active"
        }
    }
    """
    user = request.user

    # Get profile info
    profile_data = None
    try:
        profile = user.profile
        profile_data = {
            "branch_of_service": profile.branch_of_service,
            "disability_rating": profile.disability_rating,
        }
    except Exception:
        pass

    # Get subscription info
    subscription_data = None
    try:
        subscription = user.subscription
        subscription_data = {
            "plan_type": subscription.plan_type,
            "status": subscription.status,
            "current_period_end": (
                subscription.current_period_end.isoformat()
                if subscription.current_period_end
                else None
            ),
        }
    except Exception:
        pass

    return Response(
        {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_premium": user.is_premium,
            "is_verified": user.is_verified,
            "date_joined": user.date_joined.isoformat(),
            "profile": profile_data,
            "subscription": subscription_data,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    """
    Logout by blacklisting the refresh token.

    POST /api/v1/auth/logout/
    Authorization: Bearer <access_token>
    {
        "refresh": "eyJ..."
    }

    Response: 200 OK
    """
    from rest_framework_simplejwt.tokens import RefreshToken
    from rest_framework_simplejwt.exceptions import TokenError

    refresh_token = request.data.get("refresh")
    if not refresh_token:
        return Response(
            {"error": "Refresh token is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        token = RefreshToken(refresh_token)
        token.blacklist()

        # Audit log the logout
        try:
            AuditLog.objects.create(
                user=request.user,
                action="api_logout",
                resource_type="User",
                resource_id=request.user.id,
                details={"method": "jwt"},
                success=True,
            )
        except Exception:
            logger.exception("Failed to write audit log for api_logout")

        return Response({"message": "Successfully logged out"})
    except TokenError:
        return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)
