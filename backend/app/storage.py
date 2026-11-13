import hashlib
import os
import sqlite3

import aiofiles

from . import config


def _safe_path(repo: str, path: str) -> str:
    digest = hashlib.sha256(f"{repo}:{path}".encode()).hexdigest()
    return os.path.join(config.CACHE_DIR, repo, digest[:2], digest)


def tmp_dir():
    """与缓存目录同盘的临时目录，保证重命名的原子性。"""
    d = os.path.join(config.DATA_DIR, "tmp")
    os.makedirs(d, exist_ok=True)
    return d


async def save_async(tmp_path: str, repo: str, path: str) -> str:
    target = _safe_path(repo, path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.replace(tmp_path, target)
    return target


def open_stream(file_path: str, chunk_size: int = 64 * 1024):
    async def gen():
        async with aiofiles.open(file_path, "rb") as f:
            while True:
                chunk = await f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    return gen()


def cleanup_keep_last_n(days: int = 0) -> int:
    conn = sqlite3.connect(config.DB_PATH)
    total_freed = 0
    if days <= 0:
        cur = conn.execute(
            "SELECT id, file_path, size FROM cache_entries"
        )
    else:
        cur = conn.execute(
            "SELECT id, file_path, size FROM cache_entries "
            "WHERE (last_hit_at IS NULL AND fetched_at < datetime('now', 'localtime', ?)) "
            "OR last_hit_at < datetime('now', 'localtime', ?)",
            (f"-{days} days", f"-{days} days"),
        )
    rows = cur.fetchall()
    for row in rows:
        try:
            if os.path.exists(row[1]):
                os.remove(row[1])
                total_freed += row[2]
        except OSError:
            pass
    conn.executemany("DELETE FROM cache_entries WHERE id = ?", [(r[0],) for r in rows])
    conn.commit()
    conn.close()
    _prune_dirs()
    return total_freed


def _prune_dirs():
    for root, dirs, files in os.walk(config.CACHE_DIR, topdown=False):
        if not os.listdir(root) and root != config.CACHE_DIR:
            os.rmdir(root)


def dir_size(path: str) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def repo_usage(repo: str) -> int:
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute(
        "SELECT coalesce(sum(size),0) s FROM cache_entries WHERE repo=?", (repo,)
    ).fetchone()
    conn.close()
    return int(row[0])


def enforce_quota(repo: str, quota_mb: int) -> int:
    if not quota_mb or quota_mb <= 0:
        return 0

    limit = quota_mb * 1024 * 1024
    conn = sqlite3.connect(config.DB_PATH)
    total = conn.execute(
        "SELECT coalesce(sum(size),0) s FROM cache_entries WHERE repo=?", (repo,)
    ).fetchone()[0]
    if total <= limit:
        conn.close()
        return 0
    target = int(limit * 0.9)
    rows = conn.execute(
        "SELECT id, file_path, size FROM cache_entries WHERE repo=? "
        "ORDER BY coalesce(last_hit_at,'') ASC, hits ASC",
        (repo,),
    ).fetchall()
    freed = 0
    for row in rows:
        if total <= target:
            break
        try:
            if os.path.exists(row[1]):
                os.remove(row[1])
        except OSError:
            pass
        conn.execute("DELETE FROM cache_entries WHERE id=?", (row[0],))
        total -= row[2]
        freed += row[2]
    conn.commit()
    conn.close()
    _prune_dirs()
    return freed
