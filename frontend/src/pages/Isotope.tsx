import { useEffect, useState } from 'react'
import Plot from 'react-plotly.js'
import { listProjects, listDatasets, runIsotope } from '../api'
import { Project, Dataset } from '../types'

export default function Isotope() {
  const [projects, setProjects] = useState<Project[]>([])
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [projectId, setProjectId] = useState<number | ''>('')
  const [datasetId, setDatasetId] = useState<number | ''>('')
  const [tracer, setTracer] = useState('13C')
  const [maxLabel, setMaxLabel] = useState(6)
  const [results, setResults] = useState<any>(null)

  useEffect(() => { listProjects().then((r) => setProjects(r.data)) }, [])
  useEffect(() => { if (projectId) listDatasets(Number(projectId)).then((r) => setDatasets(r.data)) }, [projectId])

  const run = async () => {
    if (!projectId || !datasetId) return
    const res = await runIsotope(Number(projectId), Number(datasetId), { tracer, max_label: maxLabel, natural_abundance_correction: false, normalization: 'none' })
    setResults(res.data)
  }

  const makeBar = () => {
    if (!results || !results.fractions) return null
    const first = Object.values(results.fractions)[0] as Record<string, number>
    const labels = Object.keys(first)
    const values = Object.values(first).map((v) => Number(v))
    return { data: [{ x: labels, y: values, type: 'bar' as const }], layout: { title: 'Isotopologue Fractions', yaxis: { title: 'Fraction' } } }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4 text-gray-900 dark:text-white">Isotope Tracing</h1>
      <div className="flex flex-wrap gap-2 mb-4">
        <select value={projectId} onChange={(e) => setProjectId(Number(e.target.value))} className="border rounded-lg p-2"><option value="">Project</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        <select value={datasetId} onChange={(e) => setDatasetId(Number(e.target.value))} className="border rounded-lg p-2"><option value="">Dataset</option>{datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
        <select value={tracer} onChange={(e) => setTracer(e.target.value)} className="border rounded-lg p-2"><option value="13C">13C</option><option value="15N">15N</option><option value="D">D</option></select>
        <input type="number" value={maxLabel} onChange={(e) => setMaxLabel(Number(e.target.value))} className="border rounded-lg p-2" placeholder="Max label" />
        <button onClick={run} className="bg-blue-600 text-white rounded-lg px-4 py-2 hover:bg-blue-700">Run</button>
      </div>
      {results && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <p className="text-sm text-gray-600 dark:text-gray-300">Pooled labeling: {JSON.stringify(results.pooled_labeling).slice(0, 200)}</p>
          {makeBar() && <Plot data={makeBar()!.data} layout={makeBar()!.layout} style={{ width: '100%', height: '400px' }} config={{ responsive: true }} />}
        </div>
      )}
    </div>
  )
}
