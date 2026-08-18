import { useMemo, useState } from 'react'
import { useWorkspace } from '../context/WorkspaceContext'
import { generatePDFReport } from '../api'
import { LuFileText, LuDownload, LuLoader2 } from 'react-icons/lu'

const ALL_SECTIONS = [
  { key: 'summary', label: 'Summary' },
  { key: 'heatmap_unclustered', label: 'Heatmap - Abundance (Un-clustered)' },
  { key: 'heatmap_clustered', label: 'Heatmap - Abundance (Clustered)' },
  { key: 'pca_score', label: 'PCA Score Plot' },
  { key: 'pca_loadings', label: 'PCA Top Loadings' },
  { key: 'pca_scree', label: 'PCA Scree Plot' },
  { key: 'pls_da', label: 'PLS-DA' },
  { key: 'opls_da', label: 'OPLS-DA' },
  { key: 'volcano', label: 'Volcano Plot' },
  { key: 'functional', label: 'Functional Lipid Volcano' },
  { key: 'food_profile', label: 'Nutritional Metabolic Lipid Profile' },
  { key: 'chain_space', label: 'Chain Space Analysis' },
  { key: 'lipid_class', label: 'Lipid Class Distribution' },
  { key: 'per_lipid_bars', label: 'Individual Feature Bar Plots' },
  { key: 'biomarker', label: 'Biomarker Discovery' },
  { key: 'permanova', label: 'PERMANOVA' },
  { key: 'outlier', label: 'Outlier Analysis' },
  { key: 'rt_mz', label: 'Retention Time vs m/z' },
]

export default function PDFReportPanel() {
  const { projectId, datasetId, selectedDataset } = useWorkspace()
  const groups = useMemo(() => {
    const meta = selectedDataset?.sample_metadata || {}
    const set = new Set<string>()
    Object.values(meta).forEach((g) => set.add(g as string))
    return Array.from(set).sort()
  }, [selectedDataset])

  const [title, setTitle] = useState(`${selectedDataset?.name || 'Dataset'} Report`)
  const [subtitle, setSubtitle] = useState('')
  const [preparedFor, setPreparedFor] = useState('')
  const [preparedBy, setPreparedBy] = useState('Metabolomics Platform')
  const [groupA, setGroupA] = useState(groups[0] || '')
  const [groupB, setGroupB] = useState(groups[1] || '')
  const [topN, setTopN] = useState(8)
  const [nPerm, setNPerm] = useState(50)
  const [fcThreshold, setFcThreshold] = useState(1)
  const [pThreshold, setPThreshold] = useState(0.05)
  const [test, setTest] = useState('t_test')
  const [multipleTesting, setMultipleTesting] = useState('fdr_bh')
  const [showLabels, setShowLabels] = useState(false)
  const [sections, setSections] = useState<string[]>(ALL_SECTIONS.map((s) => s.key))
  const [coverStyle, setCoverStyle] = useState('classic')
  const [organization, setOrganization] = useState('UCLA Metabolomics Center')
  const [reportType, setReportType] = useState('Lipidomics Statistical Report')
  const [reportContents, setReportContents] = useState('Untargeted Lipidomics Report')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState('')
  const [footerText, setFooterText] = useState('Confidential')
  const [reportDate, setReportDate] = useState(new Date().toISOString().split('T')[0])
  const [titleFontSize, setTitleFontSize] = useState(16)
  const [axisLabelFontSize, setAxisLabelFontSize] = useState(12)
  const [tickFontSize, setTickFontSize] = useState(11)
  const [engine, setEngine] = useState<'plotly' | 'r'>('plotly')
  const [plotStyle, setPlotStyle] = useState<'default' | 'publication' | 'lipidone'>('default')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const toggleSection = (key: string) => {
    setSections((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]))
  }

  const toggleAll = () => {
    setSections(sections.length === ALL_SECTIONS.length ? [] : ALL_SECTIONS.map((s) => s.key))
  }

  const generate = async () => {
    if (!projectId || !datasetId) {
      setError('Select a project and dataset first')
      return
    }
    if (!groupA || !groupB || groupA === groupB) {
      setError('Select two different groups for comparison')
      return
    }
    setLoading(true)
    setError('')
    try {
      const res = await generatePDFReport(Number(projectId), Number(datasetId), {
        title,
        subtitle,
        prepared_for: preparedFor,
        prepared_by: preparedBy,
        group_a: groupA,
        group_b: groupB,
        sections,
        top_n: topN,
        n_perm: nPerm,
        fc_threshold: fcThreshold,
        p_threshold: pThreshold,
        test,
        multiple_testing: multipleTesting,
        show_labels: showLabels,
        style: {
          cover_style: coverStyle,
          organization,
          report_type: reportType,
          report_contents: reportContents,
          description,
          tags,
          footer_text: footerText,
          date: reportDate,
          engine,
          plot_style: plotStyle,
          title_size: titleFontSize,
          axis_label_size: axisLabelFontSize,
          tick_size: tickFontSize,
        },
      })
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${(selectedDataset?.name || 'report').replace(/\s+/g, '_')}_report.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to generate PDF')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card p-5 space-y-5">
      <div className="flex items-center gap-2 text-slate-900 dark:text-white font-semibold">
        <LuFileText /> PDF Report Export
      </div>
      <p className="text-sm text-slate-500 dark:text-slate-400">
        Build a styled, multi-page PDF report with a cover page, summary, and selected plots.
      </p>

      {!selectedDataset && (
        <div className="text-sm text-slate-500 dark:text-slate-400">Select a dataset using the picker above to enable PDF export.</div>
      )}

      {selectedDataset && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div><label className="label-like">Report title</label><input type="text" value={title} onChange={(e) => setTitle(e.target.value)} className="input" /></div>
            <div><label className="label-like">Subtitle / comparison</label><input type="text" value={subtitle} onChange={(e) => setSubtitle(e.target.value)} className="input" placeholder="e.g. Tumor vs Normal" /></div>
            <div><label className="label-like">Prepared for</label><input type="text" value={preparedFor} onChange={(e) => setPreparedFor(e.target.value)} className="input" /></div>
            <div><label className="label-like">Prepared by</label><input type="text" value={preparedBy} onChange={(e) => setPreparedBy(e.target.value)} className="input" /></div>
            <div><label className="label-like">Group A</label><select value={groupA} onChange={(e) => setGroupA(e.target.value)} className="input">{groups.map((g) => <option key={g} value={g}>{g}</option>)}</select></div>
            <div><label className="label-like">Group B</label><select value={groupB} onChange={(e) => setGroupB(e.target.value)} className="input">{groups.map((g) => <option key={g} value={g}>{g}</option>)}</select></div>
            <div><label className="label-like">Cover style</label><select value={coverStyle} onChange={(e) => setCoverStyle(e.target.value)} className="input"><option value="classic">Classic Deep</option><option value="minimal">Clean Minimal</option><option value="teal">Ocean Teal</option><option value="split">Split Panel</option></select></div>
            <div><label className="label-like">Organization</label><input type="text" value={organization} onChange={(e) => setOrganization(e.target.value)} className="input" /></div>
            <div><label className="label-like">Report type</label><input type="text" value={reportType} onChange={(e) => setReportType(e.target.value)} className="input" /></div>
            <div><label className="label-like">Report contents</label><input type="text" value={reportContents} onChange={(e) => setReportContents(e.target.value)} className="input" /></div>
            <div className="md:col-span-2"><label className="label-like">Description</label><input type="text" value={description} onChange={(e) => setDescription(e.target.value)} className="input" placeholder="Brief description shown on the cover" /></div>
            <div><label className="label-like">Tags (comma-separated)</label><input type="text" value={tags} onChange={(e) => setTags(e.target.value)} className="input" placeholder="Heatmap, PCA, Volcano" /></div>
            <div><label className="label-like">Footer text</label><input type="text" value={footerText} onChange={(e) => setFooterText(e.target.value)} className="input" /></div>
            <div><label className="label-like">Report date</label><input type="date" value={reportDate} onChange={(e) => setReportDate(e.target.value)} className="input" /></div>
            <div><label className="label-like">Top N features (per-lipid bars)</label><input type="number" min={1} max={50} value={topN} onChange={(e) => setTopN(Number(e.target.value))} className="input" /></div>
            <div><label className="label-like">Permutations (PLS/OPLS-DA)</label><input type="number" min={10} max={500} value={nPerm} onChange={(e) => setNPerm(Number(e.target.value))} className="input" /></div>
            <div><label className="label-like">FC threshold</label><input type="number" step={0.1} value={fcThreshold} onChange={(e) => setFcThreshold(Number(e.target.value))} className="input" /></div>
            <div><label className="label-like">p threshold</label><input type="number" step={0.001} value={pThreshold} onChange={(e) => setPThreshold(Number(e.target.value))} className="input" /></div>
            <div><label className="label-like">Statistical test</label><select value={test} onChange={(e) => setTest(e.target.value)} className="input"><option value="t_test">t_test</option><option value="mannwhitneyu">Mann-Whitney U</option><option value="wilcoxon">Wilcoxon</option></select></div>
            <div><label className="label-like">Multiple testing</label><select value={multipleTesting} onChange={(e) => setMultipleTesting(e.target.value)} className="input"><option value="fdr_bh">fdr_bh</option><option value="bonferroni">Bonferroni</option><option value="holm">Holm</option><option value="none">None</option></select></div>
            <div><label className="label-like">Plot engine</label><select value={engine} onChange={(e) => setEngine(e.target.value as any)} className="input"><option value="plotly">Plotly</option><option value="r">R (static)</option></select></div>
            {engine === 'plotly' && (
              <div><label className="label-like">Plot style</label><select value={plotStyle} onChange={(e) => setPlotStyle(e.target.value as any)} className="input"><option value="default">Default</option><option value="publication">Publication</option><option value="lipidone">LipidOne</option></select></div>
            )}
            <div className="flex items-center gap-2 md:col-span-2"><input id="showLabels" type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} /><label htmlFor="showLabels">Label top features on volcano plot</label></div>
          </div>

          <div>
            <label className="label-like mb-2 block">Plot font sizes</label>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div><label className="label-like">Plot title</label><input type="number" min={8} max={32} value={titleFontSize} onChange={(e) => setTitleFontSize(Number(e.target.value))} className="input" /></div>
              <div><label className="label-like">Axis labels</label><input type="number" min={8} max={24} value={axisLabelFontSize} onChange={(e) => setAxisLabelFontSize(Number(e.target.value))} className="input" /></div>
              <div><label className="label-like">Tick labels</label><input type="number" min={8} max={24} value={tickFontSize} onChange={(e) => setTickFontSize(Number(e.target.value))} className="input" /></div>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="label-like">Sections to include</label>
              <button onClick={toggleAll} className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline">{sections.length === ALL_SECTIONS.length ? 'Deselect all' : 'Select all'}</button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 max-h-64 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg p-3">
              {ALL_SECTIONS.map((s) => (
                <label key={s.key} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300 cursor-pointer">
                  <input type="checkbox" checked={sections.includes(s.key)} onChange={() => toggleSection(s.key)} />
                  {s.label}
                </label>
              ))}
            </div>
          </div>

          {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}

          <button onClick={generate} disabled={loading} className="btn-primary">
            {loading ? <><LuLoader2 className="animate-spin" /> Generating...</> : <><LuDownload /> Generate & Download PDF</>}
          </button>
        </>
      )}
    </div>
  )
}
