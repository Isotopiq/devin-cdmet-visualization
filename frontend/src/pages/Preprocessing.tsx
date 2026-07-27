import { useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import DatasetPicker from '../components/DatasetPicker'
import { preprocess } from '../api'
import { LuSlidersHorizontal, LuPlay, LuHistory, LuAlertCircle, LuCheckCircle2 } from 'react-icons/lu'

export default function Preprocessing() {
  const { projectId, datasetId, selectedDataset } = useWorkspace()
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [params, setParams] = useState({
    missing_value_filter: 0.2,
    log_transform: true,
    scale: 'standard',
    normalization: 'total_area',
    imputation: 'min',
    qc_cv_filter: 0,
  })

  const run = async () => {
    if (!projectId || !datasetId) return
    setLoading(true)
    setMessage('')
    setError('')
    try {
      const body = {
        missing_value_filter: params.missing_value_filter,
        log_transform: params.log_transform,
        scale: params.scale,
        normalization: params.normalization,
        imputation: params.imputation,
        blank_subtraction: false,
        blank_columns: [],
        qc_cv_filter: params.qc_cv_filter,
        qc_columns: [],
        duplicate_handling: 'mean',
        batch_correction: 'none',
        batch_column: null,
        custom_factor: null,
      }
      await preprocess(Number(projectId), Number(datasetId), body)
      setMessage('Preprocessing applied. New dataset created.')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Preprocessing failed')
    } finally {
      setLoading(false)
    }
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
            </div>
            <div className="mt-5">
              <button onClick={run} disabled={loading} className="btn-primary"><LuPlay /> {loading ? 'Running...' : 'Apply Pipeline'}</button>
            </div>
            {message && <div className="mt-4 p-3 rounded-lg bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200 flex items-center gap-2 text-sm"><LuCheckCircle2 /> {message}</div>}
            {error && <div className="mt-4 p-3 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-200 flex items-center gap-2 text-sm"><LuAlertCircle /> {error}</div>}
          </div>

          <div className="card p-5">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-3 flex items-center gap-2"><LuHistory /> Reversible Pipeline</h3>
            <p className="text-sm text-slate-600 dark:text-slate-300">Each transformation is recorded in the dataset history. The current dataset is not overwritten; a new processed dataset is created.</p>
          </div>
        </>
      )}
    </div>
  )
}
