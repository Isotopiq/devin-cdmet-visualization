import { useState, FormEvent } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { resetPassword } from '../api'
import { LuLock } from 'react-icons/lu'

export default function ResetPassword() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') || ''
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }
    try {
      await resetPassword(token, password)
      setSuccess('Password reset successfully. Redirecting to login...')
      setTimeout(() => navigate('/'), 2000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to reset password')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-200 dark:from-slate-900 dark:to-slate-800 p-4">
      <div className="w-full max-w-md card p-8">
        <h1 className="text-xl font-semibold text-slate-900 dark:text-white mb-4">Reset Password</h1>
        {error && <div className="mb-4 p-3 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-200 text-sm">{error}</div>}
        {success && <div className="mb-4 p-3 rounded-lg bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200 text-sm">{success}</div>}
        {!token && <div className="text-sm text-red-600 dark:text-red-400">Invalid or missing reset token.</div>}
        {token && (
          <form onSubmit={submit} className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">New password</label>
              <div className="relative">
                <LuLock className="absolute left-3 top-2.5 text-slate-400" />
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="input pl-10" placeholder="••••••••" required minLength={6} />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Confirm password</label>
              <div className="relative">
                <LuLock className="absolute left-3 top-2.5 text-slate-400" />
                <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className="input pl-10" placeholder="••••••••" required minLength={6} />
              </div>
            </div>
            <button type="submit" className="btn-primary w-full py-2.5">Reset Password</button>
          </form>
        )}
      </div>
    </div>
  )
}
