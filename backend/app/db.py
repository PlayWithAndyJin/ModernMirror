import json
import os
import shutil
import sqlite3
import threading

from . import config

_lock = threading.Lock()
_inited_paths = set()


def get_db():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    # 建表和补列只在进程内首次连接时执行
    if config.DB_PATH not in _inited_paths:
        with _lock:
            if config.DB_PATH not in _inited_paths:
                _init(conn)
                _inited_paths.add(config.DB_PATH)
    return conn


def _init(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL,
            upstream TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS cache_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT NOT NULL,
            path TEXT NOT NULL,
            upstream_url TEXT NOT NULL,
            file_path TEXT NOT NULL,
            size INTEGER NOT NULL,
            content_type TEXT,
            etag TEXT,
            fetched_at TEXT,
            last_hit_at TEXT,
            hits INTEGER NOT NULL DEFAULT 0,
            UNIQUE(repo, path)
        );
        CREATE TABLE IF NOT EXISTS private_packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT NOT NULL,
            name TEXT NOT NULL,
            version TEXT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            size INTEGER NOT NULL,
            sha256 TEXT,
            uploader TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(repo, filename)
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            mfa_secret TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            username TEXT NOT NULL,
            expires TEXT NOT NULL,
            mfa_state INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS user_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            group_id INTEGER NOT NULL,
            UNIQUE(username, group_id)
        );
        CREATE TABLE IF NOT EXISTS group_repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            repo TEXT NOT NULL,
            can_download INTEGER NOT NULL DEFAULT 1,
            can_upload INTEGER NOT NULL DEFAULT 0,
            UNIQUE(group_id, repo)
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS api_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            name TEXT NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            token_prefix TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            last_used_at TEXT,
            revoked INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    try:
        conn.execute("ALTER TABLE cache_entries ADD COLUMN verified INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    for stmt in [
        "ALTER TABLE users ADD COLUMN password_algo TEXT NOT NULL DEFAULT 'sha256'",
        "ALTER TABLE api_tokens ADD COLUMN token_algo TEXT NOT NULL DEFAULT 'sha256'",
        "ALTER TABLE repos ADD COLUMN upstreams TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE repos ADD COLUMN quota_mb INTEGER NOT NULL DEFAULT 0",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.commit()


def backfill_repos():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT name, upstream, upstreams FROM repos").fetchall()
    for row in rows:
        try:
            arr = json.loads(row["upstreams"] or "[]")
        except Exception:
            arr = []
        if not arr and row["upstream"]:
            conn.execute("UPDATE repos SET upstreams=? WHERE name=?",
                         (json.dumps([row["upstream"]]), row["name"]))
    conn.commit()
    conn.close()


def seed_admin():
    from . import auth

    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    # 默认组必须先于成员关系创建，否则首次安装时管理员入组会落空
    conn.execute(
        "INSERT OR IGNORE INTO groups (name, description) VALUES ('default', '默认组,新增用户自动加入')"
    )
    wizard_user = os.environ.get("MODERNMIRROR_ADMIN_USER", "admin").strip()
    wizard_pass = os.environ.get("MODERNMIRROR_ADMIN_PASSWORD", "admin123")
    is_first_install = conn.execute("SELECT count(*) c FROM users").fetchone()["c"] == 0

    if is_first_install:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, password_algo) "
            "VALUES (?,?, 'admin', 'sm3')",
            (wizard_user, auth.hash_password(wizard_pass)),
        )
        conn.execute(
            "INSERT OR IGNORE INTO user_groups (username, group_id) "
            "SELECT ?, id FROM groups WHERE name='default'",
            (wizard_user,),
        )
    elif bool(wizard_pass and wizard_pass != "admin123"):
        status = os.environ.get("TRIM_APP_STATUS", "")
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('admin_provisioned','0')")
        stated = conn.execute("SELECT value FROM settings WHERE key='admin_provisioned'").fetchone()["value"]
        if stated in ("", "0") or status == "CONFIG":
            row = conn.execute("SELECT username FROM users WHERE username=? AND role='admin'", (wizard_user,)).fetchone()
            if row:
                conn.execute("UPDATE users SET password_hash=?, password_algo='sm3' WHERE username=?",
                             (auth.hash_password(wizard_pass), wizard_user))
            else:
                base = conn.execute(
                    "SELECT username FROM users WHERE role='admin' LIMIT 1").fetchone()
                if base and base["username"] == "admin":
                    conn.execute("UPDATE users SET username=?, password_hash=?, password_algo='sm3' WHERE username='admin'",
                                 (wizard_user, auth.hash_password(wizard_pass)))
            # 向导配置视为新的身份基线，清除历史绑定和会话
            conn.execute("UPDATE users SET mfa_secret=NULL WHERE username=? AND role='admin'", (wizard_user,))
            conn.execute("DELETE FROM sessions WHERE username=?", (wizard_user,))
            # 管理员也需要加入用户组才能获得代理权限
            conn.execute(
                "INSERT OR IGNORE INTO user_groups (username, group_id) "
                "SELECT ?, id FROM groups WHERE name='default'",
                (wizard_user,),
            )
            conn.execute("UPDATE settings SET value='1' WHERE key='admin_provisioned'")
    else:
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('admin_provisioned','1')")

    conn.commit()
    conn.close()


def seed():
    conn = get_db()
    backfill_repos()
    with _lock:
        for name, rtype, upstream in [
            ("pypi", "pypi", "https://pypi.org"),
            ("npm", "npm", "https://registry.npmjs.org"),
            ("debian", "raw", "https://deb.debian.org"),
            ("alpine", "raw", "https://dl-cdn.alpinelinux.org"),
        ]:
            conn.execute(
                "INSERT OR IGNORE INTO repos (name, type, upstream, upstreams) VALUES (?,?,?,?)",
                (name, rtype, upstream, json.dumps([upstream])),
            )
        try:
            conn.execute("ALTER TABLE cache_entries ADD COLUMN verified INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE private_packages ADD COLUMN verified INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.commit()
    conn.close()


def migrate_crypto_data():
    """把旧版密文迁移为国密，使旧会话失效并标记需要重置的密码。"""
    from . import crypto

    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('crypto_version','0')")
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('password_reset_needed','0')")
    conn.commit()
    version = int(conn.execute("SELECT value FROM settings WHERE key='crypto_version'").fetchone()["value"] or 0)
    if version >= 2 or not config.DB_MASTER_KEY:
        conn.close()
        return

    rows = conn.execute("SELECT username, mfa_secret FROM users WHERE mfa_secret IS NOT NULL").fetchall()
    for row in rows:
        secret = row["mfa_secret"]
        if crypto.is_legacy_cipher(secret):
            plain = crypto.decrypt_text(secret)
            conn.execute("UPDATE users SET mfa_secret=? WHERE username=?",
                         (crypto.encrypt_text(plain), row["username"]))
    pending = conn.execute("SELECT key, value FROM settings WHERE key LIKE 'pending_mfa:%'").fetchall()
    for row in pending:
        if row["value"] and crypto.is_legacy_cipher(row["value"]):
            plain = crypto.decrypt_text(row["value"])
            conn.execute("UPDATE settings SET value=? WHERE key=?", (crypto.encrypt_text(plain), row["key"]))
    log = config.AUDIT_LOG
    if os.path.exists(log):
        rewritten = []
        changed = False
        with open(log, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.startswith("enc|") and "enc:v1:" in line:
                    try:
                        plain = crypto.decrypt_text(line[4:])
                        rewritten.append("sm|" + crypto.encrypt_text(plain))
                        changed = True
                        continue
                    except Exception:
                        pass
                rewritten.append(line)
        if changed:
            shutil.copyfile(log, log + ".legacy.bak")
            with open(log, "w", encoding="utf-8") as f:
                f.write("\n".join(rewritten) + "\n")
    conn.execute("DELETE FROM sessions")
    legacy_pw = conn.execute(
        "SELECT count(*) c FROM users WHERE password_hash NOT LIKE 'sm3$%'").fetchone()["c"]
    conn.execute("UPDATE settings SET value=? WHERE key='password_reset_needed'",
                 ("1" if legacy_pw > 0 else "0",))
    conn.execute("UPDATE settings SET value='2' WHERE key='crypto_version'")
    conn.commit()
    conn.close()
