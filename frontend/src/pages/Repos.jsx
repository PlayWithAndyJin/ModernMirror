import React, { useEffect, useState } from 'react'
import {
  Button, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table,
  Tag, Tooltip, Typography, message
} from 'antd'
import { CopyOutlined, DeleteOutlined, EditOutlined, PlusOutlined, SettingOutlined } from '@ant-design/icons'
import { api, whoami } from '../api'

const typeColor = {
  pypi: 'gold', npm: 'green', raw: 'blue', go: 'cyan', maven: 'geekblue',
  nuget: 'purple', rubygems: 'magenta', crates: 'volcano', conan: 'brown',
  pub: 'blue', hex: 'teal', hackage: 'cyan', cran: 'red',
  luarocks: 'lime', cocoapods: 'orange'
}

const TEMPLATES = [
  { value: 'tmpl-go', label: 'Go Modules (GOPROXY)', type: 'go', upstream: 'https://proxy.golang.org' },
  { value: 'tmpl-maven', label: 'Maven Central (Maven/Gradle/SBT)', type: 'maven', upstream: 'https://repo1.maven.org/maven2' },
  { value: 'tmpl-nuget', label: 'NuGet (.NET)', type: 'nuget', upstream: 'https://api.nuget.org/v3' },
  { value: 'tmpl-rubygems', label: 'RubyGems', type: 'rubygems', upstream: 'https://rubygems.org' },
  { value: 'tmpl-crates', label: 'Rust Crates 静态文件', type: 'crates', upstream: 'https://static.crates.io' },
  { value: 'tmpl-pypi', label: 'Python PyPI', type: 'pypi', upstream: 'https://pypi.org' },
  { value: 'tmpl-npm', label: 'Node npm', type: 'npm', upstream: 'https://registry.npmjs.org' },
  { value: 'tmpl-debian', label: 'Debian apt', type: 'raw', upstream: 'https://deb.debian.org' },
  { value: 'tmpl-alpine', label: 'Alpine apk', type: 'raw', upstream: 'https://dl-cdn.alpinelinux.org' },
  { value: 'tmpl-fedora', label: 'Fedora dnf', type: 'raw', upstream: 'https://dl.fedoraproject.org' },
  { value: 'tmpl-arch', label: 'Arch pacman', type: 'raw', upstream: 'https://geo.mirror.pkgbuild.com' },
  { value: 'tmpl-conan', label: 'Conan Center (C++)', type: 'conan', upstream: 'https://center.conan.io' },
  { value: 'tmpl-pub', label: 'Dart pub.dev', type: 'pub', upstream: 'https://pub.dev' },
  { value: 'tmpl-hex', label: 'Erlang/Elixir hex.pm', type: 'hex', upstream: 'https://repo.hex.pm' },
  { value: 'tmpl-hackage', label: 'Haskell Hackage', type: 'hackage', upstream: 'https://hackage.haskell.org' },
  { value: 'tmpl-cran', label: 'R CRAN', type: 'cran', upstream: 'https://cloud.r-project.org' },
  { value: 'tmpl-luarocks', label: 'Lua Rocks', type: 'luarocks', upstream: 'https://luarocks.org' },
  { value: 'tmpl-cocoapods', label: 'CocoaPods CDN', type: 'cocoapods', upstream: 'https://cdn.cocoapods.org' }
]

export default function Repos() {
  const [adm, setAdm] = React.useState(false)
  const [repos, setRepos] = useState([])
  const [latency, setLatency] = useState({})
  const [modal, setModal] = useState(null)
  const [snippetRepo, setSnippetRepo] = useState(null)
  const [form] = Form.useForm()

  const load = async () => setRepos(await api('/admin/repos'))

  useEffect(() => { load(); whoami().then((u) => setAdm(u?.role === 'admin')) }, [])

  useEffect(() => {
    if (!repos.length) return
    const probe = async () => {
      try {
        const { latency: l } = await api('/admin/ping')
        setLatency(l)
      } catch (err) {}
    }
    probe()
    const timer = setInterval(probe, 5000)
    return () => clearInterval(timer)
  }, [repos.length])

  useEffect(() => {
    if (!form) return
    if (modal && modal !== 'add') {
      let backups = []
      try { backups = JSON.parse(modal.upstreams || '[]').slice(1) } catch (e) { backups = [] }
      form.setFieldsValue({
        name: modal.name,
        type: modal.type,
        upstream: modal.upstream,
        backup_upstreams: backups.join('\n'),
        quota_mb: modal.quota_mb || 0,
        enabled: !!modal.enabled
      })
    } else if (modal === 'add') {
      form.resetFields()
    }
  }, [modal, form])

  const toggle = async (name, enabled) => {
    const r = repos.find((x) => x.name === name)
    if (!r) return
    setRepos(repos.map((x) => (x.name === name ? { ...x, enabled: enabled ? 1 : 0 } : x)))
    try {
      let upstreams = []
      try { upstreams = JSON.parse(r.upstreams || '[]') } catch (e) { upstreams = [] }
      if (!upstreams.length) upstreams = [r.upstream]
      await api(`/admin/repos/${name}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          type: r.type,
          upstream: r.upstream,
          upstreams,
          quota_mb: r.quota_mb || 0,
          enabled
        })
      })
    } catch (err) {
      message.error('更新失败: ' + (err.message || ''))
      load()
    }
  }

  const save = async (values) => {
    try {
      const backups = String(values.backup_upstreams || '')
        .split('\n').map((x) => x.trim()).filter(Boolean)
      const payload = {
        name: values.name,
        type: values.type,
        upstream: values.upstream,
        upstreams: [values.upstream, ...backups],
        quota_mb: values.quota_mb || 0,
        enabled: !!values.enabled
      }
      if (modal === 'add') {
        await api('/admin/repos', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
      } else {
        await api(`/admin/repos/${values.name}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
      }
      message.success('已保存')
      setModal(null)
      load()
    } catch (err) {
      message.error(err.message || '保存失败')
    }
  }

  const remove = async (name) => {
    await api(`/admin/repos/${name}`, { method: 'DELETE' })
    message.success('已删除')
    load()
  }

  const columns = [
    { title: '名称', dataIndex: 'name', render: (v) => <b>{v}</b> },
    {
      title: '类型', dataIndex: 'type',
      render: (v) => <Tag color={typeColor[v]}>{v}</Tag>
    },
    { title: '上游地址', dataIndex: 'upstream', ellipsis: true },
    {
      title: '配额', dataIndex: 'quota_mb', width: 100,
      render: (v) => (v ? <Tag color="blue">{v} MB</Tag> : <Tag>不限</Tag>)
    },
    {
      title: '延迟', dataIndex: 'latency', width: 96,
      render: (_, r) => {
        if (!(r.name in latency)) return <Tag> 测量中…</Tag>
        const ms = latency[r.name]
        if (ms < 0) return <Tag color="red">超时/故障</Tag>
        const color = ms < 300 ? 'green' : ms < 1200 ? 'orange' : 'red'
        return <Tag color={color}>{ms} ms</Tag>
      }
    },
    {
      title: '启用', dataIndex: 'enabled',
      render: (v, r) => <Switch checked={!!v} onChange={(c) => toggle(r.name, c)} />
    },
    {
      title: '代理地址', dataIndex: 'name', width: 270,
      render: (v) => {
        const url = `${window.location.origin}/proxy/${v}/`
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, minWidth: 0, width: '100%' }}>
            <code
              style={{
                fontSize: 12,
                minWidth: 0,
                wordBreak: 'break-all',
                lineHeight: 1.5
              }}
            >
              {url}
            </code>
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined />}
              style={{ flexShrink: 0 }}
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(url)
                  message.success('代理地址已复制')
                } catch (err) {
                  message.warning('复制失败, 请手动复制')
                }
              }
              }
            />
          </div>
        )
      }
    },
    ...(adm ? [{
      title: '操作', dataIndex: 'action',
      render: (_, r) => (
        <Space size={2}>
          <Tooltip title="客户端配置">
            <Button size="small" type="text" icon={<SettingOutlined />} onClick={() => setSnippetRepo(r)} />
          </Tooltip>
          <Tooltip title="编辑">
            <Button size="small" type="text" icon={<EditOutlined />} onClick={() => setModal(r)} />
          </Tooltip>
          <Popconfirm title="确认删除该仓库?" onConfirm={() => remove(r.name)}>
            <Tooltip title="删除">
              <Button size="small" type="text" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      )
    }] : [])
  ]

  const snippetText = (repo) => {
    if (!repo) return ''
    const base = `${window.location.origin}/proxy/${repo.name}`
    const token = '<API密钥>'
    switch (repo.type) {
      case 'pypi':
        return `pip config set global.index-url "${base}/simple/?token=${token}"`
      case 'npm':
        return `npm config set registry "${base}/?token=${token}"`
      case 'go':
        return `export GOPROXY="${base}/,direct"`
      case 'maven':
        return `<mirror>\n  <id>modernmirror-${repo.name}</id>\n  <mirrorOf>central</mirrorOf>\n  <url>${base}/</url>\n</mirror>`
      case 'nuget':
        return `dotnet nuget add source "${base}/index.json?token=${token}" -n ModernMirror`
      default:
        return `# 通用代理地址\n${base}/?token=${token}\n\n# curl 示例\ncurl -O "${base}/<文件路径>?token=${token}"`
    }
  }

  const isEdit = !!modal && modal !== 'add'

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>镜像仓库</h2>
        {adm && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModal('add')}>
            添加仓库
          </Button>
        )}
      </div>
      <Table rowKey="id" dataSource={repos} columns={columns} />
      <Modal
        open={!!modal}
        title={modal === 'add' ? '添加仓库' : `编辑仓库: ${modal?.name || ''}`}
        onCancel={() => setModal(null)}
        footer={null}
        destroyOnClose
      >
        <Form
          form={form}
          initialValues={{ type: 'raw', enabled: true }}
          layout="vertical"
          onFinish={save}
        >
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input disabled={modal !== 'add'} placeholder="如 upstream-maven" />
          </Form.Item>
          {!isEdit && (
            <Form.Item label="模板快速填充 (可选)" style={{ marginBottom: 4 }}>
              <Select
                allowClear
                placeholder="选择官方上游自动填充类型和地址"
                onChange={(v) => {
                  const t = TEMPLATES.find((x) => x.value === v)
                  if (t) {
                    form.setFieldsValue({ type: t.type, upstream: t.upstream, name: t.label.split(' ')[0].toLowerCase() })
                  }
                }}
                options={TEMPLATES}
              />
            </Form.Item>
          )}
          <Form.Item name="type" label="类型" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'pypi', label: 'PyPI (pip)' },
                { value: 'npm', label: 'npm' },
                { value: 'go', label: 'Go Modules (GOPROXY)' },
                { value: 'maven', label: 'Maven / Gradle / SBT' },
                { value: 'nuget', label: 'NuGet (.NET)' },
                { value: 'rubygems', label: 'RubyGems' },
                { value: 'crates', label: 'crates 静态文件' },
                { value: 'conan', label: 'Conan (C++)' },
                { value: 'pub', label: 'dart pub.dev' },
                { value: 'hex', label: 'hex.pm (Erlang)' },
                { value: 'hackage', label: 'Hackage (Haskell)' },
                { value: 'cran', label: 'CRAN (R)' },
                { value: 'luarocks', label: 'LuaRocks' },
                { value: 'cocoapods', label: 'CocoaPods' },
                { value: 'raw', label: '通用文件 (apt/yum 等)' }
              ]}
            />
          </Form.Item>
          <Form.Item name="upstream" label="主上游地址" rules={[{ required: true }]}>
            <Input placeholder="https://maven.aliyun.com/repository/public" />
          </Form.Item>
          <Form.Item name="backup_upstreams" label="备用上游地址 (每行一个, 按顺序故障转移)">
            <Input.TextArea rows={2} placeholder="https://mirror.example.com/maven2" />
          </Form.Item>
          <Form.Item name="quota_mb" label="缓存配额 (MB, 0 表示不限制)">
            <InputNumber min={0} step={1024} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>保存</Button>
        </Form>
      </Modal>

      <Modal
        open={!!snippetRepo}
        title={`客户端配置：${snippetRepo?.name || ''}`}
        onCancel={() => setSnippetRepo(null)}
        footer={[
          <Button key="copy" type="primary" icon={<CopyOutlined />} onClick={async () => {
            try {
              await navigator.clipboard.writeText(snippetText(snippetRepo))
              message.success('配置已复制')
            } catch (e) {
              message.warning('复制失败，请手动选择文本复制')
            }
          }}>复制配置</Button>,
          <Button key="close" onClick={() => setSnippetRepo(null)}>关闭</Button>
        ]}
        width={680}
      >
        <Typography.Paragraph type="secondary">
          将 &lt;API密钥&gt; 替换为系统设置中生成的密钥；该密钥需具备当前仓库的下载权限。
        </Typography.Paragraph>
        <Input.TextArea value={snippetText(snippetRepo)} readOnly rows={8} style={{ fontFamily: 'monospace' }} />
      </Modal>
    </>
  )
}
