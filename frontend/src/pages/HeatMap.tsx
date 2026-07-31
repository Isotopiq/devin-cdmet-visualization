import { useEffect, useMemo, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import PlotWithDownload from '../components/PlotWithDownload'
import { generatePlot } from '../api'
import { LuLayoutGrid, LuRefreshCw } from 'react-icons/lu'

export default function HeatMap() {
  const { projectId, datasetId, selectedDataset } = useWorkspace()
  const [heatmapType, setHeatmapType] = useState('abundance')
  const [cluster, setCluster] = useState('both')
  const [figure, setFigure] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const groups = useMemo(() => {
    const meta = selectedDataset?.sample_metadata || {}
    const set = new Set<string>()
    Object.values(meta).forEach((g) => set.add(g as string))
    return Array.from(set)
  }, [selectedDataset])

  const clusterFlags = () => ({
    cluster_rows: ['both', 'row'].includes(cluster),
    cluster_cols: ['both', 'col'].includes(cluster),
  })

  const generate = async () => {
    if (!projectId || !datasetId) return
    setLoading(true)
    const { cluster_rows, cluster_cols } = clusterFlags()
    const res = await generatePlot(Number(projectId), Number(datasetId), {
      plot_type: 'heatmap',
      parameters: {
        heatmap_type: heatmapType,
        cluster_rows,
        cluster_cols,
        group_order: [...groups].sort(),
      },
    })
    setFigure(res.data)
    setLoading(false)
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
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Heatmap type</label>
                <select value={heatmapType} onChange={(e) => setHeatmapType(e.target.value)} className="input">
                  <option value="abundance">Abundance</option>
                  <option value="correlation">Sample correlation</option>
                </select>
              </div>
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
              </div>
            </div>
          </div>

          {figure && (
            <div className="card p-5">
              <PlotWithDownload data={figure.data} layout={figure.layout} style={{ width: '100%', height: '600px' }} filename={`heatmap_${cluster}`} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
