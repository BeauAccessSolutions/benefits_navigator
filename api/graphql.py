"""
Custom GraphQL View with JWT Authentication Support

This module provides a GraphQL view that supports both:
- Session-based authentication (for web browsers)
- JWT Bearer token authentication (for mobile apps)
"""

from django.http import HttpRequest
from strawberry.django.views import GraphQLView as BaseGraphQLView


class JWTAuthGraphQLView(BaseGraphQLView):
    """
    GraphQL view that supports JWT authentication.

    Mobile apps can authenticate by passing:
    Authorization: Bearer <access_token>

    Web browsers continue to use session cookies.
    """

    def get_context(self, request: HttpRequest, response):
        """
        Override to add JWT authentication to the request.

        Checks for Bearer token in Authorization header and authenticates
        the user if a valid token is found.
        """
        # Try JWT authentication if not already authenticated
        if not request.user.is_authenticated:
            self._authenticate_jwt(request)

        return super().get_context(request, response)

    def _authenticate_jwt(self, request: HttpRequest) -> None:
        """
        Attempt to authenticate the request using JWT.

        Looks for Authorization: Bearer <token> header and validates
        the token using simplejwt.
        """
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if not auth_header.startswith("Bearer "):
            return

        try:
            from rest_framework_simplejwt.authentication import JWTAuthentication
            from rest_framework.request import Request

            # Wrap Django request for DRF
            drf_request = Request(request)

            # Authenticate using JWT
            jwt_auth = JWTAuthentication()
            result = jwt_auth.authenticate(drf_request)

            if result is not None:
                user, token = result
                # Set the user on the Django request
                request.user = user
                request._jwt_token = token

        except Exception:
            # If JWT auth fails, continue with anonymous user
            # The GraphQL permissions will handle access control
            pass
