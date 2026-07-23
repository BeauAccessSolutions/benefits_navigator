"""
Redis/Valkey TLS options helper.

Centralizes how the app resolves the ``ssl_cert_reqs`` policy for ``rediss://``
connections (Celery broker/result backend and the Django cache). ``rediss://``
already encrypts the transport; verifying the server certificate additionally
prevents a man-in-the-middle — the HIPAA Security Rule transmission-security
addressable spec, §164.312(e).

Kept as a plain, Django-free module so it can be imported at settings-eval time
and unit-tested without standing up Redis.
"""

import ssl

# Accepted REDIS_SSL_CERT_REQS values -> Python ssl constant.
CERT_REQS = {
    "none": ssl.CERT_NONE,  # encrypt only, do not verify the server cert
    "optional": ssl.CERT_OPTIONAL,
    "required": ssl.CERT_REQUIRED,  # encrypt AND verify (default)
}


def resolve_cert_reqs(value):
    """Map a REDIS_SSL_CERT_REQS string to an ssl.CERT_* constant.

    Unknown/empty values fall back to CERT_REQUIRED (secure by default).
    """
    return CERT_REQS.get((value or "required").strip().lower(), ssl.CERT_REQUIRED)


def redis_ssl_options(cert_reqs="required", ca_certs=None):
    """Build the SSL options dict for a rediss:// connection.

    Args:
        cert_reqs: REDIS_SSL_CERT_REQS string ("none"/"optional"/"required").
        ca_certs: optional path to a CA bundle (REDIS_SSL_CA_CERTS) — needed
            when the managed provider's cert chain isn't in the system trust
            store (e.g. a provider-specific CA).

    Returns:
        Dict suitable for Celery's ``broker_use_ssl`` and django-redis
        ``OPTIONS``.
    """
    options = {"ssl_cert_reqs": resolve_cert_reqs(cert_reqs)}
    if ca_certs:
        options["ssl_ca_certs"] = ca_certs
    return options
