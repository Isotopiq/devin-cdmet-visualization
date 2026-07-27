import { useState, useEffect, FormEvent } from 'react'
import { login, getSettings } from '../api'
import { LuMail, LuLock } from 'react-icons/lu'

export default function Login({ onLogin }: { onLogin: (t: string) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [logoUrl, setLogoUrl] = useState('/logo.png')

  useEffect(() => {
    getSettings().then((res) => {
      if (res.data.login_logo_url) setLogoUrl(res.data.login_logo_url)
    }).catch(() => { /* use default */ })
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      const res = await login({ username: email, password })
      onLogin(res.data.access_token)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Login failed')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-200 dark:from-slate-900 dark:to-slate-800 p-4">
      <div className="w-full max-w-md card p-8">
        <div className="flex justify-center mb-8">
          <img src={logoUrl} alt="isotopiq" className="h-10 w-auto object-contain" />
        </div>
        {error && <div className="mb-4 p-3 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-200 text-sm">{error}</div>}
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
        </form>
      </div>
    </div>
  )
}
