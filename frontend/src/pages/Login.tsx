import { useState, useEffect, FormEvent } from 'react'
import { login, getSettings, forgotPassword } from '../api'
import { LuMail, LuLock, LuArrowLeft } from 'react-icons/lu'

export default function Login({ onLogin }: { onLogin: (t: string) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [showForgot, setShowForgot] = useState(false)
  const [logoUrl, setLogoUrl] = useState('/logo.png')

  useEffect(() => {
    getSettings().then((res) => {
      if (res.data.login_logo_url) setLogoUrl(res.data.login_logo_url)
    }).catch(() => { /* use default */ })
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const res = await login({ username: email, password })
      onLogin(res.data.access_token)
    } catch (err: any) {
      const detail = err.response?.data?.detail
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail || 'Login failed'))
    }
  }

  const sendReset = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setMessage('')
    try {
      const res = await forgotPassword(email)
      setMessage(res.data.detail || 'If this email exists, a reset link has been sent.')
    } catch (err: any) {
      const detail = err.response?.data?.detail
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail || 'Request failed'))
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-200 dark:from-slate-900 dark:to-slate-800 p-4">
      <div className="w-full max-w-md card p-8">
        <div className="flex justify-center mb-8">
          <img src={logoUrl} alt="isotopiq" className="h-10 w-auto object-contain" />
        </div>
        {error && <div className="mb-4 p-3 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-200 text-sm">{error}</div>}
        {message && <div className="mb-4 p-3 rounded-lg bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200 text-sm">{message}</div>}
        {showForgot ? (
          <>
            <button onClick={() => setShowForgot(false)} className="text-sm text-slate-500 dark:text-slate-400 hover:underline flex items-center gap-1 mb-4"><LuArrowLeft /> Back to sign in</button>
            <form onSubmit={sendReset} className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Email</label>
                <div className="relative">
                  <LuMail className="absolute left-3 top-2.5 text-slate-400" />
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="input pl-10" placeholder="you@example.com" required />
                </div>
              </div>
              <button type="submit" className="btn-primary w-full py-2.5">Send Reset Link</button>
            </form>
          </>
        ) : (
          <form onSubmit={submit} className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Email</label>
              <div className="relative">
                <LuMail className="absolute left-3 top-2.5 text-slate-400" />
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="input pl-10" placeholder="you@example.com" required />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Password</label>
              <div className="relative">
                <LuLock className="absolute left-3 top-2.5 text-slate-400" />
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="input pl-10" placeholder="••••••••" required />
              </div>
            </div>
            <button type="submit" className="btn-primary w-full py-2.5">Sign In</button>
            <div className="text-center">
              <button type="button" onClick={() => setShowForgot(true)} className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline">Forgot password?</button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
