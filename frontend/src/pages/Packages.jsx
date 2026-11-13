import React, { useState } from 'react'
import { Button, Card, Input, Modal, Popconfirm, Table, Tag, Upload, message } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import { api, whoami, fmtBytes } from '../api'

export default function Packages() {
  const [adm, setAdm] = React.useState(false)
  const [data, setData] = useState([])
  const [repo, setRepo] = useState('')
  const [uploadRepo, setUploadRepo] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)

  React.useEffect(() => { whoami().then((u) => setAdm(u?.role === 'admin')) }, [])

  const load = async (r = repo) => {
    setRepo(r)
    try {
      const all = await api('/admin/packages')
      all.sort((a, b) => b.id - a.id)
      setData(r ? all.filter((x) => x.repo === r) : all)
      if (r && all.every((x) => x.repo !== r)) {
        message.info(`仓库 "${r}" 下暂无私有包`)
      }
    } catch (err) {
      message.error('加载私有包失败: ' + err.message)
      setData([])
    }
  }

  const remove = async (r, f) => {
    await api(`/admin/packages/${r}/${f}`, { method: 'DELETE' })
    message.success('已删除')
    load()
  }

  const upload = async ({ file, onSuccess, onError }) => {
    if (!uploadRepo || !uploadRepo.trim()) {
      message.error('请先在上方填写仓库名 (如 pypi / mypkg), 再上传私有包')
      onError(new Error('missing repo name'), file)
      return
    }
    const safeRepo = uploadRepo.trim()
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await fetch(`/admin/packages/${encodeURIComponent(safeRepo)}`, {
        method: 'POST',
        headers: { 'Session-Token': sessionStorage.getItem('modernmirror_session') || '' },
        body: fd
      })
      if (res.ok) {
        message.success('上传成功')
        setUploadOpen(false)
        onSuccess(res, file)
        loadRepoAfterUpload()
      } else {
        let detail = await res.text()
        try { detail = JSON.parse(detail).detail || detail } catch (e) {}
        message.error('上传失败: ' + detail)
        onError(new Error(detail), file)
      }
    } catch (err) {
      message.error('上传失败: ' + err.message)
      onError(err, file)
    }
  }

  const loadRepoAfterUpload = async () => {
    const r = uploadRepo.trim()
    setRepo(r)
    const all = await api('/admin/packages')
    setData(all.filter((x) => x.repo === r))
  }

  const columns = [
    { title: '仓库', dataIndex: 'repo', render: (v) => <Tag color="purple">{v}</Tag> },
    { title: '文件名', dataIndex: 'filename' },
    { title: '版本', dataIndex: 'version', render: (v) => v || '-' },
    { title: '大小', dataIndex: 'size', render: (v) => fmtBytes(v) },
    { title: '上传时间', dataIndex: 'created_at' },
    {
      title: '操作', render: (_, r) => (
        <>
          <Button size="small" href={`/pkg/${r.repo}/${r.filename}?token=${sessionStorage.getItem('modernmirror_session') || ''}`} target="_blank">下载链接</Button>
          {adm && (
            <Popconfirm title="确认删除?" onConfirm={() => remove(r.repo, r.filename)}>
              <Button size="small" danger style={{ marginLeft: 8 }}>删除</Button>
            </Popconfirm>
          )}
        </>
      )
    }
  ]

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
        <h2 style={{ margin: 0, flex: 1 }}>私有包托管</h2>
        <Input.Search
          placeholder="按仓库名过滤 (留空显示全部)"
          allowClear
          style={{ width: 280 }}
          onSearch={(v) => load(v)}
        />
        <Button
          onClick={() => {
            setRepo('')
            load('')
          }}
        >
          显示全部
        </Button>
        {adm && <Button type="primary" onClick={() => setUploadOpen(true)}>上传包</Button>}
      </div>
      <Table rowKey="id" dataSource={data} columns={columns} size="middle" />
      <Modal
        open={uploadOpen}
        title="上传私有包"
        onCancel={() => setUploadOpen(false)}
        footer={null}
      >
        <Input
          placeholder="仓库名 (必填, 如 pypi / mypkg)"
          value={uploadRepo}
          onChange={(e) => setUploadRepo(e.target.value)}
          style={{ marginBottom: 16 }}
        />
        <Upload.Dragger customRequest={upload} multiple={false} data-testid="pkg-upload">
          <p style={{ fontSize: 40, margin: 0 }}><InboxOutlined /></p>
          <p>点击或拖拽文件到此处上传</p>
        </Upload.Dragger>
      </Modal>
    </>
  )
}
