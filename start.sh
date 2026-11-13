#!/bin/bash
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "!! 需要 Python 3.11 或更高版本 (当前: $("$PY" --version 2>&1))" >&2
  echo "   可通过 PYTHON=/path/to/python3.12 ./start.sh 指定解释器" >&2
  exit 1
fi

if [ ! -x backend/venv/bin/python ]; then
  echo ">> 创建 Python 虚拟环境..."
  "$PY" -m venv backend/venv
fi

# 依赖清单变化时才重新安装
STAMP=backend/venv/.requirements.sha256
REQ_SUM=$("$PY" -c "import hashlib; print(hashlib.sha256(open('backend/requirements.txt','rb').read()).hexdigest())")
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$REQ_SUM" ]; then
  echo ">> 安装 Python 依赖..."
  backend/venv/bin/pip install -q --disable-pip-version-check -r backend/requirements.txt
  echo "$REQ_SUM" > "$STAMP"
fi

if [ ! -f frontend/dist/index.html ]; then
  echo ">> 构建前端..."
  if [ ! -d frontend/node_modules ]; then
    (cd frontend && { [ -f package-lock.json ] && npm ci || npm install; })
  fi
  (cd frontend && npm run build)
fi

echo ">> 启动 ModernMirror (http://localhost:${MODERNMIRROR_PORT:-8800})"
cd backend
exec ./venv/bin/python -m app.main
