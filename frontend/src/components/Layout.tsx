import { useEffect, useState, useRef } from 'react'
import { NavLink, Outlet, useLocation, Link } from 'react-router-dom'
import {
  LuLayoutDashboard, LuFolderOpen, LuUploadCloud, LuTable,
  LuSlidersHorizontal, LuCalculator, LuBarChart3, LuPieChart, LuLayers, LuDna,
  LuGitMerge, LuFileText, LuSettings, LuSun, LuMoon,
  LuLogOut, LuMenu, LuChevronLeft, LuMicroscope, LuUsers, LuUser
} from 'react-icons/lu'
import { useWorkspace } from '../context/WorkspaceContext'
import { useAuth } from '../context/AuthContext'
import type { SiteSettings, User } from '../types'
import { getSettings, getAvatar } from '../api'

interface NavItem {
  to: string
  label: string
  icon: React.ReactNode
  section?: string
}

const baseNavItems: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: <LuLayoutDashboard /> },
  { to: '/projects', label: 'Projects', icon: <LuFolderOpen /> },
  { to: '/import', label: 'Import Data', icon: <LuUploadCloud /> },
  { to: '/data', label: 'Data Table', icon: <LuTable /> },
  { section: 'Analysis', to: '/preprocessing', label: 'Preprocessing', icon: <LuSlidersHorizontal /> },
  { to: '/stats', label: 'Statistics', icon: <LuCalculator /> },
  { to: '/visualize', label: 'Visualize', icon: <LuBarChart3 /> },
  { section: 'Specialized', to: '/isotope', label: 'Isotope Tracing', icon: <LuDna /> },
  { to: '/pathway', label: 'Pathway Mapping', icon: <LuGitMerge /> },
  { section: 'Output', to: '/reports', label: 'Reports', icon: <LuFileText /> },
  { to: '/settings', label: 'Settings', icon: <LuSettings /> },
]

function ThemeToggle() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))

  useEffect(() => {
    const saved = localStorage.getItem('theme')
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    const isDark = saved ? saved === 'dark' : prefersDark
    setDark(isDark)
    if (isDark) document.documentElement.classList.add('dark')
    else document.documentElement.classList.remove('dark')
  }, [])

  const toggle = () => {
    const next = !dark
    setDark(next)
    localStorage.setItem('theme', next ? 'dark' : 'light')
    if (next) document.documentElement.classList.add('dark')
    else document.documentElement.classList.remove('dark')
  }

  return (
    <button onClick={toggle} className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700" title="Toggle theme">
      {dark ? <LuSun /> : <LuMoon />}
    </button>
  )
}

function WorkspaceBadge() {
  const { projectId, selectedDataset, projects } = useWorkspace()
  const project = projects.find((p) => p.id === projectId)
  if (!project) return <span className="text-sm text-slate-500">No project selected</span>
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="px-2 py-1 rounded-md bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-200 font-medium truncate max-w-[12rem]">{project.name}</span>
      {selectedDataset && <span className="text-slate-400">/</span>}
      {selectedDataset && <span className="px-2 py-1 rounded-md bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-200 font-medium truncate max-w-[14rem]">{selectedDataset.name}</span>}
    </div>
  )
}

function UserMenu({ user, onLogout }: { user: User | null; onLogout: () => void }) {
  const [open, setOpen] = useState(false)
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handle = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [])

  useEffect(() => {
    let url: string | null = null
    if (user?.avatar_url && user.id) {
      const rev = user.avatar_url.split('?')[1]?.replace(/^v=/, '')
      getAvatar(user.id, rev)
        .then((res) => {
          url = URL.createObjectURL(res.data)
          setAvatarUrl(url)
        })
        .catch(() => setAvatarUrl(null))
    } else {
      setAvatarUrl(null)
    }
    return () => { if (url) URL.revokeObjectURL(url) }
  }, [user?.avatar_url, user?.id])

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(!open)} className="flex items-center gap-2 p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-sm">
        <span className="hidden sm:inline max-w-[8rem] truncate">{user?.name || user?.email || 'User'}</span>
        <span className="w-8 h-8 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center overflow-hidden">
          {avatarUrl ? (
            <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
          ) : (
            <LuUser className="text-sm" />
          )}
        </span>
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-48 bg-white dark:bg-slate-800 rounded-lg shadow-lg border border-slate-200 dark:border-slate-700 py-1 z-50">
          <Link to="/profile" onClick={() => setOpen(false)} className="flex items-center gap-2 px-4 py-2 text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700">
            <LuUser /> Profile
          </Link>
          {user?.is_admin && (
            <Link to="/admin" onClick={() => setOpen(false)} className="flex items-center gap-2 px-4 py-2 text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700">
              <LuUsers /> Admin
            </Link>
          )}
          <button onClick={() => { setOpen(false); onLogout() }} className="w-full flex items-center gap-2 px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-slate-100 dark:hover:bg-slate-700">
            <LuLogOut /> Logout
          </button>
        </div>
      )}
    </div>
  )
}

export default function Layout() {
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const { user, logout } = useAuth()
  const [logoUrl, setLogoUrl] = useState('/logo-white.png')

  useEffect(() => {
    getSettings().then((res: { data: SiteSettings }) => {
      if (res.data.dashboard_logo_url) setLogoUrl(res.data.dashboard_logo_url)
    }).catch(() => { })
  }, [])

  const navItems: NavItem[] = [...baseNavItems]
  if (user?.is_admin) {
    navItems.push({ section: 'Admin', to: '/admin', label: 'Admin Panel', icon: <LuUsers /> })
  }

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-slate-900">
      <aside className={`${collapsed ? 'w-16' : 'w-64'} flex-shrink-0 bg-slate-900 text-slate-200 transition-all duration-300 flex flex-col`}>
        <div className="h-16 flex items-center justify-between px-4 border-b border-slate-700">
          <div className={`flex items-center ${collapsed ? 'justify-center w-full' : ''}`}>
            <img src={logoUrl} alt="isotopiq" className={`object-contain ${collapsed ? 'h-7 max-w-[2.5rem]' : 'h-8 max-w-[11rem]'}`} />
          </div>
          <button onClick={() => setCollapsed(!collapsed)} className="p-1.5 rounded-md hover:bg-slate-700 text-slate-300 flex-shrink-0">
            {collapsed ? <LuMenu /> : <LuChevronLeft />}
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-1">
          {navItems.map((item, idx) => (
            <div key={item.to}>
              {item.section && !collapsed && (idx === 0 || navItems[idx - 1].section !== item.section) && (
                <div className="px-3 pt-4 pb-1 text-xs font-semibold uppercase tracking-wider text-slate-500">{item.section}</div>
              )}
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                  } ${collapsed ? 'justify-center' : ''}`
                }
                title={collapsed ? item.label : undefined}
              >
                <span className="text-lg">{item.icon}</span>
                {!collapsed && <span>{item.label}</span>}
              </NavLink>
            </div>
          ))}
        </nav>
        <div className="p-3 border-t border-slate-700">
          <button onClick={logout} className={`flex items-center gap-3 w-full px-3 py-2 text-sm font-medium text-red-400 hover:bg-slate-800 rounded-lg transition-colors ${collapsed ? 'justify-center' : ''}`} title={collapsed ? 'Logout' : undefined}>
            <LuLogOut />
            {!collapsed && <span>Logout</span>}
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-16 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between px-6 shadow-sm">
          <div className="flex items-center gap-4 min-w-0">
            <h1 className="text-lg font-semibold text-slate-900 dark:text-white truncate">
              {navItems.find((n) => n.to === location.pathname)?.label || 'MetaboScope'}
            </h1>
            <div className="hidden md:block h-6 w-px bg-slate-200 dark:bg-slate-700" />
            <div className="hidden md:flex items-center gap-2 min-w-0">
              <WorkspaceBadge />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <UserMenu user={user} onLogout={logout} />
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
