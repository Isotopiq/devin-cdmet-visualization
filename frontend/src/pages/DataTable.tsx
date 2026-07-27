import { useEffect, useState, useMemo } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import { LuSearch, LuDownload } from 'react-icons/lu'

export default function DataTable() {
  const { selectedDataset } = useWorkspace()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 15

  useEffect(() => { setPage(1) }, [selectedDataset, search])

  const features = selectedDataset?.feature_metadata || []
  const sampleMeta = selectedDataset?.sample_metadata || {}
  const samples = Object.keys(sampleMeta)
  const groups = useMemo(() => {
    const g: Record<string, number> = {}
    Object.values(sampleMeta).forEach((v) => { g[v] = (g[v] || 0) + 1 })
    return g
  }, [sampleMeta])

  const filtered = useMemo(() => features.filter((f: any) => {
    const text = JSON.stringify(f).toLowerCase()
    return text.includes(search.toLowerCase())
  }), [features, search])

  const paged = filtered.slice((page - 1) * pageSize, page * pageSize)
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))

  const downloadCsv = () => {
    if (!selectedDataset) return
    const cols = ['feature_id', 'formula', 'mz', 'rt', 'adduct', 'lipid_class', 'grade', 'fa']
    const rows = (selectedDataset.feature_metadata || []).map((f: any) => cols.map((c) => f[c] ?? '').join(','))
    const csv = [cols.join(','), ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${selectedDataset.name}_features.csv`
    a.click()
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Data Table</h1>
        <p className="page-subtitle">Inspect imported features, metadata, and sample group assignments.</p>
      </div>

      <DatasetPicker />

      {!selectedDataset && <div className="card p-8 text-center text-slate-500 dark:text-slate-400">Select a project and dataset to view the data table.</div>}

      {selectedDataset && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="card p-4"><div className="text-xs uppercase text-slate-500">Feature type</div><div className="text-lg font-semibold capitalize">{selectedDataset.feature_type}</div></div>
            <div className="card p-4"><div className="text-xs uppercase text-slate-500">Features</div><div className="text-lg font-semibold">{features.length}</div></div>
            <div className="card p-4"><div className="text-xs uppercase text-slate-500">Samples</div><div className="text-lg font-semibold">{samples.length}</div></div>
            <div className="card p-4"><div className="text-xs uppercase text-slate-500">Groups</div><div className="text-lg font-semibold">{Object.keys(groups).length}</div></div>
          </div>

          <div className="card p-5">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
              <div className="relative flex-1 max-w-md">
                <LuSearch className="absolute left-3 top-2.5 text-slate-400" />
                <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search features..." className="input pl-9" />
              </div>
              <div className="flex items-center gap-3">
                <div className="text-sm text-slate-500 dark:text-slate-400">{filtered.length} features</div>
                <button onClick={downloadCsv} className="btn-secondary"><LuDownload /> Export CSV</button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 dark:bg-slate-700/50 text-slate-500 dark:text-slate-300 uppercase text-xs">
                  <tr>
                    <th className="text-left p-3">Feature</th>
                    <th className="text-left p-3">Formula</th>
                    <th className="text-left p-3">m/z</th>
                    <th className="text-left p-3">RT</th>
                    <th className="text-left p-3">Adduct</th>
                    <th className="text-left p-3">Class / Grade</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                  {paged.map((f: any, i: number) => (
                    <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                      <td className="p-3 font-medium text-slate-900 dark:text-white">{f.feature_id}</td>
                      <td className="p-3 text-slate-600 dark:text-slate-300">{f.formula || '-'}</td>
                      <td className="p-3 text-slate-600 dark:text-slate-300">{f.mz ?? '-'}</td>
                      <td className="p-3 text-slate-600 dark:text-slate-300">{f.rt ?? '-'}</td>
                      <td className="p-3 text-slate-600 dark:text-slate-300">{f.adduct || '-'}</td>
                      <td className="p-3 text-slate-600 dark:text-slate-300">{f.lipid_class || f.grade || '-'}</td>
                    </tr>
                  ))}
                  {paged.length === 0 && <tr><td colSpan={6} className="p-6 text-center text-slate-500 dark:text-slate-400">No features match.</td></tr>}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between mt-4">
              <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1} className="btn-secondary">Previous</button>
              <span className="text-sm text-slate-500 dark:text-slate-400">Page {page} of {totalPages}</span>
              <button onClick={() => setPage(Math.min(totalPages, page + 1))} disabled={page === totalPages} className="btn-secondary">Next</button>
            </div>
          </div>

          <div className="card p-5">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-3">Group Summary</h3>
            <div className="flex flex-wrap gap-2">
              {Object.entries(groups).map(([group, count]) => (
                <span key={group} className="px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-200 text-sm font-medium">{group}: {count}</span>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
