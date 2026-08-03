import { useEffect, useState, useMemo } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import { listAnalyses, deleteAnalysis } from '../api'
import { LuFileText, LuClock, LuDownload, LuTrash2, LuChevronLeft, LuChevronRight } from 'react-icons/lu'
import DatasetPicker from '../components/DatasetPicker'
import PDFReportPanel from '../components/PDFReportPanel'

const PER_PAGE_OPTIONS = [5, 10, 25, 50, 100]

export default function Reports() {
  const { projectId, selectedDataset } = useWorkspace()
  const [analyses, setAnalyses] = useState<any[]>([])
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(10)

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

  useEffect(() => {
    setPage(1)
  }, [projectId, selectedDataset, perPage])

  const handleDelete = async (analysisId: number) => {
    if (!projectId || !analysisId) return
    try {
      await deleteAnalysis(Number(projectId), analysisId)
      load()
    } catch {
      // swallow errors; list refreshes on success
    }
  }

  const totalPages = Math.max(1, Math.ceil(analyses.length / perPage))
  const safePage = Math.min(page, totalPages)
  const start = (safePage - 1) * perPage
  const visible = useMemo(() => analyses.slice(start, start + perPage), [analyses, start, perPage])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Reports & History</h1>
        <p className="page-subtitle">Project-level analysis history and downloadable summaries.</p>
      </div>

      <DatasetPicker />

      <PDFReportPanel />

      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2"><LuFileText /> Analyses</h3>
          {analyses.length > 0 && (
            <div className="flex items-center gap-3 text-sm">
              <span className="text-slate-500 dark:text-slate-400">{analyses.length} total</span>
              <label className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
                Per page
                <select
                  value={perPage}
                  onChange={(e) => setPerPage(Number(e.target.value))}
                  className="input py-1 px-2 text-sm"
                >
                  {PER_PAGE_OPTIONS.map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </label>
            </div>
          )}
        </div>

        {analyses.length === 0 ? (
          <div className="text-sm text-slate-500 dark:text-slate-400">No saved analyses yet. Run statistics, plots, or preprocessing to build a history.</div>
        ) : (
          <>
            <div className="space-y-3">
              {visible.map((a, i) => (
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

            <div className="flex items-center justify-between mt-5 pt-4 border-t border-slate-200 dark:border-slate-700">
              <div className="text-sm text-slate-500 dark:text-slate-400">
                Showing {start + 1}-{Math.min(start + perPage, analyses.length)} of {analyses.length}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={safePage === 1}
                  className="btn-secondary text-xs px-2 py-1 disabled:opacity-50"
                >
                  <LuChevronLeft />
                </button>
                {Array.from({ length: totalPages }, (_, i) => i + 1).map((n) => (
                  <button
                    key={n}
                    onClick={() => setPage(n)}
                    className={`text-xs px-3 py-1 rounded-md ${n === safePage ? 'bg-indigo-600 text-white' : 'btn-secondary'}`}
                  >
                    {n}
                  </button>
                ))}
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={safePage === totalPages}
                  className="btn-secondary text-xs px-2 py-1 disabled:opacity-50"
                >
                  <LuChevronRight />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
