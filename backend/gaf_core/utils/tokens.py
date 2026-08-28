"""Shared token utility functions.

Extracted from ``agents/models.py`` so that cross-app callers (accounts,
protocol, agents) depend on ``core`` rather than the agents app. This breaks
the reverse dependency ``agents -> accounts`` (accounts imported from agents
merely to reach these helpers) and centralizes auth-adjacent utilities.
"""

import hashlib


def hash_token(token: str) -> str:
    """Hash an Agent token using SHA-256 and return the hex digest.

    C4 fix: tokens are stored as hashes (not plaintext) so that DB leaks
    do not immediately expose usable credentials. The plaintext token is
    returned to the caller only at creation/rotation time.
    """
    if not token:
        return ''
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def make_token_preview(token: str) -> str:
    """Build a non-reversible preview of a token for list views.

    Format: first 4 chars + '...' + last 4 chars. Empty string for empty
    tokens. The preview is stored at creation time so list views do not
    need to read the (now-hashed) token field.
    """
    if not token:
        return ''
    if len(token) > 8:
        return f"{token[:4]}...{token[-4:]}"
    return token[:4] + '...'
