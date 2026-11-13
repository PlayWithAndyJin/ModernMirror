"""加密统一入口，新数据使用国密算法，旧数据保持可读。"""

import hashlib
import hmac
import secrets

from . import config
from . import crypto_legacy as legacy
from . import crypto_sm as sm

SM_PREFIX = sm.PREFIX
LEGACY_PREFIX = legacy.PREFIX


def enabled() -> bool:
    return bool(config.DB_MASTER_KEY)


def encrypt_text(plaintext: str) -> str:
    if not enabled():
        return plaintext
    return sm.encrypt(config.DB_MASTER_KEY, plaintext)


def decrypt_text(stored: str) -> str:
    if not stored:
        return stored
    if not enabled():
        return stored
    if stored.startswith(SM_PREFIX):
        return sm.decrypt(config.DB_MASTER_KEY, stored)
    if stored.startswith(LEGACY_PREFIX):
        return legacy.decrypt(config.DB_MASTER_KEY, stored)
    return stored


def is_legacy_cipher(stored: str) -> bool:
    return bool(stored) and stored.startswith(LEGACY_PREFIX)


def is_sm_cipher(stored: str) -> bool:
    return bool(stored) and stored.startswith(SM_PREFIX)


def hash_password(password: str) -> str:
    return sm.hash_password(password)


def hash_password_legacy(password: str) -> str:
    return legacy.hash_password(password)


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("sm3$"):
        return sm.verify_password(password, stored)
    return legacy.verify_password(password, stored)


def password_needs_upgrade(stored: str) -> bool:
    return bool(stored) and not stored.startswith("sm3$")


def token_hash(token: str) -> str:
    return sm.token_hash(token)


def token_hash_legacy(token: str) -> str:
    return legacy.token_hash(token)


def master_fingerprint() -> str:
    if not enabled():
        return ""
    return sm.sm3_hex(config.DB_MASTER_KEY.encode())[:8]


def gen_password(n: int = 14) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(n))
