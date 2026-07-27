import { useEffect, useState } from 'react'
import Plot from 'react-plotly.js'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import { generatePlot } from '../api'
import { LuLayoutGrid, LuRefreshCw, LuDownload } from 'react-icons/lu'

export default function HeatMap() {
  const { projectId, datasetId, selectedDataset } = useWorkspace()
  const [cluster, setCluster] = useState('both')
  const [figure, setFigure] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const generate = async () => {
    if (!projectId || !datasetId) return
    setLoading(true)
    const res = await generatePlot(Number(projectId), Number(datasetId), { plot_type: 'heatmap', parameters: { cluster } })
    setFigure(res.data)
    setLoading(false)
  }

  const exportJson = () => {
    if (!figure) return
    const blob = new Blob([JSON.stringify(figure)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `heatmap_${cluster}.json`
    a.click()
  }

  useEffect(() => { setFigure(null) }, [selectedDataset])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Heat Map</h1>
        <p className="page-subtitle">Correlation or abundance heatmaps with hierarchical clustering.</p>
      </div>

      <DatasetPicker />

      {!selectedDataset && <div className="card p-8 text-center text-slate-500 dark:text-slate-400">Select a dataset to generate a heat map.</div>}

      {selectedDataset && (
        <>
          <div className="card p-5">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2"><LuLayoutGrid /> Options</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Clustering</label>
                <select value={cluster} onChange={(e) => setCluster(e.target.value)} className="input">
                  <option value="both">Rows + Columns</option>
                  <option value="row">Rows only</option>
                  <option value="col">Columns only</option>
                  <option value="none">None</option>
                </select>
              </div>
              <div className="flex gap-3">
                <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
                <button onClick={exportJson} disabled={!figure} className="btn-secondary"><LuDownload /> Export</button>
              </div>
            </div>
          </div>

          {figure && (
            <div className="card p-5">
              <Plot data={figure.data} layout={figure.layout} style={{ width: '100%', height: '600px' }} config={{ responsive: true }} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
