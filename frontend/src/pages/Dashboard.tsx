import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspace } from '../context/WorkspaceContext'
import { listAnalyses, listDatasets } from '../api'
import { LuFolderOpen, LuDatabase, LuActivity, LuUploadCloud, LuArrowRight } from 'react-icons/lu'

export default function Dashboard() {
  const { projects, projectId, selectedDataset, refreshProjects } = useWorkspace()
  const [datasetCount, setDatasetCount] = useState(0)
  const [analysisCount, setAnalysisCount] = useState(0)

  useEffect(() => { refreshProjects() }, [])

  useEffect(() => {
    if (projectId) {
      listDatasets(Number(projectId)).then((r) => setDatasetCount(r.data.length))
      listAnalyses(Number(projectId)).then((r) => setAnalysisCount(r.data.length)).catch(() => setAnalysisCount(0))
    } else {
      setDatasetCount(0)
      setAnalysisCount(0)
    }
  }, [projectId])

  const cards = [
    { label: 'Projects', value: projects.length, icon: <LuFolderOpen />, color: 'bg-blue-500', to: '/projects' },
    { label: 'Datasets', value: datasetCount, icon: <LuDatabase />, color: 'bg-emerald-500', to: '/data' },
    { label: 'Analyses', value: analysisCount, icon: <LuActivity />, color: 'bg-amber-500', to: '/reports' },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">Overview of your metabolomics and lipidomics workspace.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {cards.map((c) => (
          <Link key={c.label} to={c.to} className="card p-5 hover:shadow-md transition-shadow group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{c.label}</p>
                <p className="text-3xl font-bold text-slate-900 dark:text-white mt-1">{c.value}</p>
              </div>
              <div className={`${c.color} text-white p-3 rounded-xl text-xl group-hover:scale-105 transition-transform`}>{c.icon}</div>
            </div>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-5">
          <h3 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2"><LuUploadCloud /> Quick Start</h3>
          <ol className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
            <li className="flex gap-3"><span className="font-bold text-indigo-600">1</span> Create a project in <Link to="/projects" className="text-indigo-600 hover:underline">Projects</Link>.</li>
            <li className="flex gap-3"><span className="font-bold text-indigo-600">2</span> Upload Compound Discoverer or LipidSearch files in <Link to="/import" className="text-indigo-600 hover:underline">Import Data</Link>.</li>
            <li className="flex gap-3"><span className="font-bold text-indigo-600">3</span> Explore the data table, statistics, plots, and reports.</li>
          </ol>
          <div className="mt-5 flex gap-3">
            <Link to="/import" className="btn-primary"><LuUploadCloud /> Import Data</Link>
            <Link to="/projects" className="btn-secondary">Manage Projects</Link>
          </div>
        </div>

        <div className="card p-5">
          <h3 className="font-semibold text-slate-900 dark:text-white mb-4">Active Dataset</h3>
          {selectedDataset ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-slate-500 dark:text-slate-400">Name</span><span className="font-medium text-slate-900 dark:text-white">{selectedDataset.name}</span></div>
              <div className="flex justify-between"><span className="text-slate-500 dark:text-slate-400">Type</span><span className="font-medium capitalize">{selectedDataset.feature_type}</span></div>
              <div className="flex justify-between"><span className="text-slate-500 dark:text-slate-400">Features</span><span className="font-medium">{(selectedDataset.feature_metadata || []).length}</span></div>
              <div className="flex justify-between"><span className="text-slate-500 dark:text-slate-400">Samples</span><span className="font-medium">{Object.keys(selectedDataset.sample_metadata || {}).length}</span></div>
              <Link to="/stats" className="inline-flex items-center gap-1 mt-3 text-indigo-600 hover:underline"><LuArrowRight /> Start analysis</Link>
            </div>
          ) : (
            <p className="text-sm text-slate-500 dark:text-slate-400">No dataset selected. Choose a project and dataset above or import a new file.</p>
          )}
        </div>
      </div>
    </div>
  )
}
