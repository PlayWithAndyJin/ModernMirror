import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, config, private, proxy, security, storage
from .admin import router as admin_router
from .routes_auth import router as auth_router
from .db import get_db, migrate_crypto_data, seed, seed_admin


def _startup():
    seed()
    seed_admin()
    migrate_crypto_data()
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    os.makedirs(config.PRIVATE_DIR, exist_ok=True)
    threading.Thread(target=_cleanup_scheduler, daemon=True).start()
    if config.ADMIN_TOKEN == "admin-token":
        print(
            "!!! 警告: 使用默认管理 Token 'admin-token'。对外部署请设 MODERNMIRROR_TOKEN 环境变量!",
            file=sys.stderr,
        )
        security.audit("startup.warn", "local", {"detail": "default admin token in use"})
    if config.MASTER_KEY_SOURCE == "generated":
        print(
            f"!!! 已自动生成数据加密主密钥: {config.MASTER_KEY_PATH}\n"
            "    该文件用于解密 MFA 密钥与审计日志, 请务必备份且不要提交到版本库; 丢失将无法恢复。",
            file=sys.stderr,
        )


@asynccontextmanager
async def _lifespan(_app):
    _startup()
    yield


app = FastAPI(
    title="ModernMirror", docs_url="/docs", redoc_url=None, lifespan=_lifespan
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "HEAD", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(admin_router)

SKILL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")

_TEMPLATE_FILES = {
    "csv": ("members.csv", "text/csv"),
    "json": ("members.json", "application/json"),
    "toml": ("members.toml", "application/toml"),
    "txt": ("members.txt", "text/plain"),
}


@app.get("/templates/members.{ext}", include_in_schema=False)
def template_download(ext: str, request: Request):
    ctx = auth.auth_ctx(request)
    if not ctx:
        return JSONResponse({"detail": "login required"}, status_code=401)
    ext = ext.lower()
    if ext not in _TEMPLATE_FILES:
        raise HTTPException(404, "template not found")
    filename, media_type = _TEMPLATE_FILES[ext]
    path = os.path.join(TEMPLATE_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "template file missing")
    return FileResponse(path, media_type=media_type, filename=filename)


@app.get("/skill/modernmirror-config/SKILL.md", include_in_schema=False)
def skill_download(request: Request):
    ctx = auth.auth_ctx(request)
    if not ctx:
        return JSONResponse({"detail": "login required"}, status_code=401)
    skill_path = os.path.join(SKILL_DIR, "SKILL.md")
    if not os.path.exists(skill_path):
        raise HTTPException(404, "skill file not found")
    return FileResponse(skill_path, media_type="text/markdown", filename="modernmirror-config-SKILL.md")

rate_limiter = security.RateLimiter(config.RATE_LIMIT, config.RATE_WINDOW)

_DOCS_PATHS = {"/docs", "/openapi.json", "/redoc"}
_DOCS_COOKIE = "modernmirror_docok"


def _docs_allowed(request: Request):
    token = auth.extract_token(request)
    ctx = auth.auth_ctx(request)
    if ctx and ctx.get("is_admin") and (ctx.get("user") is None or ctx.get("mfa_ready")):
        sess = auth.get_session(token) if token else None
        return True, (auth._session_hash(token) if sess else None)
    if token == config.ADMIN_TOKEN and config.ADMIN_TOKEN != "admin-token":
        return True, None
    return False, None


@app.middleware("http")
async def docs_auth_mw(request: Request, call_next):
    path = request.scope.get("path")
    if path in _DOCS_PATHS:
        allowed, token_hash = _docs_allowed(request)
        if not allowed:
            cookie = request.cookies.get(_DOCS_COOKIE)
            if cookie:
                conn = auth.get_db()
                row = conn.execute(
                    "SELECT username FROM sessions "
                    "WHERE token=? AND expires > datetime('now', 'localtime')",
                    (cookie,),
                ).fetchone()
                if row:
                    user = auth.get_user_by_name(row["username"])
                    if user and user["role"] == "admin":
                        allowed = True
        if not allowed:
            return JSONResponse(
                {"detail": "管理员登录后才能访问接口文档"}, status_code=401
            )
        resp = await call_next(request)
        if token_hash:
            resp.set_cookie(
                _DOCS_COOKIE, token_hash, max_age=3600,
                httponly=True, samesite="lax",
            )
        return resp
    return await call_next(request)


@app.middleware("http")
async def rate_limit_mw(request: Request, call_next):
    client_ip = request.client.host if request.client else "local"
    if not rate_limiter.check(client_ip):
        return JSONResponse({"detail": "太频繁, 触发限流"}, status_code=429)
    return await call_next(request)


def _cleanup_scheduler():
    while True:
        try:
            now = datetime.now()
            today = date.today().isoformat()
            enabled = auth.get_setting("cleanup_enabled", "1") == "1"
            last = auth.get_setting("last_cleanup_date", "")
            if enabled and now.hour >= 3 and last != today:
                days = int(auth.get_setting("cache_retention_days", "30"))
                freed = storage.cleanup_keep_last_n(days)
                auth.set_setting("last_cleanup_date", today)
                if freed:
                    security.audit("cache.scheduled_cleanup", "scheduler",
                                   {"days": days, "freed": freed})
        except Exception:
            pass
        time.sleep(1800)

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/whoami")
def whoami(request: Request):
    ctx = auth.auth_ctx(request)
    if not ctx:
        return {"user": None}
    username = ctx["user"]["username"] if ctx["user"] else "cli"
    role = ctx["user"]["role"] if ctx["user"] else "admin"
    pub = {
        "username": username,
        "role": role,
        "mfa": bool(ctx["user"]["mfa_secret"]) if ctx["user"] else False,
    }
    legacy_tokens = 0
    reset_needed = False
    try:
        conn = get_db()
        legacy_tokens = conn.execute(
            "SELECT count(*) c FROM api_tokens WHERE username=? AND revoked=0 AND token_algo='sha256'",
            (username,),
        ).fetchone()["c"]
        if role == "admin":
            row = conn.execute("SELECT value FROM settings WHERE key='password_reset_needed'").fetchone()
            legacy_pw = conn.execute(
                "SELECT count(*) c FROM users WHERE password_hash NOT LIKE 'sm3$%'"
            ).fetchone()["c"]
            reset_needed = (row and row["value"] == "1") or legacy_pw > 0
    except Exception:
        pass
    pub["legacy_tokens"] = legacy_tokens
    pub["password_reset_needed"] = reset_needed
    return {"user": pub}


@app.get("/proxy/{repo}/{path:path}")
async def proxy_get(repo: str, path: str, request: Request):
    if repo.startswith(".") or "/" in repo or "\\" in repo:
        raise HTTPException(400, "invalid repo name")
    auth.require_repo_perm("can_download")(request, repo)
    return await proxy.fetch_and_cache(repo, path, request)


@app.head("/proxy/{repo}/{path:path}")
async def proxy_head(repo: str, path: str, request: Request):
    if repo.startswith(".") or "/" in repo or "\\" in repo:
        raise HTTPException(400, "invalid repo name")
    auth.require_repo_perm("can_download")(request, repo)
    return await proxy.fetch_and_cache(repo, path, request)


@app.get("/pkg/{repo}/{filename}")
def pkg_download(repo: str, filename: str, request: Request):
    auth.require_repo_perm("can_download")(request, repo)
    return private.download_package(repo, filename)


@app.get("/simple/{repo}")
def simple_index(repo: str, request: Request):
    auth.require_repo_perm("can_download")(request, repo)
    return private.simple_index(repo, "")


_HERE = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIST = next(
    (
        p
        for p in [
            os.path.join(_HERE, "..", "..", "frontend", "dist"),
            os.path.join(_HERE, "..", "dist"),
            os.environ.get("MODERNMIRROR_DIST", ""),
        ]
        if p and os.path.isdir(p)
    ),
    "",
)

if os.path.isdir(FRONTEND_DIST):

    class SPAFiles(StaticFiles):
        async def get_response(self, path, scope):
            from starlette.exceptions import HTTPException as StarletteHTTPException
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as e:
                if e.status_code == 404:
                    return await super().get_response("index.html", scope)
                raise

    app.mount("/ui", SPAFiles(directory=FRONTEND_DIST, html=True), name="ui")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse(
            '<meta http-equiv="refresh" content="0; url=/ui/">'
        )
else:

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse(
            "<h1>ModernMirror</h1><p>管理界面未构建。运行 frontend 的 build 后访问 /ui/</p>"
            '<p>API 文档: <a href="/docs">/docs</a></p>'
        )


def main():
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
