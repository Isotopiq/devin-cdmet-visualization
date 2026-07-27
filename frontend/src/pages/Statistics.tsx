import { useEffect, useMemo, useState } from 'react'
import Plot from 'react-plotly.js'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import { runStats, generatePlot } from '../api'
import { LuPlay, LuDownload, LuAlertCircle } from 'react-icons/lu'

export default function Statistics() {
  const { selectedDataset, projectId, datasetId } = useWorkspace()
  const [test, setTest] = useState('t_test')
  const [groupA, setGroupA] = useState('')
  const [groupB, setGroupB] = useState('')
  const [paired, setPaired] = useState(false)
  const [multipleTesting, setMultipleTesting] = useState('fdr_bh')
  const [alpha, setAlpha] = useState(0.05)
  const [fcThreshold, setFcThreshold] = useState(0)
  const [results, setResults] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [volcano, setVolcano] = useState<any>(null)

  const groups = useMemo(() => {
    const meta = selectedDataset?.sample_metadata || {}
    const set = new Set<string>()
    Object.values(meta).forEach((g) => set.add(g))
    return Array.from(set)
  }, [selectedDataset])

  useEffect(() => {
    setGroupA(groups[0] || '')
    setGroupB(groups[1] || '')
  }, [groups])

  const run = async () => {
    if (!projectId || !datasetId) return
    setLoading(true)
    setError('')
    try {
      const res = await runStats(Number(projectId), Number(datasetId), { test, group_a: groupA, group_b: groupB, paired, multiple_testing: multipleTesting, alpha })
      const data = res.data
      if (fcThreshold > 0) {
        data.results = data.results.filter((r: any) => Math.abs(r.log2fc || 0) >= fcThreshold)
        data.n_features = data.results.length
      }
      data.results.sort((a: any, b: any) => (a.pvalue || 1) - (b.pvalue || 1))
      setResults(data)
      const vres = await generatePlot(Number(projectId), Number(datasetId), { plot_type: 'volcano', parameters: { stats: data.results } })
      setVolcano(vres.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Statistics failed')
    } finally {
      setLoading(false)
    }
  }

  const downloadCsv = () => {
    if (!results) return
    const headers = ['feature_id', 'mean_a', 'mean_b', 'log2fc', 'statistic', 'pvalue', 'padj']
    const rows = results.results.map((r: any) => headers.map((h) => r[h] ?? '').join(','))
    const csv = [headers.join(','), ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `stats_${test}_${groupA}_vs_${groupB}.csv`
    a.click()
  }

  const testOptions = [
    { value: 't_test', label: 'Student t-test' },
    { value: 'welch', label: 'Welch t-test' },
    { value: 'mannwhitney', label: 'Mann-Whitney U' },
    { value: 'paired', label: 'Paired t-test' },
    { value: 'wilcoxon', label: 'Wilcoxon signed-rank' },
    { value: 'anova', label: 'One-way ANOVA' },
    { value: 'kruskal', label: 'Kruskal-Wallis' },
  ]

  const mtOptions = [
    { value: 'fdr_bh', label: 'Benjamini-Hochberg (FDR)' },
    { value: 'bonferroni', label: 'Bonferroni' },
    { value: 'holm', label: 'Holm' },
    { value: 'none', label: 'None' },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Statistics</h1>
        <p className="page-subtitle">Univariate tests, fold change, and multiple-testing correction.</p>
      </div>

      <DatasetPicker />

      {!selectedDataset && <div className="card p-8 text-center text-slate-500 dark:text-slate-400">Select a dataset to run statistical tests.</div>}

      {selectedDataset && (
        <>
          <div className="card p-5">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-4">Test Parameters</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
              <div>
                <label className="label-like">Test</label>
                <select value={test} onChange={(e) => setTest(e.target.value)} className="input">
                  {testOptions.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
              <div>
                <label className="label-like">Group A</label>
                <select value={groupA} onChange={(e) => setGroupA(e.target.value)} className="input">
                  {groups.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </div>
              <div>
                <label className="label-like">Group B</label>
                <select value={groupB} onChange={(e) => setGroupB(e.target.value)} className="input">
                  {groups.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </div>
              <div>
                <label className="label-like">Multiple testing</label>
                <select value={multipleTesting} onChange={(e) => setMultipleTesting(e.target.value)} className="input">
                  {mtOptions.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              </div>
              <div>
                <label className="label-like">Alpha</label>
                <input type="number" step="0.01" min="0" max="1" value={alpha} onChange={(e) => setAlpha(Number(e.target.value))} className="input" />
              </div>
              <div>
                <label className="label-like">|log2FC| threshold</label>
                <input type="number" step="0.1" min="0" value={fcThreshold} onChange={(e) => setFcThreshold(Number(e.target.value))} className="input" />
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200 cursor-pointer">
                  <input type="checkbox" checked={paired} onChange={(e) => setPaired(e.target.checked)} className="rounded border-slate-300" />
                  Paired test
                </label>
              </div>
              <div className="flex items-end">
                <button onClick={run} disabled={loading || !groupA || !groupB} className="btn-primary"><LuPlay /> {loading ? 'Running...' : 'Run Test'}</button>
              </div>
            </div>
            {error && <div className="p-3 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-200 flex items-center gap-2 text-sm"><LuAlertCircle /> {error}</div>}
          </div>

          {results && (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              <div className="card p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-slate-900 dark:text-white">Results <span className="text-sm font-normal text-slate-500">({results.n_features} features, {test})</span></h3>
                  <button onClick={downloadCsv} className="btn-secondary"><LuDownload /> CSV</button>
                </div>
                <div className="overflow-x-auto max-h-[32rem]">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-50 dark:bg-slate-700/50 text-slate-500 dark:text-slate-300 uppercase text-xs sticky top-0">
                      <tr>
                        <th className="text-left p-2">Feature</th>
                        <th className="text-left p-2">log2FC</th>
                        <th className="text-left p-2">p-value</th>
                        <th className="text-left p-2">adj. p</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                      {(results.results || []).map((r: any, i: number) => (
                        <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                          <td className="p-2 font-medium text-slate-900 dark:text-white">{r.feature_id}</td>
                          <td className="p-2">{r.log2fc?.toFixed(3) || '-'}</td>
                          <td className="p-2">{r.pvalue?.toExponential(2)}</td>
                          <td className="p-2">{r.padj?.toExponential(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {volcano && (
                <div className="card p-5">
                  <h3 className="font-semibold text-slate-900 dark:text-white mb-3">Volcano Plot</h3>
                  <Plot data={volcano.data} layout={volcano.layout} style={{ width: '100%', height: '500px' }} config={{ responsive: true }} />
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
