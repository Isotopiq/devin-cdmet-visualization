import { useWorkspace } from '../context/WorkspaceContext'
import { LuDatabase, LuFolder } from 'react-icons/lu'

export default function DatasetPicker({ showSummary = true }: { showSummary?: boolean }) {
  const { projects, projectId, setProjectId, datasets, datasetId, setDatasetId, selectedDataset, loading } = useWorkspace()

  return (
    <div className="card p-4 mb-6">
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
    </div>
  )
}
