"""
Mobile API URL Configuration

All API endpoints are prefixed with /api/v1/
"""

from django.urls import path

from .views import (
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    CustomTokenVerifyView,
    me,
    logout,
)

app_name = "api"

urlpatterns = [
    # JWT Authentication
    path("auth/token/", CustomTokenObtainPairView.as_view(), name="token_obtain"),
    path("auth/token/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("auth/token/verify/", CustomTokenVerifyView.as_view(), name="token_verify"),
    # User endpoints
    path("auth/me/", me, name="me"),
    path("auth/logout/", logout, name="logout"),
]
