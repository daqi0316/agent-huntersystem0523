"""API Key 加密工具 — AES-256-GCM (Fernet) + Key Salt。

复用 account_manager.py 的 Fernet 密钥派生逻辑，但增加 salt 支持密钥轮换。
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet

# 加密密钥：从环境变量获取，不存在则用开发固定密钥
_ENCRYPTION_KEY = os.environ.get("LLM_ENCRYPTION_KEY", "")


def _get_fernet(salt: str = "") -> Fernet:
    """获取 Fernet 实例。

    用 salt 派生不同的密钥，支持密钥轮换。
    """
    if _ENCRYPTION_KEY:
        material = _ENCRYPTION_KEY + salt
    else:
        # 开发环境：用固定密钥 + salt
        material = "dev-llm-encryption-key-v1" + salt
    derived = hashlib.sha256(material.encode()).digest()
    key = base64.urlsafe_b64encode(derived)
    return Fernet(key)


def encrypt_api_key(plain: str) -> str:
    """加密 API Key。

    返回: "salt:encrypted_base64" 格式
    """
    salt = os.urandom(8).hex()
    f = _get_fernet(salt)
    encrypted = f.encrypt(plain.encode()).decode()
    return f"{salt}:{encrypted}"


def decrypt_api_key(encrypted: str) -> str | None:
    """解密 API Key。

    支持两种格式:
      - "salt:encrypted_base64"（新格式，带 salt）
      - "encrypted_base64"（旧格式，纯加密）
    """
    if not encrypted:
        return None

    try:
        if ":" in encrypted:
            salt, token = encrypted.split(":", 1)
            f = _get_fernet(salt)
            return f.decrypt(token.encode()).decode()
        else:
            # 旧格式（无 salt）
            f = _get_fernet("")
            return f.decrypt(encrypted.encode()).decode()
    except Exception:
        return None


def mask_api_key(key: str | None) -> str | None:
    """脱敏显示 API Key。

    "sk-abc123def456" → "sk-abc****456"
    "abcdefghijklmn"  → "abcd****mn"
    None              → None
    """
    if not key:
        return None
    if len(key) <= 8:
        return key[:4] + "****"
    return key[:6] + "****" + key[-4:]
