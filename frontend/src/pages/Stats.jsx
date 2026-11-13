import React, { useEffect, useState } from 'react'
import { Button, Card, Col, InputNumber, Popconfirm, Row, Statistic, Switch, Table, Tag, message } from 'antd'
import { api, fmtBytes } from '../api'

const fmtTime = (t) => t ? new Date(t.replace(' ', 'T')).toLocaleString() : '-'

export default function Stats() {
  const [s, setS] = useState(null)
  const [retention, setRetention] = useState({ enabled: true, days: 30 })

  const load = async () => {
    try {
      setS(await api('/admin/stats'))
    } catch (err) {
      message.error('加载统计失败: ' + err.message)
      setS({ per_repo: [], total_size: 0, total_files: 0, total_hits: 0, recent: [] })
    }
  }
  useEffect(() => {
    load()
    api('/admin/settings').then((cfg) => setRetention({
      enabled: cfg.cleanup_enabled !== false,
      days: cfg.cache_retention_days || 30
    })).catch(() => {})
  }, [])

  const saveRetention = async (next) => {
    const value = next || retention
    try {
      await api(`/admin/settings?cleanup_enabled=${value.enabled}&cache_retention_days=${value.days}`, { method: 'PUT' })
      setRetention(value)
      message.success('自动清理策略已保存')
    } catch (err) { message.error(err.message) }
  }

  const cleanup = async (days) => {
    const r = await api(`/admin/cache/cleanup?days=${days}`, { method: 'POST' })
    message.success(`清理完成, 释放 ${fmtBytes(r.freed_bytes)}`)
    load()
  }

  if (!s) return null

  return (
    <>
      <h2>缓存统计</h2>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="缓存文件数" value={s.total_files} /></Card></Col>
        <Col span={6}><Card><Statistic title="缓存总大小" value={fmtBytes(s.total_size)} /></Card></Col>
        <Col span={6}><Card><Statistic title="累计命中" value={s.total_hits} /></Card></Col>
        <Col span={6}>
          <Card>
            <div style={{ display: 'grid', gap: 8 }}>
              <Popconfirm title="清理 7 天未访问的缓存?" onConfirm={() => cleanup(7)}>
                <Button>清理 7 天未访问</Button>
              </Popconfirm>
              <Popconfirm title="清空全部缓存? (不影响私有包)" onConfirm={() => cleanup(0)}>
                <Button danger>清空全部缓存</Button>
              </Popconfirm>
            </div>
          </Card>
        </Col>
      </Row>

      <Card title="自动清理策略" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
          <span>启用每日自动清理</span>
          <Switch checked={retention.enabled} onChange={(v) => setRetention({ ...retention, enabled: v })} />
          <span>保留最近</span>
          <InputNumber min={1} max={3650} value={retention.days}
            onChange={(v) => setRetention({ ...retention, days: v || 1 })} />
          <span>天内访问过的缓存</span>
          <Button type="primary" onClick={() => saveRetention()}>保存</Button>
          <span style={{ color: '#8a94a6' }}>每日 03:00 后执行一次，仅清理代理缓存，不影响私有包。</span>
        </div>
      </Card>

      <h3>按仓库</h3>
      <Table
        rowKey="repo" size="middle" pagination={false}
        dataSource={s.per_repo || []}
        columns={[
          { title: '仓库', dataIndex: 'repo', render: (v) => <Tag color="blue">{v}</Tag> },
          { title: '文件数', dataIndex: 'n' },
          { title: '大小', dataIndex: 'total', render: (v) => fmtBytes(v) },
          { title: '命中次数', dataIndex: 'hits', render: (v) => v || 0 }
        ]}
        style={{ marginBottom: 24 }}
      />

      <h3>最近访问</h3>
      <Table
        rowKey={(r, i) => String(i)} size="middle" pagination={false}
        dataSource={s.recent || []}
        columns={[
          { title: '仓库', dataIndex: 'repo' },
          { title: '路径', dataIndex: 'path', ellipsis: true },
          { title: '大小', dataIndex: 'size', render: (v) => fmtBytes(v) },
          { title: '命中', dataIndex: 'hits' },
          { title: '时间', dataIndex: 'fetched_at', render: fmtTime }
        ]}
      />
    </>
  )
}
