import hashlib
import html
import os
import re
import secrets

import aiofiles
from fastapi import HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse

from . import config, storage
from .db import get_db


async def save_upload(file: UploadFile, repo: str, uploader: str = "admin"):
    safe_name = os.path.basename(file.filename or "upload.bin")
    if not safe_name or safe_name.startswith("."):
        raise HTTPException(400, "invalid filename")
    repo_dir = os.path.join(config.PRIVATE_DIR, repo)
    os.makedirs(repo_dir, exist_ok=True)
    dest = os.path.join(repo_dir, safe_name)
    tmp = f"{dest}.upload-{secrets.token_hex(6)}"
    sha = hashlib.sha256()
    size = 0
    max_bytes = config.MAX_UPLOAD_MB * 1024 * 1024
    try:
        async with aiofiles.open(tmp, "wb") as out:
            while chunk := await file.read(256 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        413, f"文件超过上限 ({config.MAX_UPLOAD_MB}MB)"
                    )
                sha.update(chunk)
                await out.write(chunk)
        os.replace(tmp, dest)
    except BaseException:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise
    conn = get_db()
    conn.execute(
        """INSERT INTO private_packages (repo, name, version, filename, filepath, size, sha256, uploader)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(repo, filename) DO UPDATE SET
           filepath=excluded.filepath, size=excluded.size,
           sha256=excluded.sha256, uploader=excluded.uploader,
           created_at=datetime('now', 'localtime')""",
        (
            repo, guess_name(safe_name), guess_version(safe_name),
            safe_name, dest, size, sha.hexdigest(), uploader,
        ),
    )
    conn.commit()
    return {"filename": safe_name, "size": size, "sha256": sha.hexdigest()}


def guess_name(filename: str) -> str:
    for sep in ("-", "_"):
        if sep in filename:
            return filename.split(sep)[0]
    return filename.rsplit(".", 1)[0]


def guess_version(filename: str) -> str:
    m = re.search(r"-(\d+\.\d+[\w.]*)\.", filename)
    return m.group(1) if m else ""


def download_package(repo: str, filename: str):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM private_packages WHERE repo=? AND filename=?",
        (repo, filename),
    ).fetchone()
    if not row or not os.path.exists(row["filepath"]):
        raise HTTPException(404, "not found")

    def gen():
        with open(row["filepath"], "rb") as f:
            while chunk := f.read(256 * 1024):
                yield chunk

    return StreamingResponse(gen(), media_type="application/octet-stream",
                             headers={"Content-Length": str(row["size"])})


def simple_index(repo: str, host: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT filename FROM private_packages WHERE repo=? ORDER BY filename",
        (repo,),
    ).fetchall()
    safe_repo = html.escape(repo)
    links = "".join(
        f'<a href="/pkg/{safe_repo}/{html.escape(r["filename"])}">{html.escape(r["filename"])}</a><br>\n'
        for r in rows
    )
    return HTMLResponse(
        f"<html><head><title>{safe_repo}</title></head><body><h1>{safe_repo}</h1>{links}</body></html>"
    )
