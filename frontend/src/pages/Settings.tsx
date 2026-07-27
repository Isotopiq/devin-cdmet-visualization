import { useEffect, useState } from 'react'
import { LuSun, LuMoon, LuMonitor, LuPalette } from 'react-icons/lu'

export default function Settings() {
  const [theme, setTheme] = useState<'light' | 'dark' | 'system'>('system')

  useEffect(() => {
    const saved = localStorage.getItem('theme') as 'light' | 'dark' | 'system' | null
    setTheme(saved || 'system')
  }, [])

  useEffect(() => {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    const isDark = theme === 'dark' || (theme === 'system' && prefersDark)
    if (isDark) document.documentElement.classList.add('dark')
    else document.documentElement.classList.remove('dark')
    if (theme === 'system') localStorage.removeItem('theme')
    else localStorage.setItem('theme', theme)
  }, [theme])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Settings</h1>
        <p className="page-subtitle">Application preferences and display options.</p>
      </div>

      <div className="card p-5 max-w-xl">
        <div className="flex items-center gap-2 mb-4 text-slate-900 dark:text-white font-semibold"><LuPalette className="text-indigo-500" /> Appearance</div>
        <div className="grid grid-cols-3 gap-3">
          {[
            { value: 'light', label: 'Light', icon: <LuSun /> },
            { value: 'dark', label: 'Dark', icon: <LuMoon /> },
            { value: 'system', label: 'System', icon: <LuMonitor /> },
          ].map((t) => (
            <button
              key={t.value}
              onClick={() => setTheme(t.value as any)}
              className={`flex flex-col items-center gap-2 p-4 rounded-xl border transition-colors ${theme === t.value ? 'border-indigo-600 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-200' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/30 text-slate-700 dark:text-slate-200'}`}
            >
              <span className="text-xl">{t.icon}</span>
              <span className="text-sm font-medium">{t.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
