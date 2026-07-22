import { NavLink, Outlet, useNavigate } from 'react-router-dom'

const links = [
  { to: '/projects', label: 'Projects' },
  { to: '/import', label: 'Import' },
  { to: '/data', label: 'Data Table' },
  { to: '/stats', label: 'Statistics' },
  { to: '/compound-plots', label: 'Compound Plots' },
  { to: '/heatmap', label: 'Heat Map' },
  { to: '/pca', label: 'PCA' },
  { to: '/volcano', label: 'Volcano Plot' },
  { to: '/isotope', label: 'Isotope Tracing' },
  { to: '/pathway', label: 'Pathway Mapping' },
  { to: '/reports', label: 'Reports' },
  { to: '/settings', label: 'Settings' },
]

export default function Layout() {
  const navigate = useNavigate()

  const logout = () => {
    localStorage.removeItem('token')
    navigate('/')
    window.location.reload()
  }

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-900">
      <aside className="w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex flex-col">
        <div className="p-4 font-bold text-xl text-blue-700 dark:text-blue-400">MetaboScope</div>
        <nav className="flex-1 overflow-y-auto px-2 space-y-1">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              className={({ isActive }) =>
                `block px-4 py-2 rounded-lg text-sm font-medium ${
                  isActive ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300' : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
        <button onClick={logout} className="m-4 px-4 py-2 text-sm text-white bg-red-600 rounded-lg hover:bg-red-700">Logout</button>
      </aside>
      <main className="flex-1 overflow-y-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
