import { Routes, Route, Navigate } from 'react-router-dom'
import { WorkspaceProvider } from './context/WorkspaceContext'
import { PlotConfigProvider } from './context/PlotConfigContext'
import { useAuth } from './context/AuthContext'
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
import Visualize from './pages/Visualize'
import Isotope from './pages/Isotope'
import Pathway from './pages/Pathway'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Preprocessing from './pages/Preprocessing'
import Profile from './pages/Profile'
import Admin from './pages/Admin'

function App() {
  const { user, ready, login } = useAuth()

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <span className="text-slate-500 text-sm">Loading…</span>
      </div>
    )
  }

  if (!user) {
    return <Login onLogin={login} />
  }

  return (
    <PlotConfigProvider>
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
          <Route path="visualize" element={<Visualize />} />
          <Route path="isotope" element={<Isotope />} />
          <Route path="pathway" element={<Pathway />} />
          <Route path="reports" element={<Reports />} />
          <Route path="settings" element={<Settings />} />
          <Route path="preprocessing" element={<Preprocessing />} />
          <Route path="profile" element={<Profile />} />
          <Route path="admin" element={<Admin />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Route>
      </Routes>
    </WorkspaceProvider>
    </PlotConfigProvider>
  )
}

export default App
