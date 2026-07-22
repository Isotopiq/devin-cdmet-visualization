import { useEffect, useState } from 'react'
import { listProjects, listDatasets, runStats } from '../api'
import { Project, Dataset } from '../types'

export default function Statistics() {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState<number | ''>('')
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [datasetId, setDatasetId] = useState<number | ''>('')
  const [test, setTest] = useState('t_test')
  const [groupA, setGroupA] = useState('')
  const [groupB, setGroupB] = useState('')
  const [results, setResults] = useState<any>(null)

  useEffect(() => { listProjects().then((r) => setProjects(r.data)) }, [])
  useEffect(() => { if (projectId) listDatasets(Number(projectId)).then((r) => setDatasets(r.data)) }, [projectId])

  const run = async () => {
    if (!projectId || !datasetId) return
    const res = await runStats(Number(projectId), Number(datasetId), { test, group_a: groupA, group_b: groupB, paired: false, multiple_testing: 'fdr_bh', alpha: 0.05 })
    setResults(res.data)
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4 text-gray-900 dark:text-white">Statistics</h1>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
        <select value={projectId} onChange={(e) => setProjectId(Number(e.target.value))} className="border rounded-lg p-2">
          <option value="">Project</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select value={datasetId} onChange={(e) => setDatasetId(Number(e.target.value))} className="border rounded-lg p-2">
          <option value="">Dataset</option>
          {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <select value={test} onChange={(e) => setTest(e.target.value)} className="border rounded-lg p-2">
          <option value="t_test">Student t-test</option>
          <option value="welch">Welch t-test</option>
          <option value="mannwhitney">Mann-Whitney</option>
          <option value="paired">Paired t-test</option>
          <option value="wilcoxon">Wilcoxon</option>
          <option value="anova">One-way ANOVA</option>
          <option value="kruskal">Kruskal-Wallis</option>
        </select>
        <button onClick={run} className="bg-blue-600 text-white rounded-lg p-2 hover:bg-blue-700">Run</button>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <input placeholder="Group A" value={groupA} onChange={(e) => setGroupA(e.target.value)} className="border rounded-lg p-2" />
        <input placeholder="Group B" value={groupB} onChange={(e) => setGroupB(e.target.value)} className="border rounded-lg p-2" />
      </div>

      {results && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">Test: {results.test}, Features: {results.n_features}</p>
          <table className="min-w-full text-sm">
            <thead><tr className="border-b"><th className="text-left p-2">Feature</th><th className="text-left p-2">log2FC</th><th className="text-left p-2">p-value</th><th className="text-left p-2">adj. p</th></tr></thead>
            <tbody>
              {(results.results || []).slice(0, 50).map((r: any, i: number) => (
                <tr key={i} className="border-b"><td className="p-2">{r.feature_id}</td><td className="p-2">{r.log2fc?.toFixed(3) || '-'}</td><td className="p-2">{r.pvalue?.toExponential(2)}</td><td className="p-2">{r.padj?.toExponential(2)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
