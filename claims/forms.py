"""
Forms for claims app with accessibility and validation
"""

import logging

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import Document

logger = logging.getLogger(__name__)

# python-magic is REQUIRED for secure file validation
# It validates file content via magic bytes, not just extension/MIME header
try:
    import magic

    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    logger.error(
        "SECURITY WARNING: python-magic is not installed. "
        "File uploads will be rejected until it is installed. "
        "Install with: pip install python-magic (or python-magic-bin on Windows)"
    )


class DocumentUploadForm(forms.ModelForm):
    """
    Accessible document upload form with comprehensive validation
    """

    ai_consent = forms.BooleanField(
        required=False,  # Only required if user hasn't consented before
        label=_("I consent to AI processing"),
        help_text=_(
            "I understand that my document will be processed using OCR (optical character "
            "recognition) and AI (OpenAI) to extract and analyze its contents. "
            "My document data will be transmitted securely and processed according to "
            "our Privacy Policy."
        ),
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500",
                "aria-describedby": "ai-consent-help",
            }
        ),
    )

    class Meta:
        model = Document
        fields = ["file", "document_type"]
        widgets = {
            "file": forms.FileInput(
                attrs={
                    "class": "block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none",
                    "accept": ".pdf,.jpg,.jpeg,.png,.tiff",
                    "aria-describedby": "file-help",
                }
            ),
            "document_type": forms.Select(
                attrs={
                    "class": "block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500",
                    "aria-describedby": "document-type-help",
                }
            ),
        }
        labels = {
            "file": _("Select Document"),
            "document_type": _("Document Type"),
        }
        help_texts = {
            "file": _("Accepted formats: PDF, JPG, PNG, TIFF. Maximum size: 50 MB."),
            "document_type": _("Select the type of document you are uploading."),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Check if user has already consented
        self.user_has_consent = False
        if self.user:
            try:
                profile = self.user.profile
                self.user_has_consent = profile.ai_processing_consent
            except Exception:
                pass

        # If user has already consented, hide the consent field
        if self.user_has_consent:
            self.fields["ai_consent"].widget = forms.HiddenInput()
            self.fields["ai_consent"].initial = True
        else:
            # Make consent required for new users
            self.fields["ai_consent"].required = True

        # Add required asterisks for screen readers
        for field_name, field in self.fields.items():
            if field.required and not isinstance(field.widget, forms.HiddenInput):
                field.label = f"{field.label} (required)"

    def clean_file(self):
        """
        Validate uploaded file
        Checks file size, type, magic bytes, and user limits
        """
        file = self.cleaned_data.get("file")

        if not file:
            raise ValidationError(_("Please select a file to upload."))

        # Check file size
        if file.size > settings.MAX_DOCUMENT_SIZE:
            max_size_mb = settings.MAX_DOCUMENT_SIZE / (1024 * 1024)
            raise ValidationError(
                _(
                    f"File size exceeds maximum allowed size of {max_size_mb} MB. "
                    f"Your file is {round(file.size / (1024 * 1024), 2)} MB."
                )
            )

        # Check file extension (first layer of defense)
        allowed_extensions = [".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"]
        ext = file.name.lower().split(".")[-1]
        if f".{ext}" not in allowed_extensions:
            raise ValidationError(
                _(
                    "Invalid file extension. Allowed extensions: PDF, JPG, JPEG, PNG, TIFF."
                )
            )

        # Check file type via content_type header
        allowed_types = settings.ALLOWED_DOCUMENT_TYPES
        if file.content_type not in allowed_types:
            raise ValidationError(
                _(
                    "File type not supported. Please upload PDF, JPG, PNG, or TIFF files only."
                )
            )

        # SECURITY: Validate actual file content using magic bytes
        # This prevents malicious files disguised with fake extensions
        if not MAGIC_AVAILABLE:
            # python-magic is required for secure uploads
            raise ValidationError(
                _(
                    "File upload is temporarily unavailable due to a server configuration issue. "
                    "Please contact support."
                )
            )

        file.seek(0)
        file_magic = magic.from_buffer(file.read(2048), mime=True)
        file.seek(0)  # Reset file pointer

        if file_magic not in allowed_types:
            raise ValidationError(
                _(
                    "File content does not match expected type. "
                    "Please ensure you are uploading a valid PDF or image file."
                )
            )

        # Check page count for PDFs to prevent extremely large documents
        if ext == "pdf":
            page_count = self._get_pdf_page_count(file)
            max_pages = getattr(settings, "MAX_DOCUMENT_PAGES", 100)
            if page_count and page_count > max_pages:
                raise ValidationError(
                    _(
                        f"PDF has too many pages ({page_count}). Maximum allowed is {max_pages} pages."
                    )
                )

        # Check user's limits using UsageTracking (includes storage cap)
        if self.user:
            from accounts.models import UsageTracking

            usage, created = UsageTracking.objects.get_or_create(user=self.user)
            can_upload, reason = usage.can_upload_document(file.size)
            if not can_upload:
                raise ValidationError(
                    _(reason + " Please upgrade to Premium for unlimited uploads.")
                )

        return file

    def clean(self):
        """
        Additional form-level validation
        """
        cleaned_data = super().clean()

        # Validate AI consent
        if not self.user_has_consent:
            ai_consent = cleaned_data.get("ai_consent")
            if not ai_consent:
                raise ValidationError(
                    {
                        "ai_consent": _(
                            "You must consent to AI processing to upload documents."
                        )
                    }
                )

        return cleaned_data

    def save_consent(self):
        """
        Save AI processing consent to user profile.
        Call this after form validation.
        """
        if self.user and not self.user_has_consent:
            from django.utils import timezone
            from accounts.models import UserProfile

            profile, _ = UserProfile.objects.get_or_create(user=self.user)
            profile.ai_processing_consent = True
            profile.ai_consent_date = timezone.now()
            profile.save()

    def _get_pdf_page_count(self, file):
        """
        Get page count from a PDF file.

        Returns:
            int or None: Page count, or None if unable to determine.
        """
        try:
            import PyPDF2

            file.seek(0)
            reader = PyPDF2.PdfReader(file)
            page_count = len(reader.pages)
            file.seek(0)
            return page_count
        except ImportError:
            logger.debug("PyPDF2 not available for page count validation")
            return None
        except Exception as e:
            logger.warning(f"Could not determine PDF page count: {e}")
            return None


class DenialLetterUploadForm(forms.ModelForm):
    """
    Simplified upload form specifically for VA denial letters.
    Pre-configured for decision_letter document type.
    """

    ai_consent = forms.BooleanField(
        required=False,  # Only required if user hasn't consented before
        label=_("I consent to AI processing"),
        help_text=_(
            "I understand that my denial letter will be processed using OCR and AI "
            "to extract and analyze its contents. My document data will be transmitted "
            "securely and processed according to our Privacy Policy."
        ),
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500",
                "aria-describedby": "ai-consent-help",
            }
        ),
    )

    class Meta:
        model = Document
        fields = ["file"]
        widgets = {
            "file": forms.FileInput(
                attrs={
                    "class": "block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none",
                    "accept": ".pdf,.jpg,.jpeg,.png,.tiff",
                    "aria-describedby": "file-help",
                }
            ),
        }
        labels = {
            "file": _("Upload VA Denial Letter"),
        }
        help_texts = {
            "file": _(
                "Upload your VA Rating Decision letter (PDF or image). Maximum size: 50 MB."
            ),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Check if user has already consented
        self.user_has_consent = False
        if self.user:
            try:
                profile = self.user.profile
                self.user_has_consent = profile.ai_processing_consent
            except Exception:
                pass

        # If user has already consented, hide the consent field
        if self.user_has_consent:
            self.fields["ai_consent"].widget = forms.HiddenInput()
            self.fields["ai_consent"].initial = True
        else:
            # Make consent required for new users
            self.fields["ai_consent"].required = True

        # Add required indicator
        self.fields["file"].label = f"{self.fields['file'].label} (required)"
        if self.fields["ai_consent"].required:
            self.fields["ai_consent"].label = (
                f"{self.fields['ai_consent'].label} (required)"
            )

    def clean_file(self):
        """
        Validate uploaded denial letter.
        """
        file = self.cleaned_data.get("file")

        if not file:
            raise ValidationError(_("Please select a denial letter to upload."))

        # Check file size
        if file.size > settings.MAX_DOCUMENT_SIZE:
            max_size_mb = settings.MAX_DOCUMENT_SIZE / (1024 * 1024)
            raise ValidationError(
                _(f"File size exceeds maximum allowed size of {max_size_mb} MB.")
            )

        # Check file extension
        allowed_extensions = [".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"]
        ext = file.name.lower().split(".")[-1]
        if f".{ext}" not in allowed_extensions:
            raise ValidationError(
                _(
                    "Invalid file extension. Allowed extensions: PDF, JPG, JPEG, PNG, TIFF."
                )
            )

        # Check file type via content_type
        allowed_types = settings.ALLOWED_DOCUMENT_TYPES
        if file.content_type not in allowed_types:
            raise ValidationError(
                _("File type not supported. Please upload PDF or image files only.")
            )

        # SECURITY: Validate via magic bytes
        if not MAGIC_AVAILABLE:
            # python-magic is required for secure uploads
            raise ValidationError(
                _(
                    "File upload is temporarily unavailable due to a server configuration issue. "
                    "Please contact support."
                )
            )

        file.seek(0)
        file_magic = magic.from_buffer(file.read(2048), mime=True)
        file.seek(0)

        if file_magic not in allowed_types:
            raise ValidationError(_("File content does not match expected type."))

        # Check page count for PDFs
        if ext == "pdf":
            page_count = self._get_pdf_page_count(file)
            max_pages = getattr(settings, "MAX_DOCUMENT_PAGES", 100)
            if page_count and page_count > max_pages:
                raise ValidationError(
                    _(
                        f"PDF has too many pages ({page_count}). Maximum allowed is {max_pages} pages."
                    )
                )

        # Check user's upload limits using UsageTracking
        if self.user:
            from accounts.models import UsageTracking

            usage, created = UsageTracking.objects.get_or_create(user=self.user)

            # Check document upload limit
            can_upload, reason = usage.can_upload_document(file.size)
            if not can_upload:
                raise ValidationError(
                    _(reason + " Please upgrade to Premium for unlimited uploads.")
                )

            # Also check denial decoder limit (this form is specifically for denial letters)
            can_decode, decode_reason = usage.can_use_denial_decoder()
            if not can_decode:
                raise ValidationError(
                    _(
                        decode_reason
                        + " Please upgrade to Premium for unlimited denial decodes."
                    )
                )

        return file

    def _get_pdf_page_count(self, file):
        """
        Get page count from a PDF file.

        Returns:
            int or None: Page count, or None if unable to determine.
        """
        try:
            import PyPDF2

            file.seek(0)
            reader = PyPDF2.PdfReader(file)
            page_count = len(reader.pages)
            file.seek(0)
            return page_count
        except ImportError:
            logger.debug("PyPDF2 not available for page count validation")
            return None
        except Exception as e:
            logger.warning(f"Could not determine PDF page count: {e}")
            return None

    def clean(self):
        """
        Additional form-level validation including consent.
        """
        cleaned_data = super().clean()

        # Validate AI consent
        if not self.user_has_consent:
            ai_consent = cleaned_data.get("ai_consent")
            if not ai_consent:
                raise ValidationError(
                    {
                        "ai_consent": _(
                            "You must consent to AI processing to upload documents."
                        )
                    }
                )

        return cleaned_data

    def save_consent(self):
        """
        Save AI processing consent to user profile.
        Call this after form validation.
        """
        if self.user and not self.user_has_consent:
            from django.utils import timezone
            from accounts.models import UserProfile

            profile, _ = UserProfile.objects.get_or_create(user=self.user)
            profile.ai_processing_consent = True
            profile.ai_consent_date = timezone.now()
            profile.save()
