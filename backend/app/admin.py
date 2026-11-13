import os
import csv
import io
import json
import re
import secrets
import string
import tomllib

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel

from . import auth, config, crypto, private, security, storage
from .db import get_db
from .routes_auth import router as auth_router

router = APIRouter(prefix="/admin")



class RepoIn(BaseModel):
    name: str
    type: str
    upstream: str
    upstreams: list[str] | None = None
    quota_mb: int = 0
    enabled: bool = True


class UserIn(BaseModel):
    username: str
    password: str
    role: str = "user"
    enabled: bool = True


class UserPatch(BaseModel):
    password: str = ""
    role: str = ""
    enabled: bool | None = None


class GroupIn(BaseModel):
    name: str
    description: str = ""


class GroupPermIn(BaseModel):
    can_download: bool = True
    can_upload: bool = False


class MemberIn(BaseModel):
    username: str


@router.get("/users")
def list_users(request: Request):
    auth.require_admin(request)
    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, role, mfa_secret, enabled, created_at FROM users"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["mfa"] = bool(d.pop("mfa_secret"))
        d["groups"] = [
            x["name"]
            for x in conn.execute(
                "SELECT g.name FROM groups g JOIN user_groups ug ON ug.group_id=g.id WHERE ug.username=?",
                (d["username"],),
            )
        ]
        out.append(d)
    return out


@router.post("/users")
def add_user(body: UserIn, request: Request):
    auth.require_admin(request)
    if body.role not in ("admin", "user"):
        raise HTTPException(400, "role must be admin/user")
    username = (body.username or "").strip()
    error = _username_error(username)
    if error:
        raise HTTPException(400, error)
    if len(body.password) < 8:
        raise HTTPException(400, "密码至少 8 位")
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, enabled) VALUES (?,?,?,?)",
            (username, auth.hash_password(body.password), body.role, int(body.enabled)),
        )
    except Exception:
        raise HTTPException(400, "用户名已存在或非法")
    gid = conn.execute("SELECT id FROM groups WHERE name='default'").fetchone()
    if gid:
        conn.execute("INSERT OR IGNORE INTO user_groups (username, group_id) VALUES (?,?)", (username, gid["id"]))
    conn.commit()
    security.audit("user.add", request.client.host, {"user": username, "role": body.role})
    return {"ok": True}


@router.put("/users/{username}")
def update_user(username: str, body: UserPatch, request: Request):
    ctx = auth.require_admin(request)
    conn = get_db()
    cur = conn.execute("SELECT 1 FROM users WHERE username=?", (username,))
    if not cur.fetchone():
        raise HTTPException(404, "user not found")
    if body.password:
        if len(body.password) < 8:
            raise HTTPException(400, "密码至少 8 位")
        conn.execute("UPDATE users SET password_hash=?, password_algo='sm3' WHERE username=?",
                     (auth.hash_password(body.password), username))
    if body.role:
        if body.role not in ("admin", "user"):
            raise HTTPException(400, "role must be admin/user")
    current = ctx.get("user")
    if current and current["username"] == username:
        if body.role and body.role != "admin":
            raise HTTPException(400, "不能降级当前登录账号")
        if body.enabled is False:
            raise HTTPException(400, "不能禁用当前登录账号")
    _ensure_admin_remains(conn, username, body.role, body.enabled)
    if body.role:
        conn.execute("UPDATE users SET role=? WHERE username=?", (body.role, username))
    if body.enabled is not None:
        conn.execute("UPDATE users SET enabled=? WHERE username=?", (int(body.enabled), username))
    conn.commit()
    security.audit("user.update", request.client.host, {"user": username, "operator": _operator(ctx)})
    return {"ok": True}


def _operator(ctx):
    return ctx["user"]["username"] if ctx.get("user") else "cli"


def _ensure_admin_remains(conn, username, new_role="", new_enabled=None):
    """禁止降级或禁用最后一个启用的管理员，避免把自己锁在门外。"""
    row = conn.execute("SELECT role, enabled FROM users WHERE username=?", (username,)).fetchone()
    if not row:
        return
    resulting_role = new_role or row["role"]
    resulting_enabled = row["enabled"] if new_enabled is None else int(new_enabled)
    if resulting_role == "admin" and resulting_enabled:
        return
    others = conn.execute(
        "SELECT count(*) c FROM users WHERE role='admin' AND enabled=1 AND username<>?",
        (username,),
    ).fetchone()["c"]
    if others == 0:
        raise HTTPException(400, "系统至少需要保留一个启用状态的管理员")


@router.delete("/users/{username}")
def delete_user(username: str, request: Request):
    ctx = auth.require_admin(request)
    if ctx.get("user") and ctx["user"]["username"] == username:
        raise HTTPException(400, "不能删除当前登录账号")
    conn = get_db()
    _ensure_admin_remains(conn, username, new_role="user", new_enabled=False)
    cur = conn.execute("DELETE FROM users WHERE username=?", (username,))
    conn.execute("DELETE FROM user_groups WHERE username=?", (username,))
    conn.execute("DELETE FROM sessions WHERE username=?", (username,))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "user not found")
    security.audit("user.delete", request.client.host, {"user": username, "operator": _operator(ctx)})
    return {"ok": True}


@router.post("/users/{username}/reset-mfa")
def reset_mfa(username: str, request: Request):
    auth.require_admin(request)
    conn = get_db()
    cur = conn.execute("UPDATE users SET mfa_secret=NULL WHERE username=?", (username,))
    conn.commit()
    security.audit("user.mfa_reset", request.client.host, {"user": username})
    return {"ok": cur.rowcount > 0}


@router.get("/groups")
def list_groups(request: Request):
    auth.require_admin(request)
    conn = get_db()
    out = []
    for g in conn.execute("SELECT * FROM groups"):
        d = dict(g)
        d["members"] = [
            x["username"]
            for x in conn.execute("SELECT username FROM user_groups WHERE group_id=?", (g["id"],))
        ]
        d["repos"] = [
            dict(x)
            for x in conn.execute(
                "SELECT repo, can_download, can_upload FROM group_repos WHERE group_id=?",
                (g["id"],),
            )
        ]
        out.append(d)
    return out


@router.post("/groups")
def add_group(body: GroupIn, request: Request):
    auth.require_admin(request)
    conn = get_db()
    try:
        conn.execute("INSERT INTO groups (name, description) VALUES (?,?)", (body.name, body.description))
    except Exception:
        raise HTTPException(400, "组名已存在")
    conn.commit()
    security.audit("group.add", request.client.host, {"name": body.name})
    return {"ok": True}


@router.put("/groups/{gid}")
def update_group(gid: int, body: GroupIn, request: Request):
    auth.require_admin(request)
    conn = get_db()
    row = conn.execute("SELECT name FROM groups WHERE id=?", (gid,)).fetchone()
    if not row:
        raise HTTPException(404, "group not found")
    if row["name"] == "default" and body.name != "default":
        raise HTTPException(400, "默认组不能改名")
    conn.execute("UPDATE groups SET name=?, description=? WHERE id=?", (body.name, body.description, gid))
    conn.commit()
    return {"ok": True}


@router.delete("/groups/{gid}")
def delete_group(gid: int, request: Request):
    auth.require_admin(request)
    conn = get_db()
    row = conn.execute("SELECT name FROM groups WHERE id=?", (gid,)).fetchone()
    if not row:
        raise HTTPException(404, "group not found")
    if row["name"] == "default":
        raise HTTPException(400, "默认组不能删除")
    conn.execute("DELETE FROM user_groups WHERE group_id=?", (gid,))
    conn.execute("DELETE FROM group_repos WHERE group_id=?", (gid,))
    conn.execute("DELETE FROM groups WHERE id=?", (gid,))
    conn.commit()
    security.audit("group.delete", request.client.host, {"gid": gid})
    return {"ok": True}


@router.post("/groups/{gid}/members")
def add_member(gid: int, body: MemberIn, request: Request):
    auth.require_admin(request)
    conn = get_db()
    if not conn.execute("SELECT 1 FROM users WHERE username=?", (body.username,)).fetchone():
        raise HTTPException(400, "用户不存在")
    if not conn.execute("SELECT 1 FROM groups WHERE id=?", (gid,)).fetchone():
        raise HTTPException(404, "组不存在")
    cur = conn.execute(
        "INSERT OR IGNORE INTO user_groups (username, group_id) VALUES (?,?)", (body.username, gid)
    )
    conn.commit()
    security.audit("group.member_add", request.client.host, {"gid": gid, "user": body.username})
    return {"ok": cur.rowcount > 0}


def _parse_members(filename: str, raw: bytes):
    suffix = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    text = raw.decode("utf-8-sig", errors="replace")
    entries = []
    if suffix == "csv":
        for row in csv.DictReader(io.StringIO(text)):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if row.get("username"):
                entries.append(row)
    elif suffix == "json":
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("JSON must be an array")
        for row in data:
            if isinstance(row, dict) and str(row.get("username", "")).strip():
                entries.append({str(k).lower(): v for k, v in row.items()})
            elif isinstance(row, str):
                entries.append({"username": row.strip()})
    elif suffix == "toml":
        data = tomllib.loads(text)
        rows = data.get("members") or data.get("users") or []
        for row in rows:
            if isinstance(row, dict) and str(row.get("username", "")).strip():
                entries.append({str(k).lower(): v for k, v in row.items()})
    elif suffix == "txt":
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                parts = next(csv.reader([line]))
                parts = [p.strip() for p in parts]
                entry = {"username": parts[0]}
                if len(parts) > 1:
                    entry["password"] = parts[1]
                if len(parts) > 2:
                    entry["role"] = parts[2]
                if len(parts) > 3:
                    entry["groups"] = parts[3]
                entries.append(entry)
    else:
        raise ValueError("unsupported file type, use csv/json/toml/txt")
    return entries


_IMPORT_ERROR_TEXT = {
    "missing": "用户名为空",
    "invalid_name": "用户名不能为空、不能包含空白字符且最长 64 位",
    "invalid_role": "角色不正确，仅支持 user 或 admin",
    "short_password": "初始密码长度不足 8 位",
    "role_conflict": "用户已存在，当前角色为 {existing}，未变更角色",
    "duplicate": "用户 {uname} 在文件中重复出现，已跳过",
}


def _import_error(username, code, **kw):
    template = _IMPORT_ERROR_TEXT.get(code, "导入失败")
    return {"username": username, "reason": template.format(**kw)}


def _gen_password(n: int = 12):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _parse_groups(value):
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = str(value).replace(";", ",").replace("|", ",").split(",")
    out = []
    for item in items:
        name = str(item).strip().strip('"').strip("'")
        if name and name not in out:
            out.append(name)
    return out


@router.post("/groups/{gid}/members/import")
async def import_members(gid: int, file: UploadFile, request: Request):
    auth.require_admin(request)
    if not (file.filename or "").lower().endswith((".csv", ".json", ".toml", ".txt")):
        raise HTTPException(400, "仅支持 CSV / JSON / TOML / TXT 文件")
    raw = await file.read()
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(400, "文件超过 2MB")
    try:
        entries = _parse_members(file.filename, raw)
    except Exception as e:
        raise HTTPException(400, "文件内容格式不正确，请参照模板检查后重试")
    if not entries:
        raise HTTPException(400, "文件中没有可导入的成员")

    conn = get_db()
    if not conn.execute("SELECT 1 FROM groups WHERE id=?", (gid,)).fetchone():
        raise HTTPException(404, "组不存在")
    group_name = conn.execute("SELECT name FROM groups WHERE id=?", (gid,)).fetchone()["name"]

    created, added, exists, errors, group_created = [], [], [], [], []
    seen = set()
    for row in entries:
        username = str(row.get("username", "")).strip()
        password = str(row.get("password", "") or "").strip()
        role = str(row.get("role", "") or "user").strip().lower() or "user"
        groups = _parse_groups(row.get("groups"))
        if not groups:
            groups = [group_name]
        if not username:
            errors.append(_import_error("", "missing"))
            continue
        if _username_error(username):
            errors.append(_import_error(username, "invalid_name"))
            continue
        if role not in ("admin", "user"):
            errors.append(_import_error(username, "invalid_role"))
            continue
        if username in seen:
            errors.append(_import_error(username, "duplicate", uname=username))
            continue
        seen.add(username)

        user_row = conn.execute("SELECT username, role FROM users WHERE username=?", (username,)).fetchone()
        generated = None
        if not user_row:
            if password and len(password) < 8:
                errors.append(_import_error(username, "short_password"))
                continue
            generated = None if password else _gen_password()
            conn.execute(
                "INSERT INTO users (username, password_hash, role, password_algo) VALUES (?,?,?,'sm3')",
                (username, auth.hash_password(password or generated), role),
            )
            created.append({
                "username": username,
                "role": role,
                "password": password or generated,
                "generated": generated is not None,
                "groups": groups,
            })
        else:
            if str(row.get("role", "")).strip() and role != user_row["role"]:
                errors.append(_import_error(username, "role_conflict", existing=user_row["role"]))

        for gname in groups:
            g = conn.execute("SELECT id FROM groups WHERE name=?", (gname,)).fetchone()
            if not g:
                conn.execute("INSERT INTO groups (name, description) VALUES (?, '')", (gname,))
                g = conn.execute("SELECT id FROM groups WHERE name=?", (gname,)).fetchone()
                group_created.append(gname)
            cur = conn.execute(
                "INSERT OR IGNORE INTO user_groups (username, group_id) VALUES (?,?)",
                (username, g["id"]),
            )
            if cur.rowcount > 0 and gname == group_name:
                added.append(username)
            elif cur.rowcount > 0:
                pass
            elif gname == group_name:
                exists.append(username)
    conn.commit()
    security.audit("group.member_import", request.client.host,
                   {"gid": gid, "group": group_name, "count": len(seen),
                    "created": len(created), "groups_created": group_created})
    return {
        "total": len(seen),
        "created": created,
        "added_to_group": added,
        "already_in_group": exists,
        "groups_created": group_created,
        "errors": errors,
    }


@router.delete("/groups/{gid}/members/{username}")
def del_member(gid: int, username: str, request: Request):
    auth.require_admin(request)
    conn = get_db()
    conn.execute("DELETE FROM user_groups WHERE group_id=? AND username=?", (gid, username))
    conn.commit()
    return {"ok": True}


@router.post("/groups/{gid}/repos/{repo}")
def grant_repo(gid: int, repo: str, body: GroupPermIn, request: Request):
    auth.require_admin(request)
    conn = get_db()
    conn.execute(
        """INSERT INTO group_repos (group_id, repo, can_download, can_upload) VALUES (?,?,?,?)
           ON CONFLICT(group_id, repo) DO UPDATE SET
           can_download=excluded.can_download, can_upload=excluded.can_upload""",
        (gid, repo, int(body.can_download), int(body.can_upload)),
    )
    conn.commit()
    security.audit("group.grant", request.client.host, {"gid": gid, "repo": repo})
    return {"ok": True}


@router.delete("/groups/{gid}/repos/{repo}")
def revoke_repo(gid: int, repo: str, request: Request):
    auth.require_admin(request)
    conn = get_db()
    conn.execute("DELETE FROM group_repos WHERE group_id=? AND repo=?", (gid, repo))
    conn.commit()
    security.audit("group.revoke", request.client.host, {"gid": gid, "repo": repo})
    return {"ok": True}


@router.get("/settings")
def get_settings(request: Request):
    auth.require_admin(request)
    return {
        "mfa_enforced": auth.get_setting("mfa_enforced", "0") == "1",
    }


@router.put("/settings")
def put_settings(request: Request, mfa_enforced: bool = None,
                 cleanup_enabled: bool = None, cache_retention_days: int = None):
    auth.require_admin(request)
    if mfa_enforced is not None:
        auth.set_setting("mfa_enforced", "1" if mfa_enforced else "0")
        security.audit("settings.mfa_enforced", request.client.host, {"value": mfa_enforced})
    if cleanup_enabled is not None:
        auth.set_setting("cleanup_enabled", "1" if cleanup_enabled else "0")
    if cache_retention_days is not None:
        auth.set_setting("cache_retention_days", str(max(1, min(cache_retention_days, 3650))))
    return {
        "mfa_enforced": auth.get_setting("mfa_enforced", "0") == "1",
        "cleanup_enabled": auth.get_setting("cleanup_enabled", "1") == "1",
        "cache_retention_days": int(auth.get_setting("cache_retention_days", "30")),
    }


def _username_error(name: str) -> str:
    if not name or len(name) > 64 or any(ch.isspace() for ch in name):
        return "用户名不能为空、不能包含空白字符且最长 64 位"
    return ""


def _validate_repo_name(name: str):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", name or ""):
        raise HTTPException(
            400,
            "仓库名仅支持字母、数字、点、下划线和短横线, 以字母或数字开头, 最长 64 位",
        )


def _normalize_upstreams(body: RepoIn):
    raw = body.upstreams if body.upstreams else [body.upstream]
    urls = []
    for u in raw:
        u = (u or "").strip().rstrip("/")
        if not u:
            continue
        if not u.startswith("https://"):
            raise HTTPException(400, "upstream must use https:// (防中间人投毒)")
        if u not in urls:
            urls.append(u)
    if not urls:
        raise HTTPException(400, "at least one upstream is required")
    return urls


@router.get("/repos")
def list_repos(request: Request):
    ctx = auth.auth_ctx(request)
    if not ctx:
        raise HTTPException(401, "login required")
    conn = get_db()
    if ctx["is_admin"]:
        return [dict(r) for r in conn.execute("SELECT * FROM repos ORDER BY name")]
    # 普通用户仅能看到已授权的仓库
    rows = ctx["user"]["username"]
    allowed = conn.execute(
        """SELECT DISTINCT gr.repo FROM group_repos gr
           JOIN user_groups ug ON ug.group_id = gr.group_id
           WHERE ug.username=? AND (gr.can_download=1 OR gr.can_upload=1)""",
        (rows,),
    ).fetchall()
    names = [r["repo"] for r in allowed]
    if not names:
        return []
    qmarks = ",".join("?" for _ in names)
    return [dict(r) for r in conn.execute(f"SELECT * FROM repos WHERE name IN ({qmarks}) ORDER BY name", names)]


@router.get("/ping")
async def ping_upstreams(request: Request):
    auth.require_session(request)
    import asyncio
    import time

    import httpx

    conn = get_db()
    repos = conn.execute("SELECT name, upstream, upstreams FROM repos WHERE enabled=1").fetchall()
    out = {}

    details = {}

    async def probe(name, upstream, primary=False):
        t0 = time.perf_counter()
        ms = -1
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=5.0) as client:
                resp = await client.head(upstream.rstrip("/"))
                if resp.status_code < 500:
                    ms = round((time.perf_counter() - t0) * 1000)
        except httpx.HTTPError:
            ms = -1
        details.setdefault(name, []).append({"upstream": upstream, "ms": ms})
        if primary:
            out[name] = ms

    jobs = []
    for r in repos:
        try:
            urls = json.loads(r["upstreams"] or "[]") or [r["upstream"]]
        except Exception:
            urls = [r["upstream"]]
        for i, u in enumerate(urls):
            jobs.append(probe(r["name"], u, primary=(i == 0)))
    await asyncio.gather(*jobs)
    for name, arr in details.items():
        healthy = [x["ms"] for x in arr if x["ms"] >= 0]
        out[name] = min(healthy) if healthy else -1
    return {"latency": out, "details": details, "probed_at": int(time.time())}


@router.post("/repos")
def add_repo(body: RepoIn, request: Request):
    auth.require_admin(request)
    if body.type not in ("pypi", "npm", "raw", "go", "maven", "nuget", "rubygems",
                         "crates", "conan", "pub", "hex", "hackage", "cran",
                         "luarocks", "cocoapods"):
        raise HTTPException(400, "type must be pypi/npm/raw/go/maven/nuget/rubygems/crates/conan/pub/hex/hackage/cran/luarocks/cocoapods")
    if not body.upstream.startswith("https://"):
        raise HTTPException(400, "upstream must use https:// (防中间人投毒)")
    _validate_repo_name(body.name)
    urls = _normalize_upstreams(body)
    conn = get_db()
    conn.execute(
        "INSERT INTO repos (name, type, upstream, upstreams, quota_mb, enabled) VALUES (?,?,?,?,?,?)",
        (body.name, body.type, urls[0], json.dumps(urls), int(body.quota_mb), int(body.enabled)),
    )
    conn.commit()
    security.audit("repo.add", request.client.host, {"name": body.name, "upstream": body.upstream})
    return {"ok": True}


@router.put("/repos/{name}")
def update_repo(name: str, body: RepoIn, request: Request):
    auth.require_admin(request)
    if body.type not in ("pypi", "npm", "raw", "go", "maven", "nuget", "rubygems",
                         "crates", "conan", "pub", "hex", "hackage", "cran",
                         "luarocks", "cocoapods"):
        raise HTTPException(400, "invalid type")
    if not body.upstream.startswith("https://"):
        raise HTTPException(400, "upstream must use https:// (防中间人投毒)")
    _validate_repo_name(body.name)
    urls = _normalize_upstreams(body)
    conn = get_db()
    cur = conn.execute(
        "UPDATE repos SET upstream=?, upstreams=?, quota_mb=?, enabled=?, type=? WHERE name=?",
        (urls[0], json.dumps(urls), int(body.quota_mb), int(body.enabled), body.type, name),
    )
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "not found")
    security.audit("repo.update", request.client.host, {"name": name, "upstream": body.upstream})
    return {"ok": True}


@router.delete("/repos/{name}")
def delete_repo(name: str, request: Request):
    auth.require_admin(request)
    conn = get_db()
    packages = conn.execute(
        "SELECT filepath FROM private_packages WHERE repo=?", (name,)
    ).fetchall()
    for row in packages:
        try:
            if os.path.exists(row["filepath"]):
                os.remove(row["filepath"])
        except OSError:
            pass
    conn.execute("DELETE FROM private_packages WHERE repo=?", (name,))
    conn.execute("DELETE FROM group_repos WHERE repo=?", (name,))
    cur = conn.execute("DELETE FROM repos WHERE name=?", (name,))
    conn.commit()
    try:
        os.rmdir(os.path.join(config.PRIVATE_DIR, name))
    except OSError:
        pass
    if cur.rowcount == 0:
        raise HTTPException(404, "repo not found")
    security.audit("repo.delete", request.client.host, {"name": name})
    return {"ok": True}


@router.get("/stats")
def stats(request: Request):
    auth.require_session(request)
    conn = get_db()
    entries = conn.execute(
        "SELECT repo, count(*) n, sum(size) total, sum(hits) hits FROM cache_entries GROUP BY repo"
    ).fetchall()
    per_repo = [dict(r) for r in entries]
    recent = conn.execute(
        "SELECT repo, path, size, hits, fetched_at FROM cache_entries ORDER BY last_hit_at DESC LIMIT 15"
    ).fetchall()
    return {
        "per_repo": per_repo,
        "total_size": storage.dir_size(config.CACHE_DIR),
        "total_files": sum(r["n"] for r in per_repo),
        "total_hits": sum(r["hits"] or 0 for r in per_repo),
        "recent": [dict(r) for r in recent],
    }


@router.post("/cache/cleanup")
def cleanup(request: Request, days: int = 7):
    auth.require_admin(request)
    freed = storage.cleanup_keep_last_n(days)
    if request:
        security.audit("cache.cleanup", request.client.host, {"days": days, "freed": freed})
    return {"freed_bytes": freed}


@router.get("/packages")
def list_packages(request: Request):
    ctx = auth.auth_ctx(request)
    if not ctx:
        raise HTTPException(401, "login required")
    conn = get_db()
    if ctx["is_admin"]:
        return [dict(r) for r in conn.execute("SELECT * FROM private_packages ORDER BY repo, filename")]
    # 普通用户仅能看到已授权仓库下的私有包
    allowed = conn.execute(
        """SELECT DISTINCT gr.repo FROM group_repos gr
           JOIN user_groups ug ON ug.group_id = gr.group_id
           WHERE ug.username=? AND (gr.can_download=1 OR gr.can_upload=1)""",
        (ctx["user"]["username"],),
    ).fetchall()
    names = [r["repo"] for r in allowed]
    if not names:
        return []
    qmarks = ",".join("?" for _ in names)
    return [dict(r) for r in conn.execute(f"SELECT * FROM private_packages WHERE repo IN ({qmarks}) ORDER BY repo, filename", names)]


@router.post("/packages/{repo}")
async def upload(repo: str, file: UploadFile, request: Request):
    ctx = auth.auth_ctx(request)
    if not ctx:
        raise HTTPException(401, "login required")
    if not (ctx["is_admin"] or auth.can(ctx, repo, "can_upload")):
        raise HTTPException(403, f"no upload permission on repo {repo}")
    if not repo or repo.startswith(".") or "/" in repo or "\\" in repo or repo in ("default",):
        raise HTTPException(400, "请在「仓库路径名」输入具体的仓库名后再上传 (如 pypi / mypkg)")
    result = await private.save_upload(
        file, repo, uploader=(ctx["user"]["username"] if ctx.get("user") else "cli")
    )
    security.audit("package.upload", request.client.host, {"repo": repo, "file": result["filename"], "sha256": result["sha256"]})
    return result


@router.delete("/packages/{repo}/{filename}")
def delete_package(repo: str, filename: str, request: Request):
    auth.require_admin(request)
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM private_packages WHERE repo=? AND filename=?", (repo, filename)
    ).fetchone()
    if not row:
        raise HTTPException(404, "not found")
    if os.path.exists(row["filepath"]):
        os.remove(row["filepath"])
    conn.execute("DELETE FROM private_packages WHERE repo=? AND filename=?", (repo, filename))
    conn.commit()
    security.audit("package.delete", request.client.host, {"repo": repo, "file": filename})
    return {"ok": True}


@router.get("/audit")
def list_audit(request: Request, limit: int = 200):
    auth.require_session(request)
    entries = []
    if os.path.exists(config.AUDIT_LOG):
        with open(config.AUDIT_LOG, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-max(1, min(limit, 1000)):]
        for line in lines:
            try:
                if line.startswith("sm|"):
                    entries.append(json.loads(auth.decrypt_mfa_secret(line[3:].strip())))
                elif line.startswith("enc|"):
                    entries.append(json.loads(auth.decrypt_mfa_secret(line[4:].strip())))
                elif line.startswith("plain|"):
                    payload = line[6:].strip()
                    if payload.startswith("enc:"):
                        payload = auth.decrypt_mfa_secret(payload)
                    entries.append(json.loads(payload))
                else:
                    entries.append(json.loads(line))
            except Exception:
                continue
    return entries


@router.get("/security/status")
def security_status(request: Request):
    auth.require_admin(request)
    conn = get_db()
    version = conn.execute("SELECT value FROM settings WHERE key='crypto_version'").fetchone()
    reset_needed = conn.execute("SELECT value FROM settings WHERE key='password_reset_needed'").fetchone()
    legacy_tokens = conn.execute(
        "SELECT count(*) c FROM api_tokens WHERE revoked=0 AND token_algo='sha256'"
    ).fetchone()["c"]
    legacy_pw = conn.execute(
        "SELECT count(*) c FROM users WHERE password_hash NOT LIKE 'sm3$%'"
    ).fetchone()["c"]
    return {
        "crypto_version": int(version["value"]) if version else 0,
        "password_reset_needed": bool(reset_needed and reset_needed["value"] == "1") or legacy_pw > 0,
        "legacy_password_users": legacy_pw,
        "legacy_api_tokens": legacy_tokens,
    }


@router.post("/security/reset-passwords")
def reset_all_passwords(request: Request):
    ctx = auth.require_admin(request)

    current = ctx["user"]["username"] if ctx["user"] else ""
    conn = get_db()
    users = conn.execute("SELECT username FROM users WHERE username<>?", (current,)).fetchall()
    generated = []
    for row in users:
        password = crypto.gen_password(14)
        conn.execute(
            "UPDATE users SET password_hash=?, password_algo='sm3' WHERE username=?",
            (auth.hash_password(password), row["username"]),
        )
        generated.append({"username": row["username"], "password": password})
    conn.execute("DELETE FROM sessions WHERE username<>?", (current,))
    conn.execute("UPDATE settings SET value='0' WHERE key='password_reset_needed'")
    conn.commit()
    security.audit("security.reset_all_passwords", request.client.host,
                   {"count": len(generated), "operator": current})
    return {"count": len(generated), "users": generated}
