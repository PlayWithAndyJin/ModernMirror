---
name: modernmirror-config
description: 将本机的 pip, npm, Go, Maven/Gradle, apt/yum 等软件源配置为指向用户自建的 ModernMirror 镜像缓存服务, 含备份与回滚; 也可协助管理员生成成员批量导入模板并执行导入。当用户要求把本机软件源切换到 ModernMirror、配置内部镜像源, 或批量导入成员时使用。
---

# ModernMirror 本机软件源配置

将用户设备上一个或多个包管理器的默认源切换为指向其自建的 ModernMirror 服务, 全程保留备份以便回滚。

服务端参数须向用户确认, 未知必须先询问:
- HOST: 服务地址, 如 192.168.1.10
- PORT: 服务端口, 默认 8800
- TOKEN: API 密钥, 在应用 Web 界面 系统设置 - API 密钥管理 中生成

通用代理地址格式:
`http://$HOST:$PORT/proxy/<仓库名>/?token=$TOKEN`

## 执行原则
1. 修改任何配置前, 先备份原文件为同目录 .bak-mm 后缀。
2. 一次只处理一个生态, 完成后立即执行该生态的验证命令。
3. TOKEN 只写入包管理器自身配置或用户 shell 环境文件, 不写入项目代码文件。
4. 请求 401/403 时提示检查密钥与用户组权限（注意:即使是管理员也要将自己添加到相应用户组）; 502 或哈希校验失败时建议查看应用审计日志。

## 各生态操作

所有生态的操作逻辑一致, 仅"配置入口文件位置"不同:
1. 确认镜像仓库页面已存在对应类型的仓库。
2. 将该生态配置文件中的默认源地址替换为通用代理地址 `http://$HOST:$PORT/proxy/<仓库名>/?token=$TOKEN`。
3. 修改前后均以 curl 验证代理地址可达, 修改后执行一次该生态的默认安装/查询命令进行验证。
4. 回滚时恢复修改前的备份文件。

通用示例 - 验证代理可达:
`curl "http://$HOST:$PORT/proxy/<仓库名>/?token=$TOKEN"`

通用示例 - 环境变量型源 (适用于 GOPROXY 等):
`export <生态的源环境变量>="http://$HOST:$PORT/proxy/<仓库名>/?token=$TOKEN"`

常见的配置文件型源 (pip/npm/Maven 等) 做法:
`<生态的源配置命令/文件> 设置默认源为 "http://$HOST:$PORT/proxy/<对应仓库名>/?token=$TOKEN"`

## 成员批量导入

当管理员提供成员名单时, 可协助生成 ModernMirror 支持的模板文件并完成导入。

### 文件格式
支持 CSV / JSON / TOML / TXT, 模板可在应用内 用户组权限 -> 批量导入 中下载。

字段:
- username: 必填, 仅允许字母、数字、下划线、短横线, 长度 2 至 32 位。
- password: 可选; 留空时系统生成随机密码, 结果中只显示一次。
- role: 可选, user 或 admin, 缺省为 user; 使用 admin 前必须与用户确认。
- groups: 可选, 多个组用逗号分隔或数组表示; 留空时加入执行导入的当前组; 不存在的组会自动创建。

示例 CSV:
```
username,password,role,groups
alice,ChangeMe123,user,"devteam,qa"
bob,,user,devteam
```

### 生成与校验规则
1. 优先使用 CSV; 含逗号的多值字段必须使用双引号包裹。
2. 文件须为 UTF-8 编码, 且 CSV 首行为字段名。
3. 不要编造弱密码; 未提供初始密码时留空由系统生成, 并在导入后立即提示用户保存。
4. 不要将密码写入日志、截图或项目代码。

### 通过接口导入
1. 查询目标组 ID:
   `curl -s -H "X-Auth-Token: $TOKEN" "http://$HOST:$PORT/admin/groups"`
2. 上传文件:
   `curl -s -H "X-Auth-Token: $TOKEN" -F "file=@members.csv" "http://$HOST:$PORT/admin/groups/<组ID>/members/import"`
3. 将返回中的 created / added_to_group / errors 汇总给用户; 初始密码仅在 created 中返回一次。
4. 若返回 403, 确认 $TOKEN 属于管理员账号; 若 400, 按返回的中文原因修正文件后重试。

## 收尾
1. 列出本次全部被修改的文件与对应回滚命令, 供用户核对。
2. 提醒用户在 ModernMirror 的 缓存统计 页面确认命中率上升, 证明配置已生效。
