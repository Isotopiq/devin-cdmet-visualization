import { useEffect, useState } from 'react'
import Plot from 'react-plotly.js'
import { listProjects, listDatasets, buildPathway } from '../api'
import { Project, Dataset } from '../types'

export default function Pathway() {
  const [projects, setProjects] = useState<Project[]>([])
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [projectId, setProjectId] = useState<number | ''>('')
  const [datasetId, setDatasetId] = useState<number | ''>('')
  const [valueType, setValueType] = useState('abundance')
  const [figure, setFigure] = useState<any>(null)

  useEffect(() => { listProjects().then((r) => setProjects(r.data)) }, [])
  useEffect(() => { if (projectId) listDatasets(Number(projectId)).then((r) => setDatasets(r.data)) }, [projectId])

  const generate = async () => {
    if (!projectId || !datasetId) return
    const res = await buildPathway(Number(projectId), Number(datasetId), { value_type: valueType, pathway_source: 'kegg' })
    setFigure(res.data)
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4 text-gray-900 dark:text-white">Pathway Mapping</h1>
      <p className="text-sm text-gray-600 dark:text-gray-300 mb-4">Nodes: metabolites; edges: reactions. Colors distinguish measured abundance, isotope enrichment, inferred flux proxies, and user-provided values.</p>
      <div className="flex flex-wrap gap-2 mb-4">
        <select value={projectId} onChange={(e) => setProjectId(Number(e.target.value))} className="border rounded-lg p-2"><option value="">Project</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        <select value={datasetId} onChange={(e) => setDatasetId(Number(e.target.value))} className="border rounded-lg p-2"><option value="">Dataset</option>{datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
        <select value={valueType} onChange={(e) => setValueType(e.target.value)} className="border rounded-lg p-2">
          <option value="abundance">Measured Abundance</option>
          <option value="isotope_enrichment">Measured Isotope Enrichment</option>
          <option value="inferred_flux">Inferred Flux Proxy</option>
          <option value="user_flux">User-provided Flux</option>
          <option value="modeled_flux">Modeled Flux</option>
        </select>
        <button onClick={generate} className="bg-blue-600 text-white rounded-lg px-4 py-2 hover:bg-blue-700">Generate</button>
      </div>
      {figure && <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4"><Plot data={figure.data} layout={figure.layout} style={{ width: '100%', height: '600px' }} config={{ responsive: true }} /></div>}
    </div>
  )
}
