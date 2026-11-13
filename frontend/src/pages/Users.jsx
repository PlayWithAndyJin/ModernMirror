import React, { useEffect, useState } from 'react'
import {
  Button, Card, Form, Input, List, Modal, Popconfirm, Select, Switch,
  Table, Tag, Typography, message
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { api } from '../api'

export default function Users() {
  const [users, setUsers] = useState([])
  const [modal, setModal] = useState(null)

  const load = async () => setUsers(await api('/admin/users'))
  useEffect(() => { load() }, [])

  const save = async (values) => {
    try {
      await api('/admin/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values)
      })
      message.success('已创建')
      setModal(null)
      load()
    } catch (err) {
      message.error(err.message)
    }
  }

  const patch = async (username, body) => {
    try {
      await api(`/admin/users/${username}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
      message.success('已更新')
      load()
    } catch (err) {
      message.error(err.message)
    }
  }

  const remove = async (username) => {
    try {
      await api(`/admin/users/${username}`, { method: 'DELETE' })
      message.success('已删除')
      load()
    } catch (err) {
      message.error(err.message)
    }
  }

  const resetMfa = async (username) => {
    try {
      await api(`/admin/users/${username}/reset-mfa`, { method: 'POST' })
      message.success('已重置该用户的 MFA')
      load()
    } catch (err) {
      message.error(err.message)
    }
  }

  const columns = [
    { title: '用户名', dataIndex: 'username', render: (v) => <b>{v}</b> },
    {
      title: '角色', dataIndex: 'role',
      render: (v) => <Tag color={v === 'admin' ? 'red' : 'blue'}>{v}</Tag>
    },
    {
      title: 'MFA', dataIndex: 'mfa',
      render: (v, r) => v ? <Tag color="green">已开启</Tag> : <Tag>未开启</Tag>
    },
    {
      title: '所属组', dataIndex: 'groups',
      render: (v) => (v || []).map((g) => <Tag key={g} style={{ marginBottom: 2 }}>{g}</Tag>)
    },
    {
      title: '启用', dataIndex: 'enabled',
      render: (v, r) => (
        <Switch
          disabled={r.username === 'admin'}
          checked={!!v}
          onChange={(c) => patch(r.username, { enabled: c })}
        />
      )
    },
    { title: '创建时间', dataIndex: 'created_at' },
    {
      title: '操作', render: (_, r) => (
        <>
          <Button
            size="small"
            onClick={() => {
              setModal({ user: r })
            }}
          >
            重置密码
          </Button>
          <Button size="small" style={{ marginLeft: 8 }} onClick={() => resetMfa(r.username)}>
            重置MFA
          </Button>
          <Popconfirm
            title={`删除用户 ${r.username}?`}
            disabled={r.username === 'admin'}
            onConfirm={() => remove(r.username)}
          >
            <Button size="small" danger style={{ marginLeft: 8 }} disabled={r.username === 'admin'}>
              删除
            </Button>
          </Popconfirm>
        </>
      )
    }
  ]

  let form = null

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>用户管理</h2>
        <Button
          type="primary" icon={<PlusOutlined />}
          onClick={() => setModal({})}
        >
          添加用户
        </Button>
      </div>
      <Table rowKey="id" dataSource={users} columns={columns} />
      <Modal
        open={!!modal}
        title={
          modal?.user
            ? `重置 ${modal.user.username} 的密码`
            : '添加用户'
        }
        onCancel={() => setModal(null)}
        footer={null}
      >
        <Form
          ref={(f) => (form = f)}
          initialValues={modal?.user ? { role: modal.user.role } : { role: 'user' }}
          layout="vertical"
          onFinish={save}
        >
          {!modal?.user && (
            <Form.Item
              name="username"
              label="用户名"
              rules={[{ required: true, pattern: /^[a-zA-Z0-9_-]+$/, message: '仅限字母数字_-且非空' }]}
            >
              <Input placeholder="如 bob" />
            </Form.Item>
          )}
          <Form.Item
            name="password"
            label={modal?.user ? '新密码' : '初始密码'}
            rules={[{ required: true, min: 8, message: '至少 8 位' }]}
          >
            <Input.Password placeholder="至少 8 位" />
          </Form.Item>
          {!modal?.user && (
            <Form.Item name="role" label="角色" rules={[{ required: true }]}>
              <Select
                options={[
                  { value: 'user', label: '普通用户 (仅使用被授权的源)' },
                  { value: 'admin', label: '管理员 (全部管理权限)' }
                ]}
              />
            </Form.Item>
          )}
          <Button type="primary" htmlType="submit" block>
            {modal?.user ? '重置密码' : '创建用户'}
          </Button>
        </Form>
      </Modal>
    </>
  )
}
