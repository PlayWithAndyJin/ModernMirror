import React from 'react'
import { Button, Card, Typography } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'

const { Text, Paragraph, Title } = Typography

const Block = ({ id, title, children }) => (
  <Card id={id} style={{ marginBottom: 16 }}>
    <Title level={5} style={{ marginTop: 0, marginBottom: 12 }}>{title}</Title>
    {children}
  </Card>
)

const Code = ({ children }) => (
  <pre
    style={{
      background: '#0f172a', color: '#d4e2ff', padding: 12, borderRadius: 8,
      fontSize: 12, lineHeight: 1.7, margin: '8px 0', whiteSpace: 'pre-wrap'
    }}
  >
    {children}
  </pre>
)

const Li = ({ children }) => <li style={{ lineHeight: 2 }}>{children}</li>

export default function Docs() {
  const toc = [
    ['sec-overview', '简介与工作原理'],
    ['sec-quickstart', '接入流程'],
    ['sec-url', '通用代理地址'],
    ['sec-packages', '私有包托管'],
    ['sec-groups', '用户组与权限'],
    ['sec-token', 'API 密钥'],
    ['sec-mfa', 'MFA 二次认证'],
    ['sec-stats', '缓存统计与清理'],
    ['sec-api', '开放接口文档'],
    ['sec-cli', '命令行速查'],
    ['sec-faq', '常见问题']
  ]

  return (
    <>
      <Card style={{ marginBottom: 16 }}>
        <Title level={4} style={{ marginBottom: 8 }}>ModernMirror 使用文档</Title>
        <ol style={{ margin: 0, paddingLeft: 20 }}>
          {toc.map(([id, label]) => (
            <Li key={id}>
              <a
                href={`#${id}`}
                onClick={(e) => {
                  e.preventDefault()
                  const el = document.getElementById(id)
                  el && el.scrollIntoView({ behavior: 'smooth', block: 'start' })
                }}
              >
                {label}
              </a>
            </Li>
          ))}
        </ol>
        <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid #eceef2' }}>
          <Paragraph style={{ marginBottom: 8 }}>
            为了提高工作效率，您可以直接下载技能包并配置给大模型助手帮助您完成需要的配置。
          </Paragraph>
          <a
            href={`/skill/modernmirror-config/SKILL.md?token=${encodeURIComponent(sessionStorage.getItem('modernmirror_session') || '')}`}
            target="_blank"
            rel="noreferrer"
          >
            <Button type="primary" icon={<DownloadOutlined />}>
              下载 AI 配置 Skill
            </Button>
          </a>
        </div>
      </Card>

      <Block id="sec-overview" title="一、简介与工作原理">
        <Paragraph>
          ModernMirror 是部署于本机的软件源代理与缓存管理系统。客户端将其默认索引地址指向本应用后,
          依赖下载将经由本机代理完成: 系统首先检索本地缓存, 若命中则直接从磁盘读取并返回;
          若未命中, 则向上游仓库发起下载, 产物写入本地缓存后再次返回。可显著降低重复安装的带宽开销并缩短下载时间。
        </Paragraph>
        <Paragraph>处理单个请求的基本流程如下:</Paragraph>
        <ol style={{ paddingLeft: 20 }}>
          <Li>客户端按配置的索引地址向本应用发起下载请求。</Li>
          <Li>系统校验登录态及其对相应仓库的下载权限。</Li>
          <Li>查询本地缓存, 命中时直接从磁盘读取文件返回。</Li>
          <Li>未命中时向上游仓库拉取产物, 完成完整性校验后写入缓存并返回。</Li>
          <Li>响应头 X-Cache-Status 可用于观测 hit / fresh / revalidated / stale 四种状态。</Li>
        </ol>
      </Block>

      <Block id="sec-quickstart" title="二、接入流程">
        <ol style={{ paddingLeft: 20 }}>
          <Li>使用管理员账号登录管理界面。</Li>
          <Li>进入系统设置中的 API 密钥管理, 生成一个用于客户端访问的密钥。</Li>
          <Li>在用户组权限页面创建用户组, 为其分配各仓库的下载与上传权限, 并将需要使用代理的用户加入该组。请注意: 管理员账号同样需要手动加入用户组并配置该组的仓库使用权限, 否则其代理请求同样会因未被授权而被拒绝。</Li>
          <Li>按下一节介绍的通用代理地址格式配置客户端。</Li>
          <Li>向仓库发起请求以验证链路, 并在缓存统计页面确认命中情况。</Li>
        </ol>
      </Block>

      <Block id="sec-url" title="三、通用代理地址">
        <Paragraph>
          所有仓库均遵循同一路径透传规则, 通用代理地址格式如下, 使用时替换其中的主机地址、仓库名称与密钥即可:
        </Paragraph>
        <Code>{`${window.location.origin}/proxy/<仓库名>/?token=<API密钥>`}</Code>
        <Paragraph style={{ marginTop: 12 }}>
          于各语言客户端内的接入位置示例说明见镜像仓库页面中每一行「代理地址」列的说明(应用自带的列复制按钮可直接复制基础地址)。
        </Paragraph>
      </Block>

      <Block id="sec-packages" title="四、私有包托管">
        <Paragraph>在私有包页面上传企业或个人自建的软件包后, 系统将提供:</Paragraph>
        <ol style={{ paddingLeft: 20 }}>
          <Li>下载地址 /pkg/仓库名/文件名, 供 curl 或任意客户端直接下载。</Li>
          <Li>PEP 503 风格的简单索引 /simple/仓库名, 供 pip 等 Python 工具链直接引用。</Li>
          <Li>文件唯一性校验, 上传即计算 SHA256 并落库, 后续下载可对齐校验。</Li>
        </ol>
        <Paragraph>上传要求:</Paragraph>
        <ol style={{ paddingLeft: 20 }}>
          <Li>在指定仓库名后执行上传, 上传目标仓库不支持为空值, 也不使用任何默认仓库名兜底。</Li>
          <Li>用户所在组需对目标仓库具备上传权限; 管理员可直接上传, 无需额外授权。</Li>
        </ol>
        <Paragraph>
          <Text strong>
            注意: 若页面上没有看到之前上传的私有包, 请先点击 <b>显示全部</b> 按钮清除仓库过滤条件即可显示。
          </Text>
        </Paragraph>
      </Block>

      <Block id="sec-groups" title="五、用户组与权限">
        <ol style={{ paddingLeft: 20 }}>
          <Li>权限模型: 权限的最小单位是"用户组 × 仓库"的组合, 每个组合可独立设置下载与上传权限。</Li>
          <Li>管理员在管理端拥有全部管理能力; 但对仓库代理访问而言, 管理员与其他角色一致, 必须加入用户组并为该组配置相应仓库的下载或上传权限后方可使用。</Li>
          <Li>普通用户必须通过其所在组的授权才能访问相应仓库, 否则返回 403。</Li>
          <Li>添加成员: 用户组页面内, 在成员标签右侧的输入框中填写用户名并回车即可加入; 删除成员可直接关闭标签。</Li>
          <Li>授权矩阵: 打开组的"设置"弹窗, 在每行仓库后勾选下载与上传能力, 统一点击保存全部生效。</Li>
          <Li>会话过期时登录页可再次登录; API 密钥被作废时需重新生成并更新客户端配置。</Li>
        </ol>
        <Paragraph><b>成员批量导入</b></Paragraph>
        <Paragraph>
          入口位于用户组权限页面每一行的「批量导入」按钮。支持 CSV / JSON / TOML / TXT 四种格式,
          可在导入弹窗内直接下载对应模板。
        </Paragraph>
        <ol style={{ paddingLeft: 20 }}>
          <Li>username 必填; 用户名仅支持字母、数字、下划线与短横线, 长度为 2 至 32 位。</Li>
          <Li>password 可选; 未填写时系统生成随机密码, 并在导入结果中显示一次, 请及时保存。</Li>
          <Li>role 可选, 取值为 user 或 admin, 缺省为 user。</Li>
          <Li>groups 可选; 多个组用逗号分隔或使用数组表示, 留空时加入执行导入的当前组; 不存在的组会自动创建。</Li>
          <Li>已存在的用户不会修改密码; 若文件中要求的角色与该用户当前角色不同, 会列入失败原因且不做变更。</Li>
          <Li>导入结果以提示形式汇总为成功导入 X 名成员、Y 名成员导入失败, 弹窗内可查看新建成员的初始密码、自动创建的组与失败明细。</Li>
        </ol>
      </Block>

      <Block id="sec-token" title="六、API 密钥">
        <Paragraph>API 密钥用于客户端侧的长期代理访问, 页面入口为系统设置中的 API 密钥管理。</Paragraph>
        <ol style={{ paddingLeft: 20 }}>
          <Li>生成: 指定一个便于识别的备注名生成密钥, 密钥明文仅在生成时展示一次, 请立即保存。</Li>
          <Li>存储: 数据库仅存放 SM3 哈希, 拖库亦无法还原密钥明文。</Li>
          <Li>作废: 疑似泄露时点击对应条目的作废按钮, 密钥即刻失效, 客户端换用新密钥即可。</Li>
          <Li>使用: 密钥通过代理地址的 token 参数传递, 各客户端均可直接嵌入 URL 使用。</Li>
        </ol>
      </Block>

      <Block id="sec-mfa" title="七、MFA 二次认证">
        <ol style={{ paddingLeft: 20 }}>
          <Li>绑定: 系统设置进入我的 MFA 卡片, 点击生成密钥并使用任何标准认证器扫描二维码添加, 输入当前动态码确认生效。</Li>
          <Li>登录: 该账号此后的登录流程需要在密码验证之后输入动态码完成二段认证。</Li>
          <Li>重置: 用户忘记动态码时, 管理员可在用户管理页面对其重置 MFA; 重置后用户需重新绑定。</Li>
          <Li>强制策略: 管理员可开启强制 MFA, 未绑定用户将被拦截在管理端之外; 下载类请求与 API 密钥不受此策略影响。</Li>
        </ol>
      </Block>

      <Block id="sec-stats" title="八、缓存统计与清理">
        <ol style={{ paddingLeft: 20 }}>
          <Li>按仓库统计: 各仓库的缓存文件数、占用体积与累计命中次数。</Li>
          <Li>最近访问: 展示最近请求过的缓存条目, 便于确认代理行为。</Li>
          <Li>清理: 支持按天数清理长期未访问条目, 也可一键全清; 清理仅作用于代理缓存, 私有包数据不受影响。</Li>
          <Li>清理可释放的容量会以字节数返回, 与按仓库明细配合可用于容量规划。</Li>
        </ol>
      </Block>

      <Block id="sec-api" title="九、开放接口文档">
        <Paragraph>
          全部管理接口由后端自动生成 OpenAPI 规范文档, 包含请求参数、字段定义与在线调试, 请在浏览器中打开:
        </Paragraph>
        <Code>{`${window.location.origin}/docs`}</Code>
        <Paragraph>
          <a href={`/docs?token=${encodeURIComponent(sessionStorage.getItem('modernmirror_session') || '')}`} target="_blank" rel="noreferrer">
            点此打开接口文档页面
          </a>
          , 文档列出所有可用接口的路径与完整字段, 便于用户直接在浏览器中进行接口调试与体验。
        </Paragraph>
      </Block>

      <Block id="sec-cli" title="十、命令行速查">
        <Paragraph>以下为用户可直接使用的命令示例, 请求头携带 API 密钥, 代理下载私有仓库文件:</Paragraph>
        <Code>{`export KEY="<你的API密钥>"
BASE="${window.location.origin}"

# 通过代理下载数据
curl -o demo.whl "$BASE/pkg/<仓库名>/demo.whl?token=$KEY"

# 查看私有包索引数据
curl -s "$BASE/simple/<仓库名>?token=$KEY"

# 查看当前登录账号自身的 API 密钥列表
curl -s -H "Session-Token: $KEY" "$BASE/auth/tokens"

# 下载后校验文件完整性
sha256sum demo.whl`}</Code>
        <Paragraph type="secondary" style={{ fontSize: 12 }}>
          以上示例中的会话 Token 与 API 密钥的权限范围仅限当前用户; 与管理相关的仓库配置、审计日志等接口不对使用者公开。
        </Paragraph>
      </Block>

      <Block id="sec-faq" title="十一、常见问题">
        <Paragraph>1. 请求返回 502 且提示上游校验不匹配是什么原因?</Paragraph>
        <Paragraph style={{ marginTop: 0, marginBottom: 12 }}>
          表示上游返回的文件与其官方元数据中的哈希值不一致, 系统已拒绝将其写入缓存。请检查所配置的上游地址是否可信任, 必要时更换官方源; 详情可在审计日志中查看 expected 与 got 两组哈希值。
        </Paragraph>
        <Paragraph>2. 返回 401 或 403 分别意味着什么?</Paragraph>
        <Paragraph style={{ marginTop: 0, marginBottom: 12 }}>
          401 表示未登录或凭据已过期; 403 表示使用者不具备访问该仓库的权限, 需在用户组权限页面完成授权。
        </Paragraph>
        <Paragraph>3. 应用打开失败或提示端口被占用如何处理?</Paragraph>
        <Paragraph style={{ marginTop: 0, marginBottom: 12 }}>
          在设备终端执行 fuser -k 端口号/tcp 或者更换端口后重新启动; 数据目录不会因停止应用而丢失。
        </Paragraph>
        <Paragraph>4. 上游仓库均连通但客户端仍使用旧版本?</Paragraph>
        <Paragraph style={{ marginTop: 0, marginBottom: 12 }}>
          部分客户端存在本地索引缓存, 清空对应客户端的缓存目录后重新请求即可。
        </Paragraph>
        <Paragraph>5. 如何在公网上安全使用?</Paragraph>
        <Paragraph style={{ marginTop: 0 }}>
          不建议将端口直接映射到公网。如需远程访问, 请使用低可信度较大的网络接入方案, 例如 Tailscale 或其他具备认证能力的反向代理。
        </Paragraph>
      </Block>

      <div style={{ padding: '8px 4px 24px', textAlign: 'center' }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          ModernMirror 使用文档 v1.1.23
        </Typography.Text>
      </div>
    </>
  )
}
