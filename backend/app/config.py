import os
import secrets
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("MODERNMIRROR_DATA", os.path.join(BASE_DIR, "data"))
DB_PATH = os.path.join(DATA_DIR, "modernmirror.db")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
PRIVATE_DIR = os.path.join(DATA_DIR, "private")
ADMIN_TOKEN = os.environ.get("MODERNMIRROR_TOKEN", "admin-token")
HOST = os.environ.get("MODERNMIRROR_HOST", "0.0.0.0")
PORT = int(os.environ.get("MODERNMIRROR_PORT", "8800"))
MAX_UPSTREAM_MB = int(os.environ.get("MODERNMIRROR_MAX_MB", "2048"))
MAX_UPLOAD_MB = int(os.environ.get("MODERNMIRROR_MAX_UPLOAD_MB", "2048"))
RATE_LIMIT = int(os.environ.get("MODERNMIRROR_RATE_LIMIT", "600"))
RATE_WINDOW = 60
AUDIT_LOG = os.path.join(DATA_DIR, "audit.log")
MASTER_KEY_PATH = os.path.join(DATA_DIR, "master.key")


def _load_master_key():
    """主密钥优先取环境变量，其次读取数据目录中的密钥文件，首次启动时自动生成。

    自动生成是为了让默认部署也处于国密加密状态，
    避免审计日志和多因素认证密钥静默降级为明文。
    """
    env_key = os.environ.get("MODERNMIRROR_DB_MASTER_KEY", "").strip()
    if env_key:
        return env_key, "env"

    try:
        with open(MASTER_KEY_PATH, "r", encoding="utf-8") as f:
            key = f.read().strip()
        if key:
            return key, "file"
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise RuntimeError(f"无法读取主密钥 {MASTER_KEY_PATH}: {exc}") from exc

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        key = secrets.token_hex(32)
        fd = os.open(MASTER_KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(key + "\n")
        return key, "generated"
    except FileExistsError:
        # 多进程首次启动时以先写入的密钥为准
        for _ in range(20):
            try:
                with open(MASTER_KEY_PATH, "r", encoding="utf-8") as f:
                    key = f.read().strip()
            except OSError:
                key = ""
            if key:
                return key, "file"
            time.sleep(0.05)
        raise RuntimeError(
            f"主密钥文件 {MASTER_KEY_PATH} 为空, 请删除后重启以重新生成, 或显式设置 MODERNMIRROR_DB_MASTER_KEY"
        )
    except OSError as exc:
        raise RuntimeError(
            f"无法创建主密钥 {MASTER_KEY_PATH}: {exc}. "
            "请检查数据目录权限, 或通过 MODERNMIRROR_DB_MASTER_KEY 显式指定。"
        ) from exc


DB_MASTER_KEY, MASTER_KEY_SOURCE = _load_master_key()
