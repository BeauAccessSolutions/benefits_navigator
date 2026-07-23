"""
Tests for JWT Authentication API

Tests the mobile API authentication endpoints:
- Token obtain (login)
- Token refresh
- Token verify
- User info (me)
- Logout (token blacklist)
"""

import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()


@pytest.fixture
def api_client():
    """Return an API client for testing."""
    return APIClient()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        email="testuser@example.com",
        password="testpass123",
        is_verified=True,
    )


@pytest.fixture
def premium_user(db, user):
    """Create a user with premium subscription."""
    from accounts.models import Subscription

    Subscription.objects.create(
        user=user,
        plan_type="premium",
        status="active",
    )
    return user


@pytest.mark.django_db
class TestTokenObtain:
    """Tests for /api/v1/auth/token/ endpoint."""

    def test_obtain_token_success(self, api_client, user):
        """Test successful token obtain with valid credentials."""
        url = reverse("api:token_obtain")
        response = api_client.post(
            url,
            {
                "email": "testuser@example.com",
                "password": "testpass123",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data
        assert "user" in response.data
        assert response.data["user"]["email"] == "testuser@example.com"

    def test_obtain_token_wrong_password(self, api_client, user):
        """Test token obtain fails with wrong password."""
        url = reverse("api:token_obtain")
        response = api_client.post(
            url,
            {
                "email": "testuser@example.com",
                "password": "wrongpassword",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_obtain_token_nonexistent_user(self, api_client):
        """Test token obtain fails for nonexistent user."""
        url = reverse("api:token_obtain")
        response = api_client.post(
            url,
            {
                "email": "nonexistent@example.com",
                "password": "testpass123",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_obtain_token_includes_premium_status(self, api_client, premium_user):
        """Test token response includes premium status."""
        url = reverse("api:token_obtain")
        response = api_client.post(
            url,
            {
                "email": "testuser@example.com",
                "password": "testpass123",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["user"]["is_premium"] is True


@pytest.mark.django_db
class TestTokenRefresh:
    """Tests for /api/v1/auth/token/refresh/ endpoint."""

    def test_refresh_token_success(self, api_client, user):
        """Test successful token refresh."""
        # First get tokens
        obtain_url = reverse("api:token_obtain")
        obtain_response = api_client.post(
            obtain_url,
            {
                "email": "testuser@example.com",
                "password": "testpass123",
            },
        )
        refresh_token = obtain_response.data["refresh"]

        # Then refresh
        refresh_url = reverse("api:token_refresh")
        response = api_client.post(
            refresh_url,
            {
                "refresh": refresh_token,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        # With rotation enabled, should get new refresh token
        assert "refresh" in response.data

    def test_refresh_token_invalid(self, api_client):
        """Test refresh fails with invalid token."""
        refresh_url = reverse("api:token_refresh")
        response = api_client.post(
            refresh_url,
            {
                "refresh": "invalid-token",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTokenVerify:
    """Tests for /api/v1/auth/token/verify/ endpoint."""

    def test_verify_token_success(self, api_client, user):
        """Test token verification succeeds with valid token."""
        # Get token
        obtain_url = reverse("api:token_obtain")
        obtain_response = api_client.post(
            obtain_url,
            {
                "email": "testuser@example.com",
                "password": "testpass123",
            },
        )
        access_token = obtain_response.data["access"]

        # Verify
        verify_url = reverse("api:token_verify")
        response = api_client.post(
            verify_url,
            {
                "token": access_token,
            },
        )

        assert response.status_code == status.HTTP_200_OK

    def test_verify_token_invalid(self, api_client):
        """Test verification fails with invalid token."""
        verify_url = reverse("api:token_verify")
        response = api_client.post(
            verify_url,
            {
                "token": "invalid-token",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestMeEndpoint:
    """Tests for /api/v1/auth/me/ endpoint."""

    def test_me_authenticated(self, api_client, user):
        """Test getting user info when authenticated."""
        # Get token
        obtain_url = reverse("api:token_obtain")
        obtain_response = api_client.post(
            obtain_url,
            {
                "email": "testuser@example.com",
                "password": "testpass123",
            },
        )
        access_token = obtain_response.data["access"]

        # Get user info
        me_url = reverse("api:me")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = api_client.get(me_url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == "testuser@example.com"
        assert response.data["id"] == user.id

    def test_me_unauthenticated(self, api_client):
        """Test me endpoint requires authentication."""
        me_url = reverse("api:me")
        response = api_client.get(me_url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestLogout:
    """Tests for /api/v1/auth/logout/ endpoint."""

    def test_logout_blacklists_token(self, api_client, user):
        """Test logout blacklists the refresh token."""
        # Get tokens
        obtain_url = reverse("api:token_obtain")
        obtain_response = api_client.post(
            obtain_url,
            {
                "email": "testuser@example.com",
                "password": "testpass123",
            },
        )
        access_token = obtain_response.data["access"]
        refresh_token = obtain_response.data["refresh"]

        # Logout
        logout_url = reverse("api:logout")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = api_client.post(
            logout_url,
            {
                "refresh": refresh_token,
            },
        )

        assert response.status_code == status.HTTP_200_OK

        # Try to use the blacklisted refresh token
        refresh_url = reverse("api:token_refresh")
        api_client.credentials()  # Clear credentials
        refresh_response = api_client.post(
            refresh_url,
            {
                "refresh": refresh_token,
            },
        )

        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_requires_refresh_token(self, api_client, user):
        """Test logout requires refresh token in request."""
        # Get tokens
        obtain_url = reverse("api:token_obtain")
        obtain_response = api_client.post(
            obtain_url,
            {
                "email": "testuser@example.com",
                "password": "testpass123",
            },
        )
        access_token = obtain_response.data["access"]

        # Try logout without refresh token
        logout_url = reverse("api:logout")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = api_client.post(logout_url, {})

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestAuditLogFailureIsNotSilent:
    """
    Login/logout wrap their AuditLog.objects.create() call in try/except so
    a broken audit log can't block auth — but TODO.md flagged that failure
    as a completely silent `except: pass`, which is a security blind spot.
    It must now be logged (and auth must still succeed) instead of vanishing.
    """

    def test_login_succeeds_and_logs_when_audit_log_write_fails(
        self, api_client, user, monkeypatch, caplog
    ):
        from core.models import AuditLog

        def boom(*args, **kwargs):
            raise RuntimeError("simulated audit log outage")

        monkeypatch.setattr(AuditLog.objects, "create", boom)

        with caplog.at_level("ERROR"):
            response = api_client.post(
                reverse("api:token_obtain"),
                {"email": "testuser@example.com", "password": "testpass123"},
            )

        assert response.status_code == status.HTTP_200_OK
        assert any("audit log" in record.message.lower() for record in caplog.records)

    def test_logout_succeeds_and_logs_when_audit_log_write_fails(
        self, api_client, user, monkeypatch, caplog
    ):
        from core.models import AuditLog

        obtain_response = api_client.post(
            reverse("api:token_obtain"),
            {"email": "testuser@example.com", "password": "testpass123"},
        )
        access_token = obtain_response.data["access"]
        refresh_token = obtain_response.data["refresh"]

        def boom(*args, **kwargs):
            raise RuntimeError("simulated audit log outage")

        monkeypatch.setattr(AuditLog.objects, "create", boom)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        with caplog.at_level("ERROR"):
            response = api_client.post(
                reverse("api:logout"), {"refresh": refresh_token}
            )

        assert response.status_code == status.HTTP_200_OK
        assert any("audit log" in record.message.lower() for record in caplog.records)


@pytest.mark.django_db
class TestGraphQLWithJWT:
    """Tests for GraphQL endpoint with JWT authentication."""

    def test_graphql_with_jwt_auth(self, api_client, user):
        """Test GraphQL endpoint accepts JWT authentication."""
        # Get token
        obtain_url = reverse("api:token_obtain")
        obtain_response = api_client.post(
            obtain_url,
            {
                "email": "testuser@example.com",
                "password": "testpass123",
            },
        )
        access_token = obtain_response.data["access"]

        # Query GraphQL with JWT
        graphql_url = reverse("graphql")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = api_client.post(
            graphql_url,
            {"query": "{ me { id email } }"},
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "errors" not in data or data["errors"] is None
        assert data["data"]["me"]["email"] == "testuser@example.com"

    def test_graphql_without_auth_fails_protected_query(self, api_client):
        """Test GraphQL protected queries fail without auth."""
        graphql_url = reverse("graphql")
        response = api_client.post(
            graphql_url,
            {"query": "{ me { id email } }"},
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Should have authentication error
        assert "errors" in data and data["errors"] is not None
