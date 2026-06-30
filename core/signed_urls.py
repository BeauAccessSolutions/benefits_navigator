"""
Signed URL utilities for secure file access.

Provides time-limited, cryptographically signed URLs for accessing
protected files. This prevents enumeration attacks and ensures URLs
expire after a configurable period.

Usage:
    from core.signed_urls import SignedURLGenerator

    generator = SignedURLGenerator()

    # Generate a signed URL
    signed_url = generator.generate_url(
        resource_type='document',
        resource_id=123,
        user_id=456,
        action='download',
        expires_minutes=30
    )

    # Validate and extract data from a signed URL
    data = generator.validate_token(token)
    if data:
        # Access granted
        resource_id = data['resource_id']
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Optional, Dict, Any

from django.conf import settings
from django.urls import reverse


class SignedURLError(Exception):
    """Base exception for signed URL errors."""

    pass


class TokenExpiredError(SignedURLError):
    """Token has expired."""

    pass


class InvalidTokenError(SignedURLError):
    """Token is invalid or tampered with."""

    pass


class SignedURLGenerator:
    """
    Generate and validate signed URLs for secure resource access.

    Uses HMAC-SHA256 for signing with Django's SECRET_KEY.
    Tokens include expiration time and are base64url encoded.
    """

    # Default expiration in minutes
    DEFAULT_EXPIRES_MINUTES = 30

    # Maximum allowed expiration (24 hours)
    MAX_EXPIRES_MINUTES = 1440

    def __init__(self, secret_key: str = None):
        """
        Initialize with a secret key.

        Args:
            secret_key: Key for HMAC signing. Defaults to Django SECRET_KEY.
        """
        self.secret_key = secret_key or settings.SECRET_KEY
        if isinstance(self.secret_key, str):
            self.secret_key = self.secret_key.encode("utf-8")

    def _generate_signature(self, data: str) -> str:
        """Generate HMAC-SHA256 signature for data."""
        signature = hmac.new(
            self.secret_key, data.encode("utf-8"), hashlib.sha256
        ).digest()
        return base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")

    def _verify_signature(self, data: str, signature: str) -> bool:
        """Verify HMAC-SHA256 signature."""
        expected = self._generate_signature(data)
        return hmac.compare_digest(expected, signature)

    def generate_token(
        self,
        resource_type: str,
        resource_id: int,
        user_id: int,
        action: str = "download",
        expires_minutes: int = None,
        extra_data: Dict[str, Any] = None,
    ) -> str:
        """
        Generate a signed token for resource access.

        Args:
            resource_type: Type of resource (e.g., 'document')
            resource_id: ID of the resource
            user_id: ID of the user who should have access
            action: Action type ('download', 'view', etc.)
            expires_minutes: Token validity period in minutes
            extra_data: Additional data to include in token

        Returns:
            Base64url-encoded signed token
        """
        if expires_minutes is None:
            expires_minutes = self.DEFAULT_EXPIRES_MINUTES

        # Cap expiration time
        expires_minutes = min(expires_minutes, self.MAX_EXPIRES_MINUTES)

        # Calculate expiration timestamp
        expires_at = int(time.time()) + (expires_minutes * 60)

        # Build payload
        payload = {
            "rt": resource_type,  # resource_type
            "ri": resource_id,  # resource_id
            "ui": user_id,  # user_id
            "a": action,  # action
            "e": expires_at,  # expires_at
        }

        if extra_data:
            payload["x"] = extra_data

        # Encode payload
        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        payload_b64 = (
            base64.urlsafe_b64encode(payload_json.encode("utf-8"))
            .decode("utf-8")
            .rstrip("=")
        )

        # Generate signature
        signature = self._generate_signature(payload_b64)

        # Combine payload and signature
        token = f"{payload_b64}.{signature}"

        return token

    def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate a signed token and extract its data.

        Args:
            token: The signed token to validate

        Returns:
            Dict with token data if valid, None if invalid

        Raises:
            TokenExpiredError: If token has expired
            InvalidTokenError: If token is malformed or signature invalid
        """
        if not token or "." not in token:
            raise InvalidTokenError("Invalid token format")

        try:
            # Split token into payload and signature
            parts = token.split(".")
            if len(parts) != 2:
                raise InvalidTokenError("Invalid token format")

            payload_b64, signature = parts

            # Verify signature first
            if not self._verify_signature(payload_b64, signature):
                raise InvalidTokenError("Invalid signature")

            # Decode payload (add padding if needed)
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding

            payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
            payload = json.loads(payload_json)

            # Check expiration
            expires_at = payload.get("e", 0)
            if time.time() > expires_at:
                raise TokenExpiredError("Token has expired")

            # Return normalized data
            return {
                "resource_type": payload.get("rt"),
                "resource_id": payload.get("ri"),
                "user_id": payload.get("ui"),
                "action": payload.get("a"),
                "expires_at": expires_at,
                "extra_data": payload.get("x"),
            }

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise InvalidTokenError(f"Invalid token data: {e}")

    def generate_url(
        self,
        resource_type: str,
        resource_id: int,
        user_id: int,
        action: str = "download",
        expires_minutes: int = None,
        extra_data: Dict[str, Any] = None,
        url_name: str = None,
        absolute: bool = False,
        request=None,
    ) -> str:
        """
        Generate a complete signed URL for resource access.

        Args:
            resource_type: Type of resource (e.g., 'document')
            resource_id: ID of the resource
            user_id: ID of the user who should have access
            action: Action type ('download', 'view')
            expires_minutes: Token validity period in minutes
            extra_data: Additional data to include in token
            url_name: Django URL name to use (auto-detected if not provided)
            absolute: Whether to return an absolute URL
            request: Django request object (required for absolute URLs)

        Returns:
            Complete URL with signed token
        """
        token = self.generate_token(
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            action=action,
            expires_minutes=expires_minutes,
            extra_data=extra_data,
        )

        # Determine URL name
        if url_name is None:
            if resource_type == "document":
                url_name = f"claims:document_{action}_signed"
            else:
                url_name = f"{resource_type}_{action}_signed"

        # Build URL
        try:
            url = reverse(url_name, kwargs={"token": token})
        except Exception:
            # Fallback: append token as query parameter
            base_url = reverse(f"claims:document_{action}", kwargs={"pk": resource_id})
            url = f"{base_url}?token={token}"

        if absolute and request:
            url = request.build_absolute_uri(url)

        return url


# Singleton instance for convenience
_generator = None


def get_signed_url_generator() -> SignedURLGenerator:
    """Get the singleton SignedURLGenerator instance."""
    global _generator
    if _generator is None:
        _generator = SignedURLGenerator()
    return _generator


def generate_signed_url(
    resource_type: str,
    resource_id: int,
    user_id: int,
    action: str = "download",
    expires_minutes: int = 30,
    request=None,
) -> str:
    """
    Convenience function to generate a signed URL.

    Args:
        resource_type: Type of resource (e.g., 'document')
        resource_id: ID of the resource
        user_id: ID of the user who should have access
        action: Action type ('download', 'view')
        expires_minutes: Token validity period in minutes
        request: Django request object (for absolute URLs)

    Returns:
        Signed URL string
    """
    generator = get_signed_url_generator()
    return generator.generate_url(
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        action=action,
        expires_minutes=expires_minutes,
        request=request,
    )


def validate_signed_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Convenience function to validate a signed token.

    Args:
        token: The signed token to validate

    Returns:
        Dict with token data if valid

    Raises:
        TokenExpiredError: If token has expired
        InvalidTokenError: If token is invalid
    """
    generator = get_signed_url_generator()
    return generator.validate_token(token)
