import { useEffect, useState, FormEvent } from 'react'
import {
  listUsers, createUser, updateUser, deleteUser, listLogs, clearLogs, uploadLogo,
  getSettings, updateSettings, uploadFavicon, getSMTPSettings, testSMTP,
  resetAnalyses, getAnalysisCount
} from '../api'
import type { User, AdminLog } from '../types'
import { LuTrash2, LuRotateCcw, LuImage, LuSettings, LuMail, LuSend, LuUser } from 'react-icons/lu'

export default function Admin() {
  const [users, setUsers] = useState<User[]>([])
  const [logs, setLogs] = useState<AdminLog[]>([])
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [activeTab, setActiveTab] = useState<'users' | 'logs' | 'logos' | 'settings'>('users')
  const [analysisCount, setAnalysisCount] = useState(0)

  const [settings, setSettings] = useState<any>({})
  const [smtp, setSmtp] = useState<any>({ host: '', port: 587, user: '', from_address: '', use_tls: true })
  const [smtpPassword, setSmtpPassword] = useState('')
  const [logUserFilter, setLogUserFilter] = useState<number | ''>('')
  const [previewTimestamp, setPreviewTimestamp] = useState(Date.now())

  const load = async () => {
    try {
      const [uRes, lRes, aRes] = await Promise.all([listUsers(), listLogs(logUserFilter || undefined), getAnalysisCount()])
      setUsers(uRes.data)
      setLogs(lRes.data)
      setAnalysisCount(aRes.data.count)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load admin data')
    }
  }

  const loadSettings = async () => {
    try {
      const [sRes, mRes] = await Promise.all([getSettings(), getSMTPSettings()])
      setSettings(sRes.data)
      setSmtp(mRes.data)
    } catch (err: any) {
      // ignore errors for public settings
    }
  }

  useEffect(() => {
    load()
    loadSettings()
  }, [])

  useEffect(() => {
    load()
  }, [logUserFilter])

  const handleTab = (t: 'users' | 'logs' | 'logos' | 'settings') => {
    setActiveTab(t)
    setError('')
    setSuccess('')
  }

  const reset = async () => {
    if (!window.confirm('Reset all analyses? This permanently deletes every analysis record.')) return
    setError('')
    setSuccess('')
    try {
      const res = await resetAnalyses()
      setAnalysisCount(0)
      setSuccess(`Analyses reset. ${res.data.deleted} records deleted.`)
      load()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to reset analyses')
    }
  }

  const create = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    try {
      await createUser({ name: name || undefined, email, password, is_admin: isAdmin, is_active: true })
      setSuccess('User created')
      setName('')
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
    setError('')
    setSuccess('')
    try {
      await uploadLogo(type, file)
      setPreviewTimestamp(Date.now())
      await loadSettings()
      setSuccess(`${type} logo uploaded`)
    } catch (err: any) {
      setError(err.response?.data?.detail || `Failed to upload ${type} logo`)
    }
  }

  const uploadFav = async (file: File | null) => {
    if (!file) return
    setError('')
    setSuccess('')
    try {
      await uploadFavicon(file)
      setPreviewTimestamp(Date.now())
      await loadSettings()
      setSuccess('Favicon uploaded')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to upload favicon')
    }
  }

  const handleClearLogs = async (userId?: number) => {
    const label = userId ? 'this user' : 'all'
    if (!window.confirm(`Clear ${label} logs? This cannot be undone.`)) return
    setError('')
    setSuccess('')
    try {
      await clearLogs(userId)
      load()
      setSuccess(`Cleared ${label} logs`)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to clear logs')
    }
  }

  const saveSmtp = async () => {
    setError('')
    setSuccess('')
    try {
      await updateSettings({
        smtp_host: smtp.host || null,
        smtp_port: smtp.port || null,
        smtp_user: smtp.user || null,
        smtp_from: smtp.from_address || null,
        smtp_use_tls: smtp.use_tls,
        smtp_password: smtpPassword || null,
      })
      setSuccess('SMTP settings saved')
      setSmtpPassword('')
      loadSettings()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save SMTP settings')
    }
  }

  const testSmtpConnection = async () => {
    setError('')
    setSuccess('')
    try {
      const res = await testSMTP({
        host: smtp.host,
        port: Number(smtp.port) || 587,
        user: smtp.user,
        from_address: smtp.from_address,
        use_tls: smtp.use_tls,
      })
      setSuccess(`SMTP test sent to ${res.data.recipient}`)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'SMTP test failed')
    }
  }

  return (
    <div className="max-w-5xl mx-auto">
      <h2 className="text-2xl font-semibold mb-6 text-slate-900 dark:text-white">Admin Panel</h2>

      <div className="flex gap-2 mb-4 border-b border-slate-200 dark:border-slate-700">
        {(['users', 'logs', 'logos', 'settings'] as const).map((t) => (
          <button
            key={t}
            onClick={() => handleTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize ${activeTab === t ? 'border-b-2 border-indigo-600 text-indigo-600 dark:text-indigo-400' : 'text-slate-500 dark:text-slate-400'}`}
          >
            {t === 'logos' ? 'Logos & Favicon' : t}
          </button>
        ))}
      </div>

      {error && <div className="mb-4 p-3 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-200 text-sm">{error}</div>}
      {success && <div className="mb-4 p-3 rounded-lg bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200 text-sm">{success}</div>}

      {activeTab === 'users' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="card p-4">
              <div className="text-xs uppercase text-slate-500 dark:text-slate-400">Analyses</div>
              <div className="text-2xl font-semibold text-slate-900 dark:text-white">{analysisCount}</div>
            </div>
            <div className="card p-4 md:col-span-2 flex items-center justify-between">
              <p className="text-sm text-slate-600 dark:text-slate-300">Reset the number of stored analyses across all projects.</p>
              <button onClick={reset} className="btn-secondary text-red-600 dark:text-red-400 border-red-200 dark:border-red-900/50"><LuRotateCcw /> Reset Analyses</button>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="text-lg font-medium mb-4 text-slate-900 dark:text-white">Create User</h3>
            <form onSubmit={create} className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Name</label>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} className="input" placeholder="Display name" />
              </div>
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
                  <th className="px-4 py-3 font-medium">Name</th>
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
                    <td className="px-4 py-3 text-slate-900 dark:text-slate-100">{u.name || '-'}</td>
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
        <div className="space-y-4">
          <div className="card p-4 flex flex-col md:flex-row md:items-center gap-3">
            <div className="flex items-center gap-2 text-slate-900 dark:text-white">
              <LuUser className="w-4 h-4" />
              <span className="text-sm font-medium">Filter by user</span>
            </div>
            <select
              value={logUserFilter}
              onChange={(e) => setLogUserFilter(e.target.value ? Number(e.target.value) : '')}
              className="input md:w-64"
            >
              <option value="">All users</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.email}</option>
              ))}
            </select>
            <div className="flex-1" />
            <button onClick={() => handleClearLogs(logUserFilter || undefined)} className="btn-secondary text-red-600 dark:text-red-400 border-red-200 dark:border-red-900/50"><LuTrash2 /> Clear {logUserFilter ? 'user' : 'all'} logs</button>
          </div>
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
                    <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{log.user_email || `user ${log.user_id || 'system'}`}</td>
                    <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{Object.entries(log.details || {}).map(([k, v]) => `${k}: ${v}`).join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {logs.length === 0 && <div className="p-6 text-slate-500 dark:text-slate-400 text-sm">No logs found.</div>}
          </div>
        </div>
      )}

      {activeTab === 'logos' && (
        <div className="card p-6 space-y-6">
          <div>
            <h3 className="text-lg font-medium mb-2 text-slate-900 dark:text-white flex items-center gap-2"><LuImage /> Login Logo</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-2">Displayed on the login page.</p>
            {settings.login_logo_url && (
              <img src={`${settings.login_logo_url}?t=${previewTimestamp}`} alt="login logo" className="h-10 w-auto object-contain mb-2 border border-slate-200 dark:border-slate-700 rounded p-1" />
            )}
            <input type="file" accept="image/png,image/jpeg,image/svg+xml" onChange={(e) => upload('login', e.target.files?.[0] || null)} />
          </div>
          <div>
            <h3 className="text-lg font-medium mb-2 text-slate-900 dark:text-white flex items-center gap-2"><LuImage /> Dashboard Logo</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-2">Displayed in the sidebar. Use a white/light version for dark backgrounds.</p>
            {settings.dashboard_logo_url && (
              <img src={`${settings.dashboard_logo_url}?t=${previewTimestamp}`} alt="dashboard logo" className="h-10 w-auto object-contain mb-2 border border-slate-200 dark:border-slate-700 rounded p-1" />
            )}
            <input type="file" accept="image/png,image/jpeg,image/svg+xml" onChange={(e) => upload('dashboard', e.target.files?.[0] || null)} />
          </div>
          <div>
            <h3 className="text-lg font-medium mb-2 text-slate-900 dark:text-white flex items-center gap-2"><LuSettings /> Favicon</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-2">Browser tab icon.</p>
            {settings.favicon_url && (
              <img src={`${settings.favicon_url}?t=${previewTimestamp}`} alt="favicon" className="h-8 w-auto object-contain mb-2 border border-slate-200 dark:border-slate-700 rounded p-1" />
            )}
            <input type="file" accept="image/x-icon,image/png,image/jpeg,image/svg+xml" onChange={(e) => uploadFav(e.target.files?.[0] || null)} />
          </div>
        </div>
      )}

      {activeTab === 'settings' && (
        <div className="card p-6 space-y-6">
          <div className="flex items-center gap-2 mb-2 text-slate-900 dark:text-white font-semibold"><LuMail /> SMTP Configuration</div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">Required for forgot-password emails and other system notifications.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Host</label>
              <input type="text" value={smtp.host || ''} onChange={(e) => setSmtp({ ...smtp, host: e.target.value })} className="input" placeholder="smtp.gmail.com" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Port</label>
              <input type="number" value={smtp.port || ''} onChange={(e) => setSmtp({ ...smtp, port: e.target.value })} className="input" placeholder="587" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Username</label>
              <input type="text" value={smtp.user || ''} onChange={(e) => setSmtp({ ...smtp, user: e.target.value })} className="input" placeholder="user@example.com" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Password</label>
              <input type="password" value={smtpPassword} onChange={(e) => setSmtpPassword(e.target.value)} className="input" placeholder="Leave blank to keep existing" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">From address</label>
              <input type="email" value={smtp.from_address || ''} onChange={(e) => setSmtp({ ...smtp, from_address: e.target.value })} className="input" placeholder="noreply@example.com" />
            </div>
            <div className="flex items-center gap-2 h-10">
              <input id="tls" type="checkbox" checked={smtp.use_tls} onChange={(e) => setSmtp({ ...smtp, use_tls: e.target.checked })} className="rounded" />
              <label htmlFor="tls" className="text-sm text-slate-700 dark:text-slate-300">Use TLS</label>
            </div>
          </div>
          <div className="flex gap-3">
            <button onClick={saveSmtp} className="btn-primary">Save SMTP Settings</button>
            <button onClick={testSmtpConnection} className="btn-secondary"><LuSend /> Test SMTP</button>
          </div>
          {smtp.configured && <div className="text-sm text-emerald-600 dark:text-emerald-400">SMTP is configured.</div>}
        </div>
      )}
    </div>
  )
}
