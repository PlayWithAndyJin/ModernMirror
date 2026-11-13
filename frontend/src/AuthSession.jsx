import React, { useEffect, useState } from 'react'
import LoginCard from './LoginCard'
import TotpCard from './TotpCard'

export default function useAuthSession() {
  const [state, setState] = useState({ u: null, ready: false, view: 'loading', nonce: '' })
  const setS = (patch) => setState((s) => ({ ...s, ...patch }))
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    fetch('/api/whoami', {
      headers: { 'Session-Token': sessionStorage.getItem('modernmirror_session') || '' }
    })
      .then((r) => r.json())
      .then((out) => {
        if (out.user) {
          setS({ u: out.user, ready: true, view: 'app' })
        } else {
          // 未登录时清理过期凭据并回到登录页
          sessionStorage.removeItem('modernmirror_session')
          setS({ u: null, ready: true, view: 'login', nonce: '' })
        }
      })
      .catch(() => setS({ u: null, ready: true, view: 'login' }))
  }, [])

  useEffect(() => {
    const onFail = () => setS({ u: null, view: 'login', nonce: '' })
    window.addEventListener('modernmirror-logout', onFail)
    return () => window.removeEventListener('modernmirror-logout', onFail)
  }, [])

  const logout = async () => {
    fetch('/auth/logout', { method: 'POST', headers: { 'Session-Token': sessionStorage.getItem('modernmirror_session') || '' } }).catch(() => {})
    sessionStorage.removeItem('modernmirror_session')
    setS({ u: null, view: 'login', nonce: '' })
  }

  const gate =
    state.view === 'login' ? (
      <LoginCard
        busy={busy} setBusy={setBusy}
        onLogin={(token, u) => {
          sessionStorage.setItem('modernmirror_session', token)
          setS({ u, view: 'app' })
          window.location.reload()
        }}
        onMfa={(nonce) => {
          sessionStorage.removeItem('modernmirror_session')
          setS({ nonce, view: 'totp' })
        }}
      />
    ) : state.view === 'totp' ? (
      <TotpCard
        nonce={state.nonce} busy={busy} setBusy={setBusy}
        onDone={(token) => {
          sessionStorage.setItem('modernmirror_session', token)
          setS({ view: 'app' })
          window.location.reload()
        }}
      />
    ) : null

  return { user: state.u, ready: state.ready, logout, gate }
}
