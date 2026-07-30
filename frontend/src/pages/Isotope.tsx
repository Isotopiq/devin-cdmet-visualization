import { useEffect, useMemo, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import PlotWithDownload from '../components/PlotWithDownload'
import { runIsotope, searchBiGGModels, searchGEMModels, loadModelNetwork } from '../api'
import { LuDna, LuRefreshCw, LuSearch, LuMap, LuNetwork } from 'react-icons/lu'

export default function Isotope() {
  const { selectedDataset, projectId, datasetId } = useWorkspace()
  const [tracer, setTracer] = useState('13C')
  const [maxLabel, setMaxLabel] = useState(6)
  const [naturalAbundanceCorrection, setNaturalAbundanceCorrection] = useState(false)
  const [circulatingEnrichment, setCirculatingEnrichment] = useState('')
  const [normalization, setNormalization] = useState('none')

  // Flux map options
  const [layout, setLayout] = useState('spring')
  const [graphMode, setGraphMode] = useState('full')
  const [edgeWeight, setEdgeWeight] = useState('label_gradient')
  const [k, setK] = useState(3)
  const [sourceNode, setSourceNode] = useState('')
  const [targetNode, setTargetNode] = useState('')

  // Map source / model loading
  const [mapSource, setMapSource] = useState<'none' | 'bigg' | 'gem'>('none')
  const [selectedModel, setSelectedModel] = useState<any>(null)
  const [modelQuery, setModelQuery] = useState('')
  const [modelResults, setModelResults] = useState<any[]>([])
  const [modelLoading, setModelLoading] = useState(false)
  const [modelError, setModelError] = useState('')

  const [results, setResults] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const featureOptions = useMemo(() => {
    return (selectedDataset?.feature_metadata || []).map((f: any) => f.feature_id)
  }, [selectedDataset])
  const [selectedFeature, setSelectedFeature] = useState('')

  useEffect(() => { if (featureOptions[0]) setSelectedFeature(featureOptions[0]) }, [featureOptions])

  const searchModels = async () => {
    setModelLoading(true)
    setModelError('')
    setModelResults([])
    try {
      if (mapSource === 'bigg') {
        const res = await searchBiGGModels(modelQuery)
        setModelResults(res.data.models || [])
      } else if (mapSource === 'gem') {
        const res = await searchGEMModels(modelQuery)
        setModelResults(res.data.models || [])
      }
    } catch (err: any) {
      setModelError(err.response?.data?.detail || 'Model search failed')
    } finally {
      setModelLoading(false)
    }
  }

  const loadNetwork = async (model: any) => {
    setModelLoading(true)
    setModelError('')
    try {
      const id = mapSource === 'bigg' ? model.bigg_id : model.id
      await loadModelNetwork(mapSource, id)
      setSelectedModel({ ...model, source: mapSource, model_id: id })
    } catch (err: any) {
      setModelError(err.response?.data?.detail || 'Network load failed')
    } finally {
      setModelLoading(false)
    }
  }

  const run = async () => {
    if (!projectId || !datasetId) return
    setLoading(true)
    setError('')
    try {
      const payload: any = {
        tracer,
        max_label: maxLabel,
        natural_abundance_correction: naturalAbundanceCorrection,
        normalization,
        layout,
        graph_mode: graphMode,
        edge_weight: edgeWeight,
        k,
      }
      if (circulatingEnrichment) payload.circulating_enrichment = Number(circulatingEnrichment)
      if (sourceNode) payload.source_node = sourceNode
      if (targetNode) payload.target_node = targetNode
      if (selectedModel) {
        payload.map_source = selectedModel.source
        payload.map_id = selectedModel.model_id
      }
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
        <p className="page-subtitle">M+0 through M+n isotopologue fractions, pooled labeling, enrichment, and flux maps from curated or database models.</p>
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

          <div className="card p-5">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2"><LuMap /> Flux Map Options</h3>
            <div className="grid grid-cols-1 md:grid-cols-6 gap-4 items-end">
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Layout</label>
                <select value={layout} onChange={(e) => setLayout(e.target.value)} className="input">
                  <option value="spring">Spring</option>
                  <option value="curated">Curated pathways</option>
                  <option value="circular">Circular</option>
                  <option value="kamada_kawai">Kamada-Kawai</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Graph mode</label>
                <select value={graphMode} onChange={(e) => setGraphMode(e.target.value)} className="input">
                  <option value="full">Full reaction network</option>
                  <option value="spanning_tree">Spanning tree</option>
                  <option value="k_shortest_paths">K-shortest paths</option>
                  <option value="bipartite">Bipartite (metabolites + reactions)</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Edge weight</label>
                <select value={edgeWeight} onChange={(e) => setEdgeWeight(e.target.value)} className="input">
                  <option value="label_gradient">Label gradient</option>
                  <option value="intensity">Total intensity</option>
                  <option value="flux">Flux (gradient × intensity)</option>
                  <option value="uniform">Uniform</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">K paths</label>
                <input type="number" min={1} value={k} onChange={(e) => setK(Number(e.target.value))} className="input" />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Source</label>
                <select value={sourceNode} onChange={(e) => setSourceNode(e.target.value)} className="input">
                  <option value="">Auto / none</option>
                  {featureOptions.map((f) => <option key={`src-${f}`} value={f}>{f}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Target</label>
                <select value={targetNode} onChange={(e) => setTargetNode(e.target.value)} className="input">
                  <option value="">Auto / none</option>
                  {featureOptions.map((f) => <option key={`tgt-${f}`} value={f}>{f}</option>)}
                </select>
              </div>
            </div>
          </div>

          <div className="card p-5">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2"><LuNetwork /> Metabolic Model Map</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">Optionally load a genome-scale model from BiGG or the Metabolic Atlas GEM repository. The flux map will be drawn from the selected model using your measured metabolites.</p>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end mb-4">
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Map source</label>
                <select value={mapSource} onChange={(e) => { setMapSource(e.target.value as any); setSelectedModel(null); setModelResults([]); setModelError('') }} className="input">
                  <option value="none">Manual (central carbon)</option>
                  <option value="bigg">BiGG Models</option>
                  <option value="gem">Metabolic Atlas GEMs</option>
                </select>
              </div>
              {mapSource !== 'none' && (
                <>
                  <div>
                    <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Search models</label>
                    <input type="text" value={modelQuery} onChange={(e) => setModelQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && searchModels()} className="input" placeholder={mapSource === 'bigg' ? 'e_coli_core' : 'Human'} />
                  </div>
                  <button onClick={searchModels} disabled={modelLoading} className="btn-secondary flex items-center gap-2"><LuSearch /> Search</button>
                </>
              )}
            </div>
            {modelError && <div className="mb-4 p-3 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-200 text-sm">{modelError}</div>}
            {selectedModel && (
              <div className="mb-4 p-3 rounded-lg bg-green-50 text-green-800 dark:bg-green-900/30 dark:text-green-200 text-sm flex items-center justify-between">
                <span>Loaded: <strong>{selectedModel.bigg_id || selectedModel.id}</strong> — {selectedModel.organism}</span>
                <button onClick={() => setSelectedModel(null)} className="text-xs underline">Clear</button>
              </div>
            )}
            {modelResults.length > 0 && (
              <div className="max-h-48 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg divide-y divide-slate-200 dark:divide-slate-700">
                {modelResults.map((m: any) => (
                  <div key={m.bigg_id || m.id} className="p-3 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-800">
                    <div>
                      <div className="font-medium text-slate-900 dark:text-white">{m.bigg_id || m.id}</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">{m.organism} {m.reaction_count ? `• ${m.reaction_count} reactions` : ''} {m.metabolite_count ? `• ${m.metabolite_count} metabolites` : ''}</div>
                    </div>
                    <button onClick={() => loadNetwork(m)} className="btn-secondary text-xs">Load</button>
                  </div>
                ))}
              </div>
            )}
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
                  <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">Network colored by mean labeled atoms, sized by total intensity, with pathway legend.</p>
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
