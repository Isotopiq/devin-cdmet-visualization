import { useEffect, useMemo, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import { preprocess, uploadFile, exportDataset } from '../api'
import { LuSlidersHorizontal, LuPlay, LuHistory, LuAlertCircle, LuCheckCircle2, LuPlus, LuTrash2, LuDownload, LuUpload, LuX, LuSearch } from 'react-icons/lu'

const DEFAULT_ISOBARIC_RULE = {
  name: 'O-/P- ether/vinyl-ether',
  applicable_classes: 'PC,PE,PI,PS,PA,PG,DG,TG',
  prefix_a: 'O-',
  prefix_b: 'P-',
  db_offset: 1,
  carbon_count_match: true,
}

export default function Preprocessing() {
  const { projectId, datasetId, selectedDataset, refreshDatasets } = useWorkspace()
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [processedDataset, setProcessedDataset] = useState<any | null>(null)
  const [blankModalOpen, setBlankModalOpen] = useState(false)
  const [blankModalSearch, setBlankModalSearch] = useState('')
  const [blankModalPage, setBlankModalPage] = useState(1)
  const [blankModalSelected, setBlankModalSelected] = useState<string[]>([])
  const blankModalPageSize = 10
  const [params, setParams] = useState({
    missing_value_filter: 0.2,
    log_transform: true,
    scale: 'none',
    normalization: 'total_area',
    imputation: 'min',
    qc_cv_filter: 0,
    blank_subtraction: false,
    blank_columns: [] as string[],
    exclude_blanks_from_imputation: false,
    enable_isobaric_substitution_check: true,
    isobaric_substitution_mode: 'flag_ambiguous',
    isobaric_substitution_rules: [DEFAULT_ISOBARIC_RULE],
    isobaric_clustering_enabled: true,
    isobaric_mz_tolerance: 0.005,
    isobaric_rt_tolerance: 0.2,
    isobaric_rollup_preference: 'alphabetical',
    output_name: '',
    custom_factor: '',
    normalization_file_id: null as number | null,
    normalization_column: 'Value',
    normalization_file_name: '',
    rename_samples: false,
    qc_pool_drift_correction: false,
    qc_pool_group: '',
    qc_pool_method: 'loess_tic',
    qc_pool_space: 'log',
    qc_pool_span: 0.75,
    qc_pool_target: 'median',
    qc_pool_extrapolate: 'last',
    qc_pool_run_order_file_id: null as number | null,
    qc_pool_run_order_file_name: '',
  })

  useEffect(() => {
    if (selectedDataset && !params.output_name) {
      setParams((prev: any) => ({ ...prev, output_name: `${selectedDataset.name}_processed` }))
    }
  }, [selectedDataset])

  useEffect(() => {
    if (!params.blank_subtraction && !params.exclude_blanks_from_imputation && blankModalOpen) {
      setBlankModalOpen(false)
    }
  }, [params.blank_subtraction, params.exclude_blanks_from_imputation, blankModalOpen])

  const sampleMeta = selectedDataset?.sample_metadata || {}
  const blankSamples = useMemo(() => {
    return Object.entries(sampleMeta)
      .filter((entry) => /blank|solvent|ntc|negative.?control|no.?template/i.test(String(entry[1])))
      .map((entry) => entry[0])
  }, [sampleMeta])

  const uniqueGroups = useMemo(() => {
    const set = new Set<string>()
    Object.values(sampleMeta).forEach((g) => set.add(String(g || 'unknown')))
    return Array.from(set)
  }, [sampleMeta])

  const qcPoolGroups = useMemo(() => {
    const poolPattern = /qc[-_\s]*pool|pool[-_\s]*qc|pooled[-_\s]*qc|quality[-_\s]*control[-_\s]*pool/i
    const fallback = /\bqc\b|quality[-_\s]*control|pooled/i
    const groups = uniqueGroups.filter((g) => poolPattern.test(g) || fallback.test(g))
    return groups
  }, [uniqueGroups])

  useEffect(() => {
    if (selectedDataset && qcPoolGroups.length > 0 && !params.qc_pool_group) {
      setParams((prev: any) => ({ ...prev, qc_pool_group: qcPoolGroups[0] }))
    }
  }, [selectedDataset, qcPoolGroups])

  const openBlankModal = () => {
    setBlankModalSelected(params.blank_columns)
    setBlankModalSearch('')
    setBlankModalPage(1)
    setBlankModalOpen(true)
  }

  const applyBlankModal = () => {
    setParams((prev: any) => ({ ...prev, blank_columns: blankModalSelected }))
    setBlankModalOpen(false)
  }

  const toggleBlankSample = (name: string) => {
    setBlankModalSelected((prev: string[]) =>
      prev.includes(name) ? prev.filter((s) => s !== name) : [...prev, name]
    )
  }

  const selectBlankPage = () => {
    const pageNames = blankModalPageItems.map((s) => s.name)
    setBlankModalSelected((prev: string[]) => Array.from(new Set([...prev, ...pageNames])))
  }

  const deselectBlankPage = () => {
    const pageNames = new Set(blankModalPageItems.map((s) => s.name))
    setBlankModalSelected((prev: string[]) => prev.filter((s) => !pageNames.has(s)))
  }

  const autoDetectBlanks = () => setBlankModalSelected(blankSamples)

  const clearBlankSelection = () => setBlankModalSelected([])

  const blankModalSamples = useMemo(() => {
    return Object.entries(sampleMeta)
      .map(([name, group]) => ({ name, group: String(group || 'unknown') }))
      .filter((s) => {
        const q = blankModalSearch.toLowerCase()
        return q === '' || s.name.toLowerCase().includes(q) || s.group.toLowerCase().includes(q)
      })
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [sampleMeta, blankModalSearch])

  const blankModalTotalPages = Math.max(1, Math.ceil(blankModalSamples.length / blankModalPageSize))
  const blankModalPageItems = blankModalSamples.slice(
    (blankModalPage - 1) * blankModalPageSize,
    blankModalPage * blankModalPageSize
  )

  useEffect(() => {
    if (blankModalPage > blankModalTotalPages) {
      setBlankModalPage(blankModalTotalPages)
    }
  }, [blankModalPage, blankModalTotalPages])

  const isLipid = selectedDataset?.feature_type === 'lipid'

  const run = async () => {
    if (!projectId || !datasetId) return
    setLoading(true)
    setMessage('')
    setError('')
    try {
      setProcessedDataset(null)
      const rules = params.isobaric_substitution_rules.map((r: any) => ({
        name: r.name,
        applicable_classes: r.applicable_classes.split(',').map((s: string) => s.trim()).filter(Boolean),
        prefix_pair: [r.prefix_a, r.prefix_b],
        db_offset: Number(r.db_offset),
        carbon_count_match: r.carbon_count_match,
      }))
      const body = {
        missing_value_filter: params.missing_value_filter,
        log_transform: params.log_transform,
        scale: params.scale,
        normalization: params.normalization,
        imputation: params.imputation,
        blank_subtraction: params.blank_subtraction,
        blank_columns: params.blank_columns,
        exclude_blanks_from_imputation: params.exclude_blanks_from_imputation,
        qc_cv_filter: params.qc_cv_filter,
        qc_columns: [],
        duplicate_handling: 'mean',
        batch_correction: 'none',
        batch_column: null,
        custom_factor: params.normalization === 'custom_factor' && params.custom_factor ? Number(params.custom_factor) : null,
        normalization_file_id: params.normalization_file_id,
        normalization_column: params.normalization_column,
        enable_isobaric_substitution_check: isLipid ? params.enable_isobaric_substitution_check : false,
        isobaric_substitution_mode: params.isobaric_substitution_mode,
        isobaric_substitution_rules: rules,
        isobaric_clustering_enabled: params.isobaric_clustering_enabled,
        isobaric_mz_tolerance: params.isobaric_mz_tolerance,
        isobaric_rt_tolerance: params.isobaric_rt_tolerance,
        isobaric_rollup_preference: params.isobaric_rollup_preference,
        output_name: params.output_name || undefined,
        rename_samples: params.rename_samples,
        qc_pool_drift_correction: params.qc_pool_drift_correction,
        qc_pool_group: params.qc_pool_drift_correction ? params.qc_pool_group : null,
        qc_pool_method: params.qc_pool_drift_correction ? params.qc_pool_method : 'loess_tic',
        qc_pool_space: params.qc_pool_drift_correction ? params.qc_pool_space : 'log',
        qc_pool_span: params.qc_pool_drift_correction ? params.qc_pool_span : 0.75,
        qc_pool_target: params.qc_pool_drift_correction ? params.qc_pool_target : 'median',
        qc_pool_extrapolate: params.qc_pool_drift_correction ? params.qc_pool_extrapolate : 'last',
        qc_pool_run_order_file_id: params.qc_pool_drift_correction ? params.qc_pool_run_order_file_id : null,
      }
      const res = await preprocess(Number(projectId), Number(datasetId), body)
      setProcessedDataset(res.data)
      setMessage(`Preprocessing applied. New dataset "${res.data.name}" created.`)
      refreshDatasets()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Preprocessing failed')
    } finally {
      setLoading(false)
    }
  }

  const exportProcessed = async (format: 'metaboanalyst' | 'lipidone') => {
    if (!projectId || !processedDataset?.id) return
    try {
      const res = await exportDataset(Number(projectId), Number(processedDataset.id), format)
      const blob = new Blob([res.data], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${processedDataset.name}_${format}.csv`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err: any) {
      alert(err.response?.data?.detail || `Failed to export ${format}`)
    }
  }

  const updateRule = (idx: number, field: string, value: any) => {
    setParams((prev: any) => {
      const rules = [...prev.isobaric_substitution_rules]
      rules[idx] = { ...rules[idx], [field]: value }
      return { ...prev, isobaric_substitution_rules: rules }
    })
  }

  const addRule = () => {
    setParams((prev: any) => ({
      ...prev,
      isobaric_substitution_rules: [...prev.isobaric_substitution_rules, { ...DEFAULT_ISOBARIC_RULE }],
    }))
  }

  const removeRule = (idx: number) => {
    setParams((prev: any) => ({
      ...prev,
      isobaric_substitution_rules: prev.isobaric_substitution_rules.filter((_: any, i: number) => i !== idx),
    }))
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Preprocessing</h1>
        <p className="page-subtitle">Filter, impute, transform, scale, and normalize your data.</p>
      </div>

      <DatasetPicker />

      {!selectedDataset && <div className="card p-8 text-center text-slate-500 dark:text-slate-400">Select a dataset to configure preprocessing.</div>}

      {selectedDataset && (
        <>
          <div className="card p-5">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2"><LuSlidersHorizontal /> Pipeline Steps</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Missing value filter</label>
                <input type="number" step="0.05" min={0} max={1} value={params.missing_value_filter} onChange={(e) => setParams({ ...params, missing_value_filter: Number(e.target.value) })} className="input" />
                <p className="text-xs text-slate-500 mt-1">Max fraction of missing values per feature.</p>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Imputation</label>
                <select value={params.imputation} onChange={(e) => setParams({ ...params, imputation: e.target.value })} className="input">
                  <option value="none">None</option>
                  <option value="min">Half minimum</option>
                  <option value="median">Median</option>
                  <option value="knn">Mean (KNN fallback)</option>
                </select>
                <p className="text-xs text-slate-500 mt-1">No imputation keeps missing values as missing.</p>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Scaling</label>
                <select value={params.scale} onChange={(e) => setParams({ ...params, scale: e.target.value })} className="input">
                  <option value="none">None</option>
                  <option value="standard">Unit variance (auto-scaling)</option>
                  <option value="robust">Robust scaling</option>
                  <option value="minmax">Range (0-1)</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Normalization</label>
                <select value={params.normalization} onChange={(e) => setParams({ ...params, normalization: e.target.value })} className="input">
                  <option value="none">None</option>
                  <option value="total_area">Total area</option>
                  <option value="internal_standard">Internal standard</option>
                  <option value="protein">Protein</option>
                  <option value="dna">DNA</option>
                  <option value="cell_number">Cell number</option>
                  <option value="tissue_weight">Tissue weight</option>
                  <option value="custom_factor">Custom factor</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">QC CV filter</label>
                <input type="number" step="0.05" min={0} value={params.qc_cv_filter} onChange={(e) => setParams({ ...params, qc_cv_filter: Number(e.target.value) })} className="input" />
                <p className="text-xs text-slate-500 mt-1">Disabled when 0.</p>
              </div>
              <div className="flex items-center gap-2 pb-2">
                <input type="checkbox" id="log" checked={params.log_transform} onChange={(e) => setParams({ ...params, log_transform: e.target.checked })} className="rounded border-slate-300" />
                <label htmlFor="log" className="text-sm text-slate-700 dark:text-slate-200">Log2 transform</label>
              </div>
              <div className="flex items-center gap-2 pb-2">
                <input type="checkbox" id="rename-samples" checked={params.rename_samples} onChange={(e) => setParams({ ...params, rename_samples: e.target.checked })} className="rounded border-slate-300" />
                <label htmlFor="rename-samples" className="text-sm text-slate-700 dark:text-slate-200">Rename samples to group_R#</label>
              </div>
              <div className="md:col-span-3 flex flex-col gap-2">
                <div className="flex flex-wrap items-center gap-4">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="blank-subtraction"
                      checked={params.blank_subtraction}
                      onChange={(e) => {
                        const enabled = e.target.checked
                        const showSelector = enabled || params.exclude_blanks_from_imputation
                        setParams({
                          ...params,
                          blank_subtraction: enabled,
                          blank_columns: showSelector ? (params.blank_columns.length ? params.blank_columns : blankSamples) : [],
                        })
                      }}
                      className="rounded border-slate-300"
                    />
                    <label htmlFor="blank-subtraction" className="text-sm text-slate-700 dark:text-slate-200">Subtract blank samples</label>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="exclude-blanks-imputation"
                      checked={params.exclude_blanks_from_imputation}
                      onChange={(e) => {
                        const enabled = e.target.checked
                        const showSelector = params.blank_subtraction || enabled
                        setParams({
                          ...params,
                          exclude_blanks_from_imputation: enabled,
                          blank_columns: showSelector ? (params.blank_columns.length ? params.blank_columns : blankSamples) : [],
                        })
                      }}
                      className="rounded border-slate-300"
                    />
                    <label htmlFor="exclude-blanks-imputation" className="text-sm text-slate-700 dark:text-slate-200">Exclude blanks from imputation</label>
                  </div>
                </div>
                {(params.blank_subtraction || params.exclude_blanks_from_imputation) && (
                  <div className="flex flex-wrap items-center gap-3">
                    <button type="button" onClick={openBlankModal} className="btn-secondary text-sm">Select blank samples</button>
                    <span className="text-xs text-slate-500 dark:text-slate-400">{params.blank_columns.length} selected. Auto-detected blank groups are pre-selected.</span>
                  </div>
                )}
              </div>

              <div className="md:col-span-3 flex flex-col gap-3 border-t border-slate-200 dark:border-slate-700 pt-4">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="qc-drift"
                    checked={params.qc_pool_drift_correction}
                    onChange={(e) => setParams({ ...params, qc_pool_drift_correction: e.target.checked })}
                    className="rounded border-slate-300"
                  />
                  <label htmlFor="qc-drift" className="text-sm font-medium text-slate-700 dark:text-slate-200">QC-Pool drift correction</label>
                </div>
                {params.qc_pool_drift_correction && (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="md:col-span-3">
                      <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">QC-Pool group</label>
                      <select
                        value={params.qc_pool_group}
                        onChange={(e) => setParams({ ...params, qc_pool_group: e.target.value })}
                        className="input"
                      >
                        <option value="">Select a group...</option>
                        {uniqueGroups.map((g) => (
                          <option key={g} value={g}>{g}</option>
                        ))}
                      </select>
                      {qcPoolGroups.length > 0 && !params.qc_pool_group && (
                        <p className="text-xs text-amber-600 mt-1">Auto-detected candidate groups: {qcPoolGroups.join(', ')}</p>
                      )}
                    </div>
                    <div>
                      <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Method</label>
                      <select value={params.qc_pool_method} onChange={(e) => setParams({ ...params, qc_pool_method: e.target.value })} className="input">
                        <option value="median_tic">Median QC TIC</option>
                        <option value="linear_tic">Linear TIC</option>
                        <option value="loess_tic">LOWESS TIC</option>
                        <option value="spline_tic">Spline TIC</option>
                        <option value="median_per_feature">Median per feature</option>
                        <option value="linear_per_feature">Linear per feature</option>
                        <option value="loess_per_feature">LOWESS per feature</option>
                        <option value="spline_per_feature">Spline per feature</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Correction space</label>
                      <select value={params.qc_pool_space} onChange={(e) => setParams({ ...params, qc_pool_space: e.target.value })} className="input">
                        <option value="log">Log2 additive (recommended)</option>
                        <option value="raw">Raw multiplicative</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Span / smoothing</label>
                      <input type="number" step={0.05} min={0.1} max={1.0} value={params.qc_pool_span} onChange={(e) => setParams({ ...params, qc_pool_span: Number(e.target.value) })} className="input" />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Reference target</label>
                      <select value={params.qc_pool_target} onChange={(e) => setParams({ ...params, qc_pool_target: e.target.value })} className="input">
                        <option value="median">Median QC</option>
                        <option value="mean">Mean QC</option>
                        <option value="first">First QC</option>
                        <option value="last">Last QC</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Extrapolation</label>
                      <select value={params.qc_pool_extrapolate} onChange={(e) => setParams({ ...params, qc_pool_extrapolate: e.target.value })} className="input">
                        <option value="last">Nearest QC</option>
                        <option value="linear">Linear</option>
                        <option value="none">No correction</option>
                      </select>
                    </div>
                    <div className="md:col-span-3 flex flex-wrap items-end gap-3">
                      <button
                        onClick={() => {
                          const cols = Object.keys(selectedDataset?.sample_metadata || {})
                          const header = 'Sample,Order'
                          const rows = cols.map((s, i) => `"${s.replace(/"/g, '""')}",${i + 1}`)
                          const csv = [header, ...rows].join('\n')
                          const blob = new Blob([csv], { type: 'text/csv' })
                          const url = window.URL.createObjectURL(blob)
                          const a = document.createElement('a')
                          a.href = url
                          a.download = 'run_order_template.csv'
                          document.body.appendChild(a)
                          a.click()
                          a.remove()
                          window.URL.revokeObjectURL(url)
                        }}
                        className="btn-secondary text-sm"
                      >
                        <LuDownload /> Download run-order template
                      </button>
                      <label className="btn-secondary text-sm cursor-pointer inline-flex items-center gap-1">
                        <LuUpload /> {params.qc_pool_run_order_file_name || 'Upload run-order file'}
                        <input
                          type="file"
                          accept=".csv,.xlsx,.xls,.txt"
                          className="hidden"
                          onChange={async (e) => {
                            const file = e.target.files?.[0]
                            if (!file || !projectId) return
                            setLoading(true)
                            try {
                              const res = await uploadFile(Number(projectId), file)
                              setParams((prev: any) => ({ ...prev, qc_pool_run_order_file_id: res.data.id, qc_pool_run_order_file_name: file.name }))
                            } catch (err: any) {
                              setError(err.response?.data?.detail || 'Upload failed')
                            } finally {
                              setLoading(false)
                            }
                          }}
                        />
                      </label>
                      {params.qc_pool_run_order_file_name && <p className="text-xs text-slate-500">Uploaded: {params.qc_pool_run_order_file_name}</p>}
                    </div>
                    <p className="md:col-span-3 text-xs text-slate-500">If no run-order file is uploaded, the column order in the dataset is used. Use a Sample and Order column.</p>
                  </div>
                )}
              </div>

              {['internal_standard', 'protein', 'dna', 'cell_number', 'tissue_weight'].includes(params.normalization) && (
                <div className="md:col-span-3 flex flex-col gap-2">
                  <div className="flex flex-wrap items-end gap-3">
                    <div>
                      <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Value column name</label>
                      <input type="text" value={params.normalization_column} onChange={(e) => setParams({ ...params, normalization_column: e.target.value })} className="input" placeholder="Value" />
                    </div>
                    <button
                      onClick={() => {
                        const cols = Object.keys(selectedDataset?.sample_metadata || {})
                        const header = `Sample,${params.normalization_column}`
                        const rows = cols.map((s) => `"${s.replace(/"/g, '""')}",`)
                        const csv = [header, ...rows].join('\n')
                        const blob = new Blob([csv], { type: 'text/csv' })
                        const url = window.URL.createObjectURL(blob)
                        const a = document.createElement('a')
                        a.href = url
                        a.download = 'normalization_template.csv'
                        document.body.appendChild(a)
                        a.click()
                        a.remove()
                        window.URL.revokeObjectURL(url)
                      }}
                      className="btn-secondary text-sm"
                    >
                      <LuDownload /> Download template
                    </button>
                    <label className="btn-secondary text-sm cursor-pointer inline-flex items-center gap-1">
                      <LuUpload /> {params.normalization_file_name || 'Upload metadata'}
                      <input
                        type="file"
                        accept=".csv,.xlsx,.xls,.txt"
                        className="hidden"
                        onChange={async (e) => {
                          const file = e.target.files?.[0]
                          if (!file || !projectId) return
                          setLoading(true)
                          try {
                            const res = await uploadFile(Number(projectId), file)
                            setParams((prev: any) => ({ ...prev, normalization_file_id: res.data.id, normalization_file_name: file.name }))
                          } catch (err: any) {
                            setError(err.response?.data?.detail || 'Upload failed')
                          } finally {
                            setLoading(false)
                          }
                        }}
                      />
                    </label>
                  </div>
                  {params.normalization_file_name && <p className="text-xs text-slate-500">Uploaded: {params.normalization_file_name}</p>}
                  <p className="text-xs text-slate-500">Upload a CSV or Excel file with a Sample column and a {params.normalization_column} column containing per-sample values.</p>
                </div>
              )}
              {params.normalization === 'custom_factor' && (
                <div>
                  <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Custom factor</label>
                  <input type="number" step="any" value={params.custom_factor} onChange={(e) => setParams({ ...params, custom_factor: e.target.value })} className="input" placeholder="e.g. 1000" />
                </div>
              )}
            </div>
            <div className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
              <div className="md:col-span-2">
                <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Processed dataset name</label>
                <input type="text" value={params.output_name} onChange={(e) => setParams({ ...params, output_name: e.target.value })} className="input" placeholder="e.g., mydataset_processed" />
              </div>
              <div>
                <button onClick={run} disabled={loading} className="btn-primary w-full"><LuPlay /> {loading ? 'Running...' : 'Apply Pipeline'}</button>
              </div>
            </div>
            {message && <div className="mt-4 p-3 rounded-lg bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200 flex items-center gap-2 text-sm"><LuCheckCircle2 /> {message}</div>}
            {error && <div className="mt-4 p-3 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-200 flex items-center gap-2 text-sm"><LuAlertCircle /> {error}</div>}
          </div>

          {processedDataset && (
            <div className="card p-5">
              <h3 className="font-semibold text-slate-900 dark:text-white mb-2 flex items-center gap-2"><LuDownload /> Export processed dataset</h3>
              <p className="text-sm text-slate-600 dark:text-slate-300 mb-4">
                <span className="font-medium">{processedDataset.name}</span> is ready. Download in the format you need for downstream analysis.
              </p>
              <div className="flex flex-wrap gap-3">
                <button onClick={() => exportProcessed('metaboanalyst')} className="btn-secondary"><LuDownload /> MetaboAnalyst CSV</button>
                <button onClick={() => exportProcessed('lipidone')} className="btn-secondary"><LuDownload /> LipidOne CSV</button>
              </div>
            </div>
          )}

          {isLipid && (
            <div className="card p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-slate-900 dark:text-white">Isobaric Substitution (lipidomics)</h3>
                <div className="flex items-center gap-2">
                  <input id="iso-enable" type="checkbox" checked={params.enable_isobaric_substitution_check} onChange={(e) => setParams({ ...params, enable_isobaric_substitution_check: e.target.checked })} className="rounded border-slate-300" />
                  <label htmlFor="iso-enable" className="text-sm text-slate-700 dark:text-slate-200">Enable</label>
                </div>
              </div>
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
                Detect pairs such as plasmanyl (O-) and plasmenyl (P-) ether lipids that are chemically distinct but share the same formula, m/z, and RT. These ambiguities cannot be resolved by MS1 data alone.
              </p>

              {params.enable_isobaric_substitution_check && (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Resolution mode</label>
                      <select value={params.isobaric_substitution_mode} onChange={(e) => setParams({ ...params, isobaric_substitution_mode: e.target.value })} className="input">
                        <option value="flag_ambiguous">Flag ambiguous</option>
                        <option value="report_combined">Report combined</option>
                        <option value="flag_and_combine">Flag ambiguous and report combined</option>
                        <option value="keep_separate_with_flag">Keep separate, one for rollups</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Roll-up preference</label>
                      <select value={params.isobaric_rollup_preference} onChange={(e) => setParams({ ...params, isobaric_rollup_preference: e.target.value })} className="input">
                        <option value="alphabetical">Alphabetical</option>
                        <option value="highest_mscore">Highest mScore/ID score</option>
                      </select>
                    </div>
                    <div className="flex items-center gap-2 pb-2">
                      <input id="iso-cluster" type="checkbox" checked={params.isobaric_clustering_enabled} onChange={(e) => setParams({ ...params, isobaric_clustering_enabled: e.target.checked })} className="rounded border-slate-300" />
                      <label htmlFor="iso-cluster" className="text-sm text-slate-700 dark:text-slate-200">m/z / RT clustering</label>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">m/z tolerance (Da)</label>
                      <input type="number" step="0.001" value={params.isobaric_mz_tolerance} onChange={(e) => setParams({ ...params, isobaric_mz_tolerance: Number(e.target.value) })} className="input" />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">RT tolerance (min)</label>
                      <input type="number" step="0.05" value={params.isobaric_rt_tolerance} onChange={(e) => setParams({ ...params, isobaric_rt_tolerance: Number(e.target.value) })} className="input" />
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <label className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Rules</label>
                      <button onClick={addRule} className="btn-secondary text-xs px-2 py-1"><LuPlus /> Add rule</button>
                    </div>
                    <div className="space-y-3">
                      {params.isobaric_substitution_rules.map((rule: any, idx: number) => (
                        <div key={idx} className="border border-slate-200 dark:border-slate-700 rounded-lg p-3 grid grid-cols-1 md:grid-cols-6 gap-3 items-end">
                          <div className="md:col-span-2">
                            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">Name</label>
                            <input type="text" value={rule.name} onChange={(e) => updateRule(idx, 'name', e.target.value)} className="input text-sm" />
                          </div>
                          <div className="md:col-span-2">
                            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">Applicable classes (comma-separated)</label>
                            <input type="text" value={rule.applicable_classes} onChange={(e) => updateRule(idx, 'applicable_classes', e.target.value)} className="input text-sm" />
                          </div>
                          <div>
                            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">Prefix A</label>
                            <input type="text" value={rule.prefix_a} onChange={(e) => updateRule(idx, 'prefix_a', e.target.value)} className="input text-sm" />
                          </div>
                          <div>
                            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">Prefix B</label>
                            <input type="text" value={rule.prefix_b} onChange={(e) => updateRule(idx, 'prefix_b', e.target.value)} className="input text-sm" />
                          </div>
                          <div>
                            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">DB offset</label>
                            <input type="number" value={rule.db_offset} onChange={(e) => updateRule(idx, 'db_offset', Number(e.target.value))} className="input text-sm" />
                          </div>
                          <div className="flex items-center gap-2 pb-2">
                            <input id={`iso-carbon-${idx}`} type="checkbox" checked={rule.carbon_count_match} onChange={(e) => updateRule(idx, 'carbon_count_match', e.target.checked)} className="rounded border-slate-300" />
                            <label htmlFor={`iso-carbon-${idx}`} className="text-xs text-slate-700 dark:text-slate-200">Carbon count must match</label>
                          </div>
                          <div className="md:col-span-6 flex justify-end">
                            <button onClick={() => removeRule(idx)} className="text-red-600 dark:text-red-400 text-xs flex items-center gap-1 hover:underline"><LuTrash2 /> Remove</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="bg-slate-50 dark:bg-slate-800/50 rounded p-3 text-xs text-slate-600 dark:text-slate-300">
                    <span className="font-semibold">Active config: </span>
                    {params.isobaric_substitution_mode} mode,{' '}
                    {params.isobaric_clustering_enabled ? `clustering on (mz ±${params.isobaric_mz_tolerance}, rt ±${params.isobaric_rt_tolerance}),` : 'clustering off,'}{' '}
                    roll-up: {params.isobaric_rollup_preference},{' '}
                    {params.isobaric_substitution_rules.length} rule(s).
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="card p-5">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-3 flex items-center gap-2"><LuHistory /> Reversible Pipeline</h3>
            <p className="text-sm text-slate-600 dark:text-slate-300">Each transformation is recorded in the dataset history. The current dataset is not overwritten; a new processed dataset is created.</p>
          </div>
        </>
      )}

      {blankModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white dark:bg-slate-900 rounded-xl shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-700">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Select blank samples</h3>
              <button onClick={() => setBlankModalOpen(false)} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700"><LuX /></button>
            </div>
            <div className="p-4 border-b border-slate-200 dark:border-slate-700 flex items-center gap-2">
              <LuSearch className="text-slate-400" />
              <input
                type="text"
                value={blankModalSearch}
                onChange={(e) => { setBlankModalSearch(e.target.value); setBlankModalPage(1) }}
                placeholder="Search samples or groups..."
                className="input flex-1"
              />
            </div>
            <div className="p-4 overflow-auto flex-1">
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <button type="button" onClick={selectBlankPage} className="btn-secondary text-xs px-2 py-1">Select page</button>
                <button type="button" onClick={deselectBlankPage} className="btn-secondary text-xs px-2 py-1">Deselect page</button>
                <button type="button" onClick={autoDetectBlanks} className="btn-secondary text-xs px-2 py-1">Auto-detect blanks</button>
                <button type="button" onClick={clearBlankSelection} className="btn-secondary text-xs px-2 py-1">Clear all</button>
                <span className="ml-auto text-xs text-slate-500 dark:text-slate-400">{blankModalSelected.length} selected</span>
              </div>
              {blankModalPageItems.length === 0 ? (
                <div className="text-center text-slate-500 dark:text-slate-400 py-6">No samples match.</div>
              ) : (
                <div className="space-y-1">
                  {blankModalPageItems.map((s) => (
                    <label key={s.name} className="flex items-center gap-2 p-2 rounded hover:bg-slate-50 dark:hover:bg-slate-700/30 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={blankModalSelected.includes(s.name)}
                        onChange={() => toggleBlankSample(s.name)}
                        className="rounded border-slate-300"
                      />
                      <span className="text-sm text-slate-700 dark:text-slate-200 flex-1">{s.name}</span>
                      <span className="text-xs text-slate-500 dark:text-slate-400">{s.group}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
            <div className="flex items-center justify-between p-4 border-t border-slate-200 dark:border-slate-700">
              <div className="flex items-center gap-2">
                <button type="button" disabled={blankModalPage <= 1} onClick={() => setBlankModalPage((p) => p - 1)} className="btn-secondary text-sm">Previous</button>
                <span className="text-sm text-slate-600 dark:text-slate-300">Page {blankModalPage} of {blankModalTotalPages}</span>
                <button type="button" disabled={blankModalPage >= blankModalTotalPages} onClick={() => setBlankModalPage((p) => p + 1)} className="btn-secondary text-sm">Next</button>
              </div>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => setBlankModalOpen(false)} className="btn-secondary text-sm">Cancel</button>
                <button type="button" onClick={applyBlankModal} className="btn-primary text-sm">Apply</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
