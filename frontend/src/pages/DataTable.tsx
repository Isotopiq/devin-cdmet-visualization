import { useEffect, useState, useMemo } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import { LuSearch, LuDownload, LuSave, LuUsers, LuUndo2 } from 'react-icons/lu'
import { exportDataset, updateSampleGroups } from '../api'

export default function DataTable() {
  const { selectedDataset, projectId, datasetId, refreshDatasets } = useWorkspace()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')
  const [editMeta, setEditMeta] = useState<Record<string, string>>({})
  const pageSize = 15

  useEffect(() => { setPage(1) }, [selectedDataset, search])

  useEffect(() => {
    if (selectedDataset) {
      setEditMeta({ ...selectedDataset.sample_metadata })
      setSaveMsg('')
    } else {
      setEditMeta({})
    }
  }, [selectedDataset])

  const features = selectedDataset?.feature_metadata || []
  const sampleMeta = selectedDataset?.sample_metadata || {}
  const samples = Object.keys(sampleMeta)

  const groups = useMemo(() => {
    const g: Record<string, number> = {}
    Object.values(editMeta).forEach((v) => { g[v] = (g[v] || 0) + 1 })
    return g
  }, [editMeta])

  const exportFile = async (format: 'metaboanalyst' | 'lipidone') => {
    if (!projectId || !datasetId) return
    try {
      const res = await exportDataset(Number(projectId), Number(datasetId), format)
      const blob = new Blob([res.data], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${selectedDataset?.name || 'dataset'}_${format}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err: any) {
      alert(err.response?.data?.detail || `Failed to export ${format}`)
    }
  }

  const saveGroups = async () => {
    if (!projectId || !datasetId) return
    setSaving(true)
    setSaveMsg('')
    try {
      await updateSampleGroups(Number(projectId), Number(datasetId), editMeta)
      await refreshDatasets()
      setSaveMsg('Groups saved.')
    } catch (err: any) {
      setSaveMsg(err.response?.data?.detail || 'Failed to save groups')
    } finally {
      setSaving(false)
    }
  }

  const resetGroups = () => {
    if (selectedDataset) setEditMeta({ ...selectedDataset.sample_metadata })
  }

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
              <div className="flex items-center gap-3 flex-wrap justify-end">
                <div className="text-sm text-slate-500 dark:text-slate-400">{filtered.length} features</div>
                <button onClick={() => exportFile('metaboanalyst')} className="btn-secondary"><LuDownload /> MetaboAnalyst</button>
                <button onClick={() => exportFile('lipidone')} className="btn-secondary"><LuDownload /> LipidOne</button>
                <button onClick={downloadCsv} className="btn-secondary"><LuDownload /> Metadata</button>
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
                    <th className="text-left p-3">Isobaric</th>
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
                      <td className="p-3 text-xs">
                        {f.isobaric_substitution_flag ? (
                          <div className="space-y-1">
                            <span className="inline-flex items-center px-2 py-0.5 rounded bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-200">{f.isobaric_substitution_resolution || 'ambiguous'}</span>
                            <div className="text-slate-500 dark:text-slate-400">{f.isobaric_substitution_rule}</div>
                            {f.isobaric_substitution_rollup_exclude && <div className="text-red-600 dark:text-red-400">excluded from rollup</div>}
                          </div>
                        ) : '-'}
                      </td>
                    </tr>
                  ))}
                  {paged.length === 0 && <tr><td colSpan={7} className="p-6 text-center text-slate-500 dark:text-slate-400">No features match.</td></tr>}
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
            <h3 className="font-semibold text-slate-900 dark:text-white mb-3 flex items-center gap-2"><LuUsers /> Group Editor</h3>
            <p className="text-sm text-slate-600 dark:text-slate-300 mb-4">
              Correct sample group labels here. The import parser tries to read them from a metadata file; if none was supplied it falls back to raw filenames.
            </p>
            <div className="overflow-y-auto max-h-96 border border-slate-200 dark:border-slate-700 rounded-lg mb-4">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 dark:bg-slate-700/50 text-slate-500 dark:text-slate-300 uppercase text-xs sticky top-0">
                  <tr>
                    <th className="text-left p-3">Sample column</th>
                    <th className="text-left p-3">Group label</th>
                    <th className="text-left p-3">Quick actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                  {samples.map((col) => (
                    <tr key={col} className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                      <td className="p-3 text-slate-700 dark:text-slate-200 font-medium max-w-xs truncate" title={col}>{col}</td>
                      <td className="p-3">
                        <input
                          type="text"
                          value={editMeta[col] ?? ''}
                          onChange={(e) => setEditMeta((prev) => ({ ...prev, [col]: e.target.value }))}
                          className="input text-sm"
                        />
                      </td>
                      <td className="p-3">
                        <div className="flex gap-2">
                          {/blank|qc/i.test(col) && (
                            <button onClick={() => setEditMeta((prev) => ({ ...prev, [col]: 'Blank' }))} className="text-xs px-2 py-1 rounded bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600">Blank</button>
                          )}
                          {/qc/i.test(col) && (
                            <button onClick={() => setEditMeta((prev) => ({ ...prev, [col]: 'QC' }))} className="text-xs px-2 py-1 rounded bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600">QC</button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button onClick={saveGroups} disabled={saving} className="btn-primary"><LuSave /> {saving ? 'Saving...' : 'Save Groups'}</button>
              <button onClick={resetGroups} className="btn-secondary"><LuUndo2 /> Reset</button>
              <div className="flex items-center gap-2 ml-auto">
                <span className="text-sm text-slate-500 dark:text-slate-400">Bulk set blanks/QCs to:</span>
                <input type="text" placeholder="Blank" defaultValue="Blank" id="bulk-blank" className="input text-sm w-28" />
                <button onClick={() => { const val = (document.getElementById('bulk-blank') as HTMLInputElement)?.value || 'Blank'; setEditMeta((prev) => { const next = { ...prev }; Object.keys(next).forEach((col) => { if (/blank|qc/i.test(col)) next[col] = val }); return next }) }} className="btn-secondary text-sm">Apply</button>
              </div>
            </div>
            {saveMsg && <div className={`mt-3 text-sm ${saveMsg.startsWith('Failed') ? 'text-red-600' : 'text-emerald-600'}`}>{saveMsg}</div>}
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
