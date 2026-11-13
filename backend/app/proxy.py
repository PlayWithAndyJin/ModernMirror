import base64
import hashlib
import json
import os
import re
import tempfile

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from . import config, security, storage
from .db import get_db

_client = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(follow_redirects=True, timeout=60.0)
    return _client


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha512_file_b64(path):
    h = hashlib.sha512()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return base64.b64encode(h.digest()).decode()


def _md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_verify_cache = {}


async def _expected_pypi_hash(repo, fname):
    pkg = fname.split("-")[0].split("_")[0].split(".")[0].lower()
    key = ("pypi", repo["name"], pkg)
    if len(_verify_cache) > 256:
        _verify_cache.clear()
    if key not in _verify_cache:
        _verify_cache[key] = {}
        try:
            base = repo["upstream"].rstrip("/")
            resp = await get_client().get(f"{base}/simple/{pkg}/")
            for m in re.finditer(
                r'href="[^"]*/([^/"#]+)#(?:sha256=([A-Za-z0-9]{64})|md5=([a-f0-9]{32}))',
                resp.text,
            ):
                if m.group(1) and (m.group(2) or m.group(3)):
                    _verify_cache[key][m.group(1)] = (
                        ("sha256", m.group(2)) if m.group(2) else ("md5", m.group(3))
                    )
        except httpx.HTTPError:
            pass
    return _verify_cache[key].get(fname)


async def _expected_npm_hash(repo, fname):
    m = re.match(r"^([@][^/]+/[^/]+|[^@/]+?)-\d+\.\d+", fname)
    pkg = m.group(1) if m else fname.split("-")[0]
    key = ("npm", repo["name"], pkg)
    if len(_verify_cache) > 256:
        _verify_cache.clear()
    if key not in _verify_cache:
        _verify_cache[key] = {}
        try:
            base = repo["upstream"].rstrip("/")
            resp = await get_client().get(f"{base}/{pkg}")
            data = resp.json()
            for _, vinfo in (data.get("versions") or {}).items():
                dist = vinfo.get("dist") or {}
                tarball = (dist.get("tarball") or "").rsplit("/", 1)[-1]
                integrity = dist.get("integrity", "")
                if tarball and integrity.startswith("sha512-"):
                    _verify_cache[key][tarball] = ("sha512", integrity.split("-", 1)[1])
        except (httpx.HTTPError, ValueError):
            pass
    return _verify_cache[key].get(fname)


async def _verify_metadata(repo_name, path, tmp_path, request):
    repo = get_repo(repo_name)
    fname = path.rsplit("/", 1)[-1]
    try:
        if repo["type"] == "pypi" and fname.endswith((".whl", ".tar.gz", ".zip", ".egg", ".bz2")):
            expected = await _expected_pypi_hash(repo, fname)
        elif repo["type"] == "npm" and fname.endswith(".tgz"):
            expected = await _expected_npm_hash(repo, fname)
        else:
            expected = None
    except Exception:
        expected = None

    if not expected:
        security.audit("verify.skipped", request.client.host if request.client else "local",
                       {"repo": repo_name, "file": path,
                        "detail": "upstream metadata offered no checksum for this file"})
        return False

    algo, digest = expected
    got = (
        _sha256_file(tmp_path) if algo == "sha256"
        else _md5_file(tmp_path) if algo == "md5"
        else _sha512_file_b64(tmp_path)
    )
    if got != digest:
        ip = request.client.host if request.client else "local"
        security.audit("verify.fail", ip, {"repo": repo_name, "file": path,
                                           "expected": f"{algo}:{digest}", "got": got})
        raise HTTPException(
            502,
            f"上游返回的 {algo} 校验不匹配, 已拒绝缓存 (疑似投毒/篡改): {path}",
        )
    return True



def _cleanup_tmp(path):
    try:
        if os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass


def upstream_urls(repo) -> list:
    try:
        arr = json.loads(repo["upstreams"] or "[]")
    except Exception:
        arr = []
    arr = [u.strip().rstrip("/") for u in arr if isinstance(u, str) and u.strip()]
    if not arr and repo["upstream"]:
        arr = [repo["upstream"].rstrip("/")]
    return arr


def get_repo(repo_name: str):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM repos WHERE name=? AND enabled=1", (repo_name,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"repo '{repo_name}' not found or disabled")
    return row


async def fetch_and_cache(repo_name: str, path: str, request: Request):
    repo = get_repo(repo_name)
    urls = [u + "/" + path for u in upstream_urls(repo)]

    conn = get_db()
    entry = conn.execute(
        "SELECT * FROM cache_entries WHERE repo=? AND path=?", (repo_name, path)
    ).fetchone()

    if entry and os.path.exists(entry["file_path"]):
        if not entry["verified"]:
            await _verify_metadata(repo_name, path, entry["file_path"], request)
            conn.execute("UPDATE cache_entries SET verified=1 WHERE id=?", (entry["id"],))
            conn.commit()
            entry = conn.execute(
                "SELECT * FROM cache_entries WHERE repo=? AND path=?", (repo_name, path)
            ).fetchone()
        current_etag = entry["etag"]
        if current_etag:
            check = None
            for u in urls:
                try:
                    candidate = await get_client().head(
                        u, headers={"If-None-Match": current_etag}
                    )
                    if candidate.status_code < 500:
                        check = candidate
                        break
                except httpx.HTTPError:
                    continue
            if check is not None and check.status_code == 304:
                ctx = hit(entry, conn, entry["id"], "revalidated")
                return respond_cached(entry, request, ctx)
            if check is not None and check.status_code == 200:
                new_etag = check.headers.get("etag")
                if new_etag and new_etag != current_etag:
                    return await download(urls, repo_name, path, request)
        ctx = hit(entry, conn, entry["id"], "hit")
        return respond_cached(entry, request, ctx)

    return await download(urls, repo_name, path, request)


async def download(targets: list, repo_name: str, path: str, request: Request):
    fwd = {
        k: v
        for k, v in request.headers.items()
        if k.lower() in ("if-none-match", "if-modified-since", "range", "user-agent")
    }
    resp = None
    last_error = None
    upstream_url = targets[0]
    for upstream_url in targets:
        try:
            candidate = await get_client().get(upstream_url, headers=fwd)
            if candidate.status_code < 500:
                resp = candidate
                break
            last_error = f"HTTP {candidate.status_code}"
        except httpx.HTTPError as e:
            last_error = str(e)
    if resp is None:
        conn = get_db()
        entry = conn.execute(
            "SELECT * FROM cache_entries WHERE repo=? AND path=?", (repo_name, path)
        ).fetchone()
        if entry and os.path.exists(entry["file_path"]):
            hit(entry, conn, entry["id"], "stale")
            return respond_cached(entry, request, "stale")
        raise HTTPException(502, f"upstream error: {last_error or 'unreachable'}")

    if 300 <= resp.status_code < 400 and resp.status_code != 304 and "location" in resp.headers:
        new_url = str(resp.headers["location"])
        if not new_url.startswith("http"):
            base = upstream_url.rsplit("/", 1)[0]
            new_url = base + "/" + new_url.lstrip("/")
        return await download([new_url], repo_name, path, request)

    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, f"upstream returned {resp.status_code}")

    if resp.status_code == 304:
        conn = get_db()
        entry = conn.execute(
            "SELECT * FROM cache_entries WHERE repo=? AND path=?", (repo_name, path)
        ).fetchone()
        if entry and os.path.exists(entry["file_path"]):
            hit(entry, conn, entry["id"], "hit")
            return respond_cached(entry, request, "hit")
        raise HTTPException(404, "not cached")

    content_type = resp.headers.get("content-type", "application/octet-stream")
    etag = resp.headers.get("etag")

    declared = resp.headers.get("content-length")
    max_bytes = config.MAX_UPSTREAM_MB * 1024 * 1024
    if declared and int(declared) > max_bytes:
        raise HTTPException(502, f"upstream file too large (>{config.MAX_UPSTREAM_MB}MB)")

    tmp = tempfile.NamedTemporaryFile(delete=False, dir=storage.tmp_dir())
    size = 0
    async for chunk in resp.aiter_bytes(256 * 1024):
        size += len(chunk)
        if size > max_bytes:
            tmp.close()
            os.unlink(tmp.name)
            raise HTTPException(502, f"upstream file too large (>{config.MAX_UPSTREAM_MB}MB)")
        tmp.write(chunk)
    tmp.close()

    try:
        # 上游没有校验和时记录审计，并标记为已尝试，避免重复拉取元数据
        await _verify_metadata(repo_name, path, tmp.name, request)
        file_path = await storage.save_async(tmp.name, repo_name, path)
    except HTTPException:
        _cleanup_tmp(tmp.name)
        raise
    except Exception:
        _cleanup_tmp(tmp.name)
        raise
    conn = get_db()
    conn.execute(
        """INSERT INTO cache_entries (repo, path, upstream_url, file_path, size,
           content_type, etag, fetched_at, last_hit_at, hits, verified)
           VALUES (?,?,?,?,?,?,?,datetime('now', 'localtime'),datetime('now', 'localtime'),0,?)
           ON CONFLICT(repo, path) DO UPDATE SET
           upstream_url=excluded.upstream_url, file_path=excluded.file_path,
           size=excluded.size, content_type=excluded.content_type,
           etag=excluded.etag, fetched_at=datetime('now', 'localtime'), verified=?""",
        (repo_name, path, upstream_url, file_path, size, content_type, etag, 1, 1),
    )
    conn.commit()
    repo_row = get_repo(repo_name)
    if repo_row["quota_mb"]:
        storage.enforce_quota(repo_name, int(repo_row["quota_mb"]))
    entry = conn.execute(
        "SELECT * FROM cache_entries WHERE repo=? AND path=?", (repo_name, path)
    ).fetchone()
    if entry is None:
        entry = {
            "file_path": file_path,
            "size": size,
            "content_type": content_type,
            "etag": etag,
        }

    range_header = request.headers.get("range")
    if range_header:
        return seek_range(entry, range_header, "fresh")
    return build_response(entry, 200)


def respond_cached(entry, request, ctx=""):
    """缓存命中的统一出口，支持断点续传并保留缓存状态标记。"""
    range_header = request.headers.get("range")
    if range_header:
        return seek_range(entry, range_header, ctx)
    return build_response(entry, 200, ctx)


def seek_range(entry, range_header, ctx=""):
    m = re.match(r"bytes=(\d*)-(\d*)", range_header)
    if not m or (not m.group(1) and not m.group(2)):
        return build_response(entry, 200, ctx)
    if m.group(1):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else entry["size"] - 1
    else:
        suffix = int(m.group(2))
        start = max(entry["size"] - suffix, 0)
        end = entry["size"] - 1
    end = min(end, entry["size"] - 1)
    if start > end or start >= entry["size"]:
        return Response(
            status_code=416,
            headers={"Content-Range": f"bytes */{entry['size']}"},
        )
    length = end - start + 1

    def gen():
        with open(entry["file_path"], "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        gen(), status_code=206,
        media_type=entry["content_type"] or "application/octet-stream",
        headers={
            "Content-Range": f"bytes {start}-{end}/{entry['size']}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "X-Cache-Status": ctx or "fresh",
        },
    )


def hit(entry, conn, entry_id, kind):
    conn.execute(
        "UPDATE cache_entries SET hits=hits+1, last_hit_at=datetime('now', 'localtime') WHERE id=?",
        (entry_id,),
    )
    conn.commit()
    return kind


def build_response(entry, status, ctx=""):
    headers = {
        "Accept-Ranges": "bytes",
        "X-Cache-Status": ctx or "fresh",
        "ETag": entry["etag"] or "",
    }
    return StreamingResponse(
        storage.open_stream(entry["file_path"]),
        status_code=status,
        media_type=entry["content_type"] or "application/octet-stream",
        headers=headers,
    )
