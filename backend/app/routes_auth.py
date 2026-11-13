from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import auth, security

router = APIRouter(prefix="/auth")


class LoginIn(BaseModel):
    username: str
    password: str


class TotpIn(BaseModel):
    nonce: str
    code: str


class PasswordIn(BaseModel):
    old_password: str
    new_password: str


class MfaSetupIn(BaseModel):
    code: str


class MfaDisableIn(BaseModel):
    password: str
    code: str


class ApiTokenIn(BaseModel):
    name: str


class ApiTokenDeleteIn(BaseModel):
    id: int


def _ctx_public(ctx):
    if ctx["user"] is None:
        return {"role": "admin", "username": "cli", "mfa": False}
    return {
        "username": ctx["user"]["username"],
        "role": ctx["user"]["role"],
        "mfa": bool(ctx["user"]["mfa_secret"]),
    }


@router.post("/login")
def login(body: LoginIn, request: Request):
    user = auth.get_user(body.username)
    if not user or not auth.verify_password(body.password, user["password_hash"]):
        security.audit("login.fail", request.client.host if request.client else "?", {"user": body.username})
        raise HTTPException(401, "用户名或密码错误")
    if not user.get("enabled", True):
        security.audit("login.disabled", request.client.host if request.client else "?", {"user": body.username})
        raise HTTPException(403, "该账号已被禁用, 请联系管理员")
    if auth.password_needs_upgrade(user["password_hash"]):
        conn = auth.get_db()
        conn.execute("UPDATE users SET password_hash=?, password_algo='sm3' WHERE username=?",
                     (auth.hash_password(body.password), user["username"]))
        conn.commit()
        user = auth.get_user_by_name(user["username"])
    enforced = auth.get_setting("mfa_enforced", "0") == "1"
    if user["mfa_secret"]:
        nonce = auth.create_login_nonce(body.username)
        return {"mfa_required": True, "nonce": nonce}
    token = auth.create_session(user["username"], 2)
    return {"mfa_required": False, "token": token, "user": _ctx_public({"user": user, "is_admin": True})}


@router.post("/verify-totp")
def verify(body: TotpIn, request: Request):
    sess = auth.get_session(body.nonce)
    if not sess or sess["mfa_state"] != 1:
        raise HTTPException(401, "登录会话已失效,请重新登录")
    user = auth.get_user_by_name(sess["username"])
    if not user or not auth.verify_totp(auth.decrypt_mfa_secret(user["mfa_secret"]), body.code):
        security.audit("login.mfa_fail", request.client.host if request.client else "?", {"user": sess["username"]})
        raise HTTPException(401, "动态码不正确")
    token = auth.complete_session(body.nonce)
    return {"token": token}


@router.post("/logout")
def logout(request: Request):
    token = auth.extract_token(request)
    if token:
        auth.revoke_session(token)
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    ctx = auth.require_session(request)
    return _ctx_public(ctx)


@router.post("/password")
def change_password(body: PasswordIn, request: Request):
    ctx = auth.require_session(request)
    if not ctx["user"]:
        raise HTTPException(400, "CLI token 无用户,请勿登录")
    user = ctx["user"]
    if not auth.verify_password(body.old_password, user["password_hash"]):
        raise HTTPException(403, "旧密码不正确")
    if len(body.new_password) < 8:
        raise HTTPException(400, "新密码至少 8 位")
    conn = auth.get_db()
    conn.execute(
        "UPDATE users SET password_hash=?, password_algo='sm3' WHERE username=?",
        (auth.hash_password(body.new_password), user["username"]),
    )
    conn.commit()
    security.audit("user.password_change", request.client.host, {"user": user["username"]})
    return {"ok": True}


@router.post("/mfa/setup")
def mfa_setup(request: Request):
    ctx = auth.require_session(request)
    if not ctx["user"]:
        raise HTTPException(400, "CLI token 无用户")
    user = ctx["user"]
    if user["mfa_secret"]:
        raise HTTPException(400, "MFA 已开启, 如需更换请先关闭")
    secret = auth.gen_totp_secret()
    auth.set_setting(f"pending_mfa:{user['username']}", auth.encrypt_mfa_secret(secret))
    return {
        "secret": secret,
        "otpauth": auth.otpauth_url(user["username"], secret),
        "hint": "密钥先保存(未生效), 在认证 App 添加后输入当前动态码点【确认开启】即可生效",
    }


@router.post("/mfa/enable")
def mfa_enable(body: MfaSetupIn, request: Request):
    ctx = auth.require_session(request)
    if not ctx["user"]:
        raise HTTPException(400, "CLI token 无用户")
    user = ctx["user"]
    pending = auth.get_setting(f"pending_mfa:{user['username']}")
    if not pending:
        raise HTTPException(400, "请先点【生成密钥】")
    pending = auth.decrypt_mfa_secret(pending)
    if not auth.verify_totp(pending, body.code):
        raise HTTPException(401, "动态码不正确, MFA 未开启")
    conn = auth.get_db()
    conn.execute("UPDATE users SET mfa_secret=? WHERE username=?", (auth.encrypt_mfa_secret(pending), user["username"]))
    conn.commit()
    auth.set_setting(f"pending_mfa:{user['username']}", "")
    security.audit("user.mfa_enable", request.client.host, {"user": user["username"]})
    return {"ok": True}


@router.post("/mfa/disable")
def mfa_disable(body: MfaDisableIn, request: Request):
    ctx = auth.require_session(request)
    if not ctx["user"]:
        raise HTTPException(400, "CLI token 无用户")
    user = ctx["user"]
    if not auth.verify_password(body.password, user["password_hash"]):
        raise HTTPException(403, "密码错误")
    if not auth.verify_totp(auth.decrypt_mfa_secret(user["mfa_secret"]), body.code):
        raise HTTPException(401, "动态码不正确")
    conn = auth.get_db()
    conn.execute("UPDATE users SET mfa_secret=NULL WHERE username=?", (user["username"],))
    conn.commit()
    security.audit("user.mfa_disable", request.client.host, {"user": user["username"]})
    return {"ok": True}


@router.get("/tokens")
def list_tokens(request: Request):
    ctx = auth.require_session(request)
    if not ctx["user"]:
        raise HTTPException(400, "CLI token 无用户")
    return auth.list_api_tokens(ctx["user"]["username"])


@router.post("/tokens")
def create_token(body: ApiTokenIn, request: Request):
    ctx = auth.require_session(request)
    if not ctx["user"]:
        raise HTTPException(400, "CLI token 无用户")
    user = ctx["user"]
    name = body.name.strip() or "未命名"
    token = auth.create_api_token(user["username"], name)
    security.audit("token.create", request.client.host,
                   {"user": user["username"], "name": name})
    return {
        "token": token,
        "hint": "此密钥仅显示一次, 请立即复制保存",
        "usage": f"pip install --index-url \"http://<host>:8800/proxy/pypi/simple/?token={token[:8]}…\" <包名>",
    }


@router.post("/tokens/revoke")
def revoke_token(body: ApiTokenDeleteIn, request: Request):
    ctx = auth.require_session(request)
    if not ctx["user"]:
        raise HTTPException(400, "CLI token 无用户")
    ok = auth.revoke_api_token(ctx["user"]["username"], body.id)
    if not ok:
        raise HTTPException(404, "该密钥不存在或不属于你")
    security.audit("token.revoke", request.client.host,
                   {"user": ctx["user"]["username"], "tid": body.id})
    return {"ok": True}


@router.post("/tokens/revoke-legacy")
def revoke_legacy_tokens(request: Request):
    ctx = auth.require_session(request)
    if not ctx["user"]:
        raise HTTPException(400, "CLI token 无用户")
    conn = auth.get_db()
    cur = conn.execute(
        "UPDATE api_tokens SET revoked=1 WHERE username=? AND token_algo='sha256' AND revoked=0",
        (ctx["user"]["username"],),
    )
    conn.commit()
    security.audit("token.revoke_legacy", request.client.host,
                   {"user": ctx["user"]["username"], "count": cur.rowcount})
    return {"revoked": cur.rowcount}
