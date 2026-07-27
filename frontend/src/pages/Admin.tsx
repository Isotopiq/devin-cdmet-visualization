import { useEffect, useState, FormEvent } from 'react'
import { listUsers, createUser, updateUser, deleteUser, listLogs, uploadLogo } from '../api'
import type { User, AdminLog } from '../types'

export default function Admin() {
  const [users, setUsers] = useState<User[]>([])
  const [logs, setLogs] = useState<AdminLog[]>([])
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [activeTab, setActiveTab] = useState<'users' | 'logs' | 'logos'>('users')

  const load = async () => {
    try {
      const [uRes, lRes] = await Promise.all([listUsers(), listLogs()])
      setUsers(uRes.data)
      setLogs(lRes.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load admin data')
    }
  }

  useEffect(() => {
    load()
  }, [])

  const create = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    try {
      await createUser({ email, password, is_admin: isAdmin, is_active: true })
      setSuccess('User created')
      setEmail('')
      setPassword('')
      setIsAdmin(false)
      load()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create user')
    }
  }

  const toggleAdmin = async (user: User) => {
    try {
      await updateUser(user.id, { is_admin: !user.is_admin })
      load()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update user')
    }
  }

  const toggleActive = async (user: User) => {
    try {
      await updateUser(user.id, { is_active: !user.is_active })
      load()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update user')
    }
  }

  const remove = async (id: number) => {
    if (!window.confirm('Delete this user? This cannot be undone.')) return
    try {
      await deleteUser(id)
      load()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete user')
    }
  }

  const upload = async (type: 'login' | 'dashboard', file: File | null) => {
    if (!file) return
    try {
      await uploadLogo(type, file)
      setSuccess(`${type} logo uploaded. Refresh to see changes.`)
    } catch (err: any) {
      setError(err.response?.data?.detail || `Failed to upload ${type} logo`)
    }
  }

  return (
    <div className="max-w-5xl mx-auto">
      <h2 className="text-2xl font-semibold mb-6 text-slate-900 dark:text-white">Admin Panel</h2>

      <div className="flex gap-2 mb-4 border-b border-slate-200 dark:border-slate-700">
        {(['users', 'logs', 'logos'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setActiveTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize ${activeTab === t ? 'border-b-2 border-indigo-600 text-indigo-600 dark:text-indigo-400' : 'text-slate-500 dark:text-slate-400'}`}
          >
            {t}
          </button>
        ))}
      </div>

      {error && <div className="mb-4 p-3 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-200 text-sm">{error}</div>}
      {success && <div className="mb-4 p-3 rounded-lg bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200 text-sm">{success}</div>}

      {activeTab === 'users' && (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-lg font-medium mb-4 text-slate-900 dark:text-white">Create User</h3>
            <form onSubmit={create} className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Email</label>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="input" required />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Password</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="input" required />
              </div>
              <div className="flex items-center gap-2 h-10">
                <input id="isAdmin" type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} className="rounded" />
                <label htmlFor="isAdmin" className="text-sm text-slate-700 dark:text-slate-300">Admin</label>
              </div>
              <button type="submit" className="btn-primary">Create</button>
            </form>
          </div>

          <div className="card overflow-hidden">
            <table className="min-w-full text-sm text-left">
              <thead className="bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                <tr>
                  <th className="px-4 py-3 font-medium">Email</th>
                  <th className="px-4 py-3 font-medium">Active</th>
                  <th className="px-4 py-3 font-medium">Admin</th>
                  <th className="px-4 py-3 font-medium">Created</th>
                  <th className="px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                {users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="px-4 py-3 text-slate-900 dark:text-slate-100">{u.email}</td>
                    <td className="px-4 py-3">
                      <button onClick={() => toggleActive(u)} className={`px-2 py-1 rounded text-xs ${u.is_active ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'}`}>
                        {u.is_active ? 'Active' : 'Inactive'}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <button onClick={() => toggleAdmin(u)} className={`px-2 py-1 rounded text-xs ${u.is_admin ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-200' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'}`}>
                        {u.is_admin ? 'Admin' : 'User'}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{new Date(u.created_at).toLocaleString()}</td>
                    <td className="px-4 py-3">
                      <button onClick={() => remove(u.id)} className="text-red-600 dark:text-red-400 hover:underline">Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'logs' && (
        <div className="card overflow-hidden">
          <table className="min-w-full text-sm text-left">
            <thead className="bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
              <tr>
                <th className="px-4 py-3 font-medium">Time</th>
                <th className="px-4 py-3 font-medium">Action</th>
                <th className="px-4 py-3 font-medium">By</th>
                <th className="px-4 py-3 font-medium">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
              {logs.map((log) => (
                <tr key={log.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{new Date(log.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-slate-900 dark:text-slate-100">{log.action}</td>
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{log.user_id || 'system'}</td>
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{JSON.stringify(log.details)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {logs.length === 0 && <div className="p-6 text-slate-500 dark:text-slate-400 text-sm">No logs yet.</div>}
        </div>
      )}

      {activeTab === 'logos' && (
        <div className="card p-6 space-y-6">
          <div>
            <h3 className="text-lg font-medium mb-2 text-slate-900 dark:text-white">Login Logo</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-2">Displayed on the login page.</p>
            <input type="file" accept="image/png,image/jpeg,image/svg+xml" onChange={(e) => upload('login', e.target.files?.[0] || null)} />
          </div>
          <div>
            <h3 className="text-lg font-medium mb-2 text-slate-900 dark:text-white">Dashboard Logo</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-2">Displayed in the sidebar. Use a white/light version for dark backgrounds.</p>
            <input type="file" accept="image/png,image/jpeg,image/svg+xml" onChange={(e) => upload('dashboard', e.target.files?.[0] || null)} />
          </div>
        </div>
      )}
    </div>
  )
}
