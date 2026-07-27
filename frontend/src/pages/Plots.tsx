import { useEffect, useMemo, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import PlotWithDownload from '../components/PlotWithDownload'
import { generatePlot } from '../api'
import { LuBarChart3, LuRefreshCw } from 'react-icons/lu'

export default function Plots() {
  const { selectedDataset, projectId, datasetId } = useWorkspace()
  const [plotType, setPlotType] = useState('bar')
  const [feature, setFeature] = useState(0)
  const [search, setSearch] = useState('')
  const [groupOrder, setGroupOrder] = useState('')
  const [figure, setFigure] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const features = useMemo(() => (selectedDataset?.feature_metadata || []).map((f: any) => f.feature_id), [selectedDataset])
  const filteredFeatures = useMemo(() => features.map((f, i) => ({ name: f, index: i })).filter((f) => f.name.toLowerCase().includes(search.toLowerCase())), [features, search])

  const generate = async () => {
    if (!projectId || !datasetId) return
    setLoading(true)
    const order = groupOrder.split(',').map((s) => s.trim()).filter(Boolean)
    const res = await generatePlot(Number(projectId), Number(datasetId), { plot_type: plotType, parameters: { feature, group_order: order } })
    setFigure(res.data)
    setLoading(false)
  }

  useEffect(() => { setFigure(null) }, [plotType, selectedDataset])

  const plotTypes = [
    { value: 'bar', label: 'Bar Plot' },
    { value: 'box', label: 'Box Plot' },
    { value: 'violin', label: 'Violin Plot' },
    { value: 'dot', label: 'Dot Plot' },
    { value: 'rt_mz', label: 'RT vs m/z' },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Compound Plots</h1>
        <p className="page-subtitle">Per-feature and global visualizations with group ordering.</p>
      </div>

      <DatasetPicker />

      {!selectedDataset && <div className="card p-8 text-center text-slate-500 dark:text-slate-400">Select a dataset to generate plots.</div>}

      {selectedDataset && (
        <>
          <div className="card p-5">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2"><LuBarChart3 /> Plot Options</h3>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Plot type</label>
                <select value={plotType} onChange={(e) => setPlotType(e.target.value)} className="input">
                  {plotTypes.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Feature</label>
                <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search feature..." className="input mb-2" />
                <select value={feature} onChange={(e) => setFeature(Number(e.target.value))} className="input" disabled={plotType === 'rt_mz'}>
                  {filteredFeatures.slice(0, 50).map((f) => <option key={f.index} value={f.index}>{f.name}</option>)}
                </select>
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Group order</label>
                <input value={groupOrder} onChange={(e) => setGroupOrder(e.target.value)} placeholder="e.g. Ctrl, KO, Treat" className="input" />
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">Comma-separated group names to reorder samples.</p>
              </div>
            </div>
            <div className="flex gap-3 mt-4">
              <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> {loading ? 'Generating...' : 'Generate'}</button>
            </div>
          </div>

          {figure && (
            <div className="card p-5">
              <PlotWithDownload data={figure.data} layout={figure.layout} style={{ width: '100%', height: '500px' }} filename={`plot_${plotType}`} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
