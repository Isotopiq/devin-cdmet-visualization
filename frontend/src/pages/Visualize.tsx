import { useEffect, useMemo, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import { usePlotConfig, styleToBackend } from '../context/PlotConfigContext'
import DatasetPicker from '../components/DatasetPicker'
import PlotWithDownload from '../components/PlotWithDownload'
import PlotStyling from '../components/PlotStyling'
import { generatePlot, runStats, generateReport } from '../api'
import { LuRefreshCw, LuFileDown, LuPrinter, LuChevronDown, LuChevronUp, LuX, LuDownload, LuFileText } from 'react-icons/lu'

const TABS = [
  { key: 'pca', label: 'PCA' },
  { key: 'volcano', label: 'Volcano' },
  { key: 'heatmap', label: 'Heatmap' },
  { key: 'per_lipid_bars', label: 'Per-lipid bars' },
  { key: 'lipid_classes', label: 'Lipid classes' },
  { key: 'outlier', label: 'Outlier' },
  { key: 'functional', label: 'Functional' },
  { key: 'food_profile', label: 'Food profile' },
]

const SCALES = [
  { value: 'row_zscore', label: 'Row z-score' },
  { value: 'log10', label: 'log10' },
  { value: 'none', label: 'None' },
]

const METRICS = [
  { value: 'euclidean', label: 'Euclidean' },
  { value: 'correlation', label: 'Correlation' },
  { value: 'cityblock', label: 'Manhattan' },
  { value: 'cosine', label: 'Cosine' },
]

const METHODS = [
  { value: 'average', label: 'Average' },
  { value: 'ward', label: 'Ward' },
  { value: 'complete', label: 'Complete' },
  { value: 'single', label: 'Single' },
]

const LIPIDS_PER_PAGE = [4, 6, 8, 12, 16, 24, 32]

const ALL_PLOT_KEYS = [
  { key: 'pca', label: 'PCA' },
  { key: 'volcano', label: 'Volcano (labels reflect current tab settings)' },
  { key: 'heatmap', label: 'Heatmap' },
  { key: 'per_lipid_bars', label: 'Per-lipid bars' },
  { key: 'lipid_classes', label: 'Lipid classes' },
  { key: 'outlier', label: 'Outlier' },
  { key: 'functional', label: 'Functional lipid indices' },
  { key: 'food_profile', label: 'Lipid food profile' },
]

export default function Visualize() {
  const { selectedDataset, projectId, datasetId } = useWorkspace()
  const { style, reportTitle, setReportTitle, includePlots, setIncludePlots } = usePlotConfig()
  const [tab, setTab] = useState('volcano')
  const [figure, setFigure] = useState<any>(null)
  const [figures, setFigures] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [ready, setReady] = useState(false)

  const groups = useMemo(() => {
    const meta = selectedDataset?.sample_metadata || {}
    const set = new Set<string>()
    Object.values(meta).forEach((g) => set.add(g as string))
    return Array.from(set)
  }, [selectedDataset])

  const [groupA, setGroupA] = useState('')
  const [groupB, setGroupB] = useState('')
  const [fcThreshold, setFcThreshold] = useState(1)
  const [pThreshold, setPThreshold] = useState(0.05)
  const [showLabels, setShowLabels] = useState(true)
  const [topN, setTopN] = useState(15)

  const [heatmapType, setHeatmapType] = useState('abundance')
  const [heatmapScale, setHeatmapScale] = useState('row_zscore')
  const [heatmapMetric, setHeatmapMetric] = useState('euclidean')
  const [heatmapMethod, setHeatmapMethod] = useState('average')
  const [heatmapTopN, setHeatmapTopN] = useState(50)
  const [rowCluster, setRowCluster] = useState(true)
  const [colCluster, setColCluster] = useState(true)

  const [lipidsPerPage, setLipidsPerPage] = useState(8)
  const [allLipids, setAllLipids] = useState(false)

  const [showContents, setShowContents] = useState(false)
  const [reportOpen, setReportOpen] = useState(false)
  const [reportSections, setReportSections] = useState<any[]>([])
  const [reportLoading, setReportLoading] = useState(false)

  useEffect(() => {
    setGroupA(groups[0] || '')
    setGroupB(groups[1] || '')
    setReady(true)
  }, [groups])

  const backendStyle = styleToBackend(style)

  const generate = async () => {
    if (!projectId || !datasetId || !groupA || !groupB) return
    setLoading(true)
    setFigure(null)
    setFigures([])
    try {
      const base = { projectId: Number(projectId), datasetId: Number(datasetId) }
      if (tab === 'pca') {
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'pca', parameters: { plot: 'score', title: reportTitle }, style: backendStyle })
        setFigure(res.data)
      } else if (tab === 'volcano') {
        const statsRes = await runStats(base.projectId, base.datasetId, { test: 't_test', group_a: groupA, group_b: groupB, paired: false, multiple_testing: 'fdr_bh', alpha: pThreshold })
        const res = await generatePlot(base.projectId, base.datasetId, {
          plot_type: 'volcano',
          parameters: { stats: statsRes.data.results, fc_threshold: fcThreshold, p_threshold: pThreshold, show_labels: showLabels, top_n: topN, group_a: groupA, group_b: groupB, title: reportTitle },
          style: backendStyle,
        })
        setFigure(res.data)
      } else if (tab === 'heatmap') {
        const res = await generatePlot(base.projectId, base.datasetId, {
          plot_type: 'heatmap',
          parameters: {
            heatmap_type: heatmapType,
            top_n: heatmapTopN,
            scale: heatmapScale,
            metric: heatmapMetric,
            method: heatmapMethod,
            cluster_rows: rowCluster,
            cluster_cols: colCluster,
          },
          style: backendStyle,
        })
        setFigure(res.data)
      } else if (tab === 'per_lipid_bars') {
        const statsRes = await runStats(base.projectId, base.datasetId, { test: 't_test', group_a: groupA, group_b: groupB, paired: false, multiple_testing: 'fdr_bh', alpha: pThreshold })
        const res = await generatePlot(base.projectId, base.datasetId, {
          plot_type: 'per_lipid_bars',
          parameters: { stats: statsRes.data.results, group_a: groupA, group_b: groupB, top_n: allLipids ? 1000 : lipidsPerPage },
          style: backendStyle,
        })
        if (Array.isArray(res.data)) setFigures(res.data)
        else setFigure(res.data)
      } else if (tab === 'lipid_classes') {
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'lipid_class', parameters: {}, style: backendStyle })
        setFigure(res.data)
      } else if (tab === 'outlier') {
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'outlier', parameters: { title: reportTitle }, style: backendStyle })
        setFigure(res.data)
      } else if (tab === 'functional') {
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'functional', parameters: { group_a: groupA, group_b: groupB, title: reportTitle }, style: backendStyle })
        setFigure(res.data)
      } else if (tab === 'food_profile') {
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'food_profile', parameters: { group_a: groupA, group_b: groupB, title: reportTitle }, style: backendStyle })
        setFigure(res.data)
      }
    } catch (err: any) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (selectedDataset && groupA && groupB) generate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, selectedDataset, groupA, groupB, ready])

  useEffect(() => {
    if (figure || figures.length) generate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [style])

  const toggleInclude = (key: string) => {
    setIncludePlots((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const buildReportParams = () => ({
    test: 't_test',
    group_a: groupA,
    group_b: groupB,
    paired: false,
    multiple_testing: 'fdr_bh',
    alpha: pThreshold,
    fc_threshold: fcThreshold,
    p_threshold: pThreshold,
    show_labels: showLabels,
    top_n: topN,
    heatmap_top_n: heatmapTopN,
    scale: heatmapScale,
    metric: heatmapMetric,
    method: heatmapMethod,
    cluster_rows: rowCluster,
    cluster_cols: colCluster,
    per_lipid_top_n: lipidsPerPage,
    all_lipids: allLipids,
  })

  const exportReport = async () => {
    if (!projectId || !datasetId || !groupA || !groupB) return
    setReportLoading(true)
    setReportOpen(true)
    try {
      const include = ALL_PLOT_KEYS.filter((p) => includePlots[p.key]).map((p) => p.key)
      const res = await generateReport(Number(projectId), Number(datasetId), {
        include,
        style: backendStyle,
        parameters: buildReportParams(),
      })
      setReportSections(res.data)
      setTimeout(() => window.print(), 1500)
    } catch (err: any) {
      console.error(err)
      setReportOpen(false)
    } finally {
      setReportLoading(false)
    }
  }

  const renderSection = (section: any, idx: number) => {
    if (section.figures) {
      return (
        <div key={idx} className="card p-4 mb-6">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">{section.title}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {section.figures.map((f: any, i: number) => (
              <div key={i} className="card p-3">
                <PlotWithDownload data={f.data} layout={f.layout} filename={`${section.key}_${i}`} style={{ width: '100%', height: '320px' }} />
              </div>
            ))}
          </div>
        </div>
      )
    }
    return (
      <div key={idx} className="card p-4 mb-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">{section.title}</h2>
        <PlotWithDownload data={section.figure.data} layout={section.figure.layout} filename={`${section.key}_${reportTitle.replace(/\s+/g, '_')}`} style={{ width: '100%', height: '520px' }} />
      </div>
    )
  }

  const tabControls = () => {
    if (tab === 'volcano') {
      return (
        <div className="grid grid-cols-2 md:grid-cols-7 gap-3 items-end">
          <div><label className="label-like">Group A</label><select value={groupA} onChange={(e) => setGroupA(e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
          <div><label className="label-like">Group B</label><select value={groupB} onChange={(e) => setGroupB(e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
          <div><label className="label-like">log2FC cutoff</label><input type="number" step="0.1" value={fcThreshold} onChange={(e) => setFcThreshold(Number(e.target.value))} className="input" /></div>
          <div><label className="label-like">p-value cutoff</label><input type="number" step="0.01" value={pThreshold} onChange={(e) => setPThreshold(Number(e.target.value))} className="input" /></div>
          <div className="flex items-center gap-2 pb-2"><input type="checkbox" id="labels" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} /><label htmlFor="labels">Label top</label></div>
          <div><input type="number" min={1} max={50} value={topN} onChange={(e) => setTopN(Number(e.target.value))} className="input" /></div>
          <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
        </div>
      )
    }
    if (tab === 'heatmap') {
      return (
        <div className="grid grid-cols-2 md:grid-cols-9 gap-3 items-end">
          <div><label className="label-like">Type</label><select value={heatmapType} onChange={(e) => setHeatmapType(e.target.value)} className="input"><option value="abundance">Abundance</option><option value="correlation">Correlation</option></select></div>
          <div><label className="label-like">Scale</label><select value={heatmapScale} onChange={(e) => setHeatmapScale(e.target.value)} className="input">{SCALES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}</select></div>
          <div><label className="label-like">Distance</label><select value={heatmapMetric} onChange={(e) => setHeatmapMetric(e.target.value)} className="input">{METRICS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}</select></div>
          <div><label className="label-like">Linkage</label><select value={heatmapMethod} onChange={(e) => setHeatmapMethod(e.target.value)} className="input">{METHODS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}</select></div>
          <div><label className="label-like">Top N</label><input type="number" value={heatmapTopN} onChange={(e) => setHeatmapTopN(Number(e.target.value))} className="input" /></div>
          <div className="flex items-center gap-2 pb-2"><input type="checkbox" id="rowCluster" checked={rowCluster} onChange={(e) => setRowCluster(e.target.checked)} /><label htmlFor="rowCluster">Rows</label></div>
          <div className="flex items-center gap-2 pb-2"><input type="checkbox" id="colCluster" checked={colCluster} onChange={(e) => setColCluster(e.target.checked)} /><label htmlFor="colCluster">Cols</label></div>
          <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
        </div>
      )
    }
    if (tab === 'per_lipid_bars') {
      return (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3 items-end">
          <div><label className="label-like">Group A</label><select value={groupA} onChange={(e) => setGroupA(e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
          <div><label className="label-like">Group B</label><select value={groupB} onChange={(e) => setGroupB(e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
          <div><label className="label-like">Lipids/page</label><select value={lipidsPerPage} onChange={(e) => setLipidsPerPage(Number(e.target.value))} className="input">{LIPIDS_PER_PAGE.map(n => <option key={n} value={n}>{n}</option>)}</select></div>
          <div className="flex items-center gap-2 pb-2"><input type="checkbox" id="allLipids" checked={allLipids} onChange={(e) => setAllLipids(e.target.checked)} /><label htmlFor="allLipids">All lipids</label></div>
          <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
        </div>
      )
    }
    if (tab === 'functional' || tab === 'food_profile') {
      return (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 items-end">
          <div><label className="label-like">Group A</label><select value={groupA} onChange={(e) => setGroupA(e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
          <div><label className="label-like">Group B</label><select value={groupB} onChange={(e) => setGroupB(e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
          <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
        </div>
      )
    }
    return <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
  }

  return (
    <>
      <div className="space-y-4 no-print">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="page-title">Visualize</h1>
            <p className="page-subtitle">Style-aware plots, single-page preview, and PDF export.</p>
          </div>
        </div>

        <DatasetPicker />

        {!selectedDataset && <div className="card p-8 text-center text-slate-500 dark:text-slate-400">Select a dataset to visualize.</div>}

        {selectedDataset && (
          <div className="flex flex-col lg:flex-row gap-4">
            <div className="flex-1 space-y-4 min-w-0">
              <div className="card p-2 flex flex-wrap gap-2">
                {TABS.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setTab(t.key)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === t.key ? 'bg-slate-800 text-white' : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'}`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              <div className="card p-4 flex flex-col md:flex-row md:items-end gap-3 flex-wrap">
                <div className="flex-1 min-w-[200px]">
                  <label className="label-like">Title</label>
                  <input value={reportTitle} onChange={(e) => setReportTitle(e.target.value)} className="input text-sm" placeholder="Report title" />
                </div>
                {tab === 'per_lipid_bars' && (
                  <>
                    <div><label className="label-like">Lipids/page</label><select value={lipidsPerPage} onChange={(e) => setLipidsPerPage(Number(e.target.value))} className="input">{LIPIDS_PER_PAGE.map(n => <option key={n} value={n}>{n}</option>)}</select></div>
                    <div className="flex items-center gap-2 pb-2"><input type="checkbox" id="allLipidsTop" checked={allLipids} onChange={(e) => setAllLipids(e.target.checked)} /><label htmlFor="allLipidsTop">All lipids</label></div>
                  </>
                )}
                <button className="btn-secondary text-sm" disabled title="ZIP export coming soon"><LuFileDown /> ZIP plots</button>
                <button onClick={exportReport} disabled={reportLoading || loading} className="btn-primary text-sm"><LuPrinter /> Export PDF</button>
              </div>

              <div className="card p-0 overflow-hidden">
                <button onClick={() => setShowContents((s) => !s)} className="w-full flex items-center justify-between p-3 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700">
                  <span className="flex items-center gap-2"><LuFileText /> PDF report contents ({ALL_PLOT_KEYS.filter(p => includePlots[p.key]).length} of {ALL_PLOT_KEYS.length} plots)</span>
                  {showContents ? <LuChevronUp /> : <LuChevronDown />}
                </button>
                {showContents && (
                  <div className="border-t border-slate-200 dark:border-slate-700 p-4 grid grid-cols-1 md:grid-cols-2 gap-2">
                    {ALL_PLOT_KEYS.map((p) => (
                      <label key={p.key} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                        <input type="checkbox" checked={!!includePlots[p.key]} onChange={() => toggleInclude(p.key)} />
                        {p.label}
                      </label>
                    ))}
                  </div>
                )}
              </div>

              <div className="card p-4">
                {tabControls()}
              </div>

              {figure && !figures.length && (
                <div className="card p-5">
                  <PlotWithDownload data={figure.data} layout={figure.layout} style={{ width: '100%', height: tab === 'heatmap' ? '650px' : '550px' }} filename={`${tab}_${reportTitle.replace(/\s+/g, '_')}`} />
                </div>
              )}

              {figures.length > 0 && (
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  {figures.map((f, i) => (
                    <div key={i} className="card p-4">
                      <PlotWithDownload data={f.data} layout={f.layout} style={{ width: '100%', height: '360px' }} filename={`per_lipid_${i}`} />
                    </div>
                  ))}
                </div>
              )}
            </div>

            <PlotStyling />
          </div>
        )}
      </div>

      {reportOpen && (
        <div className="fixed inset-0 z-50 bg-white dark:bg-slate-900 overflow-auto p-6 report-overlay print-block">
          <div className="flex items-center justify-between mb-6 no-print">
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">{reportTitle || 'Analysis report'}</h2>
            <div className="flex items-center gap-2">
              <button onClick={() => window.print()} className="btn-primary"><LuPrinter /> Print / Save PDF</button>
              <button onClick={() => setReportOpen(false)} className="btn-secondary"><LuX /> Close</button>
            </div>
          </div>
          <div className="max-w-6xl mx-auto space-y-6">
            <div className="flex items-center gap-4 mb-8">
              <img src="/logo.png" alt="isotopiq" className="h-10" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
              <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">{reportTitle || 'Analysis report'}</h1>
                <p className="text-sm text-slate-500 dark:text-slate-400">{selectedDataset?.name || ''} • {new Date().toLocaleString()}</p>
              </div>
            </div>
            {reportSections.map(renderSection)}
          </div>
        </div>
      )}
    </>
  )
}
