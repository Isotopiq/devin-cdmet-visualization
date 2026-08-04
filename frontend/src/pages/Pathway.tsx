import { useEffect, useMemo, useRef, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import PlotWithDownload from '../components/PlotWithDownload'
import { buildPathway, getPathwayJob, exportPathwayPdf } from '../api'
import { LuGitMerge, LuRefreshCw, LuFileText, LuEye, LuX } from 'react-icons/lu'

const FONT_OPTIONS = [
  { label: 'Default (system)', value: '' },
  { label: 'Helvetica', value: 'Helvetica' },
  { label: 'Times', value: 'Times' },
  { label: 'Courier', value: 'Courier' },
  { label: 'DejaVu', value: 'DejaVu' },
  { label: 'Liberation', value: 'Liberation' },
]

export default function Pathway() {
  const { projectId, datasetId, selectedDataset } = useWorkspace()
  const [pathwaySource, setPathwaySource] = useState('kegg')
  const [organism, setOrganism] = useState('hsa')
  const [groupA, setGroupA] = useState('')
  const [groupB, setGroupB] = useState('')
  const [fcThreshold, setFcThreshold] = useState(1.0)
  const [pThreshold, setPThreshold] = useState(0.05)
  const [topN, setTopN] = useState(20)
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState<string>('')
  const [percent, setPercent] = useState<number>(0)
  const [error, setError] = useState<string>('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [pdfMeta, setPdfMeta] = useState({
    primary_comparison: '',
    prepared_for: '',
    prepared_by: 'Metabolomics Platform',
    report_contents: 'Pathway Mapping Report',
  })
  const [fontFamily, setFontFamily] = useState('')
  const [includeTable, setIncludeTable] = useState(true)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)

  const groups = useMemo(() => {
    const meta = selectedDataset?.sample_metadata || {}
    const vals = Array.from(new Set(Object.values(meta as Record<string, string>)))
    return vals.filter((g) => g && g !== 'Unknown')
  }, [selectedDataset])

  useEffect(() => {
    if (groups.length >= 1 && !groupA) setGroupA(groups[0])
    if (groups.length >= 2 && !groupB) setGroupB(groups[1])
  }, [groups])

  useEffect(() => { setResult(null); setError('') }, [selectedDataset, pathwaySource])

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const clearPoll = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const buildPdfPayload = () => {
    if (!result || result.error) return null
    return {
      result,
      title: selectedDataset?.name,
      subtitle: `Source: ${result.source || pathwaySource}`,
      primary_comparison: pdfMeta.primary_comparison || undefined,
      prepared_for: pdfMeta.prepared_for || undefined,
      prepared_by: pdfMeta.prepared_by || undefined,
      report_contents: pdfMeta.report_contents || undefined,
      font_family: fontFamily || undefined,
      include_table: includeTable,
    }
  }

  const generatePdf = async () => {
    if (!projectId || !datasetId) return null
    const payload = buildPdfPayload()
    if (!payload) return null
    const res = await exportPathwayPdf(Number(projectId), Number(datasetId), payload)
    return window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
  }

  const handlePreviewPdf = async () => {
    if (!projectId || !datasetId || !result) return
    setLoading(true)
    setError('')
    try {
      const url = await generatePdf()
      if (url) {
        setPreviewUrl(url)
        setPreviewOpen(true)
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to generate pathway PDF preview')
    } finally {
      setLoading(false)
    }
  }

  const handleExportPdf = async () => {
    if (!projectId || !datasetId || !result || !selectedDataset) return
    setLoading(true)
    setError('')
    try {
      const url = await generatePdf()
      if (url) {
        const link = document.createElement('a')
        link.href = url
        link.setAttribute('download', `${selectedDataset.name.replace(/\s+/g, '_')}_pathway_report.pdf`)
        document.body.appendChild(link)
        link.click()
        link.remove()
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to export pathway PDF')
    } finally {
      setLoading(false)
    }
  }

  const closePreview = () => {
    setPreviewOpen(false)
    if (previewUrl) {
      window.URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
  }

  const generate = async () => {
    if (!projectId || !datasetId) return
    clearPoll()
    setLoading(true)
    setError('')
    setResult(null)
    setProgress('Submitting pathway job...')
    setPercent(0)
    try {
      const params: any = {
        pathway_source: pathwaySource,
        organism,
        top_n: topN,
      }
      if (pathwaySource !== 'custom' && groupA && groupB) {
        params.group_a = groupA
        params.group_b = groupB
        params.fc_threshold = fcThreshold
        params.p_threshold = pThreshold
      }
      const startRes = await buildPathway(Number(projectId), Number(datasetId), params)
      const jobId = startRes.data?.job_id
      if (!jobId) {
        throw new Error('No job id returned')
      }
      setProgress('Queued')
      setPercent(2)
      pollRef.current = setInterval(async () => {
        try {
          const jobRes = await getPathwayJob(jobId)
          const job = jobRes.data
          setProgress(job.progress || 'Running...')
          setPercent(job.percent ?? 0)
          if (job.status === 'completed') {
            clearPoll()
            setResult(job.result)
            setLoading(false)
          } else if (job.status === 'failed') {
            clearPoll()
            setError(job.error || 'Pathway analysis failed')
            setLoading(false)
          }
        } catch (pollErr: any) {
          clearPoll()
          setError(pollErr?.response?.data?.detail || pollErr?.message || 'Polling failed')
          setLoading(false)
        }
      }, 500)
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Pathway request failed'
      setError(String(msg))
      setLoading(false)
      clearPoll()
    }
  }

  const barFigure = result?.bar?.data ? result.bar : (result?.data ? result : null)
  const tableFigure = result?.table?.data ? result.table : null
  const pathways = result?.pathways || []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Pathway Mapping</h1>
        <p className="page-subtitle">Enrichment analysis against KEGG, Reactome, or GO terms.</p>
      </div>

      <DatasetPicker />

      {!selectedDataset && <div className="card p-8 text-center text-slate-500 dark:text-slate-400">Select a dataset to run pathway enrichment.</div>}

      {selectedDataset && (
        <>
          <div className="card p-5">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2"><LuGitMerge /> Pathway Options</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Pathway source</label>
                <select value={pathwaySource} onChange={(e) => setPathwaySource(e.target.value)} className="input">
                  <option value="kegg">KEGG</option>
                  <option value="reactome">Reactome</option>
                  <option value="go">GO (g:Profiler)</option>
                  <option value="custom">Static custom</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Organism</label>
                <select value={organism} onChange={(e) => setOrganism(e.target.value)} className="input">
                  <option value="hsa">Human (hsa)</option>
                  <option value="mmu">Mouse (mmu)</option>
                  <option value="rno">Rat (rno)</option>
                  <option value="dre">Zebrafish (dre)</option>
                  <option value="dme">Fruit fly (dme)</option>
                  <option value="cel">C. elegans (cel)</option>
                  <option value="sce">Yeast (sce)</option>
                  <option value="ath">Arabidopsis (ath)</option>
                  <option value="eco">E. coli (eco)</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Group A</label>
                <select value={groupA} onChange={(e) => setGroupA(e.target.value)} className="input">
                  <option value="">-</option>
                  {groups.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Group B</label>
                <select value={groupB} onChange={(e) => setGroupB(e.target.value)} className="input">
                  <option value="">-</option>
                  {groups.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">|log2FC| threshold</label>
                <input type="number" step="0.1" value={fcThreshold} onChange={(e) => setFcThreshold(Number(e.target.value))} className="input" />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">adj p-value threshold</label>
                <input type="number" step="0.01" value={pThreshold} onChange={(e) => setPThreshold(Number(e.target.value))} className="input" />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Top N</label>
                <input type="number" value={topN} onChange={(e) => setTopN(Number(e.target.value))} className="input" />
              </div>
              <div className="flex gap-3">
                <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
              </div>
            </div>

            {loading && (
              <div className="mt-4">
                <div className="w-full bg-slate-200 dark:bg-slate-700 rounded h-2 overflow-hidden">
                  <div
                    className="bg-blue-500 h-2 rounded transition-all duration-300"
                    style={{ width: `${Math.max(2, Math.min(100, percent))}%` }}
                  />
                </div>
                <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 flex items-center gap-2">
                  <span className="inline-block w-3 h-3 border-2 border-slate-300 border-t-blue-500 rounded-full animate-spin" />
                  {progress || 'Running enrichment...'}
                </p>
              </div>
            )}
            <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
              Significant features (|log2FC| and adjusted p-value) are submitted to the selected database. Results are fetched as a background job; the progress bar updates as each external API step completes.
            </p>
          </div>

          {selectedDataset && result && !result.error && (
            <div className="card p-5 space-y-4">
              <h3 className="text-md font-semibold text-slate-900 dark:text-white">Pathway PDF Report Options</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="label-like">Primary comparison</label>
                  <input type="text" className="input" value={pdfMeta.primary_comparison} onChange={(e) => setPdfMeta({ ...pdfMeta, primary_comparison: e.target.value })} placeholder="e.g. KO vs CTRL" />
                </div>
                <div>
                  <label className="label-like">Prepared for</label>
                  <input type="text" className="input" value={pdfMeta.prepared_for} onChange={(e) => setPdfMeta({ ...pdfMeta, prepared_for: e.target.value })} placeholder="Principal Investigator" />
                </div>
                <div>
                  <label className="label-like">Prepared by</label>
                  <input type="text" className="input" value={pdfMeta.prepared_by} onChange={(e) => setPdfMeta({ ...pdfMeta, prepared_by: e.target.value })} placeholder="Metabolomics Platform" />
                </div>
                <div>
                  <label className="label-like">Report contents</label>
                  <input type="text" className="input" value={pdfMeta.report_contents} onChange={(e) => setPdfMeta({ ...pdfMeta, report_contents: e.target.value })} placeholder="Pathway Mapping Report" />
                </div>
                <div>
                  <label className="label-like">PDF font</label>
                  <select className="select" value={fontFamily} onChange={(e) => setFontFamily(e.target.value)}>
                    {FONT_OPTIONS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
                  </select>
                </div>
                <div className="flex items-center h-10">
                  <input id="includeTable" type="checkbox" checked={includeTable} onChange={(e) => setIncludeTable(e.target.checked)} className="rounded mr-2" />
                  <label htmlFor="includeTable" className="text-sm text-slate-700 dark:text-slate-300">Include pathway table</label>
                </div>
              </div>
              <div className="flex gap-3">
                <button onClick={handlePreviewPdf} disabled={loading || !result} className="btn-secondary"><LuEye /> Preview PDF</button>
                <button onClick={handleExportPdf} disabled={loading || !result} className="btn-secondary"><LuFileText /> Export PDF Report</button>
              </div>
            </div>
          )}

          {(error || result?.error) && (
            <div className="card p-5 text-red-600">{error || result?.error}</div>
          )}

          {barFigure && (
            <div className="card p-5">
              <PlotWithDownload data={barFigure.data} layout={barFigure.layout} style={{ width: '100%', height: '600px' }} filename={`pathway_${pathwaySource}_bar`} />
            </div>
          )}

          {tableFigure && (
            <div className="card p-5">
              <PlotWithDownload data={tableFigure.data} layout={tableFigure.layout} style={{ width: '100%', height: '500px' }} filename={`pathway_${pathwaySource}_table`} />
            </div>
          )}

          {pathways.length > 0 && (
            <div className="card p-5 overflow-x-auto">
              <h3 className="font-semibold text-slate-900 dark:text-white mb-3">Pathway / Term Results</h3>
              <table className="min-w-full text-sm">
                <thead className="bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                  <tr>
                    <th className="text-left p-2">Pathway / Term</th>
                    <th className="text-left p-2">p-value</th>
                    <th className="text-left p-2">adj. p-value</th>
                    <th className="text-left p-2">Found</th>
                    <th className="text-left p-2">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {pathways.map((p: any, i: number) => (
                    <tr key={i} className="border-t border-slate-200 dark:border-slate-700">
                      <td className="p-2">{p.name || p.pathway_id || p.term_id}</td>
                      <td className="p-2 font-mono">{p.pvalue != null ? Number(p.pvalue).toExponential(2) : '-'}</td>
                      <td className="p-2 font-mono">{p.padj != null ? Number(p.padj).toExponential(2) : (p.fdr != null ? Number(p.fdr).toExponential(2) : '-')}</td>
                      <td className="p-2">{p.found ?? p.compound_count ?? p.intersection_size}</td>
                      <td className="p-2">{p.total ?? p.pathway_compound_count ?? p.term_size}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {previewOpen && previewUrl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="bg-white dark:bg-slate-900 rounded-xl shadow-xl w-full max-w-6xl h-[90vh] flex flex-col overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-700">
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Pathway PDF Preview</h2>
              <button onClick={closePreview} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300">
                <LuX />
              </button>
            </div>
            <div className="flex-1 min-h-0">
              <iframe src={previewUrl} title="Pathway PDF Preview" className="w-full h-full" />
            </div>
            <div className="p-4 border-t border-slate-200 dark:border-slate-700 flex justify-end gap-2">
              <button onClick={closePreview} className="btn-secondary">Close</button>
              <button onClick={handleExportPdf} disabled={loading} className="btn-primary">Export PDF</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
