import { useEffect, useMemo, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import PlotWithDownload from '../components/PlotWithDownload'
import { runIsotope } from '../api'
import { LuDna, LuRefreshCw } from 'react-icons/lu'

export default function Isotope() {
  const { selectedDataset, projectId, datasetId } = useWorkspace()
  const [tracer, setTracer] = useState('13C')
  const [maxLabel, setMaxLabel] = useState(6)
  const [naturalAbundanceCorrection, setNaturalAbundanceCorrection] = useState(false)
  const [circulatingEnrichment, setCirculatingEnrichment] = useState('')
  const [normalization, setNormalization] = useState('none')
  const [results, setResults] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const featureOptions = useMemo(() => {
    return (selectedDataset?.feature_metadata || []).map((f: any) => f.feature_id)
  }, [selectedDataset])
  const [selectedFeature, setSelectedFeature] = useState('')

  useEffect(() => { if (featureOptions[0]) setSelectedFeature(featureOptions[0]) }, [featureOptions])

  const run = async () => {
    if (!projectId || !datasetId) return
    setLoading(true)
    setError('')
    try {
      const payload: any = { tracer, max_label: maxLabel, natural_abundance_correction: naturalAbundanceCorrection, normalization }
      if (circulatingEnrichment) payload.circulating_enrichment = Number(circulatingEnrichment)
      const res = await runIsotope(Number(projectId), Number(datasetId), payload)
      setResults(res.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Isotope analysis failed')
    } finally {
      setLoading(false)
    }
  }

  const makeBar = () => {
    if (!results || !results.fractions || !selectedFeature) return null
    const fractions = results.fractions[selectedFeature]
    if (!fractions) return null
    const labels = Object.keys(fractions)
    const values = Object.values(fractions).map((v) => Number(v))
    return { data: [{ x: labels, y: values, type: 'bar' as const, marker: { color: '#3b82f6' } }], layout: { title: `Isotopologue fractions - ${selectedFeature}`, yaxis: { title: 'Fraction' }, xaxis: { title: 'Isotopologue' } } }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Isotope Tracing</h1>
        <p className="page-subtitle">M+0 through M+n isotopologue fractions, pooled labeling, enrichment, and a simplified flux map.</p>
      </div>

      <DatasetPicker />

      {!selectedDataset && <div className="card p-8 text-center text-slate-500 dark:text-slate-400">Select a dataset to run isotope tracing.</div>}

      {selectedDataset && (
        <>
          <div className="card p-5">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2"><LuDna /> Tracer Parameters</h3>
            <div className="grid grid-cols-1 md:grid-cols-6 gap-4 items-end">
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Tracer</label>
                <select value={tracer} onChange={(e) => setTracer(e.target.value)} className="input">
                  <option value="13C">13C</option>
                  <option value="15N">15N</option>
                  <option value="D">Deuterium</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Max label</label>
                <input type="number" min={1} value={maxLabel} onChange={(e) => setMaxLabel(Number(e.target.value))} className="input" />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Normalization</label>
                <select value={normalization} onChange={(e) => setNormalization(e.target.value)} className="input">
                  <option value="none">None</option>
                  <option value="total_area">Total area</option>
                  <option value="protein">Protein</option>
                  <option value="dna">DNA</option>
                  <option value="cell_number">Cell number</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Circulating enrichment</label>
                <input type="number" step="0.01" value={circulatingEnrichment} onChange={(e) => setCirculatingEnrichment(e.target.value)} className="input" placeholder="Optional" />
              </div>
              <div className="flex items-center gap-2 pb-2">
                <input type="checkbox" id="nats" checked={naturalAbundanceCorrection} onChange={(e) => setNaturalAbundanceCorrection(e.target.checked)} className="rounded border-slate-300" />
                <label htmlFor="nats" className="text-sm text-slate-700 dark:text-slate-200">Natural abundance correction</label>
              </div>
              <button onClick={run} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Run</button>
            </div>
            {error && <div className="mt-4 p-3 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-200 text-sm">{error}</div>}
          </div>

          {results && (
            <>
              <div className="card p-5">
                <h3 className="font-semibold text-slate-900 dark:text-white mb-3">Isotopologue Fractions</h3>
                <div className="mb-4">
                  <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Feature</label>
                  <select value={selectedFeature} onChange={(e) => setSelectedFeature(e.target.value)} className="input max-w-md">
                    {featureOptions.map((f) => <option key={f} value={f}>{f}</option>)}
                  </select>
                </div>
                {makeBar() && <PlotWithDownload data={makeBar()!.data} layout={makeBar()!.layout} style={{ width: '100%', height: '400px' }} filename={`isotope_${selectedFeature}`} />}
                <div className="mt-4 grid grid-cols-1 md:grid-cols-4 gap-4 text-sm">
                  <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50"><span className="text-slate-500 dark:text-slate-400">Total labeled</span><pre className="font-medium text-slate-900 dark:text-white mt-1 overflow-auto max-h-32">{JSON.stringify(results.total_labeled_fraction, null, 2)}</pre></div>
                  <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50"><span className="text-slate-500 dark:text-slate-400">Fractional enrichment</span><pre className="font-medium text-slate-900 dark:text-white mt-1 overflow-auto max-h-32">{JSON.stringify(results.fractional_enrichment, null, 2)}</pre></div>
                  <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50"><span className="text-slate-500 dark:text-slate-400">Mean labeled atoms</span><pre className="font-medium text-slate-900 dark:text-white mt-1 overflow-auto max-h-32">{JSON.stringify(results.mean_labeled_atoms, null, 2)}</pre></div>
                  <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50"><span className="text-slate-500 dark:text-slate-400">Pooled labeling</span><pre className="font-medium text-slate-900 dark:text-white mt-1 overflow-auto max-h-32">{JSON.stringify(results.pooled_labeling, null, 2)}</pre></div>
                </div>
              </div>

              {results.flux_map && (
                <div className="card p-5">
                  <h3 className="font-semibold text-slate-900 dark:text-white mb-3">Flux Map</h3>
                  <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">Simplified central carbon network colored by mean labeled atoms and sized by total intensity. Edge width shows the labeling gradient between connected metabolites.</p>
                  <PlotWithDownload data={results.flux_map.data} layout={results.flux_map.layout} style={{ width: '100%', height: '600px' }} filename="isotope_flux_map" />
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
