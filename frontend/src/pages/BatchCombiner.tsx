import { useEffect, useMemo, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import { listAllDatasets, combineDatasets, listProjects } from '../api'
import { Dataset, Project } from '../types'
import { LuCombine, LuAlertCircle, LuCheckCircle2, LuFlaskConical, LuActivity, LuBarChart2 } from 'react-icons/lu'
import PlotWithDownload from '../components/PlotWithDownload'

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

interface BatchQCReport {
  before: QCData
  after: QCData
  batch_pca: { before?: any; after?: any }
  metrics: {
    batch_r2_pct: { before: number | null; after: number | null }
    group_r2_pct: { before: number | null; after: number | null }
    median_batch_cv_pct: { before: number | null; after: number | null }
  }
}

const METHODS: Record<string, { label: string; description: string; needsRef: boolean; needsControls: boolean; needsK: boolean }> = {
  reference_group: {
    label: 'Reference/control group scaling to 1',
    description: 'For each feature, divide all samples by the mean of the chosen control/reference group within its batch. The control group then has a mean of 1.',
    needsRef: true,
    needsControls: false,
    needsK: false,
  },
  log2fc_control: {
    label: 'Log2 fold-change vs control group',
    description: 'Convert each sample to log2(sample / control-group mean) within its batch. Results are fold-changes, making cross-batch comparisons valid.',
    needsRef: true,
    needsControls: false,
    needsK: false,
  },
  mean_centering: {
    label: 'Mean centering per batch',
    description: 'Scale each batch so its per-feature mean matches the global mean across all batches.',
    needsRef: false,
    needsControls: false,
    needsK: false,
  },
  median_centering: {
    label: 'Median centering per batch',
    description: 'Scale each batch so its per-feature median matches the global median across all batches. Robust to outliers.',
    needsRef: false,
    needsControls: false,
    needsK: false,
  },
  quantile_normalization: {
    label: 'Quantile normalization across samples',
    description: 'Force all samples to share the same intensity distribution after combining. Useful for strong global batch shifts.',
    needsRef: false,
    needsControls: false,
    needsK: false,
  },
  combat: {
    label: 'ComBat empirical Bayes',
    description: 'Parametric empirical Bayes framework that adjusts batch effects while preserving biological group differences.',
    needsRef: false,
    needsControls: false,
    needsK: false,
  },
  loess_signal_drift: {
    label: 'LOESS signal-drift correction',
    description: 'Fit a LOWESS smoother to each feature along the acquisition/run order within each batch and remove the drift trend. Column order within each batch is used as the run order unless a custom order is supplied.',
    needsRef: false,
    needsControls: false,
    needsK: false,
  },
  ruv_iii_c: {
    label: 'RUV-III-C',
    description: 'Remove Unwanted Variation III-C. Uses negative control features and sample groups to estimate and remove unwanted batch factors per feature.',
    needsRef: false,
    needsControls: true,
    needsK: true,
  },
}

const DEFAULT_LIMIT = 20

export default function BatchCombiner() {
  const { projectId, refreshDatasets } = useWorkspace()

  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProjectIds, setSelectedProjectIds] = useState<Set<number>>(new Set())

  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [datasetMap, setDatasetMap] = useState<Record<number, Dataset>>({})
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [limit, setLimit] = useState(DEFAULT_LIMIT)
  const [datasetsLoading, setDatasetsLoading] = useState(false)

  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [batchLabels, setBatchLabels] = useState<Record<number, string>>({})
  const [method, setMethod] = useState<string>('reference_group')
  const [referenceGroup, setReferenceGroup] = useState<string>('')
  const [perDatasetRef, setPerDatasetRef] = useState<Record<number, string>>({})
  const [outputName, setOutputName] = useState<string>('')
  const [controlFeatures, setControlFeatures] = useState<string[]>([])
  const [nUnwantedFactors, setNUnwantedFactors] = useState<number>(1)
  const [includeQCPlots, setIncludeQCPlots] = useState<boolean>(false)

  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [qcReport, setQcReport] = useState<BatchQCReport | null>(null)
  const [qcTab, setQcTab] = useState<'before' | 'after' | 'batch_pca' | 'metrics'>('before')

  useEffect(() => {
    setMessage('')
    setError('')
    setQcReport(null)
    setSelected(new Set())
    setBatchLabels({})
    setPerDatasetRef({})
    setControlFeatures([])
    setSelectedProjectIds(new Set())
    setPage(1)
    setDatasetMap({})
    setDatasets([])
    setTotal(0)

    if (!projectId) {
      setProjects([])
      return
    }
    listProjects()
      .then((res) => setProjects(res.data))
      .catch(() => setError('Failed to load projects'))
  }, [projectId])

  useEffect(() => {
    setMessage('')
    setError('')
    setControlFeatures([])
  }, [selected, method])

  useEffect(() => {
    if (!projectId) return
    setDatasetsLoading(true)
    listAllDatasets({
      project_ids: Array.from(selectedProjectIds),
      limit,
      offset: (page - 1) * limit,
    })
      .then((res) => {
        const items: Dataset[] = res.data.items || []
        const totalCount: number = res.data.total || 0
        setDatasets(items)
        setTotal(totalCount)
        setDatasetMap((prev) => {
          const next = { ...prev }
          for (const ds of items) {
            next[ds.id] = ds
          }
          return next
        })
      })
      .catch(() => setError('Failed to load datasets'))
      .finally(() => setDatasetsLoading(false))
  }, [projectId, selectedProjectIds, page, limit])

  const allGroups = useMemo(() => {
    const groups = new Set<string>()
    for (const id of selected) {
      const ds = datasetMap[id]
      if (ds?.sample_metadata) {
        Object.values(ds.sample_metadata as Record<string, string>).forEach((g) => groups.add(g))
      }
    }
    return Array.from(groups).sort()
  }, [datasetMap, selected])

  const allFeatureIds = useMemo(() => {
    const ids = new Set<string>()
    for (const id of selected) {
      const ds = datasetMap[id]
      if (ds?.feature_metadata) {
        for (const m of ds.feature_metadata) {
          if (m.feature_id) ids.add(String(m.feature_id))
        }
      }
    }
    return Array.from(ids).sort()
  }, [datasetMap, selected])

  const selectedDatasets = useMemo(() => {
    return Array.from(selected)
      .map((id) => datasetMap[id])
      .filter((d): d is Dataset => d !== undefined)
  }, [datasetMap, selected])

  const totalSamples = useMemo(() => {
    return selectedDatasets.reduce((sum, d) => sum + Object.keys(d.sample_metadata || {}).length, 0)
  }, [selectedDatasets])

  const datasetGroups = (ds: Dataset) => {
    return Array.from(new Set(Object.values(ds.sample_metadata || {}))).sort()
  }

  const toggleProject = (id: number) => {
    setSelectedProjectIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
    setPage(1)
  }

  const toggleDataset = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
        setPerDatasetRef((refs) => {
          const updated = { ...refs }
          delete updated[id]
          return updated
        })
      } else {
        next.add(id)
        const ds = datasetMap[id]
        if (ds) {
          const groups = datasetGroups(ds)
          const defaultRef = groups.includes(referenceGroup) ? referenceGroup : groups[0] || ''
          setPerDatasetRef((refs) => ({ ...refs, [id]: refs[id] || defaultRef }))
        }
      }
      return next
    })
  }

  const updateBatchLabel = (id: number, label: string) => {
    setBatchLabels((prev) => ({ ...prev, [id]: label }))
  }

  const updatePerDatasetRef = (id: number, group: string) => {
    setPerDatasetRef((prev) => ({ ...prev, [id]: group }))
  }

  const handleControlFeatureChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const opts = Array.from(e.target.selectedOptions).map((o) => o.value)
    setControlFeatures(opts)
  }

  const handleCombine = async () => {
    if (!projectId) return
    if (selected.size < 2) {
      setError('Select at least two datasets to combine.')
      return
    }
    if (METHODS[method].needsRef) {
      const missingRef = selectedDatasets.some((d) => {
        const dsGroups = datasetGroups(d)
        const ref = perDatasetRef[d.id] || referenceGroup
        return !ref || !dsGroups.includes(ref)
      })
      if (missingRef) {
        setError('Select a reference/control group for each selected dataset.')
        return
      }
    }
    if (METHODS[method].needsControls && controlFeatures.length === 0) {
      setError('Select at least one negative control feature for RUV-III-C.')
      return
    }
    setLoading(true)
    setError('')
    setMessage('')
    const datasetIds = Array.from(selected)
    const batchAssignment: Record<string, string> = {}
    datasetIds.forEach((id) => {
      batchAssignment[id] = batchLabels[id]?.trim() || `batch_${id}`
    })
    const payload: any = {
      dataset_ids: datasetIds,
      method,
      batch_assignment: batchAssignment,
      output_name: outputName.trim() || undefined,
      include_qc_plots: includeQCPlots,
    }
    if (METHODS[method].needsRef) {
      const perDatasetMap: Record<string, string> = {}
      for (const d of selectedDatasets) {
        perDatasetMap[d.id] = perDatasetRef[d.id] || referenceGroup
      }
      payload.per_dataset_reference_group = perDatasetMap
      if (referenceGroup) {
        payload.reference_group = referenceGroup
      }
    }
    if (METHODS[method].needsControls) {
      payload.control_features = controlFeatures
      payload.n_unwanted_factors = nUnwantedFactors
    }
    try {
      const res = await combineDatasets(Number(projectId), payload)
      const ds = res.data.dataset || res.data
      setMessage(`Combined dataset "${ds.name}" created (ID ${ds.id}). You can now select it in the Visualize tab.`)
      if (includeQCPlots && res.data.qc_report) {
        setQcReport(res.data.qc_report)
        setQcTab('before')
      } else {
        setQcReport(null)
      }
      refreshDatasets()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to combine datasets')
    } finally {
      setLoading(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / limit))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Batch Combiner</h1>
        <p className="page-subtitle">
          Combine datasets from multiple LC-MS runs and correct batch effects before visualization.
        </p>
      </div>

      {!projectId && (
        <div className="card p-8 text-center text-slate-500 dark:text-slate-400">
          Select a project from the workspace to begin.
        </div>
      )}

      {projectId && (
        <>
          <div className="card p-5 space-y-4">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">1. Select projects</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Pick one or more projects to browse their datasets. Datasets from all selected projects can be combined.
            </p>
            {projects.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">No projects available.</p>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {projects.map((p) => (
                  <label
                    key={p.id}
                    className="flex items-center gap-2 p-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700"
                  >
                    <input
                      type="checkbox"
                      checked={selectedProjectIds.has(p.id)}
                      onChange={() => toggleProject(p.id)}
                      className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span className="text-sm text-slate-800 dark:text-slate-200 truncate" title={p.name}>
                      {p.name}
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>

          <div className="card p-5 space-y-4">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">2. Select datasets</h2>
              <div className="flex items-center gap-3">
                <label className="text-sm text-slate-600 dark:text-slate-300">Per page</label>
                <select
                  value={limit}
                  onChange={(e) => {
                    setLimit(Number(e.target.value))
                    setPage(1)
                  }}
                  className="select text-sm"
                >
                  {[10, 20, 50, 100].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {datasetsLoading ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">Loading datasets…</p>
            ) : datasets.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {selectedProjectIds.size === 0
                  ? 'Select at least one project above to browse its datasets.'
                  : 'No datasets found in the selected projects.'}
              </p>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 dark:border-slate-700 text-left">
                        <th className="py-2 pr-4">Include</th>
                        <th className="py-2 pr-4">Dataset</th>
                        <th className="py-2 pr-4">Project</th>
                        <th className="py-2 pr-4">Type</th>
                        <th className="py-2 pr-4">Samples</th>
                        <th className="py-2 pr-4">Groups</th>
                        {METHODS[method].needsRef && <th className="py-2 pr-4">Reference group</th>}
                        <th className="py-2">Batch label</th>
                      </tr>
                    </thead>
                    <tbody>
                      {datasets.map((ds) => {
                        const groups = Array.from(new Set(Object.values(ds.sample_metadata || {}))).join(', ')
                        const dsGroups = datasetGroups(ds)
                        return (
                          <tr key={ds.id} className="border-b border-slate-100 dark:border-slate-800">
                            <td className="py-3 pr-4">
                              <input
                                type="checkbox"
                                checked={selected.has(ds.id)}
                                onChange={() => toggleDataset(ds.id)}
                                className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                              />
                            </td>
                            <td className="py-3 pr-4 font-medium text-slate-900 dark:text-slate-100">{ds.name}</td>
                            <td className="py-3 pr-4 text-slate-600 dark:text-slate-300">{ds.project_name || '-'}</td>
                            <td className="py-3 pr-4 text-slate-600 dark:text-slate-300">{ds.feature_type}</td>
                            <td className="py-3 pr-4 text-slate-600 dark:text-slate-300">
                              {Object.keys(ds.sample_metadata || {}).length}
                            </td>
                            <td className="py-3 pr-4 text-slate-600 dark:text-slate-300 max-w-xs truncate" title={groups}>
                              {groups}
                            </td>
                            {METHODS[method].needsRef && (
                              <td className="py-3 pr-4">
                                <select
                                  value={perDatasetRef[ds.id] || ''}
                                  onChange={(e) => updatePerDatasetRef(ds.id, e.target.value)}
                                  disabled={!selected.has(ds.id) || dsGroups.length === 0}
                                  className="select disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                  {dsGroups.length === 0 && <option value="">No groups</option>}
                                  {dsGroups.map((g) => (
                                    <option key={g} value={g}>
                                      {g}
                                    </option>
                                  ))}
                                </select>
                              </td>
                            )}
                            <td className="py-3">
                              <input
                                type="text"
                                value={batchLabels[ds.id] || `batch_${ds.id}`}
                                onChange={(e) => updateBatchLabel(ds.id, e.target.value)}
                                disabled={!selected.has(ds.id)}
                                className="input disabled:opacity-50 disabled:cursor-not-allowed"
                                placeholder="Batch label"
                              />
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                {totalPages > 1 && (
                  <div className="flex items-center justify-between pt-2">
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                      Page {page} of {totalPages} ({total} dataset{total === 1 ? '' : 's'})
                    </p>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page === 1}
                        className="px-3 py-1.5 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 disabled:opacity-50 hover:bg-slate-50 dark:hover:bg-slate-700"
                      >
                        Previous
                      </button>
                      <button
                        onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                        disabled={page === totalPages}
                        className="px-3 py-1.5 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 disabled:opacity-50 hover:bg-slate-50 dark:hover:bg-slate-700"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}

            {selectedDatasets.length > 0 && (
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {selectedDatasets.length} dataset(s) selected, {totalSamples} sample(s) total.
              </p>
            )}
          </div>

          <div className="card p-5 space-y-4">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">3. Batch-correction method</h2>
            <div>
              <label className="label-like">Normalization method</label>
              <select
                className="select"
                value={method}
                onChange={(e) => setMethod(e.target.value)}
              >
                {Object.entries(METHODS).map(([key, info]) => (
                  <option key={key} value={key}>
                    {info.label}
                  </option>
                ))}
              </select>
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{METHODS[method].description}</p>
            </div>

            {METHODS[method].needsRef && (
              <div>
                <label className="label-like">Default reference / control group (optional)</label>
                <select
                  className="select"
                  value={referenceGroup}
                  onChange={(e) => setReferenceGroup(e.target.value)}
                  disabled={allGroups.length === 0}
                >
                  <option value="">Use per-dataset reference groups</option>
                  {allGroups.length === 0 && <option value="">No groups available</option>}
                  {allGroups.map((g) => (
                    <option key={g} value={g}>
                      {g}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  Choose a group for each dataset in the table, or set a default here to apply to datasets without their own selection.
                </p>
              </div>
            )}

            {METHODS[method].needsControls && (
              <>
                <div>
                  <label className="label-like">Negative control features</label>
                  <select
                    multiple
                    size={Math.min(8, Math.max(3, allFeatureIds.length))}
                    value={controlFeatures}
                    onChange={handleControlFeatureChange}
                    disabled={allFeatureIds.length === 0}
                    className="select"
                  >
                    {allFeatureIds.length === 0 && <option value="">No features available</option>}
                    {allFeatureIds.map((fid) => (
                      <option key={fid} value={fid}>
                        {fid}
                      </option>
                    ))}
                  </select>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    Hold Ctrl/Cmd to select multiple features expected to be constant across samples (e.g., internal standards).
                  </p>
                </div>
                <div>
                  <label className="label-like">Number of unwanted factors (k)</label>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={nUnwantedFactors}
                    onChange={(e) => setNUnwantedFactors(parseInt(e.target.value, 10) || 1)}
                    className="input"
                  />
                </div>
              </>
            )}

            <div>
              <label className="label-like">Output dataset name (optional)</label>
              <input
                type="text"
                className="input"
                value={outputName}
                onChange={(e) => setOutputName(e.target.value)}
                placeholder={`combined_${method}`}
              />
            </div>

            <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={includeQCPlots}
                onChange={(e) => setIncludeQCPlots(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
              Generate before/after QC plots and metrics (optional)
            </label>
          </div>

          {error && (
            <div className="rounded-lg bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-700 dark:text-red-300 flex items-start gap-2">
              <LuAlertCircle className="mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {message && (
            <div className="rounded-lg bg-emerald-50 dark:bg-emerald-900/20 p-4 text-sm text-emerald-700 dark:text-emerald-300 flex items-start gap-2">
              <LuCheckCircle2 className="mt-0.5 flex-shrink-0" />
              <span>{message}</span>
            </div>
          )}

          <button
            onClick={handleCombine}
            disabled={loading || selected.size < 2}
            className="btn-primary"
          >
            {loading ? (
              <>
                <LuFlaskConical className="animate-spin" /> Combining…
              </>
            ) : (
              <>
                <LuCombine /> Combine datasets
              </>
            )}
          </button>

          {qcReport && (
            <div className="card p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2"><LuBarChart2 /> Batch Correction QC Report</h2>
                <div className="flex gap-2">
                  {(['before', 'after', 'batch_pca', 'metrics'] as const).map((t) => (
                    <button
                      key={t}
                      onClick={() => setQcTab(t)}
                      className={`px-3 py-1.5 text-sm rounded-lg border ${qcTab === t ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700'}`}
                    >
                      {t === 'batch_pca' ? 'Batch PCA' : t[0].toUpperCase() + t.slice(1)}
                    </button>
                  ))}
                </div>
              </div>

              {qcTab === 'metrics' && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <MetricCard label="Batch R² (%)" before={qcReport.metrics.batch_r2_pct.before} after={qcReport.metrics.batch_r2_pct.after} />
                  <MetricCard label="Group R² (%)" before={qcReport.metrics.group_r2_pct.before} after={qcReport.metrics.group_r2_pct.after} />
                  <MetricCard label="Median batch CV (%)" before={qcReport.metrics.median_batch_cv_pct.before} after={qcReport.metrics.median_batch_cv_pct.after} />
                </div>
              )}

              {(qcTab === 'before' || qcTab === 'after') && (
                <div className="space-y-6">
                  {(() => {
                    const data = qcReport[qcTab]
                    return (
                      <>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                          <SmallMetric label="Features" value={data.metrics.num_features} />
                          <SmallMetric label="Samples" value={data.metrics.num_samples} />
                          <SmallMetric label="Groups" value={data.metrics.num_groups} />
                          <SmallMetric label="Missing" value={`${data.metrics.total_missing_pct}%`} />
                        </div>
                        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                          {Object.entries(data.figures).map(([key, fig]) => (
                            <div key={key} className="card p-4 bg-white dark:bg-slate-800">
                              <h3 className="font-semibold text-slate-900 dark:text-white mb-3 flex items-center gap-2"><LuActivity /> {titleFor(key)}</h3>
                              <PlotWithDownload data={fig.data} layout={fig.layout} style={{ width: '100%', height: '450px' }} filename={`batch_qc_${qcTab}_${key}`} />
                            </div>
                          ))}
                        </div>
                      </>
                    )
                  })()}
                </div>
              )}

              {qcTab === 'batch_pca' && (
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                  {qcReport.batch_pca.before && (
                    <div className="card p-4 bg-white dark:bg-slate-800">
                      <h3 className="font-semibold text-slate-900 dark:text-white mb-3">Before correction (colored by batch)</h3>
                      <PlotWithDownload data={qcReport.batch_pca.before.data} layout={qcReport.batch_pca.before.layout} style={{ width: '100%', height: '450px' }} filename="batch_pca_before" />
                    </div>
                  )}
                  {qcReport.batch_pca.after && (
                    <div className="card p-4 bg-white dark:bg-slate-800">
                      <h3 className="font-semibold text-slate-900 dark:text-white mb-3">After correction (colored by batch)</h3>
                      <PlotWithDownload data={qcReport.batch_pca.after.data} layout={qcReport.batch_pca.after.layout} style={{ width: '100%', height: '450px' }} filename="batch_pca_after" />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      )}
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

function MetricCard({ label, before, after }: { label: string; before: number | null; after: number | null }) {
  return (
    <div className="card p-4">
      <div className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">{label}</div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">Before</div>
          <div className="text-xl font-bold text-slate-900 dark:text-white">{before !== null ? before : '—'}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">After</div>
          <div className="text-xl font-bold text-slate-900 dark:text-white">{after !== null ? after : '—'}</div>
        </div>
      </div>
    </div>
  )
}

function SmallMetric({ label, value }: { label: string; value: any }) {
  return (
    <div className="card p-3">
      <div className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">{label}</div>
      <div className="text-xl font-bold text-slate-900 dark:text-white mt-1">{value}</div>
    </div>
  )
}
