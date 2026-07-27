import { useEffect, useMemo, useState } from 'react'
import Plot from 'react-plotly.js'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import { runStats, generatePlot } from '../api'
import { LuMicroscope, LuRefreshCw, LuDownload } from 'react-icons/lu'

export default function Volcano() {
  const { selectedDataset, projectId, datasetId } = useWorkspace()
  const [groupA, setGroupA] = useState('')
  const [groupB, setGroupB] = useState('')
  const [fcThreshold, setFcThreshold] = useState(0.5)
  const [pThreshold, setPThreshold] = useState(0.05)
  const [figure, setFigure] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const groups = useMemo(() => {
    const meta = selectedDataset?.sample_metadata || {}
    const set = new Set<string>()
    Object.values(meta).forEach((g) => set.add(g))
    return Array.from(set)
  }, [selectedDataset])

  useEffect(() => {
    setGroupA(groups[0] || '')
    setGroupB(groups[1] || '')
  }, [groups])

  const generate = async () => {
    if (!projectId || !datasetId) return
    setLoading(true)
    const statsRes = await runStats(Number(projectId), Number(datasetId), { test: 't_test', group_a: groupA, group_b: groupB, paired: false, multiple_testing: 'fdr_bh', alpha: pThreshold })
    const res = await generatePlot(Number(projectId), Number(datasetId), { plot_type: 'volcano', parameters: { stats: statsRes.data.results, fc_threshold: fcThreshold, p_threshold: pThreshold } })
    setFigure(res.data)
    setLoading(false)
  }

  const exportJson = () => {
    if (!figure) return
    const blob = new Blob([JSON.stringify(figure)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `volcano_${groupA}_vs_${groupB}.json`
    a.click()
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Volcano Plot</h1>
        <p className="page-subtitle">Visualize fold change and statistical significance.</p>
      </div>

      <DatasetPicker />

      {!selectedDataset && <div className="card p-8 text-center text-slate-500 dark:text-slate-400">Select a dataset for a volcano plot.</div>}

      {selectedDataset && (
        <>
          <div className="card p-5">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2"><LuMicroscope /> Comparison</h3>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Group A</label>
                <select value={groupA} onChange={(e) => setGroupA(e.target.value)} className="input">
                  {groups.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Group B</label>
                <select value={groupB} onChange={(e) => setGroupB(e.target.value)} className="input">
                  {groups.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">log2FC threshold</label>
                <input type="number" step="0.1" min="0" value={fcThreshold} onChange={(e) => setFcThreshold(Number(e.target.value))} className="input" />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">p-value threshold</label>
                <input type="number" step="0.01" min="0" max="1" value={pThreshold} onChange={(e) => setPThreshold(Number(e.target.value))} className="input" />
              </div>
              <div className="flex gap-3">
                <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
                <button onClick={exportJson} disabled={!figure} className="btn-secondary"><LuDownload /> Export</button>
              </div>
            </div>
          </div>

          {figure && (
            <div className="card p-5">
              <Plot data={figure.data} layout={figure.layout} style={{ width: '100%', height: '550px' }} config={{ responsive: true }} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
