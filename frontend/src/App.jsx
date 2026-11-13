import React, { useEffect, useState } from 'react'
import { Avatar, Button, Dropdown, Layout, Menu, Modal, Space, Table, Typography, message } from 'antd'
import {
  DatabaseOutlined, FileTextOutlined, InboxOutlined, LogoutOutlined,
  SettingOutlined, TeamOutlined, UserOutlined
} from '@ant-design/icons'
import useAuthSession from './AuthSession'
import Repos from './pages/Repos'
import Packages from './pages/Packages'
import Stats from './pages/Stats'
import Users from './pages/Users'
import Groups from './pages/Groups'
import SettingsPage from './pages/Settings'
import Audit from './pages/Audit'
import Docs from './pages/Docs'
import { api } from './api'

const { Header, Sider, Content } = Layout

export default function App() {
  const { user, ready, logout, gate } = useAuthSession()
  const [page, setPage] = useState('repos')
  const [onboardOpen, setOnboardOpen] = useState(false)
  const [resetOpen, setResetOpen] = useState(false)
  const [resetResult, setResetResult] = useState(null)
  const [resetBusy, setResetBusy] = useState(false)
  const [keyWarnOpen, setKeyWarnOpen] = useState(false)

  const isAdmin = user?.role === 'admin'

  useEffect(() => {
    if (!isAdmin || !user?.username || !ready) return
    if (sessionStorage.getItem('modernmirror_onboard') === user.username) return
    api('/admin/groups')
      .then((groups) => {
        const hasAnyMember = (groups || []).some((g) => (g.members || []).length > 0)
        if (!hasAnyMember) {
          setOnboardOpen(true)
          sessionStorage.setItem('modernmirror_onboard', user.username)
        }
      })
      .catch(() => {})
  }, [isAdmin, user?.username, ready])

  useEffect(() => {
    if (!ready || !user?.username) return
    const resetDismissed = sessionStorage.getItem('mm_pw_reset_' + user.username) === '1'
    if (user.role === 'admin' && user.password_reset_needed && !resetDismissed) {
      setResetOpen(true)
      setKeyWarnOpen(false)
      return
    }
    if (user.legacy_tokens > 0 &&
        sessionStorage.getItem('mm_key_warn_' + user.username) !== '1') {
      setKeyWarnOpen(true)
    }
  }, [ready, user])

  const maybeOpenKeyWarn = () => {
    if (!user?.username) return
    if (user.legacy_tokens > 0 &&
        sessionStorage.getItem('mm_key_warn_' + user.username) !== '1') {
      setTimeout(() => setKeyWarnOpen(true), 300)
    }
  }

  const dismissReset = (thenKeyWarn = true) => {
    setResetOpen(false)
    if (user?.username) sessionStorage.setItem('mm_pw_reset_' + user.username, '1')
    if (thenKeyWarn) maybeOpenKeyWarn()
  }
  const dismissKeyWarn = () => {
    setKeyWarnOpen(false)
    if (user?.username) sessionStorage.setItem('mm_key_warn_' + user.username, '1')
  }
  const doResetPasswords = async () => {
    setResetBusy(true)
    try {
      const r = await api('/admin/security/reset-passwords', { method: 'POST' })
      setResetResult(r)
      dismissReset(false)
      message.success(`已重置 ${r.count} 个用户的密码`)
    } catch (err) {
      message.error(err.message)
    } finally {
      setResetBusy(false)
    }
  }
  const revokeLegacyKeys = async () => {
    try {
      const r = await api('/auth/tokens/revoke-legacy', { method: 'POST' })
      message.success(`已作废 ${r.revoked} 个旧版密钥，请重新生成`)
      dismissKeyWarn()
      setPage('settings')
    } catch (err) {
      message.error(err.message)
    }
  }

  if (!ready) return null
  if (gate) return gate


  const items = [
    { key: 'repos', icon: <DatabaseOutlined />, label: '镜像仓库' },
    { key: 'packages', icon: <InboxOutlined />, label: '私有包' },
    { key: 'stats', icon: <SettingOutlined />, label: '缓存统计' },
    { key: 'docs', icon: <FileTextOutlined />, label: '使用文档' }
  ]
  if (isAdmin) {
    items.push(
      { type: 'divider' },
      { key: 'users', icon: <UserOutlined />, label: '用户管理' },
      { key: 'groups', icon: <TeamOutlined />, label: '用户组权限' },
      { key: 'audit', icon: <FileTextOutlined />, label: '审计日志' },
      { type: 'divider' },
      { key: 'settings', icon: <SettingOutlined />, label: '系统设置' }
    )
  }
  const userMenu = {
    items: [{ key: 'logout', icon: <LogoutOutlined />, label: '退出登录' }],
    onClick: ({ key }) => key === 'logout' && logout()
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="light" width={200}>
        <div style={{ padding: 20, fontWeight: 700, fontSize: 18 }}>ModernMirror</div>
        <Menu items={items} selectedKeys={[page]} onClick={(e) => setPage(e.key)} />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            borderBottom: '1px solid #eceef2'
          }}
        >
          <Dropdown menu={userMenu} placement="bottomRight">
            <Space style={{ cursor: 'pointer' }}>              <Avatar style={{ background: '#1e6fff' }} icon={<UserOutlined />} size="small" />
              <Typography.Text strong>{user?.username}</Typography.Text>
              {user?.mfa ? (
                <Typography.Text style={{ fontSize: 12 }} type="secondary">
                  🔐 MFA
                </Typography.Text>
              ) : null}
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ padding: 24, background: '#f5f7fa' }}>
          {page === 'repos' && <Repos />}
          {page === 'packages' && <Packages />}
          {page === 'stats' && <Stats />}
          {page === 'docs' && <Docs />}
          {isAdmin && page === 'users' && <Users />}
          {isAdmin && page === 'groups' && <Groups />}
          {isAdmin && page === 'audit' && <Audit />}
          {isAdmin && page === 'settings' && <SettingsPage user={user} />}
        </Content>
      </Layout>
      <Modal
        open={onboardOpen}
        title="首次登录, 请完成初始配置"
        okText="立即前往设置"
        cancelText="稍后再说"
        onOk={() => {
          setOnboardOpen(false)
          setPage('groups')
        }}
        onCancel={() => setOnboardOpen(false)}
      >
        <p style={{ marginBottom: 6 }}>
          <b>检测到尚未配置任何用户组。</b>
        </p>
        <p style={{ margin: 0, lineHeight: 1.9 }}>
          建议前往 <b>「用户组权限」</b> 页面:
          ① 创建用户组并把你常用的账号加入组;
          ② 在组的软件源权限矩阵中, 按需勾选各仓库的「可下载 / 可上传」权限。
          以上完成后, 组内用户即可通过 API 密钥访问对应代理源。
        </p>
      </Modal>

      <Modal
        open={resetOpen}
        title="安全升级提醒：请重置用户密码"
        closable={false}
        maskClosable={false}
        okText="一键重置所有用户密码"
        okButtonProps={{ danger: true, loading: resetBusy }}
        onOk={doResetPasswords}
        cancelText="稍后处理"
        onCancel={dismissReset}
      >
        <p>本次升级增强了系统安全模块，密码存储方式已更新。</p>
        <p style={{ marginBottom: 0 }}>
          当前仍有部分用户使用升级前的密码记录，系统无法自动迁移。建议立即为除当前管理员外的所有用户生成新的随机密码；
          新密码仅在重置结果中显示一次，请及时保存并分发。
        </p>
      </Modal>

      <Modal
        open={!!resetResult}
        title="密码重置完成"
        footer={<Button type="primary" onClick={() => { setResetResult(null); maybeOpenKeyWarn() }}>我已保存</Button>}
        onCancel={() => { setResetResult(null); maybeOpenKeyWarn() }}
        width={640}
      >
        <p>以下密码仅显示一次，请立即复制保存并通知对应用户修改。</p>
        <Table
          size="small" rowKey="username" pagination={false}
          dataSource={resetResult?.users || []}
          columns={[
            { title: '用户名', dataIndex: 'username' },
            { title: '新密码', dataIndex: 'password',
              render: (v) => <Typography.Text code copyable>{v}</Typography.Text> }
          ]}
        />
      </Modal>

      <Modal
        open={keyWarnOpen && !resetOpen && !resetResult}
        title="API 密钥需要重新签发"
        onCancel={dismissKeyWarn}
        footer={[
          <Button key="later" onClick={dismissKeyWarn}>稍后</Button>,
          <Button key="revoke" danger onClick={revokeLegacyKeys}>作废旧版密钥</Button>,
          <Button key="go" type="primary" onClick={() => { dismissKeyWarn(); setPage('settings') }}>
            前往设置
          </Button>
        ]}
      >
        <p>本次升级增强了系统安全模块。</p>
        <p style={{ marginBottom: 0 }}>
          检测到当前账号仍有 {user?.legacy_tokens || 0} 个旧版密钥。旧密钥暂时仍可使用，但无法自动升级到新的安全格式；
          建议尽快在系统设置中重新签发，并替换客户端配置。
        </p>
      </Modal>
    </Layout>
  )
}

