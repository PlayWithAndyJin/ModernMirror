import json
import os
import time

from . import config


def audit(event: str, client_ip: str, detail: dict):
    from . import auth as _auth

    line = json.dumps(
        {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event, "ip": client_ip, **detail}
    )
    encrypted = _auth.encrypt_mfa_secret(line)
    if encrypted.startswith("enc:sm4:"):
        mode = "sm"
    elif encrypted.startswith("enc:v1:"):
        mode = "enc"
    else:
        mode = "plain"
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(config.AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(f"{mode}|{encrypted}\n")


class RateLimiter:
    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self.buckets = {}
        self.last_cleanup = time.time()

    def check(self, key: str):
        now = time.time()
        if now - self.last_cleanup > 120:
            self.buckets = {k: v for k, v in self.buckets.items() if now - v["start"] < self.window * 4}
            self.last_cleanup = now
        b = self.buckets.setdefault(key, {"start": now, "n": 0})
        if now - b["start"] > self.window:
            b["start"], b["n"] = now, 0
        b["n"] += 1
        return b["n"] <= self.limit
