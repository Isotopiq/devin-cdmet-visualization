import { useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import { deleteDataset } from '../api'
import { LuDatabase, LuFolder, LuTrash2, LuAlertCircle } from 'react-icons/lu'

export default function DatasetPicker({ showSummary = true }: { showSummary?: boolean }) {
  const { projects, projectId, setProjectId, datasets, datasetId, setDatasetId, selectedDataset, loading, refreshDatasets } = useWorkspace()
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  const handleDeleteDataset = async () => {
    if (!projectId || !datasetId) return
    if (!window.confirm('Delete this dataset? This will also remove any analyses using it.')) return
    setDeleting(true)
    setError('')
    try {
      await deleteDataset(Number(projectId), Number(datasetId))
      setDatasetId('')
      await refreshDatasets()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="card p-4 mb-6 space-y-3">
      <div className="flex flex-col md:flex-row gap-4 items-start md:items-end">
        <div className="flex-1 min-w-[12rem]">
          <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Project</label>
          <div className="relative">
            <LuFolder className="absolute left-3 top-2.5 text-slate-400" />
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : '')}
              className="input pl-9"
            >
              <option value="">Select a project</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        </div>
        <div className="flex-[2] min-w-[16rem]">
          <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Dataset</label>
          <div className="relative">
            <LuDatabase className="absolute left-3 top-2.5 text-slate-400" />
            <select
              value={datasetId}
              onChange={(e) => setDatasetId(e.target.value ? Number(e.target.value) : '')}
              className="input pl-9"
              disabled={!projectId || loading}
            >
              <option value="">{projectId ? 'Select a dataset' : 'Choose a project first'}</option>
              {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
        </div>
        {projectId && datasetId && (
          <button
            onClick={handleDeleteDataset}
            disabled={deleting}
            className="p-2.5 text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg border border-transparent hover:border-red-100 dark:hover:border-red-900/50"
            title="Delete dataset"
          >
            <LuTrash2 />
          </button>
        )}
        {showSummary && selectedDataset && (
          <div className="flex gap-3 text-sm">
            <div className="px-3 py-2 rounded-lg bg-slate-100 dark:bg-slate-700">
              <span className="text-slate-500 dark:text-slate-400">Type</span>
              <div className="font-medium capitalize">{selectedDataset.feature_type}</div>
            </div>
            <div className="px-3 py-2 rounded-lg bg-slate-100 dark:bg-slate-700">
              <span className="text-slate-500 dark:text-slate-400">Features</span>
              <div className="font-medium">{(selectedDataset.feature_metadata || []).length}</div>
            </div>
            <div className="px-3 py-2 rounded-lg bg-slate-100 dark:bg-slate-700">
              <span className="text-slate-500 dark:text-slate-400">Samples</span>
              <div className="font-medium">{Object.keys(selectedDataset.sample_metadata || {}).length}</div>
            </div>
          </div>
        )}
      </div>
      {error && (
        <div className="text-sm text-red-600 dark:text-red-200 flex items-center gap-2">
          <LuAlertCircle /> {error}
        </div>
      )}
    </div>
  )
}
