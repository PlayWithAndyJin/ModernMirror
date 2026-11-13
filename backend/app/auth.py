import base64
import hmac
import hashlib
import os
import secrets
import struct

from fastapi import HTTPException, Request

from . import config, crypto
from .db import get_db

SESSION_HOURS = int(os.getenv("MODERNMIRROR_SESSION_HOURS", "24"))
WEB_SESSION_MINUTES = int(os.getenv("MODERNMIRROR_WEB_SESSION_MINUTES", "30"))


def encrypt_mfa_secret(secret: str):
    return crypto.encrypt_text(secret)


def decrypt_mfa_secret(stored: str):
    return crypto.decrypt_text(stored)


def master_key_fingerprint():
    return crypto.master_fingerprint()


def hash_password(password: str, salt: str = None):
    return crypto.hash_password(password)


def verify_password(password: str, stored: str):
    return crypto.verify_password(password, stored)


def password_needs_upgrade(stored: str):
    return crypto.password_needs_upgrade(stored)


def get_user(username: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if row is None:
        return None
    user = dict(row)
    user["enabled"] = bool(user.get("enabled", 1))
    return user


def get_setting(key, default=""):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_db()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    conn.commit()


def _session_hash(token: str):
    return crypto.token_hash(token)


def create_session(username: str, mfa_state: int, ttl_hours: int = None):
    ttl = ttl_hours if ttl_hours is not None else SESSION_HOURS
    token = secrets.token_urlsafe(32)
    conn = get_db()
    conn.execute(
        "INSERT INTO sessions (token, username, expires, mfa_state) "
        "VALUES (?,?,datetime('now', 'localtime', ?),?)",
        (_session_hash(token), username, f"+{ttl} minutes", mfa_state),
    )
    conn.commit()
    return token


def create_login_nonce(username: str):
    token = secrets.token_urlsafe(24)
    conn = get_db()
    conn.execute(
        "INSERT INTO sessions (token, username, expires, mfa_state) "
        "VALUES (?,?,datetime('now', 'localtime','+5 minutes'),1)",
        (_session_hash(token), username),
    )
    conn.commit()
    return token


def slide_session(nonce_token: str):
    conn = get_db()
    conn.execute(
        f"UPDATE sessions SET expires=datetime('now', 'localtime', '+{WEB_SESSION_MINUTES} minutes') "
        "WHERE token=? AND mfa_state=2 AND expires > datetime('now', 'localtime')",
        (_session_hash(nonce_token),),
    )
    conn.commit()


def get_session(token: str):
    if not token:
        return None
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM sessions WHERE token=? AND expires > datetime('now', 'localtime')",
        (_session_hash(token),),
    ).fetchone()
    return dict(row) if row else None


def complete_session(nonce_token: str):
    conn = get_db()
    nonce_hash = _session_hash(nonce_token)
    row = conn.execute(
        "SELECT username FROM sessions WHERE token=? AND mfa_state=1 "
        "AND expires > datetime('now', 'localtime')",
        (nonce_hash,),
    ).fetchone()
    if not row:
        _purge_expired()
        return None
    new_token = secrets.token_urlsafe(32)
    conn.execute("DELETE FROM sessions WHERE token=?", (nonce_hash,))
    conn.execute(
        "INSERT INTO sessions (token, username, expires, mfa_state) "
        "VALUES (?,?,datetime('now', 'localtime', ?),2)",
        (_session_hash(new_token), row["username"], f"+{WEB_SESSION_MINUTES} minutes"),
    )
    conn.commit()
    _purge_expired()
    return new_token


def revoke_session(token: str):
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE token=?", (_session_hash(token),))
    conn.commit()


def _purge_expired():
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE expires <= datetime('now', 'localtime')")
    conn.commit()


def extract_token(request: Request):
    auth_header = request.headers.get("Authorization", "")
    # 兼容 pip 的 HTTP Basic 认证，密码位置填 API 密钥
    if auth_header.lower().startswith("basic "):
        try:
            raw = base64.b64decode(auth_header[6:].strip()).decode("utf-8")
            if ":" in raw:
                return raw.split(":", 1)[1]
        except Exception:
            pass
    return (
        request.headers.get("Session-Token")
        or request.headers.get("X-Auth-Token")
        or auth_header.replace("Bearer ", "")
        or request.query_params.get("token")
        or ""
    )


def _token_sha(token: str):
    return crypto.token_hash(token)


def create_api_token(username: str, name: str):
    token = "mm_" + secrets.token_urlsafe(30)
    conn = get_db()
    conn.execute(
        "INSERT INTO api_tokens (username, name, token_hash, token_prefix, token_algo) "
        "VALUES (?,?,?,?,'sm3')",
        (username, name, _token_sha(token), token[:8]),
    )
    conn.commit()
    return token


def list_api_tokens(username: str):
    conn = get_db()
    return [
        dict(r)
        for r in conn.execute(
            "SELECT id, name, token_prefix, created_at, last_used_at, revoked, token_algo "
            "FROM api_tokens WHERE username=? ORDER BY id DESC",
            (username,),
        )
    ]


def revoke_api_token(username: str, token_id: int):
    conn = get_db()
    cur = conn.execute(
        "UPDATE api_tokens SET revoked=1 WHERE id=? AND username=?",
        (token_id, username),
    )
    conn.commit()
    return cur.rowcount > 0


def _api_token_user(token: str):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM api_tokens WHERE token_hash=? AND revoked=0",
        (_token_sha(token),),
    ).fetchone()
    if not row:
        # 旧版密钥首次使用后自动升级为国密哈希
        legacy = crypto.token_hash_legacy(token)
        row = conn.execute(
            "SELECT * FROM api_tokens WHERE token_hash=? AND revoked=0",
            (legacy,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE api_tokens SET token_hash=?, token_algo='sm3' WHERE id=?",
                (_token_sha(token), row["id"]),
            )
            conn.commit()
    if not row:
        return None
    conn.execute(
        "UPDATE api_tokens SET last_used_at=datetime('now', 'localtime') WHERE id=?", (row["id"],)
    )
    conn.commit()
    return get_user_by_name(row["username"])


def auth_ctx(request: Request):
    """返回当前请求的用户与管理员标记，未登录时返回空。"""
    token = extract_token(request)
    if token == config.ADMIN_TOKEN and config.ADMIN_TOKEN != "admin-token":
        return {"user": None, "is_admin": True, "mfa_ready": True, "web_session": False}

    user = None
    is_web = False
    sess = get_session(token)

    if sess and sess["mfa_state"] == 2:
        user = get_user_by_name(sess["username"])
        if user:
            slide_session(token)
            is_web = True

    if not user:
        user = _api_token_user(token)

    if not user or not user.get("enabled", True):
        return None
    return {
        "user": user,
        "is_admin": user["role"] == "admin",
        "mfa_ready": True,
        "web_session": is_web,
    }


def get_user_by_name(username: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return dict(row) if row else None


def require_admin(request: Request):
    ctx = auth_ctx(request)
    if not ctx:
        security_audit_fail(request)
        raise HTTPException(401, "login required")
    if not ctx["is_admin"]:
        raise HTTPException(403, "admin required")
    if ctx["user"] is not None and not (mfa_enforced_ok(ctx)):
        raise HTTPException(403, "mfa required")
    return ctx


def mfa_enforced_ok(ctx):
    user = ctx["user"]
    if user is None or user["role"] == "admin":
        return True
    enforced = get_setting("mfa_enforced", "0") == "1"
    if not enforced:
        return True
    return bool(user["mfa_secret"])


def require_session(request: Request):
    ctx = auth_ctx(request)
    if not ctx:
        security_audit_fail(request)
        raise HTTPException(401, "login required")
    return ctx


def can(ctx, repo: str, perm: str):
    # 代理权限对管理员同样生效，需要先加入用户组并获得授权
    # 命令行应急令牌没有对应用户，按无权限处理
    user = ctx.get("user")
    if not user:
        return False
    groups = get_db().execute(
        """SELECT g.id FROM groups g
           JOIN user_groups ug ON ug.group_id=g.id
           WHERE ug.username=?""",
        (user["username"],),
    ).fetchall()
    if not groups:
        return False
    placeholders = ",".join("?" for _ in groups)
    row = get_db().execute(
        f"""SELECT 1 FROM group_repos WHERE group_id IN ({placeholders})
            AND repo=? AND {perm}=1""",
        tuple(g["id"] for g in groups) + (repo,),
    ).fetchone()
    return row is not None


def require_repo_perm(perm: str):
    def checker(request: Request, repo: str):
        ctx = auth_ctx(request)
        if not ctx:
            raise HTTPException(401, "login required")
        # 管理员也不例外，必须获得所在用户组的授权
        if not can(ctx, repo, perm):
            raise HTTPException(403, f"no {perm} permission on repo {repo}")
        return ctx

    return checker


def security_audit_fail(request):
    from . import security

    security.audit(
        "auth.fail",
        request.client.host if request.client else "?",
        {"detail": "invalid session"},
    )


def gen_totp_secret():
    data = secrets.token_bytes(20)
    return base64.b32encode(data).decode().rstrip("=")


def totp(secret: str, at: float = None, step: int = 30):
    import time as _time

    if at is None:
        at = _time.time()
    s = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = int(at // step)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(s, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def verify_totp(secret: str, code: str, window: int = 1):
    import time as _time

    if not secret or not code or len(code) != 6 or not code.isdigit():
        return False
    now = _time.time()
    return any(
        hmac.compare_digest(totp(secret, now + i * 30), code)
        for i in range(-window, window + 1)
    )


def otpauth_url(username: str, secret: str):
    return (
        f"otpauth://totp/ModernMirror:{username}?secret={secret}&issuer=ModernMirror&period=30&digits=6"
    )
