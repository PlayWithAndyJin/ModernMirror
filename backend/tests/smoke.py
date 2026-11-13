"""端到端冒烟测试，覆盖登录、权限、私有包、禁用用户和加密默认值。"""

import base64
import os
import pathlib
import shutil
import stat
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="modernmirror-smoke-")
os.environ["MODERNMIRROR_DATA"] = TMP
os.environ["MODERNMIRROR_TOKEN"] = "smoke-cli-token"
os.environ.pop("MODERNMIRROR_DB_MASTER_KEY", None)

from fastapi.testclient import TestClient

from app import proxy
from app.main import app


def main():
    try:
        with TestClient(app) as c:
            assert c.get("/api/health").json()["status"] == "ok"
            assert c.get("/api/whoami").json()["user"] is None

            token = c.post(
                "/auth/login", json={"username": "admin", "password": "admin123"}
            ).json()["token"]
            headers = {"Session-Token": token}
            assert c.get("/api/whoami", headers=headers).json()["user"]["role"] == "admin"

            key_path = os.path.join(TMP, "master.key")
            assert os.path.exists(key_path)
            assert stat.S_IMODE(os.stat(key_path).st_mode) == 0o600

            bad = c.post(
                "/admin/repos",
                headers=headers,
                json={"name": "../x", "type": "raw", "upstream": "https://example.com"},
            )
            assert bad.status_code == 400
            created = c.post(
                "/admin/repos",
                headers=headers,
                json={
                    "name": "testrepo",
                    "type": "raw",
                    "upstream": "https://example.com",
                    "upstreams": ["https://example.com", "https://example.org"],
                    "quota_mb": 10,
                },
            )
            assert created.status_code == 200, created.text

            groups = c.get("/admin/groups", headers=headers).json()
            default_group = [g for g in groups if g["name"] == "default"][0]
            assert "admin" in default_group["members"]
            granted = c.post(
                f"/admin/groups/{default_group['id']}/repos/testrepo",
                headers=headers,
                json={"can_download": True, "can_upload": True},
            )
            assert granted.status_code == 200

            uploaded = c.post(
                "/admin/packages/testrepo",
                headers=headers,
                files={"file": ("demo-1.0.bin", b"hello world", "application/octet-stream")},
            )
            assert uploaded.status_code == 200, uploaded.text
            assert uploaded.json()["sha256"]
            assert c.get("/pkg/testrepo/demo-1.0.bin", headers=headers).content == b"hello world"
            assert "demo-1.0.bin" in c.get("/simple/testrepo", headers=headers).text

            api_key = c.post(
                "/auth/tokens", headers=headers, json={"name": "smoke"}
            ).json()["token"]
            basic = base64.b64encode(f"mm:{api_key}".encode()).decode()
            who = c.get("/api/whoami", headers={"Authorization": f"Basic {basic}"})
            assert who.json()["user"]["username"] == "admin"
            assert c.get(
                "/api/whoami", headers={"Authorization": f"Bearer {api_key}"}
            ).json()["user"]["username"] == "admin"

            assert c.post(
                "/admin/users",
                headers=headers,
                json={"username": "tester", "password": "password123", "role": "user"},
            ).status_code == 200
            user_token = c.post(
                "/auth/login", json={"username": "tester", "password": "password123"}
            ).json()["token"]
            user_headers = {"Session-Token": user_token}
            assert c.get("/api/whoami", headers=user_headers).json()["user"]["username"] == "tester"
            assert c.put(
                "/admin/users/tester", headers=headers, json={"enabled": False}
            ).status_code == 200
            assert c.get("/api/whoami", headers=user_headers).json()["user"] is None
            assert c.post(
                "/auth/login", json={"username": "tester", "password": "password123"}
            ).status_code == 403
            assert c.put(
                "/admin/users/admin", headers=headers, json={"enabled": False}
            ).status_code == 400

            cli = {"X-Auth-Token": "smoke-cli-token"}
            assert c.get("/admin/repos", headers=cli).status_code == 200
            assert c.get("/proxy/testrepo/x", headers=cli).status_code == 403
            assert c.get("/proxy/testrepo/x", headers=user_headers).status_code == 401

            entry = {
                "file_path": os.path.join(TMP, "range.bin"),
                "size": 11,
                "content_type": "application/octet-stream",
                "etag": None,
            }
            with open(entry["file_path"], "wb") as f:
                f.write(b"hello world")
            partial = proxy.seek_range(entry, "bytes=0-4", "hit")
            assert partial.status_code == 206
            assert partial.headers["content-range"] == "bytes 0-4/11"
            assert partial.headers["x-cache-status"] == "hit"
            tail = proxy.seek_range(entry, "bytes=-5", "hit")
            assert tail.status_code == 206
            assert tail.headers["content-range"] == "bytes 6-10/11"
            assert proxy.seek_range(entry, "bytes=99-100", "hit").status_code == 416

            lines = [l for l in open(os.path.join(TMP, "audit.log"), encoding="utf-8") if l.strip()]
            assert lines and all(l.startswith("sm|") for l in lines)
            print("smoke ok")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
