import { useEffect, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import PlotWithDownload from '../components/PlotWithDownload'
import { getQC, exportQCExcel } from '../api'
import { LuActivity, LuRefreshCw, LuDownload } from 'react-icons/lu'

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

export default function QC() {
  const { projectId, datasetId, selectedDataset } = useWorkspace()
  const [data, setData] = useState<QCData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleExportExcel = async () => {
    if (!projectId || !datasetId || !selectedDataset) return
    try {
      const res = await exportQCExcel(Number(projectId), Number(datasetId))
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

  const load = async () => {
    if (!projectId || !datasetId) return
    setLoading(true)
    setError('')
    try {
      const res = await getQC(Number(projectId), Number(datasetId))
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
            <button onClick={load} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Run QC</button>
            <button onClick={handleExportExcel} disabled={!selectedDataset} className="btn-secondary"><LuDownload /> Export Excel Summary</button>
            {error && <span className="text-sm text-red-600 dark:text-red-400">{error}</span>}
          </div>

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
                    <PlotWithDownload data={fig.data} layout={fig.layout} style={{ width: '100%', height: '450px' }} filename={`qc_${key}`} />
                  </div>
                ))}
              </div>
            </>
          )}
        </>
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
  }
  return titles[key] || key
}
