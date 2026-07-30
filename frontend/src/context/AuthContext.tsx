import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import API, { me } from '../api'
import type { User } from '../types'

interface AuthCtx {
  user: User | null
  ready: boolean
  login: (token: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthCtx | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)

  const validate = async () => {
    const token = localStorage.getItem('token')
    if (!token) {
      setReady(true)
      return
    }
    try {
      const res = await me()
      setUser(res.data)
      API.defaults.headers.common['Authorization'] = `Bearer ${token}`
    } catch {
      localStorage.removeItem('token')
      delete API.defaults.headers.common['Authorization']
    }
    setReady(true)
  }

  const login = async (token: string) => {
    localStorage.setItem('token', token)
    API.defaults.headers.common['Authorization'] = `Bearer ${token}`
    const res = await me()
    setUser(res.data)
  }

  const logout = () => {
    localStorage.removeItem('token')
    delete API.defaults.headers.common['Authorization']
    setUser(null)
    window.location.href = '/'
  }

  const refreshUser = async () => {
    try {
      const res = await me()
      setUser(res.data)
    } catch {
      logout()
    }
  }

  useEffect(() => { validate() }, [])

  return (
    <AuthContext.Provider value={{ user, ready, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
