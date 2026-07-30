import { useEffect, useMemo, useRef, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import PlotWithDownload from '../components/PlotWithDownload'
import { buildPathway, getPathwayJob } from '../api'
import { LuGitMerge, LuRefreshCw } from 'react-icons/lu'

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
                <input type="text" value={organism} onChange={(e) => setOrganism(e.target.value)} className="input" placeholder="hsa / hsapiens" />
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
    </div>
  )
}
