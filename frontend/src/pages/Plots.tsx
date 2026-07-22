import { useEffect, useState } from 'react'
import Plot from 'react-plotly.js'
import { listProjects, listDatasets, generatePlot } from '../api'
import { Project, Dataset } from '../types'

export default function Plots() {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState<number | ''>('')
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [datasetId, setDatasetId] = useState<number | ''>('')
  const [plotType, setPlotType] = useState('bar')
  const [figure, setFigure] = useState<any>(null)

  useEffect(() => { listProjects().then((r) => setProjects(r.data)) }, [])
  useEffect(() => { if (projectId) listDatasets(Number(projectId)).then((r) => setDatasets(r.data)) }, [projectId])

  const generate = async () => {
    if (!projectId || !datasetId) return
    const res = await generatePlot(Number(projectId), Number(datasetId), { plot_type: plotType, parameters: {} })
    setFigure(res.data)
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4 text-gray-900 dark:text-white">Compound Plots</h1>
      <div className="flex gap-2 mb-4">
        <select value={projectId} onChange={(e) => setProjectId(Number(e.target.value))} className="border rounded-lg p-2"><option value="">Project</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        <select value={datasetId} onChange={(e) => setDatasetId(Number(e.target.value))} className="border rounded-lg p-2"><option value="">Dataset</option>{datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
        <select value={plotType} onChange={(e) => setPlotType(e.target.value)} className="border rounded-lg p-2">
          <option value="bar">Bar Plot</option>
          <option value="box">Box Plot</option>
          <option value="rt_mz">RT vs m/z</option>
        </select>
        <button onClick={generate} className="bg-blue-600 text-white rounded-lg px-4 py-2 hover:bg-blue-700">Generate</button>
      </div>
      {figure && <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4"><Plot data={figure.data} layout={figure.layout} style={{ width: '100%', height: '500px' }} config={{ responsive: true }} /></div>}
    </div>
  )
}
