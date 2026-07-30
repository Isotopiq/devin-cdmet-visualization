import { useEffect, useState, FormEvent, useRef } from 'react'
import { me, updateMe, uploadAvatar, getAvatar } from '../api'
import { useAuth } from '../context/AuthContext'
import { LuUser } from 'react-icons/lu'
import type { User } from '../types'

export default function Profile() {
  const { refreshUser } = useAuth()
  const [user, setUser] = useState<User | null>(null)
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = async () => {
    try {
      const res = await me()
      const u = res.data as User
      setUser(u)
      setEmail(u.email)
      setName(u.name || '')
      if (u.avatar_url && u.id) {
        const avatarRes = await getAvatar(u.id)
        setAvatarPreview(URL.createObjectURL(avatarRes.data))
      }
    } catch {
      setError('Could not load profile')
    }
  }

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    return () => {
      if (avatarPreview) URL.revokeObjectURL(avatarPreview)
    }
  }, [avatarPreview])

  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setLoading(true)
    setError('')
    try {
      const res = await uploadAvatar(file)
      const u = res.data as User
      setUser(u)
      const avatarRes = await getAvatar(u.id)
      const url = URL.createObjectURL(avatarRes.data)
      setAvatarPreview(url)
      setSuccess('Avatar updated')
      await refreshUser()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Avatar upload failed')
    } finally {
      setLoading(false)
    }
  }

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
      const payload: { email?: string; name?: string; password?: string } = {}
      if (email !== user?.email) payload.email = email
      if (name !== (user?.name || '')) payload.name = name
      if (password) payload.password = password
      const res = await updateMe(payload)
      setUser(res.data)
      setSuccess('Profile updated')
      setPassword('')
      setConfirm('')
      await refreshUser()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Update failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-xl mx-auto">
      <h2 className="text-2xl font-semibold mb-6 text-slate-900 dark:text-white">User Profile</h2>
      <div className="card p-6 space-y-6">
        {error && <div className="p-3 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-200 text-sm">{error}</div>}
        {success && <div className="p-3 rounded-lg bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200 text-sm">{success}</div>}

        <div className="flex items-center gap-4">
          <div className="w-20 h-20 rounded-full overflow-hidden bg-slate-200 dark:bg-slate-700 flex items-center justify-center text-slate-500">
            {avatarPreview ? (
              <img src={avatarPreview} alt="avatar" className="w-full h-full object-cover" />
            ) : (
              <LuUser className="w-10 h-10" />
            )}
          </div>
          <div>
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={loading}
              className="btn-secondary text-sm px-4 py-2"
            >
              {loading ? 'Uploading...' : 'Upload Avatar'}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/jpg,image/webp"
              className="hidden"
              onChange={handleAvatarChange}
            />
            <p className="text-xs text-slate-500 mt-1">PNG, JPEG, or WebP up to a few MB.</p>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Display Name</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} className="input" placeholder="Your name" />
          </div>
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
