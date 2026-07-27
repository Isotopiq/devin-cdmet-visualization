import { Routes, Route, Navigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { WorkspaceProvider } from './context/WorkspaceContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Projects from './pages/Projects'
import Import from './pages/Import'
import DataTable from './pages/DataTable'
import Statistics from './pages/Statistics'
import Plots from './pages/Plots'
import HeatMap from './pages/HeatMap'
import PCA from './pages/PCA'
import Volcano from './pages/Volcano'
import Isotope from './pages/Isotope'
import Pathway from './pages/Pathway'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Preprocessing from './pages/Preprocessing'

function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'))

  useEffect(() => {
    const onStorage = () => setToken(localStorage.getItem('token'))
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  if (!token) {
    return <Login onLogin={(t) => { localStorage.setItem('token', t); setToken(t) }} />
  }

  return (
    <WorkspaceProvider>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="projects" element={<Projects />} />
          <Route path="import" element={<Import />} />
          <Route path="data" element={<DataTable />} />
          <Route path="stats" element={<Statistics />} />
          <Route path="compound-plots" element={<Plots />} />
          <Route path="heatmap" element={<HeatMap />} />
          <Route path="pca" element={<PCA />} />
          <Route path="volcano" element={<Volcano />} />
          <Route path="isotope" element={<Isotope />} />
          <Route path="pathway" element={<Pathway />} />
          <Route path="reports" element={<Reports />} />
          <Route path="settings" element={<Settings />} />
          <Route path="preprocessing" element={<Preprocessing />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Route>
      </Routes>
    </WorkspaceProvider>
  )
}

export default App
