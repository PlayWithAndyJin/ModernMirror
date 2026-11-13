import React, { useEffect, useMemo, useState } from 'react'
import { Button, Card, Input, Select, Space, Table, Tag, Typography, message } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import { api, fmtBytes } from '../api'

const EVENT_META = {
  'login.fail': ['登录失败', 'red'],
  'login.mfa_fail': ['动态码校验失败', 'red'],
  'auth.fail': ['认证失败', 'red'],
  'verify.fail': ['文件校验失败', 'red'],
  'verify.skipped': ['文件未校验', 'orange'],
  'user.add': ['新增用户', 'green'],
  'user.update': ['更新用户', 'blue'],
  'user.delete': ['删除用户', 'orange'],
  'user.password_change': ['修改密码', 'blue'],
  'user.mfa_enable': ['开启 MFA', 'green'],
  'user.mfa_disable': ['关闭 MFA', 'orange'],
  'user.mfa_reset': ['重置 MFA', 'orange'],
  'token.create': ['签发 API 密钥', 'green'],
  'token.revoke': ['作废 API 密钥', 'orange'],
  'token.revoke_legacy': ['作废旧版密钥', 'orange'],
  'group.add': ['新增用户组', 'green'],
  'group.update': ['更新用户组', 'blue'],
  'group.delete': ['删除用户组', 'orange'],
  'group.member_add': ['添加组成员', 'green'],
  'group.member_remove': ['移除组成员', 'orange'],
  'group.member_import': ['批量导入成员', 'green'],
  'group.grant': ['授权用户组', 'blue'],
  'group.revoke': ['撤销用户组权限', 'orange'],
  'repo.add': ['新增镜像仓库', 'green'],
  'repo.update': ['更新镜像仓库', 'blue'],
  'repo.delete': ['删除镜像仓库', 'orange'],
  'package.upload': ['上传私有包', 'green'],
  'package.delete': ['删除私有包', 'orange'],
  'cache.cleanup': ['手动清理缓存', 'blue'],
  'cache.scheduled_cleanup': ['定时清理缓存', 'blue'],
  'security.reset_all_passwords': ['重置用户密码', 'orange'],
  'settings.mfa_enforced': ['MFA 强制策略变更', 'blue'],
  'startup.warn': ['启动检查', 'default']
}

const fmtTime = (ts) => (ts ? String(ts).replace('T', ' ') : '-')

const DETAIL_FIELDS = {
  repo: '仓库',
  file: '文件',
  user: '用户',
  username: '用户',
  operator: '操作者',
  name: '名称',
  group: '用户组',
  gid: '组 ID',
  role: '角色',
  value: '取值',
  days: '保留天数',
  freed: '释放字节',
  count: '数量',
  created: '新建数量',
  upstream: '上游地址',
  detail: '说明',
  expected: '期望值',
  got: '实际值'
}

function describe(row) {
  const e = row.event
  const parts = []
  const push = (label, value) => {
    if (value !== undefined && value !== null && value !== '') parts.push(`${label}：${value}`)
  }
  switch (e) {
    case 'login.fail':
    case 'login.mfa_fail':
      push('用户', row.user); break
    case 'user.add':
      push('用户', row.user || row.username); push('角色', row.role); break
    case 'user.update':
    case 'user.delete':
    case 'user.password_change':
    case 'user.mfa_enable':
    case 'user.mfa_disable':
    case 'user.mfa_reset':
      push('用户', row.user || row.username); break
    case 'token.create':
      push('名称', row.name); break
    case 'token.revoke':
    case 'token.revoke_legacy':
      push('数量', row.count); break
    case 'group.add':
    case 'group.update':
    case 'group.delete':
      push('用户组', row.name); break
    case 'group.member_add':
      push('用户', row.user); push('组 ID', row.gid); break
    case 'group.member_remove':
      push('用户', row.user); push('组 ID', row.gid); break
    case 'group.member_import':
      push('用户组', row.group); push('导入', `${row.count} 人`); push('新建', `${row.created} 人`); break
    case 'group.grant':
    case 'group.revoke':
      push('组 ID', row.gid); push('仓库', row.repo); break
    case 'repo.add':
    case 'repo.update':
      push('仓库', row.name); push('上游地址', row.upstream); break
    case 'repo.delete':
      push('仓库', row.name); break
    case 'package.upload':
    case 'package.delete':
      push('仓库', row.repo); push('文件', row.file); break
    case 'cache.cleanup':
    case 'cache.scheduled_cleanup':
      push('保留天数', row.days); push('释放空间', fmtBytes(row.freed)); break
    case 'security.reset_all_passwords':
      push('重置用户数', row.count); push('操作者', row.operator); break
    case 'settings.mfa_enforced':
      push('强制 MFA', row.value ? '已开启' : '已关闭'); break
    case 'verify.fail':
      push('仓库', row.repo); push('文件', row.file); push('说明', row.detail); break
    case 'verify.skipped':
      push('仓库', row.repo); push('文件', row.file); break
    case 'auth.fail':
    case 'startup.warn':
      push('说明', row.detail); break
    default:
      Object.entries(row).forEach(([k, v]) => {
        if (['ts', 'event', 'ip'].includes(k)) return
        if (typeof v === 'object') return
        push(DETAIL_FIELDS[k] || k, v)
      })
  }
  return parts.join('；') || '-'
}

const eventColor = (e) => (EVENT_META[e] ? EVENT_META[e][1] : 'default')
const eventLabel = (e) => (EVENT_META[e] ? EVENT_META[e][0] : e)

export default function Audit() {
  const [rows, setRows] = useState([])
  const [keyword, setKeyword] = useState('')
  const [event, setEvent] = useState('')

  const load = async () => {
    try {
      setRows(await api('/admin/audit?limit=1000'))
    } catch (err) {
      message.error('加载审计日志失败: ' + err.message)
    }
  }
  useEffect(() => { load() }, [])

  const events = useMemo(
    () => Array.from(new Set(rows.map((r) => r.event))).sort(),
    [rows]
  )

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (event && r.event !== event) return false
      if (keyword) {
        const text = `${eventLabel(r.event)} ${describe(r)} ${r.ip || ''}`
        if (!text.toLowerCase().includes(keyword.toLowerCase())) return false
      }
      return true
    }).reverse()
  }, [rows, event, keyword])

  const exportCsv = () => {
    const header = ['时间', '操作类型', '来源 IP', '详情']
    const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
    const lines = [header.join(',')]
    filtered.forEach((r) => {
      lines.push([fmtTime(r.ts), eventLabel(r.event), r.ip, describe(r)].map(esc).join(','))
    })
    const blob = new Blob([`\uFEFF${lines.join('\n')}`], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `modernmirror-audit-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const columns = [
    { title: '时间', dataIndex: 'ts', width: 180, render: fmtTime },
    {
      title: '操作类型', dataIndex: 'event', width: 180,
      render: (v) => <Tag color={eventColor(v)}>{eventLabel(v)}</Tag>
    },
    { title: '来源 IP', dataIndex: 'ip', width: 140, render: (v) => v || '-' },
    {
      title: '详情',
      render: (_, r) => (
        <Typography.Text style={{ fontSize: 13 }}>{describe(r)}</Typography.Text>
      )
    }
  ]

  return (
    <Card
      title="审计日志"
      extra={
        <Space>
          <Input.Search
            allowClear placeholder="搜索操作或用户" style={{ width: 220 }}
            onSearch={setKeyword} onChange={(e) => !e.target.value && setKeyword('')}
          />
          <Select
            allowClear placeholder="按操作类型筛选" style={{ width: 220 }}
            value={event || undefined} onChange={(v) => setEvent(v || '')}
            options={events.map((e) => ({ value: e, label: eventLabel(e) }))}
          />
          <Button icon={<DownloadOutlined />} onClick={exportCsv}>导出 CSV</Button>
          <Button onClick={load}>刷新</Button>
        </Space>
      }
    >
      <Table
        rowKey={(r, i) => String(i)}
        dataSource={filtered}
        columns={columns}
        size="middle"
        pagination={{ pageSize: 20, showSizeChanger: true }}
      />
    </Card>
  )
}
