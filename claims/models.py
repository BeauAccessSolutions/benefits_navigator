"""
Claims app models - Document uploads and AI analysis for VA claims
"""

import uuid
from django.db import models
from django.conf import settings
from django.core.validators import FileExtensionValidator

from core.models import TimeStampedModel, SoftDeleteModel
from core.encryption import EncryptedJSONField


def document_upload_path(instance, filename):
    """Generate unique file path for uploaded documents"""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return f"documents/user_{instance.user.id}/{filename}"


class Document(TimeStampedModel, SoftDeleteModel):
    """
    Uploaded documents for claims analysis
    Stores file info, OCR results, and AI analysis
    """

    STATUS_CHOICES = [
        ('uploading', 'Uploading'),
        ('processing', 'Processing'),
        ('analyzing', 'Analyzing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    DOCUMENT_TYPE_CHOICES = [
        ('medical_records', 'Medical Records'),
        ('service_records', 'Service Records / STRs'),
        ('decision_letter', 'VA Decision Letter'),
        ('buddy_statement', 'Buddy Statement'),
        ('lay_statement', 'Lay Statement'),
        ('nexus_letter', 'Medical Nexus/Opinion Letter'),
        ('employment_records', 'Employment Records'),
        ('personal_statement', 'Personal Statement'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    file = models.FileField(
        'Document file',
        upload_to=document_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png', 'tiff'])]
    )
    file_name = models.CharField('Original filename', max_length=255)
    file_size = models.IntegerField('File size (bytes)', default=0)
    mime_type = models.CharField('MIME type', max_length=100, blank=True)

    document_type = models.CharField(
        'Document type',
        max_length=50,
        choices=DOCUMENT_TYPE_CHOICES,
        default='other'
    )

    status = models.CharField(
        'Processing status',
        max_length=20,
        choices=STATUS_CHOICES,
        default='uploading'
    )

    # OCR Results
    # NOTE: ocr_text field removed for PHI protection (Ephemeral OCR Refactor PR 6)
    # Raw text is no longer persisted - only metadata is stored
    ocr_confidence = models.FloatField(
        'OCR confidence score',
        null=True,
        blank=True,
        help_text='Average confidence score from OCR (0-100)'
    )
    page_count = models.IntegerField('Number of pages', default=0)

    # OCR Metadata (for observability without storing PHI)
    OCR_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    ocr_length = models.IntegerField(
        'Extracted text length',
        default=0,
        help_text='Character count of extracted text (metadata only, no PHI)'
    )
    ocr_status = models.CharField(
        'OCR status',
        max_length=20,
        choices=OCR_STATUS_CHOICES,
        default='pending',
        help_text='Status of OCR extraction process'
    )

    # AI Analysis Results (encrypted at rest — may contain PII from documents)
    ai_summary = EncryptedJSONField(
        'AI analysis summary',
        null=True,
        blank=True,
        help_text='Structured analysis results from Claude (encrypted)'
    )
    ai_model_used = models.CharField('AI model', max_length=50, blank=True)
    ai_tokens_used = models.IntegerField('Tokens used', default=0)

    # Condition tags (for organizing documents by claimed condition)
    condition_tags = models.JSONField(
        'Condition tags',
        default=list,
        blank=True,
        help_text='List of condition names this document relates to'
    )

    # Processing metadata
    processed_at = models.DateTimeField('Processing completed at', null=True, blank=True)
    processing_duration = models.FloatField(
        'Processing duration (seconds)',
        null=True,
        blank=True
    )
    error_message = models.TextField('Error message', blank=True)

    class Meta:
        verbose_name = 'Document'
        verbose_name_plural = 'Documents'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'document_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.file_name} ({self.get_document_type_display()})"

    @property
    def file_size_mb(self):
        """Return file size in megabytes"""
        return round(self.file_size / (1024 * 1024), 2)

    @property
    def is_processing(self):
        """Check if document is currently being processed"""
        return self.status in ['uploading', 'processing', 'analyzing']

    @property
    def is_complete(self):
        """Check if processing is complete"""
        return self.status == 'completed'

    @property
    def has_failed(self):
        """Check if processing failed"""
        return self.status == 'failed'

    def mark_processing(self):
        """Mark document as processing"""
        self.status = 'processing'
        self.save(update_fields=['status'])

    def mark_analyzing(self):
        """Mark document as being analyzed by AI"""
        self.status = 'analyzing'
        self.save(update_fields=['status'])

    def mark_completed(self, ocr_confidence=None, page_count=None, duration=None, ocr_length=None):
        """
        Mark document processing as completed.

        Args:
            ocr_confidence: OCR confidence score (0-100)
            page_count: Number of pages in the document
            duration: Processing duration in seconds
            ocr_length: Character count of extracted text (metadata only, no PHI)
        """
        from django.utils import timezone

        self.status = 'completed'
        self.processed_at = timezone.now()
        self.ocr_status = 'completed'

        update_fields = ['status', 'processed_at', 'ocr_status']

        if ocr_length is not None:
            self.ocr_length = ocr_length
            update_fields.append('ocr_length')

        if ocr_confidence is not None:
            self.ocr_confidence = ocr_confidence
            update_fields.append('ocr_confidence')

        if page_count is not None:
            self.page_count = page_count
            update_fields.append('page_count')

        if duration is not None:
            self.processing_duration = duration
            update_fields.append('processing_duration')

        self.save(update_fields=update_fields)

    def mark_failed(self, error_message, ocr_failed=False):
        """
        Mark document processing as failed.

        Args:
            error_message: Description of the failure
            ocr_failed: If True, marks OCR status as failed (vs AI analysis failure)
        """
        from django.utils import timezone
        self.status = 'failed'
        self.error_message = error_message
        self.processed_at = timezone.now()
        update_fields = ['status', 'error_message', 'processed_at']

        if ocr_failed:
            self.ocr_status = 'failed'
            update_fields.append('ocr_status')

        self.save(update_fields=update_fields)

    def get_signed_download_url(self, expires_minutes: int = 30, request=None) -> str:
        """
        Generate a time-limited signed URL for downloading this document.

        Args:
            expires_minutes: How long the URL is valid (default 30 minutes)
            request: Django request object (for absolute URLs)

        Returns:
            Signed URL string
        """
        from core.signed_urls import get_signed_url_generator

        generator = get_signed_url_generator()
        return generator.generate_url(
            resource_type='document',
            resource_id=self.pk,
            user_id=self.user_id,
            action='download',
            expires_minutes=expires_minutes,
            request=request
        )

    def get_signed_view_url(self, expires_minutes: int = 30, request=None) -> str:
        """
        Generate a time-limited signed URL for viewing this document inline.

        Args:
            expires_minutes: How long the URL is valid (default 30 minutes)
            request: Django request object (for absolute URLs)

        Returns:
            Signed URL string
        """
        from core.signed_urls import get_signed_url_generator

        generator = get_signed_url_generator()
        return generator.generate_url(
            resource_type='document',
            resource_id=self.pk,
            user_id=self.user_id,
            action='view',
            expires_minutes=expires_minutes,
            request=request
        )


class Claim(TimeStampedModel, SoftDeleteModel):
    """
    Optional: Group multiple documents under a single claim
    Can be implemented in future iterations
    """

    CLAIM_TYPE_CHOICES = [
        ('initial', 'Initial Claim'),
        ('increase', 'Claim for Increase'),
        ('secondary', 'Secondary Condition'),
        ('new_condition', 'New Condition'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('gathering_evidence', 'Gathering Evidence'),
        ('submitted', 'Submitted to VA'),
        ('pending', 'Pending VA Decision'),
        ('decided', 'Decision Received'),
        ('appealed', 'Under Appeal'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='claims'
    )
    title = models.CharField(
        'Claim title',
        max_length=200,
        help_text='e.g., "PTSD Service Connection" or "Knee Injury Increase"'
    )
    description = models.TextField('Description', blank=True)
    claim_type = models.CharField(
        'Claim type',
        max_length=20,
        choices=CLAIM_TYPE_CHOICES,
        default='initial'
    )
    status = models.CharField(
        'Status',
        max_length=30,
        choices=STATUS_CHOICES,
        default='draft'
    )

    # Key dates
    submission_date = models.DateField('Date submitted to VA', null=True, blank=True)
    decision_date = models.DateField('Decision received date', null=True, blank=True)

    # Link to documents
    # documents = ForeignKey relationship from Document model

    notes = models.TextField('Internal notes', blank=True)

    class Meta:
        verbose_name = 'Claim'
        verbose_name_plural = 'Claims'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_claim_type_display()})"

    @property
    def document_count(self):
        """Count of documents associated with this claim"""
        return self.documents.count()

    @property
    def days_since_submission(self):
        """Calculate days since claim was submitted"""
        if self.submission_date:
            from datetime import date
            delta = date.today() - self.submission_date
            return delta.days
        return None


# Add optional foreign key to link documents to claims
# This allows documents to exist independently or be grouped into claims
Document.add_to_class(
    'claim',
    models.ForeignKey(
        Claim,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
        help_text='Optional: Associate this document with a claim'
    )
)
