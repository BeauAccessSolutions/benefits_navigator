"""
Accounts app forms - Organization and account-related forms.
"""

from django import forms
from django.core.validators import URLValidator
from django.utils import timezone
from django.utils.text import slugify

from .models import Organization, OrganizationMembership, OrganizationInvitation


class OrganizationForm(forms.ModelForm):
    """
    Form for creating and editing organizations.
    """

    class Meta:
        model = Organization
        fields = [
            "name",
            "org_type",
            "description",
            "contact_email",
            "contact_phone",
            "website",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-input w-full rounded border-gray-300 px-3 py-2",
                    "placeholder": "e.g., Veterans Service Organization of America",
                    "aria-describedby": "name-help",
                    "autofocus": True,
                }
            ),
            "org_type": forms.Select(
                attrs={
                    "class": "form-select w-full rounded border-gray-300 px-3 py-2",
                    "aria-describedby": "org-type-help",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "class": "form-textarea w-full rounded border-gray-300 px-3 py-2",
                    "placeholder": "Describe your organization and the services you provide to veterans...",
                    "aria-describedby": "description-help",
                }
            ),
            "contact_email": forms.EmailInput(
                attrs={
                    "class": "form-input w-full rounded border-gray-300 px-3 py-2",
                    "placeholder": "contact@organization.org",
                    "aria-describedby": "email-help",
                }
            ),
            "contact_phone": forms.TextInput(
                attrs={
                    "class": "form-input w-full rounded border-gray-300 px-3 py-2",
                    "placeholder": "(555) 123-4567",
                    "aria-describedby": "phone-help",
                }
            ),
            "website": forms.URLInput(
                attrs={
                    "class": "form-input w-full rounded border-gray-300 px-3 py-2",
                    "placeholder": "https://www.organization.org",
                    "aria-describedby": "website-help",
                }
            ),
        }
        labels = {
            "name": "Organization Name",
            "org_type": "Organization Type",
            "description": "Description",
            "contact_email": "Contact Email",
            "contact_phone": "Contact Phone",
            "website": "Website URL",
        }
        help_texts = {
            "name": "The official name of your organization. This will be used to generate your unique URL.",
            "org_type": "Select the type that best describes your organization.",
            "description": "Optional. A brief description of your organization for team members.",
            "contact_email": "Optional. Primary contact email for the organization.",
            "contact_phone": "Optional. Primary contact phone number.",
            "website": "Optional. Your organization's website URL.",
        }

    def clean_name(self):
        """Validate organization name and check for duplicate slugs."""
        name = self.cleaned_data.get("name")
        if name:
            slug = slugify(name)
            if not slug:
                raise forms.ValidationError(
                    "Organization name must contain at least one alphanumeric character."
                )

            # Check for existing organization with same slug
            existing = Organization.objects.filter(slug=slug)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(
                    "An organization with a similar name already exists. "
                    "Please choose a different name."
                )
        return name

    def clean_website(self):
        """Validate website URL format."""
        website = self.cleaned_data.get("website")
        if website:
            # Ensure URL has scheme
            if not website.startswith(("http://", "https://")):
                website = "https://" + website
            # Validate URL
            validator = URLValidator()
            try:
                validator(website)
            except forms.ValidationError:
                raise forms.ValidationError("Please enter a valid URL.")
        return website


class OrganizationInviteForm(forms.Form):
    """
    Form for inviting a user to join an organization.
    """

    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(
            attrs={
                "class": "form-input w-full rounded border-gray-300 px-3 py-2",
                "placeholder": "veteran@example.com",
                "aria-describedby": "email-help",
                "autofocus": True,
            }
        ),
        help_text="Email address of the person you want to invite.",
    )
    role = forms.ChoiceField(
        label="Role",
        choices=OrganizationMembership.ROLE_CHOICES,
        initial="veteran",
        widget=forms.Select(
            attrs={
                "class": "form-select w-full rounded border-gray-300 px-3 py-2",
                "aria-describedby": "role-help",
            }
        ),
        help_text="Select the role for this member.",
    )

    def __init__(self, organization, *args, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

    def clean_email(self):
        """Validate email is not already a member or has pending invite."""
        email = self.cleaned_data.get("email").lower().strip()

        # Check if email is already a member
        if OrganizationMembership.objects.filter(
            organization=self.organization, user__email__iexact=email, is_active=True
        ).exists():
            raise forms.ValidationError(
                "This email is already a member of this organization."
            )

        # Check for pending invitation
        if OrganizationInvitation.objects.filter(
            organization=self.organization,
            email__iexact=email,
            accepted_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).exists():
            raise forms.ValidationError(
                "An invitation has already been sent to this email address."
            )

        # Check allowed email domains (if configured)
        allowed_domains = self.organization.allowed_email_domains
        if allowed_domains:
            email_domain = email.split("@")[1]
            if email_domain not in allowed_domains:
                raise forms.ValidationError(
                    f'Only emails from these domains are allowed: {", ".join(allowed_domains)}'
                )

        return email

    def clean(self):
        """Validate organization has available seats."""
        cleaned_data = super().clean()
        if self.organization.is_at_seat_limit:
            raise forms.ValidationError(
                "This organization has reached its seat limit. "
                "Please upgrade your plan to invite more members."
            )
        return cleaned_data
