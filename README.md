<p align="center">
  <img src="assets/logo.png" width="128" alt="ModernMirror logo">
</p>

<h1 align="center">ModernMirror</h1>

<p align="center"><strong>轻量级、自托管的软件源代理缓存系统。</strong><br>
把 PyPI、npm、Go、Maven、NuGet、RubyGems、apt/yum 等十余种软件源统一缓存到本机，团队内重复安装依赖时不再重复走外网。</p>

<p align="center"><a href="README.en.md">English</a> | 简体中文</p>

> ModernMirror 与 Nexus、Verdaccio 等项目没有关联，是一个独立实现。适合工作室、家庭实验室和内网团队。

## 特性

- **透明代理缓存**：首次请求回源并落盘，后续命中直接读本地磁盘；支持 ETag 条件请求与 `X-Cache-Status` 观测
- **多生态开箱即用**：PyPI、npm、Go Modules、Maven/Gradle/SBT、NuGet、RubyGems、Crates、Conan、Dart pub、Hex、Hackage、CRAN、LuaRocks、CocoaPods，以及任意文件型 apt/yum 源
- **多上游故障转移**：每个仓库可配置主源和多个备用源，按顺序自动切换
- **缓存治理**：按仓库统计命中与占用，支持容量配额、LRU 淘汰、按天数清理和每日自动清理
- **私有包托管**：上传企业内部包，提供直接下载地址和 PEP 503 简单索引
- **用户与权限**：多用户登录、用户组与仓库的读写授权矩阵、成员批量导入
- **MFA 二次认证**：标准 TOTP，兼容任意认证器；支持强制策略和管理员重置
- **API 密钥**：为持续集成和命令行单独签发、随时吊销
- **完整性校验**：PyPI 比对索引哈希，npm 比对 integrity，拒绝写入被篡改的产物
- **国密加密**：密码使用 PBKDF2-SM3，敏感数据使用 SM4 认证加密，兼容旧版数据迁移
- **审计日志**：登录、仓库变更、上传删除、校验失败等事件全部落盘并加密

## 工作原理

```
客户端 pip / npm / curl / apt
        │
        ▼
  /proxy/{仓库名}/{原始路径}
        │
   鉴权与组权限校验
        │
   查询本地缓存 ──命中──▶ 直接读磁盘返回
        │
       未命中
        ▼
   按主备顺序请求上游
        │
   完整性校验 ──失败──▶ 拒绝缓存并记录审计
        │
   原子写入缓存并返回
```

## 快速开始

### 环境要求

- Python 3.11 或更高版本
- Node.js 18 或更高版本，仅首次构建管理界面时需要
- Linux 或 macOS，Windows 建议使用 WSL

### 启动

```bash
git clone <你的仓库地址> ModernMirror
cd ModernMirror
./start.sh
```

首次启动会自动创建虚拟环境、安装依赖、构建前端，并在 `backend/data/` 下生成本地数据。

访问地址：

- 管理界面 `http://localhost:8800/ui/`
- 接口文档 `http://localhost:8800/docs`，需要管理员登录

首次启动会创建管理员 `admin / admin123`。**请立即登录修改密码，并在系统设置中生成 API 密钥。**

### 首次配置建议

1. 登录后进入「系统设置」，修改密码并生成一个 API 密钥
2. 进入「用户组权限」，确认 `default` 组对常用仓库已勾选「可下载」
3. 需要团队使用时，创建用户或使用批量导入，并把用户加入相应用户组
4. 按下方示例把客户端源地址切换到 ModernMirror

## 配置项

所有配置通过环境变量注入，带默认值的项可以省略。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MODERNMIRROR_DATA` | `backend/data` | 数据目录，存放数据库、缓存、私有包、审计日志和主密钥 |
| `MODERNMIRROR_HOST` | `0.0.0.0` | 监听地址 |
| `MODERNMIRROR_PORT` | `8800` | 监听端口 |
| `MODERNMIRROR_TOKEN` | 未设置 | 应急管理员令牌；默认值 `admin-token` 会被刻意忽略 |
| `MODERNMIRROR_ADMIN_USER` | `admin` | 首次初始化时的管理员用户名 |
| `MODERNMIRROR_ADMIN_PASSWORD` | `admin123` | 首次初始化时的管理员密码 |
| `MODERNMIRROR_DB_MASTER_KEY` | 自动生成 | 主密钥；设置后优先于 `数据目录/master.key` |
| `MODERNMIRROR_MAX_MB` | `2048` | 单个代理文件的大小上限 |
| `MODERNMIRROR_MAX_UPLOAD_MB` | `2048` | 单个私有包的大小上限 |
| `MODERNMIRROR_RATE_LIMIT` | `600` | 每 IP 每 60 秒的请求上限 |
| `MODERNMIRROR_SESSION_HOURS` | `24` | 会话初始有效期 |
| `MODERNMIRROR_WEB_SESSION_MINUTES` | `30` | Web 会话滑动过期时间 |

示例：

```bash
MODERNMIRROR_PORT=8800 \
MODERNMIRROR_TOKEN="$(openssl rand -hex 24)" \
MODERNMIRROR_ADMIN_PASSWORD="请替换为强密码" \
./start.sh
```

## 使用方式

统一代理地址格式：

```
http://<主机>:8800/proxy/<仓库名>/<原始路径>
```

鉴权方式按优先级：

1. 请求头 `Session-Token: <API 密钥>`
2. 请求头 `Authorization: Bearer <API 密钥>`
3. HTTP Basic，用户名任意，密码填 API 密钥
4. URL 查询参数 `?token=<API 密钥>`

> 不同客户端对查询参数和重定向的保留行为不同。无法自定义请求头的客户端，推荐使用 Basic 认证，或在反向代理层统一注入 `Session-Token`。

### 各生态示例

**Python / pip**

```bash
pip config set global.index-url "http://mm:<API_KEY>@HOST:8800/proxy/pypi/simple/"
pip install requests
```

**Node.js / npm**

```bash
npm config set registry "http://HOST:8800/proxy/npm/"
npm config set //HOST:8800/:_authToken "<API_KEY>"
npm install antd
```

**Go Modules**

```bash
export GOPROXY="http://HOST:8800/proxy/go/"
go get example.com/module@latest
```

Go 客户端不支持自定义鉴权头时，请通过反向代理注入请求头，或仅在可信内网中使用。

**Maven / Gradle**

```xml
<mirror>
  <id>modernmirror</id>
  <mirrorOf>central</mirrorOf>
  <url>http://HOST:8800/proxy/maven/</url>
</mirror>
```

**apt / 任意文件型仓库**

仓库类型选择「通用文件」，上游填写 `https://deb.debian.org`，然后：

```bash
# 支持 Basic 认证的客户端可把凭据写入源地址
deb http://mm:<API_KEY>@HOST:8800/proxy/debian bookworm main
```

**curl**

```bash
curl -H "Session-Token: <API_KEY>" \
  -O "http://HOST:8800/proxy/raw/path/to/file.tar.gz"
```

## 私有包托管

在管理界面「私有包」页选择仓库并上传，或使用接口：

```bash
curl -H "Session-Token: <API_KEY>" \
  -F "file=@my-package-1.0.0.whl" \
  "http://HOST:8800/admin/packages/my-repo"
```

下载与索引：

```
/pkg/<仓库名>/<文件名>
/simple/<仓库名>
```

上传时自动计算 SHA256 并入库；重复上传同名文件会覆盖。上传权限由用户组矩阵控制，管理员可以直接上传。

## 权限模型

```
管理员角色
 ├── 用户管理：增删用户、改角色、重置密码、重置 MFA、启停
 ├── 用户组：成员管理、仓库权限矩阵、批量导入
 └── 系统管理：仓库、缓存、审计、设置

用户组 × 仓库
 ├── 可下载：访问 /proxy /pkg /simple
 └── 可上传：向该仓库上传私有包
```

需要特别注意：

- **管理员访问代理源同样需要组授权。** 管理员身份只影响管理接口，不会绕过仓库权限
- 新用户会自动加入 `default` 组，但该组仍需被授予仓库权限
- 管理员上传私有包时不受组权限限制
- 被禁用的用户无法登录，已有会话会立即失效
- 系统会阻止删除或禁用最后一个启用的管理员

## MFA 与 API 密钥

- 在「系统设置」中为自己的账号绑定 TOTP，支持 Google Authenticator、Microsoft Authenticator、1Password 等
- 管理员可以在「用户管理」中重置其他用户的 MFA
- 开启「强制 MFA」后，未绑定 MFA 的普通用户将无法访问管理接口；管理员保留应急通道
- API 密钥只显示一次，数据库仅保存 SM3 哈希，可随时吊销
- 旧版密钥在首次使用后会自动升级为国密哈希

## 安全设计

- **上游强制 HTTPS**：添加或修改仓库时拒绝明文 HTTP 上游，降低中间人替换风险
- **产物校验**：PyPI 产物比对 simple 索引中的 SHA256 或 MD5，npm 产物比对 `dist.integrity`；不一致时拒绝缓存并返回 502
- **默认加密**：首次启动自动生成主密钥，审计日志和 MFA 密钥默认使用国密加密；密码使用 PBKDF2-SM3
- **会话安全**：会话令牌只存哈希，支持滑动过期和立即吊销；禁用用户即时失效
- **路径安全**：缓存文件按摘要寻址，上传文件名只取 basename，仓库名有字符白名单
- **容量与限流**：单文件上限、上传上限、每 IP 限流，避免磁盘耗尽和滥用
- **审计留痕**：登录失败、权限变更、上传删除、校验失败等关键事件加密落盘

部署到公网前请务必：

1. 设置强随机 `MODERNMIRROR_TOKEN`
2. 使用 Nginx、Caddy 等反向代理提供 HTTPS，不要把 8800 端口直接暴露到公网
3. 备份 `数据目录/master.key`，丢失后加密数据无法恢复
4. 定期备份数据库与私有包目录

## 数据与备份

```
backend/data/
├── modernmirror.db      SQLite 数据库
├── master.key           数据加密主密钥
├── audit.log            加密审计日志
├── cache/               代理缓存，可随时删除
└── private/             私有包文件
```

需要备份的是 `modernmirror.db`、`master.key` 和 `private/`。缓存目录不备份也能重建。

## 管理接口

所有管理接口都需要管理员会话或令牌。

```
GET    /admin/repos                 仓库列表
POST   /admin/repos                 新建仓库
PUT    /admin/repos/{name}          修改仓库
DELETE /admin/repos/{name}          删除仓库
GET    /admin/ping                  上游延迟探测
GET    /admin/stats                 缓存统计
POST   /admin/cache/cleanup         按天数清理缓存
GET    /admin/users                 用户列表
POST   /admin/users                 新建用户
PUT    /admin/users/{name}          修改用户
DELETE /admin/users/{name}          删除用户
GET    /admin/groups                用户组与权限
POST   /admin/groups                新建用户组
POST   /admin/groups/{id}/members   添加成员
POST   /admin/groups/{id}/members/import  批量导入成员
POST   /admin/groups/{id}/repos/{repo}    设置仓库权限
GET    /admin/packages              私有包列表
POST   /admin/packages/{repo}       上传私有包
GET    /admin/audit                 审计日志
GET    /admin/settings              系统设置
PUT    /admin/settings              更新系统设置
```

完整的请求与响应定义见 `/docs`。

## 开发

后端：

```bash
cd backend
python3.12 -m venv venv
./venv/bin/pip install -r requirements.txt
MODERNMIRROR_PORT=8800 ./venv/bin/python -m app.main
```

前端开发服务器：

```bash
cd frontend
npm install
npm run dev
```

开发服务器运行在 `http://localhost:5173/ui/`，接口请求会代理到 `http://localhost:8800`。

冒烟测试：

```bash
cd backend
./venv/bin/python tests/smoke.py
```

## 系统服务

`deploy/` 目录提供了 systemd 单元和环境变量示例，可按需修改路径后安装。

## 常见问题

**请求返回 401 或 403**

401 表示未登录或凭据失效，403 表示已登录但缺少该仓库权限。请检查用户组授权，以及管理员是否也加入了对应用户组。

**返回 502 且提示校验不匹配**

上游返回的文件与官方元数据中的哈希不一致，系统已拒绝缓存。请更换可信上游，并在审计日志中查看期望值与实际值。

**客户端仍然拿到旧版本**

部分客户端有本地索引缓存，清理客户端缓存后重试。代理缓存也可以通过「缓存统计」页面清理。

**端口被占用**

修改 `MODERNMIRROR_PORT`，或停止占用端口的进程后重启。

**忘记管理员密码**

优先通过其他管理员账号重置。若没有其他管理员，请备份数据后删除数据库重新初始化。`master.key` 不要删除。

## 贡献

欢迎提交 Issue 和 Pull Request，请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。安全相关问题请不要公开提交 Issue，参见 [SECURITY.md](SECURITY.md)。

## 许可证

[MIT](LICENSE)

ModernMirror 按现状提供，不对外部软件源的可用性、完整性或合规性作出承诺。请确保你对所代理的软件源拥有合法访问和使用权利。
