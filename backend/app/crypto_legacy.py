"""兼容旧版数据，保留旧加密与哈希算法的读取能力。"""

import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet

PREFIX = "enc:v1:"
PASSWORD_ITER = 200_000


def _fernet(master: str):
    key = base64.urlsafe_b64encode(hashlib.sha256(master.encode()).digest())
    return Fernet(key)


def encrypt(master: str, plaintext: str) -> str:
    return PREFIX + _fernet(master).encrypt(plaintext.encode()).decode()


def decrypt(master: str, token: str) -> str:
    return _fernet(master).decrypt(token[len(PREFIX):].encode()).decode()


def hash_password(password: str, salt: str = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PASSWORD_ITER)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PASSWORD_ITER)
    return hmac.compare_digest(dk.hex(), expected)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
