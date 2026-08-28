"""Fernet symmetric encryption for sensitive fields (API keys, tokens).

Used by LLMConfig.api_key to avoid plaintext storage (TD-008).
The encryption key is read from the GAF_LLM_API_KEY_ENCRYPTION_KEY
Django setting / env var. If not set, a warning is logged and values
are stored as-is (backward compat for existing deployments).

Usage::

    from settings.crypto import encrypt_api_key, decrypt_api_key

    encrypted = encrypt_api_key("sk-abc123")
    plaintext  = decrypt_api_key(encrypted)  # -> "sk-abc123"
"""
import logging
import os

logger = logging.getLogger(__name__)

# Lazy-loaded Fernet instance
_fernet = None
_encryption_key_checked = False


def _get_fernet():
    """Return a Fernet instance, or None if encryption is not configured.

    The key is read from GAF_LLM_API_KEY_ENCRYPTION_KEY (Django setting
    or env var). Must be a URL-safe base64-encoded 32-byte key (use
    ``Fernet.generate_key()`` to create one). If not set, encryption
    is disabled and values are stored as plaintext (with a warning).
    """
    global _fernet, _encryption_key_checked

    if _fernet is not None:
        return _fernet

    if _encryption_key_checked:
        return None  # Already checked, not configured

    _encryption_key_checked = True

    key = None
    try:
        from django.conf import settings as django_settings
        key = getattr(django_settings, 'GAF_LLM_API_KEY_ENCRYPTION_KEY', None)
    except Exception:
        logger.warning("settings crypto: failed to read GAF_LLM_API_KEY_ENCRYPTION_KEY from Django settings", exc_info=True)

    if not key:
        key = os.environ.get('GAF_LLM_API_KEY_ENCRYPTION_KEY', '')

    if not key:
        logger.warning(
            "GAF_LLM_API_KEY_ENCRYPTION_KEY not set — LLM API keys "
            "will be stored in plaintext. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
        return None

    try:
        from cryptography.fernet import Fernet
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
        logger.info("LLM API key encryption enabled (Fernet)")
        return _fernet
    except Exception as exc:
        logger.error("Failed to initialize Fernet encryption: %s — falling back to plaintext", exc)
        return None


def encrypt_api_key(plaintext: str) -> str:
    """Encrypt an API key. Returns ciphertext string, or plaintext if
    encryption is not configured.

    If the input is empty or already encrypted (starts with 'gAAAAA'),
    it is returned as-is.
    """
    if not plaintext:
        return ''

    # Already encrypted (Fernet ciphertext starts with 'gAAAAA')
    if plaintext.startswith('gAAAAA'):
        return plaintext

    fernet = _get_fernet()
    if fernet is None:
        return plaintext  # Encryption not configured — store as-is

    try:
        return fernet.encrypt(plaintext.encode('utf-8')).decode('utf-8')
    except Exception as exc:
        logger.error("Failed to encrypt API key: %s — storing plaintext", exc)
        return plaintext


def decrypt_api_key(ciphertext: str) -> str:
    """Decrypt an API key. Returns plaintext string, or ciphertext if
    encryption is not configured or decryption fails.

    If the input doesn't look like Fernet ciphertext (no 'gAAAAA'
    prefix), it's treated as already-plaintext (backward compat with
    existing plaintext records).
    """
    if not ciphertext:
        return ''

    # Not encrypted (plaintext from before encryption was enabled)
    if not ciphertext.startswith('gAAAAA'):
        return ciphertext

    fernet = _get_fernet()
    if fernet is None:
        logger.warning("API key is encrypted but no encryption key is configured")
        return ''

    try:
        return fernet.decrypt(ciphertext.encode('utf-8')).decode('utf-8')
    except Exception as exc:
        logger.error("Failed to decrypt API key: %s", exc)
        return ''


def is_encryption_enabled() -> bool:
    """Return True if Fernet encryption is configured and active."""
    return _get_fernet() is not None
