import { useEffect, useState } from 'react'
import { listProjects, listDatasets } from '../api'
import { Project, Dataset } from '../types'

export default function DataTable() {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState<number | ''>('')
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [selectedDataset, setSelectedDataset] = useState<Dataset | null>(null)

  useEffect(() => { listProjects().then((r) => setProjects(r.data)) }, [])
  useEffect(() => {
    if (projectId) listDatasets(Number(projectId)).then((r) => { setDatasets(r.data); setSelectedDataset(null) })
  }, [projectId])

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4 text-gray-900 dark:text-white">Data Table</h1>
      <select value={projectId} onChange={(e) => setProjectId(Number(e.target.value))} className="border rounded-lg p-2 mb-4 w-full md:w-1/3">
        <option value="">Select project</option>
        {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>

      <div className="flex gap-2 mb-4 overflow-x-auto">
        {datasets.map((d) => (
          <button key={d.id} onClick={() => setSelectedDataset(d)} className={`px-4 py-2 rounded-lg ${selectedDataset?.id === d.id ? 'bg-blue-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300'}`}>
            {d.name}
          </button>
        ))}
      </div>

      {selectedDataset && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <p className="text-sm text-gray-600 dark:text-gray-300">Feature type: {selectedDataset.feature_type}</p>
          <p className="text-sm text-gray-600 dark:text-gray-300">Samples: {Object.keys(selectedDataset.sample_metadata || {}).length}</p>
          <p className="text-sm text-gray-600 dark:text-gray-300">Features: {(selectedDataset.feature_metadata || []).length}</p>
          <table className="min-w-full mt-4 text-sm">
            <thead><tr className="border-b"><th className="text-left p-2">Feature</th><th className="text-left p-2">Group</th></tr></thead>
            <tbody>
              {(selectedDataset.feature_metadata || []).slice(0, 20).map((f: any, i: number) => (
                <tr key={i} className="border-b"><td className="p-2 text-gray-800 dark:text-gray-200">{f.feature_id}</td><td className="p-2 text-gray-600 dark:text-gray-400">{f.lipid_class || f.formula || '-'}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
