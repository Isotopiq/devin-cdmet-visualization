import { useEffect, useMemo, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import PlotWithDownload from '../components/PlotWithDownload'
import { runIsotope, searchBiGGModels, searchGEMModels, loadModelNetwork } from '../api'
import { LuDna, LuRefreshCw, LuMap, LuNetwork, LuUsers, LuDownload, LuExternalLink } from 'react-icons/lu'

function FluxMapView({ map, filename }: { map: any; filename: string }) {
  const downloadGraphML = () => {
    if (!map?.graphml) return
    const blob = new Blob([map.graphml], { type: 'application/graphml+xml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${filename}.graphml`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-end gap-2">
        {map?.graphml && (
          <button onClick={downloadGraphML} className="btn-secondary text-xs">
            <LuDownload /> Export GraphML
          </button>
        )}
        <a
          href="https://fluxer.umbc.edu/"
          target="_blank"
          rel="noreferrer"
          className="btn-secondary text-xs inline-flex items-center gap-1"
          title="Open Fluxer to upload the exported GraphML"
        >
          <LuExternalLink /> Open Fluxer
        </a>
      </div>
      {map?.type === 'escher' ? (
        <div className="w-full rounded-lg overflow-hidden border border-slate-200 dark:border-slate-700" style={{ height: '600px' }}>
          <iframe
            title={filename}
            srcDoc={map.html}
            sandbox="allow-scripts allow-same-origin"
            style={{ width: '100%', height: '100%', border: 'none' }}
          />
        </div>
      ) : (
        <PlotWithDownload data={map.data} layout={map.layout} style={{ width: '100%', height: '600px' }} filename={filename} />
      )}
    </div>
  )
}

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
  const [style, setStyle] = useState('classic')
  const [showLabels, setShowLabels] = useState(false)

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

  const availableGroups = useMemo(() => {
    if (!selectedDataset) return []
    const cols = Object.keys(selectedDataset.data_matrix || {})
    const meta = selectedDataset.sample_metadata || {}
    const groups = new Set<string>()
    for (const col of cols) {
      let g: string | undefined = meta[col]
      if (!g || g === 'unknown') {
        const prefix = col.match(/^(.+?)_M\+\d+/)?.[1]
        const suffix = col.match(/^M\+\d+_(.+)$/)?.[1]
        g = prefix || suffix
      }
      if (g && g !== 'unknown') groups.add(g)
    }
    return Array.from(groups).sort()
  }, [selectedDataset])

  const [selectedGroups, setSelectedGroups] = useState<string[]>([])
  useEffect(() => { setSelectedGroups(availableGroups) }, [availableGroups])

  useEffect(() => { if (featureOptions[0]) setSelectedFeature(featureOptions[0]) }, [featureOptions])

  const toggleGroup = (group: string) => {
    setSelectedGroups((prev) => prev.includes(group) ? prev.filter((g) => g !== group) : [...prev, group])
  }

  const fetchModelList = async (q = '') => {
    setModelLoading(true)
    setModelError('')
    try {
      if (mapSource === 'bigg') {
        const res = await searchBiGGModels(q, 100)
        setModelResults(res.data.models || [])
      } else if (mapSource === 'gem') {
        const res = await searchGEMModels(q, 100)
        setModelResults(res.data.models || [])
      } else {
        setModelResults([])
      }
    } catch (err: any) {
      setModelError(err.response?.data?.detail || 'Model search failed')
    } finally {
      setModelLoading(false)
    }
  }

  useEffect(() => {
    setModelQuery('')
    setSelectedModel(null)
    if (mapSource !== 'none') fetchModelList()
  }, [mapSource])

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
        style,
        show_labels: showLabels,
      }
      if (circulatingEnrichment) payload.circulating_enrichment = Number(circulatingEnrichment)
      if (sourceNode) payload.source_node = sourceNode
      if (targetNode) payload.target_node = targetNode
      if (selectedModel) {
        payload.map_source = selectedModel.source
        payload.map_id = selectedModel.model_id
        payload.map_organism = selectedModel.organism || ''
      }
      if (selectedGroups.length > 0 && availableGroups.length > 0) {
        payload.selected_groups = selectedGroups
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
    const palette = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16', '#14b8a6', '#f97316', '#6366f1', '#22c55e']
    return { data: [{ x: labels, y: values, type: 'bar' as const, marker: { color: labels.map((_, i) => palette[i % palette.length]) } }], layout: { title: `Isotopologue fractions - ${selectedFeature}`, yaxis: { title: 'Fraction' }, xaxis: { title: 'Isotopologue' } } }
  }

  const groupNames = useMemo(() => {
    if (!results || !results.groups) return []
    return Object.keys(results.groups)
  }, [results])

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
            <div className="grid grid-cols-1 md:grid-cols-7 gap-4 items-end">
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Layout</label>
                <select value={layout} onChange={(e) => setLayout(e.target.value)} className="input">
                  <option value="spring">Spring</option>
                  <option value="curated">Curated pathways</option>
                  <option value="circular">Circular</option>
                  <option value="kamada_kawai">Kamada-Kawai</option>
                  <option value="fruchterman_reingold">Fruchterman-Reingold</option>
                  <option value="shell">Shell</option>
                  <option value="grid">Grid</option>
                  <option value="escher">Escher map</option>
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
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Style</label>
                <select value={style} onChange={(e) => setStyle(e.target.value)} className="input">
                  <option value="classic">Classic network</option>
                  <option value="dark_modern">Dark modern</option>
                  <option value="minimal">Minimal clean</option>
                  <option value="subway">Subway map</option>
                  <option value="fluxer">Fluxer style</option>
                </select>
              </div>
              <div className="flex items-center gap-2 pb-2 md:col-span-2">
                <input id="showLabels" type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} className="rounded border-slate-300" />
                <label htmlFor="showLabels" className="text-sm text-slate-700 dark:text-slate-200">Show metabolite & reaction labels</label>
              </div>
            </div>
          </div>

          {availableGroups.length > 0 && (
            <div className="card p-5">
              <h3 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2"><LuUsers /> Groups to include</h3>
              <div className="flex flex-wrap gap-3">
                {availableGroups.map((g) => (
                  <label key={g} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200 bg-slate-50 dark:bg-slate-800 px-3 py-2 rounded-lg cursor-pointer">
                    <input type="checkbox" checked={selectedGroups.includes(g)} onChange={() => toggleGroup(g)} />
                    {g}
                  </label>
                ))}
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">Independent flux maps will be generated for each selected group.</p>
            </div>
          )}

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
                    <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Filter models</label>
                    <input
                      type="text"
                      value={modelQuery}
                      onChange={(e) => { setModelQuery(e.target.value); fetchModelList(e.target.value) }}
                      className="input"
                      placeholder={mapSource === 'bigg' ? 'Type to filter BiGG models' : 'Type to filter GEM models'}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Select a model</label>
                    <select
                      value={selectedModel ? (selectedModel.bigg_id || selectedModel.id) : ''}
                      onChange={(e) => {
                        const m = modelResults.find((x: any) => (x.bigg_id || x.id) === e.target.value)
                        if (m) loadNetwork(m)
                      }}
                      disabled={modelLoading || modelResults.length === 0}
                      className="input"
                    >
                      <option value="">-- Pick a model --</option>
                      {modelResults.map((m: any) => (
                        <option key={m.bigg_id || m.id} value={m.bigg_id || m.id}>
                          {m.bigg_id || m.id} — {m.organism} {m.reaction_count ? `(${m.reaction_count} rxn)` : ''}
                        </option>
                      ))}
                    </select>
                  </div>
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
                  <h3 className="font-semibold text-slate-900 dark:text-white mb-3">Flux Map — Overall</h3>
                  <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">Network colored by mean labeled atoms, sized by total intensity, with pathway legend.</p>
                  <FluxMapView map={results.flux_map} filename="isotope_flux_map" />
                </div>
              )}

              {groupNames.length > 0 && (
                <div className="space-y-6">
                  {groupNames.map((group) => {
                    const g = results.groups[group]
                    if (!g?.flux_map) return null
                    return (
                      <div key={group} className="card p-5">
                        <h3 className="font-semibold text-slate-900 dark:text-white mb-3">Flux Map — {group}</h3>
                        <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">Per-group network colored by mean labeled atoms, sized by total intensity, with pathway legend.</p>
                        <FluxMapView map={g.flux_map} filename={`isotope_flux_map_${group}`} />
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
