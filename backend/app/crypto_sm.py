"""国密算法封装，提供 SM3 哈希与 SM4 认证加密。"""

import base64
import hashlib
import hmac
import os
import secrets

from gmssl import sm4 as _sm4

SM3_NAME = "sm3"
PREFIX = "enc:sm4:v1:"
ENC_LABEL = b"modernmirror|sm4-enc"
MAC_LABEL = b"modernmirror|sm4-mac"
PASSWORD_ITER = 200_000


def sm3(data: bytes) -> bytes:
    return hashlib.new(SM3_NAME, data).digest()


def sm3_hex(data: bytes) -> str:
    return hashlib.new(SM3_NAME, data).hexdigest()


def _kdf(master: str, label: bytes, n: int) -> bytes:
    return hashlib.pbkdf2_hmac(SM3_NAME, master.encode(), label, 50_000, dklen=n)


def _keys(master: str):
    return _kdf(master, ENC_LABEL, 16), _kdf(master, MAC_LABEL, 32)


def encrypt(master: str, plaintext: str) -> str:
    enc_key, mac_key = _keys(master)
    iv = secrets.token_bytes(16)
    cipher = _sm4.CryptSM4()
    cipher.set_key(enc_key, _sm4.SM4_ENCRYPT)
    ct = cipher.crypt_cbc(iv, plaintext.encode())
    mac = hmac.new(mac_key, iv + ct, hashlib.new(SM3_NAME).name).digest()
    return PREFIX + base64.b64encode(iv + ct + mac).decode()


def decrypt(master: str, token: str) -> str:
    raw = base64.b64decode(token[len(PREFIX):])
    iv, ct, mac = raw[:16], raw[16:-32], raw[-32:]
    enc_key, mac_key = _keys(master)
    expected = hmac.new(mac_key, iv + ct, hashlib.new(SM3_NAME).name).digest()
    if not hmac.compare_digest(expected, mac):
        raise ValueError("SM4 ciphertext authentication failed")
    cipher = _sm4.CryptSM4()
    cipher.set_key(enc_key, _sm4.SM4_DECRYPT)
    return cipher.crypt_cbc(iv, ct).decode()


def hash_password(password: str, salt: str = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(SM3_NAME, password.encode(), salt.encode(), PASSWORD_ITER)
    return f"sm3${PASSWORD_ITER}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if not stored.startswith("sm3$"):
        return False
    try:
        _, iterations, salt, expected = stored.split("$", 3)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac(SM3_NAME, password.encode(), salt.encode(), int(iterations))
    return hmac.compare_digest(dk.hex(), expected)


def token_hash(token: str) -> str:
    return sm3_hex(token.encode())


def is_password_hash(stored: str) -> bool:
    return bool(stored) and stored.startswith("sm3$")
