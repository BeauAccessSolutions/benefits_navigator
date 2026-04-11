"""
Django settings for benefits_navigator project.
"""

import os
import ssl
from pathlib import Path
import environ

# Initialize environment variables
env = environ.Env(
    DEBUG=(bool, True),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1', '0.0.0.0']),
)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Read .env file if it exists
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# SECURITY WARNING: keep the secret key used in production secret!
# SECRET_KEY MUST be set via environment variable in ALL non-local environments
import warnings

SECRET_KEY = env('SECRET_KEY', default='')

# Only allow empty/insecure SECRET_KEY in local DEBUG mode
if not SECRET_KEY or SECRET_KEY.startswith('django-insecure'):
    if env.bool('DEBUG', default=False) and not env.bool('STAGING', default=False):
        # Local development only - generate a random key for this session
        import secrets
        SECRET_KEY = secrets.token_urlsafe(50)
        warnings.warn(
            "SECRET_KEY not set - using random key for this session. "
            "Set SECRET_KEY in .env for persistent sessions."
        )
    else:
        # Staging and production MUST have SECRET_KEY set
        raise ValueError(
            "SECRET_KEY environment variable is required in staging/production! "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(50))\""
        )

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

# Field-level encryption key for PII (VA file numbers, DOB, etc.)
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# MUST be set in staging/production - no fallback allowed for defense in depth
FIELD_ENCRYPTION_KEY = env('FIELD_ENCRYPTION_KEY', default=None)

# Require dedicated encryption key in non-local environments
if not FIELD_ENCRYPTION_KEY:
    if env.bool('DEBUG', default=False) and not env.bool('STAGING', default=False):
        # Local development only - derive from SECRET_KEY (acceptable for dev)
        import hashlib
        import base64
        FIELD_ENCRYPTION_KEY = base64.urlsafe_b64encode(
            hashlib.sha256(SECRET_KEY.encode()).digest()
        ).decode()
        warnings.warn(
            "FIELD_ENCRYPTION_KEY not set - deriving from SECRET_KEY for local dev. "
            "Set FIELD_ENCRYPTION_KEY in production for defense in depth."
        )
    else:
        # Staging and production MUST have dedicated encryption key
        raise ValueError(
            "FIELD_ENCRYPTION_KEY environment variable is required in staging/production! "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

# ALLOWED_HOSTS - MUST be explicitly set in staging/production
# Never use '*' in any deployed environment
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

# Validate ALLOWED_HOSTS in non-debug mode
if not env.bool('DEBUG', default=False):
    if not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS:
        raise ValueError(
            "ALLOWED_HOSTS must be explicitly set in staging/production! "
            "Example: ALLOWED_HOSTS=myapp.ondigitalocean.app,myapp.com"
        )

# Application definition
INSTALLED_APPS = [
    # Django apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.sitemaps',

    # Third-party apps
    'django_htmx',
    'widget_tweaks',
    'crispy_forms',
    'crispy_tailwind',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',
    'allauth_2fa',
    'django_celery_beat',
    'django_extensions',
    'viewflow',  # Workflow engine for appeals
    'strawberry.django',  # GraphQL API
    'rest_framework',  # Django REST Framework
    'rest_framework_simplejwt',  # JWT authentication
    'rest_framework_simplejwt.token_blacklist',  # Token blacklist for logout
    'corsheaders',  # CORS support for mobile apps

    # Our apps
    'core.apps.CoreConfig',
    'accounts.apps.AccountsConfig',
    'claims.apps.ClaimsConfig',
    'appeals.apps.AppealsConfig',
    'examprep.apps.ExamprepConfig',
    'agents.apps.AgentsConfig',
    'documentation.apps.DocumentationConfig',
    'vso.apps.VsoConfig',
]

MIDDLEWARE = [
    'core.middleware.HealthCheckMiddleware',  # Health check - must be before CommonMiddleware for DO health checks
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Static files
    'corsheaders.middleware.CorsMiddleware',  # CORS - must be before CommonMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_otp.middleware.OTPMiddleware',  # MFA/2FA support
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',  # HTMX support
    'allauth.account.middleware.AccountMiddleware',  # Django-allauth
    'allauth_2fa.middleware.AllauthTwoFactorMiddleware',  # Allauth 2FA
    'vso.middleware.VSOStaffMFAMiddleware',  # MFA encouragement for VSO staff
    'core.middleware.AuditMiddleware',  # Audit logging for sensitive operations
    'core.middleware.SecurityHeadersMiddleware',  # Additional security headers
    'csp.middleware.CSPMiddleware',  # Content Security Policy
]

ROOT_URLCONF = 'benefits_navigator.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.site_settings',  # Site settings
                'core.context_processors.user_usage',  # User usage tracking
                'core.context_processors.tier_limits',  # Tier limit settings
                'core.context_processors.feature_flags',  # Feature flags for dual-path
                'core.context_processors.vso_access',  # VSO staff access
                'core.context_processors.pilot_mode',  # Pilot mode settings
            ],
        },
    },
]

WSGI_APPLICATION = 'benefits_navigator.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
# Handle empty DATABASE_URL (env.db() doesn't handle empty strings well)
_database_url = env('DATABASE_URL', default='')
if _database_url:
    DATABASES = {'default': env.db('DATABASE_URL')}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Password hashers - Argon2 for better security
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files (User uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ==============================================================================
# CELERY CONFIGURATION
# ==============================================================================
# Use REDIS_URL as fallback for Celery settings
# Handle empty strings from DO Console secrets
_redis_url = env('REDIS_URL', default='') or 'redis://localhost:6379/0'
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='') or _redis_url
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', default='') or _redis_url
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True  # Retry broker connection on startup (Celery 6.0+ default)
CELERY_RESULT_EXPIRES = 3600  # Task results expire after 1 hour (frees Redis memory)

# SSL configuration for Celery when using rediss:// (SSL) connections
# Use CERT_NONE for cloud Redis providers (Upstash, etc.) that may not have verifiable certs
if CELERY_BROKER_URL.startswith('rediss://'):
    CELERY_BROKER_USE_SSL = {
        'ssl_cert_reqs': ssl.CERT_NONE,
    }
    CELERY_REDIS_BACKEND_USE_SSL = {
        'ssl_cert_reqs': ssl.CERT_NONE,
    }

# Celery Beat Schedule for periodic tasks
# DEPLOYMENT NOTE: Beat scheduler runs on the "worker" process in DigitalOcean App Platform
# (the single Procfile worker dyno). Only ONE instance must run Beat at a time —
# if you scale the worker to multiple instances, pin Beat to exactly one using
# CELERY_BEAT_MAX_LOOP_INTERVAL or a dedicated beat dyno. Duplicate Beat instances
# will double-fire all periodic tasks (duplicate emails, double data retention runs).
from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    # Health monitoring
    'record-health-metrics': {
        'task': 'core.tasks.record_health_metrics',
        'schedule': 300,  # every 5 minutes
    },
    'check-processing-health': {
        'task': 'core.tasks.check_processing_health',
        'schedule': 900,  # every 15 minutes
    },
    'cleanup-old-health-metrics': {
        'task': 'core.tasks.cleanup_old_health_metrics',
        'schedule': crontab(hour=3, minute=0),  # daily at 3 AM
    },
    # Email reminders
    'send-daily-reminders': {
        'task': 'core.tasks.send_all_reminders',
        'schedule': crontab(hour=9, minute=0),  # daily at 9 AM
    },
    # Document cleanup
    'cleanup-old-documents': {
        'task': 'claims.tasks.cleanup_old_documents',
        'schedule': crontab(hour=2, minute=0),  # daily at 2 AM
    },
    # Pilot data retention
    'enforce-pilot-data-retention': {
        'task': 'core.tasks.enforce_pilot_data_retention',
        'schedule': crontab(hour=3, minute=30),  # 3:30 AM daily (after cleanup-old-health-metrics)
    },
    'notify-pilot-users-before-retention': {
        'task': 'core.tasks.notify_pilot_users_before_retention',
        'schedule': crontab(hour=1, minute=0),  # 1 AM daily (before enforcement)
    },
    # Monitoring and alerting
    'run-monitoring-checks': {
        'task': 'core.tasks.run_monitoring_checks',
        'schedule': 300,  # every 5 minutes
    },
    'check-download-anomalies': {
        'task': 'core.tasks.check_download_anomalies_task',
        'schedule': crontab(minute=0),  # hourly (every hour at :00)
    },
}

# ==============================================================================
# REDIS CONFIGURATION
# ==============================================================================
REDIS_URL = env('REDIS_URL', default='') or 'redis://localhost:6379/0'

# Use local memory cache in development/testing when Redis isn't available
# Set USE_REDIS_CACHE=false to force local memory cache
USE_REDIS_CACHE = env.bool('USE_REDIS_CACHE', default=not DEBUG)

if USE_REDIS_CACHE:
    # Configure Redis cache with SSL support for rediss:// connections
    # Use CERT_NONE for cloud Redis providers (Upstash, etc.)
    _redis_cache_options = {}
    if REDIS_URL.startswith('rediss://'):
        _redis_cache_options = {
            'ssl_cert_reqs': ssl.CERT_NONE,
        }

    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': _redis_cache_options,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }

# ==============================================================================
# SESSION CONFIGURATION
# ==============================================================================
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 1209600  # 2 weeks
SESSION_COOKIE_SECURE = not DEBUG  # True in production
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# ==============================================================================
# CSRF CONFIGURATION
# ==============================================================================
CSRF_COOKIE_SECURE = not DEBUG  # True in production
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# ==============================================================================
# SECURITY SETTINGS
# ==============================================================================
# Always enabled
SECURE_CONTENT_TYPE_NOSNIFF = True  # Prevent MIME type sniffing
SECURE_BROWSER_XSS_FILTER = True  # Enable XSS filter
X_FRAME_OPTIONS = 'DENY'  # Prevent clickjacking
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Content Security Policy
# Restricts what resources can be loaded
CSP_DEFAULT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "https://unpkg.com")
CSP_IMG_SRC = ("'self'", "data:", "https:")
CSP_FONT_SRC = ("'self'", "https://fonts.gstatic.com")
CSP_CONNECT_SRC = ("'self'",)
CSP_FRAME_ANCESTORS = ("'none'",)
CSP_FORM_ACTION = ("'self'",)

# Production-only settings (skip SSL redirect in staging - DO handles SSL at edge)
if not DEBUG:
    # Only enable SSL redirect in production, not staging
    # DO App Platform handles SSL termination and uses HTTP for internal health checks
    STAGING = env.bool('STAGING', default=False)
    SECURE_SSL_REDIRECT = not STAGING
    SECURE_HSTS_SECONDS = 31536000 if not STAGING else 0  # 1 year in prod
    SECURE_HSTS_INCLUDE_SUBDOMAINS = not STAGING
    SECURE_HSTS_PRELOAD = not STAGING
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # CSP is already strict at module level (no unsafe-inline, no CDN).
    # Production inherits the base CSP_* settings above without override.

# ==============================================================================
# DJANGO-ALLAUTH CONFIGURATION
# ==============================================================================
SITE_ID = 1
# New allauth 65.x settings (replacing deprecated settings)
ACCOUNT_LOGIN_METHODS = {'email'}  # Email-only authentication
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']  # Required fields
# Email verification: 'mandatory' in production, 'optional' in development
ACCOUNT_EMAIL_VERIFICATION = 'optional' if DEBUG else 'mandatory'
ACCOUNT_LOGIN_ON_PASSWORD_RESET = True
ACCOUNT_LOGOUT_REDIRECT_URL = '/'
LOGIN_REDIRECT_URL = '/dashboard/'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Use allauth-2fa adapter for MFA support
ACCOUNT_ADAPTER = 'allauth_2fa.adapter.OTPAdapter'

# ==============================================================================
# TWO-FACTOR AUTHENTICATION (MFA) CONFIGURATION
# ==============================================================================
# MFA is encouraged for VSO staff (caseworkers and admins)
# Users can set up TOTP authenticator apps (Google Authenticator, Authy, etc.)
ALLAUTH_2FA_ALWAYS_REVEAL_BACKUP_TOKENS = False

# ==============================================================================
# EMAIL CONFIGURATION
# ==============================================================================
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_FILE_PATH = env('EMAIL_FILE_PATH', default=str(BASE_DIR / 'sent_emails'))
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@benefitsnavigator.com')

# ==============================================================================
# CRISPY FORMS CONFIGURATION (Tailwind CSS)
# ==============================================================================
CRISPY_ALLOWED_TEMPLATE_PACKS = 'tailwind'
CRISPY_TEMPLATE_PACK = 'tailwind'

# ==============================================================================
# OPENAI CONFIGURATION
# ==============================================================================
OPENAI_API_KEY = env('OPENAI_API_KEY', default='')
OPENAI_MODEL = env('OPENAI_MODEL', default='gpt-3.5-turbo')
OPENAI_MAX_TOKENS = env.int('OPENAI_MAX_TOKENS', default=4000)

# AI Gateway settings (timeout, retry, backoff)
OPENAI_TIMEOUT_SECONDS = env.int('OPENAI_TIMEOUT_SECONDS', default=60)
OPENAI_MAX_RETRIES = env.int('OPENAI_MAX_RETRIES', default=3)
OPENAI_RETRY_BASE_DELAY = env.float('OPENAI_RETRY_BASE_DELAY', default=1.0)
OPENAI_RETRY_MAX_DELAY = env.float('OPENAI_RETRY_MAX_DELAY', default=60.0)

# ==============================================================================
# STRIPE CONFIGURATION
# ==============================================================================
STRIPE_PUBLISHABLE_KEY = env('STRIPE_PUBLISHABLE_KEY', default='')
STRIPE_SECRET_KEY = env('STRIPE_SECRET_KEY', default='')
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET', default='')
STRIPE_PRICE_ID = env('STRIPE_PRICE_ID', default='')

# ==============================================================================
# AWS S3 CONFIGURATION (for production file storage)
# ==============================================================================
USE_S3 = env.bool('USE_S3', default=False)

if USE_S3:
    AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', default='us-east-1')
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
    AWS_DEFAULT_ACL = 'private'
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}

    # S3 static files settings
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/static/'

    # S3 media files settings
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'

# ==============================================================================
# FILE UPLOAD SETTINGS
# ==============================================================================
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50 MB
ALLOWED_DOCUMENT_TYPES = [
    'application/pdf',
    'image/jpeg',
    'image/png',
    'image/tiff',
]
MAX_DOCUMENT_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_DOCUMENT_PAGES = 100

# ==============================================================================
# PROTECTED MEDIA SETTINGS
# ==============================================================================
# Media files are served through Django views that verify authentication
# and ownership. Do NOT serve media files directly via web server.
#
# In production with nginx, enable X-Accel-Redirect for performance:
#   USE_X_SENDFILE = True
#   SENDFILE_ROOT = '/protected-media'
#
# Then configure nginx:
#   location /protected-media/ {
#       internal;
#       alias /path/to/media/;
#   }
USE_X_SENDFILE = env.bool('USE_X_SENDFILE', default=False)
SENDFILE_ROOT = env('SENDFILE_ROOT', default='')

# ==============================================================================
# LOGGING CONFIGURATION
# ==============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Create logs directory if it doesn't exist
(BASE_DIR / 'logs').mkdir(exist_ok=True)

# ==============================================================================
# SENTRY CONFIGURATION (Error Tracking)
# ==============================================================================
SENTRY_DSN = env('SENTRY_DSN', default='')
if SENTRY_DSN and not DEBUG:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
        ],
        traces_sample_rate=0.1,
        send_default_pii=False,  # Don't send user data
    )

# ==============================================================================
# RATE LIMITING
# ==============================================================================
# Disabled in DEBUG mode by default. Can be explicitly controlled via env var
# for testing scenarios (e.g., running browser tests against a live server)
RATELIMIT_ENABLE = env.bool('RATELIMIT_ENABLE', default=not DEBUG)
RATELIMIT_USE_CACHE = 'default'

# ==============================================================================
# FEATURE FLAGS
# ==============================================================================
# Controls progressive rollout of features for dual-path development
# Path A = Direct-to-Veteran (B2C), Path B = VSO Platform (B2B)

FEATURES = {
    # Path A - Direct-to-Veteran (stable, enabled)
    'freemium_limits': True,
    'stripe_individual': True,
    'usage_tracking': True,

    # Path B - VSO Platform (progressive rollout)
    'organizations': env.bool('FEATURE_ORGANIZATIONS', default=False),
    'org_roles': env.bool('FEATURE_ORG_ROLES', default=False),
    'org_invitations': env.bool('FEATURE_ORG_INVITATIONS', default=False),
    'caseworker_assignment': env.bool('FEATURE_CASEWORKER_ASSIGNMENT', default=False),
    'org_billing': env.bool('FEATURE_ORG_BILLING', default=False),
    'org_admin_dashboard': env.bool('FEATURE_ORG_ADMIN', default=False),
    'audit_export': env.bool('FEATURE_AUDIT_EXPORT', default=False),

    # Shared Features
    'doc_search': env.bool('FEATURE_DOC_SEARCH', default=True),  # Documentation search system

    # Future
    'sso_saml': env.bool('FEATURE_SSO_SAML', default=False),
    'mfa': env.bool('FEATURE_MFA', default=False),
}

# ==============================================================================
# PILOT MODE SETTINGS
# ==============================================================================
# Controls pilot/beta testing environment behavior
# Enable these flags to run pilots without real billing

# Master switch for pilot mode - enables pilot-specific behavior
PILOT_MODE = env.bool('PILOT_MODE', default=False)

# When True, blocks all real Stripe checkout sessions
# Users see a message that billing is disabled during pilot
PILOT_BILLING_DISABLED = env.bool('PILOT_BILLING_DISABLED', default=PILOT_MODE)

# When True, all authenticated users get premium access automatically
# Useful for pilot testing where you want testers to access all features
PILOT_PREMIUM_ACCESS = env.bool('PILOT_PREMIUM_ACCESS', default=False)

# List of email domains that automatically get pilot premium access
# Example: ['company.com', 'partner.org'] - users with these email domains get premium
PILOT_PREMIUM_DOMAINS = env.list('PILOT_PREMIUM_DOMAINS', default=[])

# List of specific emails that get pilot premium access
# Example: ['tester1@gmail.com', 'tester2@yahoo.com']
PILOT_PREMIUM_EMAILS = env.list('PILOT_PREMIUM_EMAILS', default=[])

# Data retention period for pilot users (days)
# After this period, pilot user data is soft-deleted
# Set to 0 to disable pilot-specific retention (use standard policies instead)
PILOT_DATA_RETENTION_DAYS = env.int('PILOT_DATA_RETENTION_DAYS', default=30)


def feature_enabled(feature_name: str) -> bool:
    """Check if a feature flag is enabled."""
    return FEATURES.get(feature_name, False)


# ==============================================================================
# APPLICATION-SPECIFIC SETTINGS
# ==============================================================================

# Free tier limits
FREE_TIER_DOCUMENTS_PER_MONTH = 3
FREE_TIER_MAX_STORAGE_MB = 100
FREE_TIER_DENIAL_DECODES_PER_MONTH = 2
FREE_TIER_AI_ANALYSES_PER_MONTH = 5

# Premium tier features
PREMIUM_UNLIMITED_DOCUMENTS = True
PREMIUM_UNLIMITED_DENIAL_DECODES = True
PREMIUM_UNLIMITED_AI_ANALYSES = True
PREMIUM_GPT4_ACCESS = False  # Enable for premium users later
PREMIUM_PRIORITY_SUPPORT = True
PREMIUM_SAVED_CALCULATIONS = True  # Save rating calculations
PREMIUM_EXPORT_DATA = True  # Export data to PDF/CSV

# OCR Settings
OCR_ENGINE = env('OCR_ENGINE', default='tesseract')  # 'tesseract' or 'textract'
TESSERACT_CMD = env('TESSERACT_CMD', default='/usr/bin/tesseract')

# Site settings
SITE_NAME = 'VA Benefits Navigator'
SITE_DESCRIPTION = 'AI-powered assistance for VA disability claims and appeals'
SUPPORT_EMAIL = 'support@benefitsnavigator.com'
SITE_URL = env('SITE_URL', default='http://localhost:8000')

# ==============================================================================
# REST FRAMEWORK & JWT AUTHENTICATION
# ==============================================================================
from datetime import timedelta

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',  # Keep for browsable API
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/hour',
        'user': '1000/hour',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
}

# ==============================================================================
# CORS CONFIGURATION
# ==============================================================================
# Allow mobile apps and development environments to access the API

# In production, set CORS_ALLOWED_ORIGINS to your mobile app domains
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[
    'http://localhost:3000',  # React Native / Expo dev
    'http://localhost:8081',  # Expo dev
    'http://127.0.0.1:3000',
    'http://127.0.0.1:8081',
])

# Allow credentials (cookies, authorization headers)
CORS_ALLOW_CREDENTIALS = True

# Allow all headers needed for JWT auth
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# Expose headers to the client
CORS_EXPOSE_HEADERS = [
    'content-disposition',
    'x-request-id',
]

# In DEBUG mode, allow all origins for easier development
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
