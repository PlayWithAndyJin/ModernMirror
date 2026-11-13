import React, { useEffect, useState } from 'react'
import {
  Button, Card, Checkbox, Input, Modal, Table, Tag, Typography, message
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { api } from '../api'

export default function SettingsPage({ user }) {
  const [enforced, setEnforced] = useState(false)
  const [mine, setMine] = useState(null)

  useEffect(() => {
    api('/admin/settings').then((s) => setEnforced(!!s.mfa_enforced)).catch(() => {})
    api('/auth/me').then(setMine).catch(() => {})
  }, [])

  const setEnforce = async (v) => {
    try {
      await api(`/admin/settings?mfa_enforced=${v}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' }
      })
      setEnforced(v)
      message.success(v ? '已开启强制 MFA' : '已关闭强制 MFA')
    } catch (err) { message.error(err.message) }
  }

  return (
    <>
      <h2>系统设置</h2>
      <Card title="登录与 MFA 策略" style={{ marginBottom: 16 }}>
        <p style={{ marginBottom: 6 }}><b>强制 MFA</b></p>
        <Checkbox checked={enforced} onChange={(e) => setEnforce(e.target.checked)}>
          开启后, 时效内未绑定 MFA 的普通用户将被拦在管理端之外
          (已绑定用户不受影响; 管理员自身保留应急通道; 下载类请求不受此限制)
        </Checkbox>
      </Card>
      <MfaMyCard user={mine || {}} />
      <ApiTokenCard user={mine || {}} />
    </>
  )
}

function ApiTokenCard({ user }) {
  const [tokens, setTokens] = useState([])
  const [addOpen, setAddOpen] = useState(false)
  const [name, setName] = useState('')
  const [created, setCreated] = useState(null)

  const load = async () => {
    try {
      setTokens(await api('/auth/tokens'))
    } catch (err) {}
  }
  useEffect(() => { if (user.username) load() }, [user.username])

  const create = async () => {
    try {
      const out = await api('/auth/tokens', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim() || '未命名' })
      })
      setCreated(out.token)
      setName('')
      setAddOpen(false)
      load()
    } catch (err) { message.error(err.message) }
  }

  const revoke = async (id) => {
    try {
      await api('/auth/tokens/revoke', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id })
      })
      message.success('已作废该密钥')
      load()
    } catch (err) { message.error(err.message) }
  }

  const columns = [
    { title: '名称', dataIndex: 'name' },
    {
      title: '前缀', dataIndex: 'token_prefix',
      render: (v) => <code>{v}…</code>
    },
    { title: '创建时间', dataIndex: 'created_at' },
    {
      title: '最近使用', dataIndex: 'last_used_at',
      render: (v) => v || <Typography.Text type="secondary">未使用</Typography.Text>
    },
    {
      title: '状态', dataIndex: 'revoked',
      render: (v) => v ? <Tag color="red">已作废</Tag> : <Tag color="green">有效</Tag>
    },
    {
      title: '安全版本', dataIndex: 'token_algo',
      render: (v) => v === 'sha256'
        ? <Tag color="orange">旧版，需重新签发</Tag>
        : <Tag color="green">当前版本</Tag>
    },
    {
      title: '操作', render: (_, r) => (
        <Button size="small" danger disabled={!!r.revoked} onClick={() => revoke(r.id)}>
          作废
        </Button>
      )
    }
  ]

  if (!user.username) return null

  return (
    <>
      <Card
        title="API 密钥管理(代理访问用)"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
            生成新密钥
          </Button>
        }
        style={{ marginBottom: 16 }}
      >
        <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
          用于客户端代理访问。疑似泄露时, 在下方点「作废」即可让其立即失效。
        </Typography.Paragraph>
        <Table
          rowKey="id" dataSource={tokens} columns={columns} size="middle"
          pagination={false} locale={{ emptyText: '暂无密钥' }}
        />
      </Card>
      <Modal
        open={addOpen}
        title="生成 API 密钥"
        onCancel={() => setAddOpen(false)}
        onOk={create}
        okText="生成"
      >
        <Input
          value={name} onChange={(e) => setName(e.target.value)}
          placeholder="密钥备注名, 如 Jenkins 构建 / 我的笔记本 pip"
          onPressEnter={create}
        />
      </Modal>
      <Modal
        open={!!created}
        title="密钥已生成"
        onCancel={() => setCreated(null)}
        footer={
          <Button type="primary" onClick={() => setCreated(null)}>我已保存</Button>
        }
      >
        <Typography.Paragraph type="warning">
          此密钥仅显示一次, 请立即复制保存:
        </Typography.Paragraph>
        <Typography.Paragraph code copyable style={{ wordBreak: 'break-all', marginBottom: 12 }}>
          {created}
        </Typography.Paragraph>
      </Modal>
    </>
  )
}

export function MfaMyCard({ user }) {
  const [state, setState] = useState({ secret: '', otpauth: '' })
  const codeInput = React.useRef()
  const [qrData, setQrData] = useState('')

  useEffect(() => {
    if (state.otpauth) {
      import('qrcode').then((QR) => {
        QR.toDataURL(state.otpauth, { width: 180, margin: 1 })
          .then(setQrData)
          .catch(() => setQrData(''))
      })
    }
  }, [state.otpauth])

  const setup = async () => {
    try {
      const out = await api('/auth/mfa/setup', { method: 'POST' })
      setState(out)
      message.info('密钥已生成, 请在认证 App 添加后输入动态码确认')
    } catch (err) { message.error(err.message) }
  }

  const enable = async (code) => {
    try {
      await api('/auth/mfa/enable', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code })
      })
      message.success('MFA 已开启! 下次登录需要输入动态码')
      window.location.reload()
    } catch (err) { message.error(err.message) }
  }

  if (user?.mfa) {
    return (
      <Card title="我的 MFA">
        🎉 你已开启 MFA。<Typography.Text type="secondary">
        (管理员如需关闭, 请联系管理员重置你的 MFA)
      </Typography.Text>
      </Card>
    )
  }

  return (
    <Card title="我的 MFA (TOTP 动态码)" style={{ marginBottom: 16 }}>
      <ol style={{ lineHeight: 2 }}>
        <li>点击下方按钮生成密钥</li>
        <li>用手机认证 App(Google Authenticator / 微软 / 1Password 等)扫二维码或手动输入密钥</li>
        <li>输入 App 显示的 6 位动态码确认</li>
      </ol>
      {state.secret ? (
        <div style={{ display: 'flex', gap: 24, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
          <img
            src={qrData}
            alt="MFA 二维码"
            style={{ width: 180, height: 180, border: '1px solid #eceef2', borderRadius: 8, padding: 8 }}
          />
          <div style={{ flex: 1, minWidth: 260 }}>
            <Typography.Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
              认证 App 扫码即可添加;无法扫码时复制以下链接到 App 手动添加:
            </Typography.Text>
            <Typography.Paragraph
              code
              copyable={{ text: state.otpauth }}
              style={{ wordBreak: 'break-all', marginBottom: 8, fontSize: 12 }}
            >
              {state.otpauth}
            </Typography.Paragraph>
            <Button
              size="small"
              onClick={() => { navigator.clipboard.writeText(state.otpauth); message.success('链接已复制') }}
            >
              复制链接
            </Button>
          </div>
        </div>
      ) : null}
      <Input
        style={{ maxWidth: 240, marginRight: 8, marginBottom: 8 }}
        placeholder="输入 6 位动态码"
        maxLength={6}
        ref={(el) => { window._mfaCodeInput = el }}
      />
      <Button type="primary" onClick={() => {
        const v = window._mfaCodeInput?.input?.value
        if (v && v.length === 6) enable(v)
        else message.error('请先输入 6 位动态码')
      }}>
        确认开启
      </Button>
      <Typography.Paragraph style={{ marginTop: 8 }}>
        <Typography.Text>
          <Button onClick={setup} disabled={!!state.secret}>
            {state.secret ? '已生成密钥 (未生效)' : '生成密钥'}
          </Button>
        </Typography.Text>
      </Typography.Paragraph>
    </Card>
  )
}
