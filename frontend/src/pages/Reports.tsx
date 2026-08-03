import { useEffect, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import { listAnalyses, deleteAnalysis } from '../api'
import { LuFileText, LuClock, LuDownload, LuTrash2 } from 'react-icons/lu'
import DatasetPicker from '../components/DatasetPicker'
import PDFReportPanel from '../components/PDFReportPanel'

export default function Reports() {
  const { projectId, selectedDataset } = useWorkspace()
  const [analyses, setAnalyses] = useState<any[]>([])

  const load = () => {
    if (projectId) {
      listAnalyses(Number(projectId)).then((r) => setAnalyses(r.data)).catch(() => setAnalyses([]))
    } else {
      setAnalyses([])
    }
  }

  useEffect(() => {
    load()
  }, [projectId, selectedDataset])

  const handleDelete = async (analysisId: number) => {
    if (!projectId || !analysisId) return
    try {
      await deleteAnalysis(Number(projectId), analysisId)
      load()
    } catch {
      // swallow errors; list refreshes on success
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Reports & History</h1>
        <p className="page-subtitle">Project-level analysis history and downloadable summaries.</p>
      </div>

      <DatasetPicker />

      <PDFReportPanel />

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
                <div className="flex items-center gap-2">
                  <button className="btn-secondary text-xs"><LuDownload /> Export</button>
                  <button onClick={() => handleDelete(a.id)} className="btn-secondary text-xs text-red-600 dark:text-red-400"><LuTrash2 /> Delete</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
