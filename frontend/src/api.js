import { message } from 'antd'

export async function api(path, options = {}) {
  const token = sessionStorage.getItem('modernmirror_session') || ''
  const res = await fetch(path, {
    ...options,
    redirect: 'error',
    headers: {
      ...(options.headers || {}),
      'Session-Token': token
    }
  })
  if (res.status === 401) {
    sessionStorage.removeItem('modernmirror_session')
    window.dispatchEvent(new CustomEvent('modernmirror-logout'))
    throw new Error('login required')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch (e) {}
    throw new Error(detail)
  }
  return res.json()
}

export async function login(username, password) {
  const res = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.detail || '登录失败')
  return body
}

export async function verifyTotp(nonce, code) {
  const res = await fetch('/auth/verify-totp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nonce, code })
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.detail || '验证失败')
  return body
}

export async function whoami() {
  const res = await fetch('/api/whoami', {
    headers: { 'Session-Token': sessionStorage.getItem('modernmirror_session') || '' }
  })
  const j = await res.json().catch(() => ({}))
  return j.user || null
}

export function fmtBytes(n) {
  if (n == null || isNaN(n)) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let v = Number(n)
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return v.toFixed(v >= 100 || i === 0 ? 0 : 1) + ' ' + units[i]
}
