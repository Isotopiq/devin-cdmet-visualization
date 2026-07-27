import { useEffect, useState } from 'react'
import Plot from 'react-plotly.js'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import { buildPathway } from '../api'
import { LuGitMerge, LuRefreshCw, LuDownload } from 'react-icons/lu'

export default function Pathway() {
  const { projectId, datasetId, selectedDataset } = useWorkspace()
  const [valueType, setValueType] = useState('abundance')
  const [pathwaySource, setPathwaySource] = useState('kegg')
  const [figure, setFigure] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const generate = async () => {
    if (!projectId || !datasetId) return
    setLoading(true)
    const res = await buildPathway(Number(projectId), Number(datasetId), { value_type: valueType, pathway_source: pathwaySource })
    setFigure(res.data)
    setLoading(false)
  }

  const exportJson = () => {
    if (!figure) return
    const blob = new Blob([JSON.stringify(figure)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `pathway_${pathwaySource}.json`
    a.click()
  }

  useEffect(() => { setFigure(null) }, [selectedDataset])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Pathway Mapping</h1>
        <p className="page-subtitle">Map abundance, fold change, significance, or isotope enrichment onto metabolic pathways.</p>
      </div>

      <DatasetPicker />

      {!selectedDataset && <div className="card p-8 text-center text-slate-500 dark:text-slate-400">Select a dataset to map onto pathways.</div>}

      {selectedDataset && (
        <>
          <div className="card p-5">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2"><LuGitMerge /> Pathway Options</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Value to map</label>
                <select value={valueType} onChange={(e) => setValueType(e.target.value)} className="input">
                  <option value="abundance">Measured Abundance</option>
                  <option value="isotope_enrichment">Measured Isotope Enrichment</option>
                  <option value="inferred_flux">Inferred Flux Proxy</option>
                  <option value="user_flux">User-provided Flux</option>
                  <option value="modeled_flux">Modeled Flux</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Pathway source</label>
                <select value={pathwaySource} onChange={(e) => setPathwaySource(e.target.value)} className="input">
                  <option value="kegg">KEGG</option>
                  <option value="hmdb">HMDB</option>
                  <option value="chebi">ChEBI</option>
                  <option value="reactome">Reactome</option>
                  <option value="sbml">SBML</option>
                  <option value="metabolika">Metabolika</option>
                  <option value="custom">User-defined</option>
                </select>
              </div>
              <div className="flex gap-3 md:col-span-2">
                <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
                <button onClick={exportJson} disabled={!figure} className="btn-secondary"><LuDownload /> Export</button>
              </div>
            </div>
            <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">Nodes: metabolites. Edges: reactions. Colors distinguish measured abundance, measured isotope enrichment, inferred flux proxies, user-provided fluxes, and formally modeled fluxes.</p>
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
