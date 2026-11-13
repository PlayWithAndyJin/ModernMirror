import React from 'react'
import { Card, Col, Input, Row, Typography, message } from 'antd'
import { login } from './api'

export default function LoginCard({ onLogin, onMfa, busy, setBusy }) {
  const tryLogin = async (username, password) => {
    if (!username || !password) return
    setBusy(true)
    try {
      const out = await login(username, password)
      if (out.mfa_required) {
        onMfa(out.nonce)
      } else {
        onLogin(out.token, out.user)
        message.success('登录成功')
      }
    } catch (err) {
      message.error(err.message)
    } finally {
      setBusy(false)
    }
  }

  const onEnter = (e) => {
    if (e.key === 'Enter') {
      const u = document.getElementById('fnm-user').value.trim()
      const p = document.getElementById('fnm-pass').value
      tryLogin(u, p)
    }
  }

  return (
    <Row justify="center" align="middle" style={{ minHeight: '100vh', background: '#f0f3f8' }}>
      <Col xs={22} sm={14} md={10} lg={8}>
        <Card style={{ borderRadius: 12, boxShadow: '0 4px 24px rgba(0,0,0,.08)' }}>
          <Typography.Title level={3} style={{ textAlign: 'center', marginBottom: 4 }}>
            ModernMirror
          </Typography.Title>
          <Typography.Text type="secondary" style={{ display: 'block', textAlign: 'center', marginBottom: 16 }}>
            本地镜像源缓存系统
          </Typography.Text>
          <Input id="fnm-user" placeholder="用户名" size="large" onKeyDown={onEnter} autoFocus style={{ marginBottom: 12 }} />
          <Input.Password id="fnm-pass" placeholder="密码" size="large" onKeyDown={onEnter} style={{ marginBottom: 16 }} />
          <button
            onClick={() => {
              const u = document.getElementById('fnm-user').value.trim()
              const p = document.getElementById('fnm-pass').value
              tryLogin(u, p)
            }}
            disabled={busy}
            style={{
              width: '100%', padding: '10px 0', border: 'none', borderRadius: 6,
              background: '#1e6fff', color: '#fff', fontSize: 15, cursor: 'pointer'
            }}
          >
            {busy ? '登录中...' : '登 录'}
          </button>
        </Card>
      </Col>
    </Row>
  )
}
