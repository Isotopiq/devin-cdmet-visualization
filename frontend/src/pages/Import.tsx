import { useEffect, useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { listProjects, listFiles, uploadFile, previewImport, importDataset } from '../api'
import { Project, UploadedFile, ImportPreview } from '../types'

export default function Import() {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState<number | ''>('')
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [selectedFile, setSelectedFile] = useState<UploadedFile | null>(null)
  const [alignmentFile, setAlignmentFile] = useState<UploadedFile | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [selectedSheet, setSelectedSheet] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    listProjects().then((r) => setProjects(r.data))
  }, [])

  useEffect(() => {
    if (projectId) {
      listFiles(Number(projectId)).then((r) => setFiles(r.data))
    }
  }, [projectId])

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (!projectId) { setMessage('Select a project first'); return }
    for (const file of acceptedFiles) {
      const res = await uploadFile(Number(projectId), file)
      setFiles((prev) => [...prev, res.data])
    }
  }, [projectId])

  const { getRootProps, getInputProps } = useDropzone({ onDrop, accept: { 'text/csv': ['.csv'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'], 'text/tab-separated-values': ['.tsv', '.txt'] } })

  const loadPreview = async () => {
    if (!selectedFile) return
    const res = await previewImport(selectedFile.id, selectedSheet || undefined, alignmentFile?.id)
    setPreview(res.data)
  }

  const runImport = async (featureType: string) => {
    if (!selectedFile) return
    await importDataset(selectedFile.id, featureType, alignmentFile?.id)
    setMessage('Dataset imported successfully')
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4 text-gray-900 dark:text-white">Import Wizard</h1>
      <select value={projectId} onChange={(e) => setProjectId(Number(e.target.value))} className="border rounded-lg p-2 mb-4 w-full md:w-1/3">
        <option value="">Select project</option>
        {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>

      <div {...getRootProps()} className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-6 text-center mb-4 cursor-pointer">
        <input {...getInputProps()} />
        <p className="text-gray-600 dark:text-gray-300">Drag & drop Excel, CSV, TSV, or LipidSearch .txt files here, or click to select files</p>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 mb-4">
        <h3 className="font-semibold mb-2 text-gray-900 dark:text-white">Uploaded Files</h3>
        <div className="space-y-2">
          {files.map((f) => (
            <div key={f.id} className={`p-2 border rounded-lg cursor-pointer ${selectedFile?.id === f.id ? 'bg-blue-50 dark:bg-blue-900' : ''}`} onClick={() => setSelectedFile(f)}>
              {f.original_name} <span className="text-xs text-gray-500">({f.detected_format || 'unknown'})</span>
              {selectedFile?.id === f.id && <span className="text-xs text-blue-600 ml-2 font-semibold">main</span>}
            </div>
          ))}
        </div>
      </div>

      {selectedFile && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 mb-4">
          <h3 className="font-semibold mb-2 text-gray-900 dark:text-white">Optional LipidSearch Alignment File</h3>
          <select value={alignmentFile?.id || ''} onChange={(e) => setAlignmentFile(files.find((f) => f.id === Number(e.target.value)) || null)} className="border rounded-lg p-2 mb-2 w-full md:w-1/2">
            <option value="">None (use header-derived groups)</option>
            {files.map((f) => <option key={f.id} value={f.id}>{f.original_name}</option>)}
          </select>
        </div>
      )}

      {selectedFile && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 mb-4">
          <h3 className="font-semibold mb-2 text-gray-900 dark:text-white">Sheet Selection & Preview</h3>
          <select value={selectedSheet} onChange={(e) => setSelectedSheet(e.target.value)} className="border rounded-lg p-2 mr-2">
            <option value="">Default sheet</option>
            {selectedFile.sheets.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button onClick={loadPreview} className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">Preview</button>
          <button onClick={() => runImport('metabolite')} className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 ml-2">Import as Metabolite</button>
          <button onClick={() => runImport('lipid')} className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 ml-2">Import as Lipid</button>
        </div>
      )}

      {preview && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <h3 className="font-semibold mb-2 text-gray-900 dark:text-white">Preview</h3>
          <p className="text-sm text-gray-600 dark:text-gray-300">Detected format: {preview.detected_format || 'unknown'}</p>
          <p className="text-sm text-gray-600 dark:text-gray-300">Rows: {preview.row_count}</p>
          <p className="text-sm text-gray-600 dark:text-gray-300">Columns: {preview.columns.length}</p>
          <p className="text-sm text-gray-600 dark:text-gray-300">Sample columns: {preview.sample_columns.length}</p>
          <p className="text-sm text-gray-600 dark:text-gray-300">Suggested mapping: {JSON.stringify(preview.suggested_mapping)}</p>
          <p className="text-sm text-gray-600 dark:text-gray-300">Sample groups: {JSON.stringify(preview.sample_groups)}</p>
        </div>
      )}

      {message && <div className="mt-4 p-2 bg-green-100 text-green-800 rounded-lg">{message}</div>}
    </div>
  )
}
