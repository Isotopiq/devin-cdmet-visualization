import { useEffect, useMemo, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import { preprocess } from '../api'
import { LuSlidersHorizontal, LuPlay, LuHistory, LuAlertCircle, LuCheckCircle2, LuPlus, LuTrash2 } from 'react-icons/lu'

const DEFAULT_ISOBARIC_RULE = {
  name: 'O-/P- ether/vinyl-ether',
  applicable_classes: 'PC,PE,PI,PS,PA,PG,DG,TG',
  prefix_a: 'O-',
  prefix_b: 'P-',
  db_offset: 1,
  carbon_count_match: true,
}

export default function Preprocessing() {
  const { projectId, datasetId, selectedDataset } = useWorkspace()
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [params, setParams] = useState({
    missing_value_filter: 0.2,
    log_transform: true,
    scale: 'none',
    normalization: 'total_area',
    imputation: 'min',
    qc_cv_filter: 0,
    blank_subtraction: false,
    blank_columns: [] as string[],
    enable_isobaric_substitution_check: true,
    isobaric_substitution_mode: 'flag_ambiguous',
    isobaric_substitution_rules: [DEFAULT_ISOBARIC_RULE],
    isobaric_clustering_enabled: true,
    isobaric_mz_tolerance: 0.005,
    isobaric_rt_tolerance: 0.2,
    isobaric_rollup_preference: 'alphabetical',
    output_name: '',
  })

  useEffect(() => {
    if (selectedDataset && !params.output_name) {
      setParams((prev: any) => ({ ...prev, output_name: `${selectedDataset.name}_processed` }))
    }
  }, [selectedDataset])

  const sampleMeta = selectedDataset?.sample_metadata || {}
  const blankSamples = useMemo(() => {
    return Object.entries(sampleMeta)
      .filter(([_, group]) => /blank|solvent|ntc/i.test(String(group)))
      .map(([sample]) => sample)
  }, [sampleMeta])

  const isLipid = selectedDataset?.feature_type === 'lipid'

  const run = async () => {
    if (!projectId || !datasetId) return
    setLoading(true)
    setMessage('')
    setError('')
    try {
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
        qc_cv_filter: params.qc_cv_filter,
        qc_columns: [],
        duplicate_handling: 'mean',
        batch_correction: 'none',
        batch_column: null,
        custom_factor: null,
        enable_isobaric_substitution_check: isLipid ? params.enable_isobaric_substitution_check : false,
        isobaric_substitution_mode: params.isobaric_substitution_mode,
        isobaric_substitution_rules: rules,
        isobaric_clustering_enabled: params.isobaric_clustering_enabled,
        isobaric_mz_tolerance: params.isobaric_mz_tolerance,
        isobaric_rt_tolerance: params.isobaric_rt_tolerance,
        isobaric_rollup_preference: params.isobaric_rollup_preference,
        output_name: params.output_name || undefined,
      }
      await preprocess(Number(projectId), Number(datasetId), body)
      setMessage('Preprocessing applied. New dataset created.')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Preprocessing failed')
    } finally {
      setLoading(false)
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
                  <option value="min">Half minimum</option>
                  <option value="median">Median</option>
                  <option value="knn">Mean (KNN fallback)</option>
                </select>
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
              <div className="md:col-span-3 flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="blank-subtraction"
                    checked={params.blank_subtraction}
                    onChange={(e) => {
                      const enabled = e.target.checked
                      setParams({
                        ...params,
                        blank_subtraction: enabled,
                        blank_columns: enabled ? blankSamples : [],
                      })
                    }}
                    className="rounded border-slate-300"
                  />
                  <label htmlFor="blank-subtraction" className="text-sm text-slate-700 dark:text-slate-200">Subtract blank samples (recommended for lipidomics)</label>
                </div>
                {params.blank_subtraction && (
                  <div>
                    <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Blank samples to subtract</label>
                    <select
                      multiple
                      value={params.blank_columns}
                      onChange={(e) => setParams({ ...params, blank_columns: Array.from(e.target.selectedOptions).map((o) => o.value) })}
                      className="input h-32"
                    >
                      {Object.keys(sampleMeta).map((s) => (
                        <option key={s} value={s}>{s} ({sampleMeta[s] || 'unknown'})</option>
                      ))}
                    </select>
                    <p className="text-xs text-slate-500 mt-1">Hold Ctrl/Cmd to select multiple. Detected blank groups are pre-selected.</p>
                  </div>
                )}
              </div>
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
    </div>
  )
}
