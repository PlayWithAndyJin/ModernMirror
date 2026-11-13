import React, { useEffect, useState } from 'react'
import {
  Button, Checkbox, Input, Modal, Popconfirm, Select, Space,
  Table, Tag, Typography, Upload, message
} from 'antd'
import { InboxOutlined, PlusOutlined } from '@ant-design/icons'
import { api } from '../api'

export default function Groups() {
  const [groups, setGroups] = useState([])
  const [repos, setRepos] = useState([])
  const [permModal, setPermModal] = useState(null)
  const [importGroup, setImportGroup] = useState(null)
  const [importResult, setImportResult] = useState(null)
  const [importing, setImporting] = useState(false)

  const load = async () => {
    const [g, r] = await Promise.all([api('/admin/groups'), api('/admin/repos')])
    setGroups(g)
    setRepos(r)
  }
  useEffect(() => { load() }, [])

  const addGroup = async () => {
    const name = document.getElementById('fnm-group-name').value.trim()
    if (!name) return message.error('请输入组名')
    try {
      await api('/admin/groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      })
      message.success('已创建')
      load()
    } catch (err) { message.error(err.message) }
  }

  const removeGroup = async (gid) => {
    await api(`/admin/groups/${gid}`, { method: 'DELETE' })
    message.success('已删除')
    load()
  }

  const MemberRow = ({ g }) => {
    const [members, setMembers] = useState(g.members || [])
    const [val, setVal] = useState('')
    const add = async () => {
      if (!val.trim()) return
      try {
        const out = await api(`/admin/groups/${g.id}/members`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: val.trim() })
        })
        setVal('')
        const fresh = await api('/admin/groups')
        const fg = fresh.find((x) => x.id === g.id)
        setMembers(fg?.members || [])
        if (!out.ok) message.info('该用户已在组中')
      } catch (err) { message.error(err.message) }
    }
    return (
      <div>
        {(members || []).length === 0 && <Typography.Text type="secondary">暂无成员</Typography.Text>}
        {(members || []).map((m) => (
          <Tag key={m} closable onClose={async () => {
            await api(`/admin/groups/${g.id}/members/${m}`, { method: 'DELETE' })
            setMembers(members.filter((x) => x !== m))
          }}>{m}</Tag>
        ))}
        <Space.Compact style={{ marginTop: 8, width: '100%' }}>
          <Input
            value={val} onChange={(e) => setVal(e.target.value)}
            placeholder="输入用户名, 回车添加"
            onPressEnter={add} size="small"
          />
          <Button size="small" onClick={add}>添加</Button>
        </Space.Compact>
      </div>
    )
  }

  const [permDraft, setPermDraft] = useState(null)

  const saveAll = async () => {
    const g = group
    try {
      await Promise.all(
        Object.entries(permDraft || {}).map(([repoName, fd]) =>
          api(`/admin/groups/${g.id}/repos/${repoName}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(fd)
          })
        )
      )
      message.success('权限已保存')
      setPermModal(null)
      load()
    } catch (err) { message.error(err.message) }
  }

  const columns = [
    { title: '组名', dataIndex: 'name', width: 120, render: (v) => <b>{v}</b> },
    {
      title: '成员', dataIndex: 'members',
      render: (_, g) => <MemberRow g={g} />
    },
    {
      title: '可用软件源', dataIndex: 'repos',
      render: (_, g) => (
        <>
          {(g.repos || []).map((r) => (
            <Tag key={r.repo} color={r.can_upload ? 'volcano' : 'green'} style={{ marginBottom: 2 }}>
              {r.repo}
              {r.can_download ? '·读' : ''}{r.can_upload ? '·写' : ''}
            </Tag>
          ))}
          <Button size="small" onClick={() => openPerm(g)} style={{ marginLeft: 4 }}>
            设置
          </Button>
        </>
      )
    },
    {
      title: '操作', render: (_, g) => (
        <>
          <Button size="small" onClick={() => { setImportResult(null); setImportGroup(g) }}>
            批量导入
          </Button>
          <Popconfirm title={`删除组 ${g.name}? (成员关系与授权都会移除)`} onConfirm={() => removeGroup(g.id)}>
            <Button size="small" danger style={{ marginLeft: 8 }}>删除</Button>
          </Popconfirm>
        </>
      )
    }
  ]

  let form = null
  const group = permModal ? groups.find((g) => g.id === permModal.id) : null
  const openPerm = (g) => {
    const draft = {}
    repos.forEach((r) => {
      const cur = (g.repos || []).find((x) => x.repo === r.name) || {}
      draft[r.name] = {
        can_download: !!cur.can_download,
        can_upload: !!cur.can_upload
      }
    })
    setPermDraft(draft)
    setPermModal(g)
  }
  const tog = (repoName, key, checked) =>
    setPermDraft({ ...permDraft, [repoName]: { ...permDraft[repoName], [key]: checked } })

  const runImport = async ({ file, onSuccess, onError }) => {
    if (!importGroup) return
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await fetch(`/admin/groups/${importGroup.id}/members/import`, {
        method: 'POST',
        headers: { 'Session-Token': sessionStorage.getItem('modernmirror_session') || '' },
        body: fd
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.detail || '导入失败')
      setImportResult(body)
      const ok = (body.created?.length || 0) + (body.added_to_group?.length || 0)
      const fail = body.errors?.length || 0
      if (fail > 0) message.warning(`成功导入 ${ok} 名成员，${fail} 名成员导入失败`)
      else message.success(`成功导入 ${ok} 名成员`)
      onSuccess(res, file)
      load()
    } catch (err) {
      message.error('导入失败: ' + err.message)
      onError(err, file)
    }
  }

  const tokenQuery = `?token=${encodeURIComponent(sessionStorage.getItem('modernmirror_session') || '')}`

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
        <h2 style={{ margin: 0, flex: 1 }}>用户组权限</h2>
        <Space.Compact>
          <Input id="fnm-group-name" placeholder="新组名称, 如 devteam" style={{ width: 220 }} />
          <Button type="primary" onClick={addGroup} icon={<PlusOutlined />}>创建组</Button>
        </Space.Compact>
      </div>
      <Table rowKey="id" dataSource={groups} columns={columns} />
      <Modal
        open={!!group}
        title={`组 ${group?.name || ''} 的软件源权限`}
        onCancel={() => setPermModal(null)}
        footer={null}
      >
        {group && (
          <div style={{ display: 'grid', gap: 12 }}>
            {repos.map((r) => {
              const draft = permDraft?.[r.name] || {}
              return (
                <div
                  key={r.name}
                  style={{
                    border: '1px solid #eee', borderRadius: 8, padding: 12,
                    display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap'
                  }}
                >
                  <div style={{ minWidth: 240 }}>
                    <b>{r.name}</b>
                    <Tag style={{ marginLeft: 8 }}>{r.type}</Tag>
                    <Typography.Text type="secondary" style={{ display: 'block', fontSize: 12 }}>
                      {r.upstream}
                    </Typography.Text>
                  </div>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Checkbox
                      checked={!!draft.can_download}
                      onChange={(e) => tog(r.name, 'can_download', e.target.checked)}
                    />
                    可下载
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Checkbox
                      checked={!!draft.can_upload}
                      onChange={(e) => tog(r.name, 'can_upload', e.target.checked)}
                    />
                    可上传
                  </label>
                </div>
              )
            })}
          </div>
        )}
        <Button
          type="primary"
          block
          style={{ marginTop: 16 }}
          onClick={saveAll}
          disabled={!group}
        >
          保存全部
        </Button>
      </Modal>

      <Modal
        open={!!importGroup}
        title={`批量导入成员到 ${importGroup?.name || ''}`}
        onCancel={() => { setImportGroup(null); setImportResult(null) }}
        footer={<Button onClick={() => { setImportGroup(null); setImportResult(null) }}>关闭</Button>}
        width={720}
      >
        <Typography.Paragraph style={{ marginBottom: 8 }}>
          批量导入说明请参考使用文档。
        </Typography.Paragraph>
        <Space wrap style={{ marginBottom: 12 }}>
          {['csv', 'json', 'toml', 'txt'].map((ext) => (
            <a key={ext} href={`/templates/members.${ext}${tokenQuery}`} target="_blank" rel="noreferrer">
              <Button size="small">下载 {ext.toUpperCase()} 模板</Button>
            </a>
          ))}
        </Space>
        <Upload.Dragger customRequest={runImport} multiple={false} showUploadList={false}>
          <p style={{ fontSize: 34, margin: 0 }}><InboxOutlined /></p>
          <p>点击或拖拽成员文件到此处导入</p>
        </Upload.Dragger>

        {importResult && (
          <div style={{ marginTop: 16 }}>
            <Typography.Paragraph>
              总计 {importResult.total} 名 · 新建 {importResult.created?.length || 0} 名 ·
              加入当前组 {importResult.added_to_group?.length || 0} 名 ·
              已在组内 {importResult.already_in_group?.length || 0} 名 ·
              失败 {importResult.errors?.length || 0} 名
            </Typography.Paragraph>
            {importResult.created?.length > 0 && (
              <Table
                size="small" rowKey="username" pagination={false}
                style={{ marginBottom: 12 }}
                dataSource={importResult.created}
                columns={[
                  { title: '用户名', dataIndex: 'username' },
                  { title: '角色', dataIndex: 'role' },
                  {
                    title: '初始密码',
                    dataIndex: 'password',
                    render: (v, r) => (
                      <Typography.Text code copyable>{v}{r.generated ? ' (随机生成)' : ''}</Typography.Text>
                    )
                  },
                  {
                    title: '属组', dataIndex: 'groups',
                    render: (v) => (v || []).map((g) => <Tag key={g}>{g}</Tag>)
                  }
                ]}
              />
            )}
            {(importResult.groups_created || []).length > 0 && (
              <Typography.Paragraph>
                自动创建组: {importResult.groups_created.map((g) => <Tag key={g}>{g}</Tag>)}
              </Typography.Paragraph>
            )}
            {importResult.errors?.length > 0 && (
              <Table
                size="small" pagination={false}
                rowKey={(r, i) => String(i)}
                dataSource={importResult.errors}
                columns={[
                  { title: '用户名', dataIndex: 'username' },
                  { title: '失败原因', dataIndex: 'reason' }
                ]}
              />
            )}
          </div>
        )}
      </Modal>
    </>
  )
}
