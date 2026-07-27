import { useEffect, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import { listAnalyses } from '../api'
import { LuFileText, LuDownload, LuClock } from 'react-icons/lu'

export default function Reports() {
  const { projectId, selectedDataset } = useWorkspace()
  const [analyses, setAnalyses] = useState<any[]>([])

  useEffect(() => {
    if (projectId) {
      listAnalyses(Number(projectId)).then((r) => setAnalyses(r.data)).catch(() => setAnalyses([]))
    } else {
      setAnalyses([])
    }
  }, [projectId, selectedDataset])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Reports & History</h1>
        <p className="page-subtitle">Project-level analysis history and downloadable summaries.</p>
      </div>

      <div className="card p-5">
        <h3 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2"><LuFileText /> Analyses</h3>
        {analyses.length === 0 ? (
          <div className="text-sm text-slate-500 dark:text-slate-400">No saved analyses yet. Run statistics, plots, or preprocessing to build a history.</div>
        ) : (
          <div className="space-y-3">
            {analyses.map((a, i) => (
              <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50">
                <div className="flex items-center gap-3">
                  <LuClock className="text-slate-400" />
                  <div>
                    <div className="text-sm font-medium text-slate-900 dark:text-white capitalize">{a.type}</div>
                    <div className="text-xs text-slate-500 dark:text-slate-400">{new Date(a.created_at).toLocaleString()}</div>
                  </div>
                </div>
                <button className="btn-secondary text-xs"><LuDownload /> Export</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
