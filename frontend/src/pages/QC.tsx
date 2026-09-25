import { useEffect, useRef, useState, useCallback } from 'react'
import Plotly from 'plotly.js/dist/plotly'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import PlotWithDownload from '../components/PlotWithDownload'
import { getQC, exportQCExcel, exportQCPdf, getSettings } from '../api'
import { LuActivity, LuRefreshCw, LuDownload, LuFileText, LuEye, LuX, LuArrowUp, LuArrowDown } from 'react-icons/lu'

interface QCData {
  metrics: {
    num_features: number
    num_samples: number
    num_groups: number
    group_counts: Record<string, number>
    total_missing_pct: number
    missing_per_sample: Record<string, number>
    tic: Record<string, number>
    log2_tic: Record<string, number>
    detected_features: Record<string, number>
    group_cv_pct: Record<string, number | null>
    qc_median_cv_pct?: number | null
    sample_to_blank_median_ratio?: number | null
    pca_outlier_count: number
    pca_outlier_samples: string[]
  }
  figures: Record<string, any>
}

const FONT_OPTIONS = [
  { label: 'Default (system)', value: '' },
  { label: 'Helvetica', value: 'Helvetica' },
  { label: 'Times', value: 'Times' },
  { label: 'Courier', value: 'Courier' },
  { label: 'DejaVu', value: 'DejaVu' },
  { label: 'Liberation', value: 'Liberation' },
]

// Keep in sync with STYLE_DEFAULTS.group_colors in backend/app/services/plots.py
const DEFAULT_GROUP_COLORS = ['#4e79a7', '#e15759', '#f28e2c', '#76b7b2', '#59a14f', '#edc949']

const PLOT_OPTIONS = [
  { key: 'tic', label: 'Total Ion Current (TIC)' },
  { key: 'missing_pct', label: 'Missing Values per Sample' },
  { key: 'detected_features', label: 'Detected Features per Sample' },
  { key: 'log2_intensity', label: 'Sample Intensity Distribution' },
  { key: 'cv_by_group', label: 'Per-Feature CV by Group' },
  { key: 'qc_pool_drift', label: 'QC-Pool TIC Drift' },
  { key: 'qc_pool_correction', label: 'QC-Pool Correction' },
  { key: 'pca', label: 'PCA Score Plot' },
  { key: 'correlation_heatmap', label: 'Sample Correlation Heatmap' },
]

export default function QC() {
  const { projectId, datasetId, selectedDataset } = useWorkspace()
  const [data, setData] = useState<QCData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedGroups, setSelectedGroups] = useState<Set<string>>(new Set())
  const [pdfMeta, setPdfMeta] = useState({
    primary_comparison: '',
    prepared_for: '',
    prepared_by: 'Metabolomics Platform',
    report_contents: 'QC Report',
  })
  const [fontFamily, setFontFamily] = useState('')
  const [plotsPerPage, setPlotsPerPage] = useState<1 | 2 | 4 | 6>(2)
  const [tickSize, setTickSize] = useState(11)
  const [axisLabelSize, setAxisLabelSize] = useState(12)
  const [groupOrder, setGroupOrder] = useState<string[]>([])
  const [groupColors, setGroupColors] = useState<Record<string, string>>({})
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [s3Configured, setS3Configured] = useState(false)
  const [saveToS3, setSaveToS3] = useState(false)
  const [selectedPlots, setSelectedPlots] = useState<Set<string>>(new Set(PLOT_OPTIONS.map((p) => p.key)))
  const graphDivs = useRef<Record<string, HTMLDivElement | null>>({})

  const allGroups = selectedDataset?.sample_metadata
    ? Array.from(new Set(Object.values(selectedDataset.sample_metadata as Record<string, string>))).sort()
    : []

  const isControlLike = (g: string) => /\b(blank|qc|solvent|standard|pool|ntc)\b/i.test(g)

  // Mirrors the backend default palette assignment (sorted included groups).
  const defaultColorFor = (g: string) => {
    const included = Array.from(selectedGroups).sort()
    const idx = included.indexOf(g)
    return DEFAULT_GROUP_COLORS[(idx < 0 ? 0 : idx) % DEFAULT_GROUP_COLORS.length]
  }
  const colorFor = (g: string) => groupColors[g] || defaultColorFor(g)
  const setGroupColor = (g: string, color: string) => setGroupColors((prev) => ({ ...prev, [g]: color }))
  const resetGroupColors = () => setGroupColors({})
  const activeGroupColors = () =>
    Object.fromEntries(Object.entries(groupColors).filter(([g]) => selectedGroups.has(g)))

  const toggleGroup = (g: string) => {
    setSelectedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(g)) next.delete(g)
      else next.add(g)
      return next
    })
    setGroupOrder((prev) => {
      if (prev.includes(g)) return prev.filter((x) => x !== g)
      return [...prev, g]
    })
  }

  const moveGroup = (index: number, direction: number) => {
    setGroupOrder((prev) => {
      if (index + direction < 0 || index + direction >= prev.length) return prev
      const next = [...prev]
      ;[next[index], next[index + direction]] = [next[index + direction], next[index]]
      return next
    })
  }

  const togglePlot = (key: string) => {
    setSelectedPlots((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  useEffect(() => {
    setData(null)
    if (selectedDataset?.sample_metadata) {
      const all = Array.from(new Set(Object.values(selectedDataset.sample_metadata as Record<string, string>)))
      const nonControl = all.filter((g) => !isControlLike(g))
      const control = all.filter((g) => isControlLike(g))
      setSelectedGroups(new Set(nonControl))
      setGroupOrder([...nonControl, ...control])
    } else {
      setSelectedGroups(new Set())
      setGroupOrder([])
    }
    setGroupColors({})
  }, [selectedDataset])

  useEffect(() => {
    getSettings()
      .then((res: any) => {
        const defaultPrepared = res.data?.pdf_prepared_by
        if (defaultPrepared) {
          setPdfMeta((prev) => ({ ...prev, prepared_by: defaultPrepared }))
        }
        setS3Configured(!!res.data?.s3_configured)
      })
      .catch(() => {})
  }, [])

  const handleGraphDiv = useCallback((key: string, gd: HTMLDivElement | null) => {
    graphDivs.current[key] = gd
  }, [])

  const capturePlotImages = useCallback(async () => {
    if (!data) return {}
    const images: Record<string, string> = {}
    await Promise.all(
      Array.from(selectedPlots).map(async (key) => {
        const gd = graphDivs.current[key]
        const fig = data.figures[key]
        if (!gd || !fig) return
        const rect = gd.getBoundingClientRect()
        if (!rect.width || !rect.height) return
        try {
          const url = await Plotly.toImage(gd, {
            format: 'png',
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            scale: 2,
          })
          images[key] = url
        } catch (err) {
          console.error(`Failed to capture QC plot ${key}`, err)
        }
      })
    )
    return images
  }, [data, selectedPlots])

  const buildPdfPayload = (plotImages?: Record<string, string>) => {
    const payload: any = {
      selected_groups: Array.from(selectedGroups),
      group_order: groupOrder,
      selected_plots: Array.from(selectedPlots),
      primary_comparison: pdfMeta.primary_comparison || undefined,
      prepared_for: pdfMeta.prepared_for || undefined,
      prepared_by: pdfMeta.prepared_by || undefined,
      report_contents: pdfMeta.report_contents || undefined,
      font_family: fontFamily || undefined,
      tick_size: tickSize,
      axis_label_size: axisLabelSize,
      plots_per_page: plotsPerPage,
      save_to_s3: saveToS3,
    }
    const colors = activeGroupColors()
    if (Object.keys(colors).length > 0) {
      payload.group_colors = colors
    }
    if (plotImages && Object.keys(plotImages).length > 0) {
      payload.plot_images = plotImages
    }
    return payload
  }

  const handleExportExcel = async () => {
    if (!projectId || !datasetId || !selectedDataset) return
    try {
      const res = await exportQCExcel(Number(projectId), Number(datasetId), Array.from(selectedGroups), groupOrder, activeGroupColors())
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `${selectedDataset.name.replace(/\s+/g, '_')}_qc_summary.xlsx`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to export QC Excel')
    }
  }

  const generatePdf = async () => {
    if (!projectId || !datasetId || !selectedDataset || selectedPlots.size === 0 || selectedGroups.size === 0) return null
    const plotImages = await capturePlotImages()
    const res = await exportQCPdf(Number(projectId), Number(datasetId), buildPdfPayload(plotImages))
    return window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
  }

  const handlePreviewPdf = async () => {
    if (!projectId || !datasetId || !selectedDataset || selectedGroups.size === 0 || selectedPlots.size === 0) return
    setLoading(true)
    setError('')
    try {
      const url = await generatePdf()
      if (url) {
        setPreviewUrl(url)
        setPreviewOpen(true)
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to generate QC PDF preview')
    } finally {
      setLoading(false)
    }
  }

  const handleExportPdf = async () => {
    if (!projectId || !datasetId || !selectedDataset || selectedGroups.size === 0 || selectedPlots.size === 0) return
    setLoading(true)
    setError('')
    try {
      const url = await generatePdf()
      if (url) {
        const link = document.createElement('a')
        link.href = url
        link.setAttribute('download', `${selectedDataset.name.replace(/\s+/g, '_')}_qc_report.pdf`)
        document.body.appendChild(link)
        link.click()
        link.remove()
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to export QC PDF')
    } finally {
      setLoading(false)
    }
  }

  const closePreview = () => {
    setPreviewOpen(false)
    if (previewUrl) {
      window.URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
  }

  const load = async () => {
    if (!projectId || !datasetId || selectedGroups.size === 0) return
    setLoading(true)
    setError('')
    try {
      const res = await getQC(Number(projectId), Number(datasetId), Array.from(selectedGroups), groupOrder, tickSize, axisLabelSize, activeGroupColors())
      setData(res.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load QC data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { setData(null) }, [selectedDataset])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Quality Control</h1>
        <p className="page-subtitle">Dataset-level QC metrics and plots for run-order, intensity, missing values, and outliers.</p>
      </div>

      <DatasetPicker />

      {!selectedDataset && <div className="card p-8 text-center text-slate-500 dark:text-slate-400">Select a dataset to run QC.</div>}

      {selectedDataset && (
        <>
          <div className="card p-5 flex items-end gap-4 flex-wrap">
            <button onClick={load} disabled={loading || selectedGroups.size === 0} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Run QC</button>
            <button onClick={handleExportExcel} disabled={!selectedDataset || selectedGroups.size === 0} className="btn-secondary"><LuDownload /> Export Excel Summary</button>
            <button onClick={handlePreviewPdf} disabled={!selectedDataset || loading || selectedGroups.size === 0 || selectedPlots.size === 0} className="btn-secondary"><LuEye /> Preview QC PDF</button>
            <button onClick={handleExportPdf} disabled={!selectedDataset || loading || selectedGroups.size === 0 || selectedPlots.size === 0} className="btn-secondary"><LuFileText /> Export QC PDF Report</button>
            {error && <span className="text-sm text-red-600 dark:text-red-400">{error}</span>}
          </div>

          {selectedDataset && allGroups.length > 0 && (
            <div className="card p-4 space-y-3">
              <div>
                <div className="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-2">Groups to include in QC</div>
                <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">Blanks, QC, solvent, standard, pool, and NTC groups are unchecked by default.</p>
                <div className="flex flex-wrap gap-4">
                  {allGroups.map((g) => (
                    <label key={g} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                      <input
                        type="checkbox"
                        checked={selectedGroups.has(g)}
                        onChange={() => toggleGroup(g)}
                      />
                      {g}
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">Group display order &amp; colors</div>
                  {Object.keys(groupColors).length > 0 && (
                    <button type="button" onClick={resetGroupColors} className="text-xs text-indigo-600 hover:underline dark:text-indigo-400">
                      Reset colors
                    </button>
                  )}
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">Click a swatch to change that group's color, then Run QC to apply. Colors are also used in Excel and PDF exports.</p>
                <ul className="space-y-1">
                  {groupOrder.map((g, i) => (
                    <li key={g} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                      <button
                        type="button"
                        disabled={i === 0}
                        onClick={() => moveGroup(i, -1)}
                        className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-30"
                      >
                        <LuArrowUp className="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        disabled={i === groupOrder.length - 1}
                        onClick={() => moveGroup(i, 1)}
                        className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-30"
                      >
                        <LuArrowDown className="w-4 h-4" />
                      </button>
                      <input
                        type="color"
                        aria-label={`Color for ${g}`}
                        title={`Color for ${g}`}
                        value={colorFor(g)}
                        onChange={(e) => setGroupColor(g, e.target.value)}
                        disabled={!selectedGroups.has(g)}
                        className="w-6 h-6 p-0 border border-slate-300 dark:border-slate-600 rounded cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed bg-transparent"
                      />
                      <span className={selectedGroups.has(g) ? '' : 'opacity-50'}>{g}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {selectedDataset && (
            <div className="card p-5 space-y-4">
              <h3 className="text-md font-semibold text-slate-900 dark:text-white">QC PDF Report Options</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="label-like">Primary comparison</label>
                  <input
                    type="text"
                    className="input"
                    value={pdfMeta.primary_comparison}
                    onChange={(e) => setPdfMeta({ ...pdfMeta, primary_comparison: e.target.value })}
                    placeholder="e.g. FLVCR1-KO vs FLVCR1-CTRL"
                  />
                </div>
                <div>
                  <label className="label-like">Prepared for</label>
                  <input
                    type="text"
                    className="input"
                    value={pdfMeta.prepared_for}
                    onChange={(e) => setPdfMeta({ ...pdfMeta, prepared_for: e.target.value })}
                    placeholder="e.g. Principal Investigator"
                  />
                </div>
                <div>
                  <label className="label-like">Prepared by</label>
                  <input
                    type="text"
                    className="input"
                    value={pdfMeta.prepared_by}
                    onChange={(e) => setPdfMeta({ ...pdfMeta, prepared_by: e.target.value })}
                    placeholder="Metabolomics Platform"
                  />
                </div>
                <div>
                  <label className="label-like">Report contents</label>
                  <input
                    type="text"
                    className="input"
                    value={pdfMeta.report_contents}
                    onChange={(e) => setPdfMeta({ ...pdfMeta, report_contents: e.target.value })}
                    placeholder="QC Report"
                  />
                </div>
                <div>
                  <label className="label-like">PDF font</label>
                  <select
                    className="select"
                    value={fontFamily}
                    onChange={(e) => setFontFamily(e.target.value)}
                  >
                    {FONT_OPTIONS.map((f) => (
                      <option key={f.value} value={f.value}>
                        {f.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="label-like">X-axis label size</label>
                  <input
                    type="number"
                    min={6}
                    max={24}
                    className="input"
                    value={tickSize}
                    onChange={(e) => setTickSize(Number(e.target.value))}
                  />
                </div>
                <div>
                  <label className="label-like">Axis title size</label>
                  <input
                    type="number"
                    min={6}
                    max={24}
                    className="input"
                    value={axisLabelSize}
                    onChange={(e) => setAxisLabelSize(Number(e.target.value))}
                  />
                </div>
                {s3Configured && (
                  <div className="flex items-center gap-2 md:col-span-2">
                    <input
                      id="qc-save-to-s3"
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                      checked={saveToS3}
                      onChange={(e) => setSaveToS3(e.target.checked)}
                    />
                    <label htmlFor="qc-save-to-s3" className="label-like !mb-0">Save a copy to S3</label>
                  </div>
                )}
              </div>

              <div>
                <label className="label-like">Plots per page</label>
                <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">
                  Choose how many QC plots appear on each PDF page. 2 per page is the recommended default.
                </p>
                <select
                  className="select"
                  value={plotsPerPage}
                  onChange={(e) => setPlotsPerPage(Number(e.target.value) as 1 | 2 | 4 | 6)}
                >
                  <option value={1}>1 plot per page</option>
                  <option value={2}>2 plots per page (default)</option>
                  <option value={4}>4 plots per page</option>
                  <option value={6}>6 plots per page</option>
                </select>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="label-like">Plots to include in QC PDF</label>
                  <div className="flex gap-2 text-xs">
                    <button
                      type="button"
                      onClick={() => setSelectedPlots(new Set(PLOT_OPTIONS.map((p) => p.key)))}
                      className="text-indigo-600 hover:text-indigo-700 dark:text-indigo-400"
                    >Select all</button>
                    <span className="text-slate-300">|</span>
                    <button
                      type="button"
                      onClick={() => setSelectedPlots(new Set())}
                      className="text-indigo-600 hover:text-indigo-700 dark:text-indigo-400"
                    >Clear</button>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {PLOT_OPTIONS.map((plot) => (
                    <label key={plot.key} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                      <input
                        type="checkbox"
                        checked={selectedPlots.has(plot.key)}
                        onChange={() => togglePlot(plot.key)}
                        className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      {plot.label}
                    </label>
                  ))}
                </div>
              </div>
            </div>
          )}

          {data && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <MetricCard label="Features" value={data.metrics.num_features} />
                <MetricCard label="Samples" value={data.metrics.num_samples} />
                <MetricCard label="Groups" value={data.metrics.num_groups} />
                <MetricCard label="Missing values" value={`${data.metrics.total_missing_pct}%`} />
                {data.metrics.qc_median_cv_pct !== undefined && data.metrics.qc_median_cv_pct !== null && (
                  <MetricCard label="QC median CV" value={`${data.metrics.qc_median_cv_pct}%`} />
                )}
                {data.metrics.sample_to_blank_median_ratio !== undefined && data.metrics.sample_to_blank_median_ratio !== null && (
                  <MetricCard label="Sample/Blank ratio" value={`${data.metrics.sample_to_blank_median_ratio}x`} />
                )}
                <MetricCard label="PCA outliers" value={data.metrics.pca_outlier_count} />
              </div>

              {data.metrics.pca_outlier_samples.length > 0 && (
                <div className="card p-4 text-sm text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900/50">
                  Flagged outlier samples: {data.metrics.pca_outlier_samples.join(', ')}
                </div>
              )}

              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {Object.entries(data.figures).map(([key, fig]) => (
                  <div key={key} className="card p-4">
                    <h3 className="font-semibold text-slate-900 dark:text-white mb-3 flex items-center gap-2"><LuActivity /> {titleFor(key)}</h3>
                    <PlotWithDownload
                      data={fig.data}
                      layout={fig.layout}
                      style={{ width: '100%', height: '450px' }}
                      filename={`qc_${key}`}
                      onGraphDiv={(gd) => handleGraphDiv(key, gd)}
                    />
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}

      {previewOpen && previewUrl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="bg-white dark:bg-slate-900 rounded-xl shadow-xl w-full max-w-6xl h-[90vh] flex flex-col overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-700">
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">QC PDF Preview</h2>
              <button onClick={closePreview} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300">
                <LuX />
              </button>
            </div>
            <div className="flex-1 min-h-0">
              <iframe src={previewUrl} title="QC PDF Preview" className="w-full h-full" />
            </div>
            <div className="p-4 border-t border-slate-200 dark:border-slate-700 flex justify-end gap-2">
              <button onClick={closePreview} className="btn-secondary">Close</button>
              <button onClick={handleExportPdf} disabled={loading} className="btn-primary">Export PDF</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function MetricCard({ label, value }: { label: string; value: any }) {
  return (
    <div className="card p-4">
      <div className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">{label}</div>
      <div className="text-2xl font-bold text-slate-900 dark:text-white mt-1">{value}</div>
    </div>
  )
}

function titleFor(key: string) {
  const titles: Record<string, string> = {
    tic: 'Total Ion Current (TIC)',
    missing_pct: 'Missing Values per Sample',
    detected_features: 'Detected Features per Sample',
    log2_intensity: 'Sample Intensity Distribution',
    cv_by_group: 'Per-Feature CV by Group',
    pca: 'PCA Score Plot',
    correlation_heatmap: 'Sample Correlation Heatmap',
    qc_pool_drift: 'QC-Pool TIC Drift',
    qc_pool_correction: 'QC-Pool Correction (before vs after)',
  }
  return titles[key] || key
}
