# 贡献指南

感谢你愿意改进 ModernMirror。提交代码前请先阅读以下约定。

## 开发环境

```bash
cd backend
python3.12 -m venv venv
./venv/bin/pip install -r requirements.txt

cd ../frontend
npm install
```

启动后端：

```bash
cd backend
MODERNMIRROR_PORT=8800 ./venv/bin/python -m app.main
```

启动前端开发服务器：

```bash
cd frontend
npm run dev
```

开发服务器地址为 `http://localhost:5173/ui/`，接口请求会代理到后端。

## 提交前检查

```bash
cd backend
./venv/bin/python tests/smoke.py
./venv/bin/python -m compileall -q app

cd ../frontend
npm run build
```

请确保：

- 不提交 `backend/data/`、数据库、缓存、审计日志、`master.key` 和 `.env`
- 不提交 `frontend/dist/` 与 `node_modules/`
- 不把真实上游凭据、内网地址或个人信息写入代码与示例
- 新增行为有对应文档更新

## 代码风格

- 后端使用 FastAPI 与标准库，保持函数短小，错误通过 `HTTPException` 返回
- 前端使用 React 18 与 Ant Design 5，页面组件放在 `frontend/src/pages/`
- 注释只保留必要的说明，统一使用中文短句，不使用括号、横杠等装饰符号
- 数据库变更必须通过 `backend/app/db.py` 中的兼容迁移完成，不能破坏已有数据
- 加密相关改动需要同时考虑旧数据读取和迁移路径

## 提交信息

提交信息使用简洁的中文或英文，说明做了什么以及为什么。一个提交只做一件事，避免把格式化与功能改动混在一起。

## 合并请求

请在合并请求中说明：

- 改动目的与用户可见行为
- 涉及的配置或数据迁移
- 已验证的场景与命令
- 是否存在安全影响

涉及权限、加密、缓存校验或文件路径的改动会被重点审查。
