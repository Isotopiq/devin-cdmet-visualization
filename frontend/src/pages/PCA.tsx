import { useEffect, useMemo, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import PlotWithDownload from '../components/PlotWithDownload'
import { generatePlot } from '../api'
import { LuLayers, LuRefreshCw } from 'react-icons/lu'

export default function PCA() {
  const { projectId, datasetId, selectedDataset } = useWorkspace()
  const [plot, setPlot] = useState('score')
  const [components, setComponents] = useState(3)
  const [scale, setScale] = useState(true)
  const [figure, setFigure] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const plotOptions = [
    { value: 'score', label: 'Score Plot' },
    { value: 'loading', label: 'Loading Plot' },
    { value: 'scree', label: 'Scree Plot' },
    { value: 'biplot', label: 'Biplot' },
  ]

  const generate = async () => {
    if (!projectId || !datasetId) return
    setLoading(true)
    const res = await generatePlot(Number(projectId), Number(datasetId), { plot_type: 'pca', parameters: { plot, components, scale } })
    setFigure(res.data)
    setLoading(false)
  }

  useEffect(() => { setFigure(null) }, [selectedDataset])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">PCA / PLS-DA</h1>
        <p className="page-subtitle">Explore variance, sample separation, and key loadings.</p>
      </div>

      <DatasetPicker />

      {!selectedDataset && <div className="card p-8 text-center text-slate-500 dark:text-slate-400">Select a dataset for PCA.</div>}

      {selectedDataset && (
        <>
          <div className="card p-5">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2"><LuLayers /> PCA Options</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Plot type</label>
                <select value={plot} onChange={(e) => setPlot(e.target.value)} className="input">
                  {plotOptions.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Components</label>
                <input type="number" min={2} max={10} value={components} onChange={(e) => setComponents(Number(e.target.value))} className="input" />
              </div>
              <div className="flex items-center gap-2 pb-2">
                <input type="checkbox" id="scale" checked={scale} onChange={(e) => setScale(e.target.checked)} className="rounded border-slate-300" />
                <label htmlFor="scale" className="text-sm text-slate-700 dark:text-slate-200">Scale variables</label>
              </div>
              <div className="flex gap-3">
                <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
              </div>
            </div>
          </div>

          {figure && (
            <div className="card p-5">
              <PlotWithDownload data={figure.data} layout={figure.layout} style={{ width: '100%', height: '500px' }} filename={`pca_${plot}`} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
