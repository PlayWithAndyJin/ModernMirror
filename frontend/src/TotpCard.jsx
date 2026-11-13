import React from 'react'
import { Card, Col, Input, Row, Typography, message } from 'antd'
import { verifyTotp } from './api'

export default function TotpCard({ nonce, onDone, busy, setBusy }) {
  const go = async () => {
    const code = document.getElementById('fnm-totp').value.trim()
    if (code.length !== 6) { message.error('请输入 6 位动态码'); return }
    setBusy(true)
    try {
      const out = await verifyTotp(nonce, code)
      onDone(out.token)
      message.success('验证通过')
    } catch (err) {
      message.error(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Row justify="center" align="middle" style={{ minHeight: '100vh', background: '#f0f3f8' }}>
      <Col xs={22} sm={14} md={10} lg={8}>
        <Card style={{ borderRadius: 12, boxShadow: '0 4px 24px rgba(0,0,0,.08)' }}>
          <Typography.Title level={4} style={{ textAlign: 'center' }}>MFA 二次认证</Typography.Title>
          <Typography.Text type="secondary" style={{ display: 'block', textAlign: 'center', marginBottom: 16 }}>
            请输入认证器 App (Google/MS/iCloud 等)中的 6 位动态码
          </Typography.Text>
          <Input
            id="fnm-totp" size="large" maxLength={6} autoFocus
            inputMode="numeric" placeholder="123456"
            onKeyDown={(e) => e.key === 'Enter' && go()}
            style={{ textAlign: 'center', letterSpacing: 8, marginBottom: 16 }}
          />
          <button
            onClick={go}
            disabled={busy}
            style={{
              width: '100%', padding: '10px 0', border: 'none', borderRadius: 6,
              background: '#1e6fff', color: '#fff', fontSize: 15, cursor: 'pointer'
            }}
          >
            {busy ? '验证中...' : '验 证'}
          </button>
        </Card>
      </Col>
    </Row>
  )
}
