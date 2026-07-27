import { useEffect, useState, FormEvent } from 'react'
import { me, updateMe } from '../api'
import type { User } from '../types'

export default function Profile() {
  const [user, setUser] = useState<User | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    me().then((res) => {
      setUser(res.data)
      setEmail(res.data.email)
    }).catch(() => setError('Could not load profile'))
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    if (password && password !== confirm) {
      setError('Passwords do not match')
      return
    }
    setLoading(true)
    try {
      const payload: { email?: string; password?: string } = {}
      if (email !== user?.email) payload.email = email
      if (password) payload.password = password
      const res = await updateMe(payload)
      setUser(res.data)
      setSuccess('Profile updated')
      setPassword('')
      setConfirm('')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Update failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-xl mx-auto">
      <h2 className="text-2xl font-semibold mb-6 text-slate-900 dark:text-white">User Profile</h2>
      <div className="card p-6 space-y-4">
        {error && <div className="p-3 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-200 text-sm">{error}</div>}
        {success && <div className="p-3 rounded-lg bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200 text-sm">{success}</div>}
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="input" required />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">New Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="input" placeholder="Leave blank to keep current" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Confirm New Password</label>
            <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className="input" placeholder="Leave blank to keep current" />
          </div>
          <button type="submit" disabled={loading} className="btn-primary">{loading ? 'Saving...' : 'Update Profile'}</button>
        </form>
      </div>
    </div>
  )
}
