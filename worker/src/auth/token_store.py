"""Agent Token local encrypted storage using Fernet symmetric encryption.

TD-036/TD-038 security hardening:
- Key is generated via ``Fernet.generate_key()`` (cryptographically secure
  random). The previous ``_derive_key_from_machine`` computed a
  COMPUTERNAME-based seed but never used it — that dead code was removed
  because it gave a false impression of weak entropy.
- The ``.key`` file is created with restrictive ACL (current user only on
  Windows via ``icacls``; ``chmod 600`` on POSIX) so same-machine other
  users cannot read it.
- ``rotate_key()`` re-encrypts all stored tokens with a fresh key.
"""

import json
import logging
import os
import stat
import subprocess
import sys
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

DEFAULT_KEY_DIR = Path(os.environ.get('APPDATA', str(Path.home() / '.gaf'))) / 'gaf'
DEFAULT_TOKEN_FILE = 'tokens.json.enc'
KEY_FILE = '.key'


def _restrict_file_permissions(path: Path) -> None:
    """Set restrictive ACL on ``path`` so only the current user can access it.

    - Windows: use ``icacls`` to grant full control to the current user only
      and remove inherited ACEs.
    - POSIX: ``chmod 600``.

    TD-038: previously the .key file was created with default permissions,
    allowing same-machine other users to read it.
    """
    try:
        if sys.platform == 'win32':
            user = os.environ.get('USERNAME') or os.environ.get('USER') or ''
            if not user:
                logger.warning("无法确定当前用户名，跳过 .key ACL 限制")
                return
            # Disable inheritance and grant full control to current user only.
            subprocess.run(
                [
                    'icacls', str(path),
                    '/inheritance:r',
                    '/grant:r', f'{user}:F',
                ],
                check=True,
                capture_output=True,
                timeout=10,
            )
            logger.debug(".key ACL 已限制为当前用户: %s", user)
        else:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            logger.debug(".key 权限已设为 600")
    except Exception as exc:
        logger.warning("限制 .key 文件权限失败: %s", exc)


def _get_or_create_key(key_dir: Path | None = None) -> bytes:
    """Load the Fernet key from disk, or generate a new secure random key.

    The key is generated via ``Fernet.generate_key()`` which uses
    ``os.urandom`` (cryptographically secure). It is stored in
    ``APPDATA/gaf/.key`` (or ``~/.gaf/.key`` on non-Windows).

    TD-036: the previous implementation computed a COMPUTERNAME-based seed
    but discarded it — the actual key was always ``Fernet.generate_key()``.
    The dead seed code was removed to avoid misleading readers.

    TD-038: the .key file is created with restrictive ACL (current user
    only).

    Args:
        key_dir: Directory for the .key file. Defaults to DEFAULT_KEY_DIR.

    Returns:
        bytes: Fernet-compatible 32-byte base64 key.
    """
    base_dir = key_dir or DEFAULT_KEY_DIR
    base_dir.mkdir(parents=True, exist_ok=True)
    key_path = base_dir / KEY_FILE

    if key_path.exists():
        return key_path.read_bytes()

    key = Fernet.generate_key()
    key_path.write_bytes(key)
    _restrict_file_permissions(key_path)
    logger.info("已生成新加密密钥 (Fernet.generate_key): %s", key_path)
    return key


class TokenStore:
    """Agent Token encrypted storage manager using Fernet symmetric encryption."""

    def __init__(self, storage_dir: Path | None = None):
        """Initialize TokenStore.

        Args:
            storage_dir: Token storage directory, defaults to APPDATA/gaf
                (Windows) or ~/.gaf.
        """
        self._storage_dir = storage_dir or DEFAULT_KEY_DIR
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._token_file = self._storage_dir / DEFAULT_TOKEN_FILE
        self._key_path = self._storage_dir / KEY_FILE
        self._cipher = Fernet(_get_or_create_key(self._storage_dir))

    def save_token(self, url: str, token: str) -> None:
        """Encrypt and save a Token to the local file.

        Args:
            url: Server WebSocket address, used as storage key.
            token: Agent authentication token.
        """
        tokens = self._load_all()
        tokens[url] = token
        self._save_all(tokens)
        logger.info("Token 已加密保存: url=%s", url)

    def load_token(self, url: str) -> str | None:
        """Read and decrypt the Token for the given URL.

        Args:
            url: Server WebSocket address.

        Returns:
            str | None: Decrypted token string, or None if not found.
        """
        tokens = self._load_all()
        return tokens.get(url)

    def remove_token(self, url: str) -> None:
        """Delete the Token for the given URL.

        Args:
            url: Server WebSocket address.
        """
        tokens = self._load_all()
        if url in tokens:
            del tokens[url]
            self._save_all(tokens)
            logger.info("Token 已删除: url=%s", url)

    def rotate_key(self) -> None:
        """Generate a new Fernet key and re-encrypt all stored tokens.

        TD-038: previously there was no key rotation mechanism. Long-lived
        keys accumulate exposure risk. This method:
        1. Loads all tokens with the current key.
        2. Generates a new key and writes it to .key (with ACL).
        3. Re-encrypts all tokens with the new key.

        If the token file does not exist or is empty, only the key is
        rotated (no tokens to re-encrypt).
        """
        tokens = self._load_all()
        new_key = Fernet.generate_key()
        self._key_path.write_bytes(new_key)
        _restrict_file_permissions(self._key_path)
        self._cipher = Fernet(new_key)
        if tokens:
            self._save_all(tokens)
        logger.info("密钥已轮换，%d 个 Token 已重新加密", len(tokens))

    def _load_all(self) -> dict:
        """Load and decrypt the local Token file.

        Returns:
            dict: URL-to-Token mapping.
        """
        if not self._token_file.exists():
            return {}
        try:
            encrypted_data = self._token_file.read_bytes()
            decrypted_data = self._cipher.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode('utf-8'))
        except Exception as exc:
            logger.warning("Token 文件解密失败: %s", exc)
            return {}

    def _save_all(self, tokens: dict) -> None:
        """Encrypt and save the Token dict to the local file.

        Args:
            tokens: URL-to-Token mapping.
        """
        raw_data = json.dumps(tokens, ensure_ascii=False).encode('utf-8')
        encrypted_data = self._cipher.encrypt(raw_data)
        self._token_file.write_bytes(encrypted_data)
