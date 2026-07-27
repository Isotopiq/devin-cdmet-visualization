import { useEffect, useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { useWorkspace } from '../context/WorkspaceContext'
import { listFiles, uploadFile, deleteFile, previewImport, importDataset } from '../api'
import { UploadedFile, ImportPreview } from '../types'
import { LuUploadCloud, LuEye, LuDatabase, LuFileSpreadsheet, LuFileText, LuCheckCircle2, LuAlertCircle, LuTrash2 } from 'react-icons/lu'

export default function Import() {
  const { projectId, setProjectId, refreshProjects, refreshDatasets, setDatasetId, projects } = useWorkspace()
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [selectedFile, setSelectedFile] = useState<UploadedFile | null>(null)
  const [alignmentFile, setAlignmentFile] = useState<UploadedFile | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [selectedSheet, setSelectedSheet] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [importing, setImporting] = useState(false)

  useEffect(() => {
    refreshProjects()
  }, [])

  useEffect(() => {
    if (projectId) {
      listFiles(Number(projectId)).then((r) => setFiles(r.data))
    } else {
      setFiles([])
    }
  }, [projectId])

  const onDropData = useCallback(async (acceptedFiles: File[]) => {
    if (!projectId) { setError('Select a project first'); return }
    setError('')
    for (const file of acceptedFiles) {
      try {
        const res = await uploadFile(Number(projectId), file)
        setFiles((prev) => [...prev, res.data])
        setSelectedFile(res.data)
        setSelectedSheet(res.data.sheets[0] || '')
        setPreview(null)
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Upload failed')
      }
    }
  }, [projectId])

  const onDropMeta = useCallback(async (acceptedFiles: File[]) => {
    if (!projectId) { setError('Select a project first'); return }
    setError('')
    for (const file of acceptedFiles) {
      try {
        const res = await uploadFile(Number(projectId), file)
        setFiles((prev) => [...prev, res.data])
        setAlignmentFile(res.data)
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Upload failed')
      }
    }
  }, [projectId])

  const dataDropzone = useDropzone({
    onDrop: onDropData,
    accept: { 'text/csv': ['.csv'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'], 'text/tab-separated-values': ['.tsv', '.txt'] }
  })

  const metaDropzone = useDropzone({
    onDrop: onDropMeta,
    accept: { 'text/csv': ['.csv'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'], 'text/tab-separated-values': ['.tsv', '.txt'] }
  })

  const handleDeleteFile = async (file: UploadedFile) => {
    try {
      await deleteFile(file.id)
      setFiles((prev) => prev.filter((f) => f.id !== file.id))
      if (selectedFile?.id === file.id) {
        setSelectedFile(null)
        setAlignmentFile(null)
        setPreview(null)
      }
      if (alignmentFile?.id === file.id) setAlignmentFile(null)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Delete failed')
    }
  }

  const loadPreview = async () => {
    if (!selectedFile) return
    setError('')
    try {
      const res = await previewImport(selectedFile.id, selectedSheet || undefined, alignmentFile?.id)
      setPreview(res.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Preview failed')
    }
  }

  const runImport = async (featureType: string) => {
    if (!selectedFile) return
    setImporting(true)
    setError('')
    try {
      const res = await importDataset(selectedFile.id, featureType, alignmentFile?.id, selectedSheet || undefined)
      setMessage(`Dataset imported as ${featureType}`)
      setPreview(null)
      await refreshDatasets()
      setDatasetId(res.data.id)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Import failed')
    } finally {
      setImporting(false)
    }
  }

  const formatIcon = (name: string) => {
    if (name.endsWith('.xlsx')) return <LuFileSpreadsheet className="text-emerald-500" />
    return <LuFileText className="text-blue-500" />
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Import Data</h1>
        <p className="page-subtitle">Upload Compound Discoverer or LipidSearch exports and map samples.</p>
      </div>

      <div className="card p-5">
        <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Project</label>
        <select value={projectId} onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : '')} className="input max-w-md">
          <option value="">Select a project</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {projectId && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="card p-6 text-center border-dashed border-2 border-indigo-300 dark:border-indigo-700" {...dataDropzone.getRootProps()}>
            <input {...dataDropzone.getInputProps()} />
            <div className="flex flex-col items-center gap-3">
              <div className="p-4 rounded-full bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 text-3xl"><LuUploadCloud /></div>
              <p className="text-slate-700 dark:text-slate-200 font-medium">
                {dataDropzone.isDragActive ? 'Drop data file here' : '1. Upload data file'}
              </p>
              <p className="text-sm text-slate-500 dark:text-slate-400">Compound Discoverer export, LipidSearch .txt, CSV, or Excel</p>
            </div>
          </div>
          <div className="card p-6 text-center border-dashed border-2 border-slate-300 dark:border-slate-600" {...metaDropzone.getRootProps()}>
            <input {...metaDropzone.getInputProps()} />
            <div className="flex flex-col items-center gap-3">
              <div className="p-4 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-500 text-3xl"><LuUploadCloud /></div>
              <p className="text-slate-700 dark:text-slate-200 font-medium">
                {metaDropzone.isDragActive ? 'Drop metadata file here' : '2. Optional: upload metadata / alignment'}
              </p>
              <p className="text-sm text-slate-500 dark:text-slate-400">Sample group mapping file (Excel/CSV/TSV)</p>
            </div>
          </div>
        </div>
      )}

      {files.length > 0 && (
        <div className="card p-5">
          <h3 className="font-semibold text-slate-900 dark:text-white mb-3">Uploaded Files</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {files.map((f) => (
              <div
                key={f.id}
                className={`flex items-center gap-3 p-3 rounded-lg border text-left transition-colors ${selectedFile?.id === f.id ? 'border-indigo-600 bg-indigo-50 dark:bg-indigo-900/30' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/30'}`}
              >
                <button
                  onClick={() => { setSelectedFile(f); setSelectedSheet(f.sheets[0] || ''); setPreview(null); setMessage(''); setError('') }}
                  className="flex items-center gap-3 flex-1 min-w-0 text-left"
                >
                  {formatIcon(f.original_name)}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-slate-900 dark:text-white truncate">{f.original_name}</div>
                    <div className="text-xs text-slate-500 dark:text-slate-400">{f.detected_format || 'unknown format'}</div>
                  </div>
                  {selectedFile?.id === f.id && <LuCheckCircle2 className="text-indigo-600" />}
                </button>
                <button onClick={() => handleDeleteFile(f)} className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded" title="Delete file">
                  <LuTrash2 />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {selectedFile && (
        <div className="card p-5 space-y-4">
          <h3 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2"><LuEye /> Preview & Import</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Sheet</label>
              <select value={selectedSheet} onChange={(e) => setSelectedSheet(e.target.value)} className="input">
                {selectedFile.sheets.length === 0 && <option value="">Default</option>}
                {selectedFile.sheets.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Optional Metadata / Alignment</label>
              <select value={alignmentFile?.id || ''} onChange={(e) => setAlignmentFile(files.find((f) => f.id === Number(e.target.value)) || null)} className="input">
                <option value="">None (use header-derived groups)</option>
                {files.filter((f) => f.id !== selectedFile.id).map((f) => <option key={f.id} value={f.id}>{f.original_name}</option>)}
              </select>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <button onClick={loadPreview} className="btn-secondary"><LuEye /> Preview</button>
            <button onClick={() => runImport('metabolite')} disabled={importing} className="btn-primary"><LuDatabase /> Import as Metabolite</button>
            <button onClick={() => runImport('lipid')} disabled={importing} className="btn-primary bg-emerald-600 hover:bg-emerald-700"><LuDatabase /> Import as Lipid</button>
          </div>

          {message && <div className="p-3 rounded-lg bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200 flex items-center gap-2"><LuCheckCircle2 /> {message}</div>}
          {error && <div className="p-3 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-200 flex items-center gap-2"><LuAlertCircle /> {error}</div>}

          {preview && (
            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50"><span className="text-slate-500 dark:text-slate-400">Format</span><div className="font-medium text-slate-900 dark:text-white capitalize">{preview.detected_format || 'unknown'}</div></div>
                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50"><span className="text-slate-500 dark:text-slate-400">Rows</span><div className="font-medium text-slate-900 dark:text-white">{preview.row_count}</div></div>
                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50"><span className="text-slate-500 dark:text-slate-400">Samples</span><div className="font-medium text-slate-900 dark:text-white">{preview.sample_columns.length}</div></div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50">
                  <h4 className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-2">Feature mapping</h4>
                  <table className="w-full text-left">
                    <thead className="text-xs text-slate-500 dark:text-slate-400 uppercase border-b border-slate-200 dark:border-slate-600">
                      <tr><th className="py-1">Field</th><th className="py-1">Column</th></tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                      {Object.entries(preview.suggested_mapping).map(([field, col]) => (
                        <tr key={field}><td className="py-1 font-medium text-slate-900 dark:text-white capitalize">{field.replace(/_/g, ' ')}</td><td className="py-1 text-slate-600 dark:text-slate-300 truncate" title={col}>{col}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50">
                  <h4 className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-2">Group summary</h4>
                  <table className="w-full text-left">
                    <thead className="text-xs text-slate-500 dark:text-slate-400 uppercase border-b border-slate-200 dark:border-slate-600">
                      <tr><th className="py-1">Group</th><th className="py-1">Samples</th></tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                      {Object.entries(
                        Object.values(preview.sample_groups || {}).reduce((acc: Record<string, number>, group: string) => {
                          acc[group] = (acc[group] || 0) + 1
                          return acc
                        }, {} as Record<string, number>)
                      ).map(([group, count]) => (
                        <tr key={group}><td className="py-1 font-medium text-slate-900 dark:text-white">{group}</td><td className="py-1 text-slate-600 dark:text-slate-300">{count}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
