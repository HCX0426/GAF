"""
AES-256-GCM 游戏账户密码加密/解密工具模块

使用 Django SECRET_KEY 通过 PBKDF2 派生 256-bit 密钥，
每个密码独立生成 12 字节随机 nonce（IV），
存储格式: base64(nonce):base64(ciphertext+tag)
"""

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

SALT = b"gaf_v2_game_account_encryption_salt"
PBKDF2_ITERATIONS = 100000
NONCE_SIZE = 12


class DecryptionError(Exception):
    """解密异常"""

    pass


def _derive_key() -> bytes:
    """从 Django SECRET_KEY 通过 PBKDF2 派生 256-bit AES 密钥"""
    secret = settings.SECRET_KEY.encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", secret, SALT, PBKDF2_ITERATIONS, dklen=32)


def encrypt_password(plaintext: str) -> str:
    """
    使用 AES-256-GCM 加密明文密码

    Args:
        plaintext: 明文密码字符串

    Returns:
        "base64(nonce):base64(ciphertext+tag)" 格式的加密文本
    """
    key = _derive_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_SIZE)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce).decode("ascii") + ":" + base64.b64encode(ciphertext).decode("ascii")


def decrypt_password(encrypted: str) -> str:
    """
    解密 AES-256-GCM 加密的密码

    Args:
        encrypted: "base64(nonce):base64(ciphertext+tag)" 格式

    Returns:
        明文密码字符串

    Raises:
        DecryptionError: 解密失败时抛出
    """
    if not encrypted or ":" not in encrypted:
        raise DecryptionError("加密文本格式无效")

    key = _derive_key()
    aesgcm = AESGCM(key)

    try:
        nonce_b64, cipher_b64 = encrypted.split(":", 1)
        nonce = base64.b64decode(nonce_b64)
        ciphertext = base64.b64decode(cipher_b64)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    except Exception as e:
        raise DecryptionError(f"解密失败: {e}") from e
