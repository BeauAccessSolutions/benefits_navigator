"""
Role-based permissions for VSO app.

This module provides decorators and utilities for enforcing access control
based on user roles (veteran, caseworker, admin).

SECURITY NOTE: All VSO staff checks MUST be scoped to a specific organization
to prevent cross-organization data access. Use get_user_staff_organizations()
to get all organizations where a user has staff access.
"""

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


class Roles:
    """Role constants matching OrganizationMembership.ROLE_CHOICES"""

    ADMIN = "admin"
    CASEWORKER = "caseworker"
    VETERAN = "veteran"

    # Role groups for permission checks
    VSO_STAFF = [ADMIN, CASEWORKER]
    ALL = [ADMIN, CASEWORKER, VETERAN]


def get_user_roles(user, organization=None):
    """
    Get all roles for a user, optionally filtered by organization.

    Args:
        user: User instance
        organization: Organization to scope the check (recommended for security)

    Returns a set of role strings.
    """
    if not user.is_authenticated:
        return set()

    memberships = user.memberships.filter(is_active=True)

    if organization:
        memberships = memberships.filter(organization=organization)

    return set(memberships.values_list("role", flat=True))


def has_role(user, roles, organization=None):
    """
    Check if user has any of the specified roles.

    Args:
        user: User instance
        roles: Single role string or list of role strings
        organization: Organization to scope the check (recommended for security)

    Returns:
        True if user has at least one of the specified roles
    """
    if isinstance(roles, str):
        roles = [roles]

    user_roles = get_user_roles(user, organization)
    return bool(user_roles.intersection(roles))


def is_vso_staff(user, organization=None):
    """
    Check if user is VSO staff (admin or caseworker).

    IMPORTANT: For security, always pass organization when checking access
    to organization-specific resources.
    """
    return has_role(user, Roles.VSO_STAFF, organization)


def is_organization_admin(user, organization=None):
    """Check if user is an organization admin."""
    return has_role(user, [Roles.ADMIN], organization)


def get_user_staff_organizations(user):
    """
    Get all organizations where user has VSO staff (admin/caseworker) access.

    Use this to scope queries and ensure users only see their own org's data.

    Returns:
        QuerySet of Organization objects
    """
    from accounts.models import Organization

    if not user.is_authenticated:
        return Organization.objects.none()

    org_ids = user.memberships.filter(
        is_active=True, organization__is_active=True, role__in=Roles.VSO_STAFF
    ).values_list("organization_id", flat=True)

    return Organization.objects.filter(id__in=org_ids)


def get_user_organization_membership(user, organization=None, roles=None):
    """
    Get user's membership for an organization.

    Args:
        user: User instance
        organization: Organization to check (optional but recommended)
        roles: Filter by roles (optional)

    Returns:
        OrganizationMembership instance or None
    """
    if not user.is_authenticated:
        return None

    memberships = user.memberships.filter(is_active=True, organization__is_active=True)

    if organization:
        memberships = memberships.filter(organization=organization)

    if roles:
        if isinstance(roles, str):
            roles = [roles]
        memberships = memberships.filter(role__in=roles)

    return memberships.select_related("organization").first()


def can_access_case(user, case):
    """
    Check if user can access a specific VeteranCase.

    Access is granted if:
    - User is the veteran associated with the case
    - User is VSO staff in the case's organization

    Args:
        user: User instance
        case: VeteranCase instance

    Returns:
        True if user can access the case
    """
    if not user.is_authenticated:
        return False

    # Case owner (veteran) always has access
    if case.veteran and case.veteran == user:
        return True

    # VSO staff in the case's organization has access
    return is_vso_staff(user, organization=case.organization)


def can_access_shared_document(user, shared_document):
    """
    Check if user can access a SharedDocument.

    Access is granted if:
    - User owns the original document
    - User is VSO staff in the document's case organization

    Args:
        user: User instance
        shared_document: SharedDocument instance

    Returns:
        True if user can access the shared document
    """
    if not user.is_authenticated:
        return False

    # Document owner always has access
    if shared_document.document.user == user:
        return True

    # VSO staff in the case's organization has access
    return is_vso_staff(user, organization=shared_document.case.organization)


# ============================================================================
# Decorators
# ============================================================================


def role_required(roles, redirect_url="home", message=None):
    """
    Decorator that requires user to have one of the specified roles.

    Usage:
        @role_required([Roles.ADMIN, Roles.CASEWORKER])
        def my_view(request):
            ...

        @role_required(Roles.ADMIN, message="Admin access required")
        def admin_only_view(request):
            ...
    """
    if isinstance(roles, str):
        roles = [roles]

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if has_role(request.user, roles):
                return view_func(request, *args, **kwargs)

            # User doesn't have required role
            error_msg = message or "You don't have permission to access this page."
            messages.error(request, error_msg)
            return redirect(redirect_url)

        return wrapper

    return decorator


def vso_staff_required(view_func):
    """
    Decorator that requires user to be VSO staff (admin or caseworker).

    This is a convenience wrapper around role_required.
    """
    return role_required(
        Roles.VSO_STAFF,
        redirect_url="claims:document_list",
        message="You don't have permission to access the VSO dashboard.",
    )(view_func)


def organization_admin_required(view_func):
    """
    Decorator that requires user to be an organization admin.
    """
    return role_required(
        [Roles.ADMIN],
        redirect_url="vso:dashboard",
        message="This action requires administrator privileges.",
    )(view_func)


def owns_resource_or_vso_staff(
    model_class, pk_kwarg="pk", user_field="user", org_field=None
):
    """
    Decorator that checks if user owns the resource OR is VSO staff with access.

    SECURITY: VSO staff access is scoped to the resource's organization.

    Args:
        model_class: The Django model class
        pk_kwarg: The URL kwarg containing the primary key
        user_field: The field name on the model that references the user
        org_field: The field path to the organization (e.g., 'case__organization')

    Usage:
        @owns_resource_or_vso_staff(Document, pk_kwarg='pk', user_field='user')
        def document_view(request, pk):
            ...
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            from django.shortcuts import get_object_or_404

            pk = kwargs.get(pk_kwarg)
            obj = get_object_or_404(model_class, pk=pk)

            # Check if user owns the resource
            owner = getattr(obj, user_field, None)
            if owner and owner == request.user:
                return view_func(request, *args, **kwargs)

            # Get the resource's organization for scoped access check
            resource_org = None

            # If org_field is specified, use that path
            if org_field:
                parts = org_field.split("__")
                resource_org = obj
                for part in parts:
                    resource_org = getattr(resource_org, part, None)
                    if resource_org is None:
                        break

            # Check if resource has case_shares (for documents)
            if resource_org is None and hasattr(obj, "case_shares"):
                # Get organizations from related case shares
                user_staff_orgs = get_user_staff_organizations(request.user)
                has_access = obj.case_shares.filter(
                    case__organization__in=user_staff_orgs
                ).exists()
                if has_access:
                    return view_func(request, *args, **kwargs)

            # Check if resource has a direct organization field
            if resource_org is None:
                resource_org = getattr(obj, "organization", None)

            # If we have an organization, check scoped VSO staff access
            if resource_org and is_vso_staff(request.user, organization=resource_org):
                return view_func(request, *args, **kwargs)

            raise PermissionDenied("You don't have permission to access this resource.")

        return wrapper

    return decorator


# ============================================================================
# Mixins for Class-Based Views
# ============================================================================


class RoleRequiredMixin:
    """
    Mixin for class-based views that requires specific roles.

    Usage:
        class MyView(RoleRequiredMixin, View):
            required_roles = [Roles.ADMIN, Roles.CASEWORKER]
            permission_denied_message = "Custom message"
    """

    required_roles = []
    permission_denied_message = "You don't have permission to access this page."
    permission_denied_redirect = "home"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("account_login")

        if not has_role(request.user, self.required_roles):
            messages.error(request, self.permission_denied_message)
            return redirect(self.permission_denied_redirect)

        return super().dispatch(request, *args, **kwargs)


class VSOStaffRequiredMixin(RoleRequiredMixin):
    """Mixin that requires VSO staff access."""

    required_roles = Roles.VSO_STAFF
    permission_denied_message = "You don't have permission to access the VSO dashboard."
    permission_denied_redirect = "claims:document_list"


class OrganizationAdminRequiredMixin(RoleRequiredMixin):
    """Mixin that requires organization admin access."""

    required_roles = [Roles.ADMIN]
    permission_denied_message = "This action requires administrator privileges."
    permission_denied_redirect = "vso:dashboard"


# ============================================================================
# Template Helpers
# ============================================================================


def get_permission_context(user):
    """
    Get permission-related context for templates.

    Returns a dict that can be added to template context.
    """
    if not user.is_authenticated:
        return {
            "is_vso_staff": False,
            "is_org_admin": False,
            "user_roles": set(),
            "user_organizations": [],
        }

    memberships = user.memberships.filter(
        is_active=True, organization__is_active=True
    ).select_related("organization")

    return {
        "is_vso_staff": any(m.role in Roles.VSO_STAFF for m in memberships),
        "is_org_admin": any(m.role == Roles.ADMIN for m in memberships),
        "user_roles": set(m.role for m in memberships),
        "user_organizations": [m.organization for m in memberships],
    }
