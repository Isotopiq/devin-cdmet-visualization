import { useEffect, useMemo, useRef, useState } from 'react'
const VISUALIZE_TAB_KEY = 'visualizeTab'
import { useWorkspace } from '../context/WorkspaceContext'
import { usePlotConfig, styleToBackend } from '../context/PlotConfigContext'
import DatasetPicker from '../components/DatasetPicker'
import PlotWithDownload from '../components/PlotWithDownload'
import PlotStyling from '../components/PlotStyling'
import { generatePlot, runStats, generatePDFReport, getSettings } from '../api'
import { LuRefreshCw, LuFileDown, LuPrinter, LuChevronDown, LuChevronUp, LuX, LuDownload, LuFileText, LuFilter } from 'react-icons/lu'
import JSZip from 'jszip'
import Plotly from 'plotly.js/dist/plotly'

const TABS = [
  { key: 'pca', label: 'PCA' },
  { key: 'pls_da', label: 'PLS-DA' },
  { key: 'opls_da', label: 'OPLS-DA' },
  { key: 'biomarker', label: 'Biomarkers' },
  { key: 'permanova', label: 'PERMANOVA' },
  { key: 'volcano', label: 'Volcano' },
  { key: 'heatmap', label: 'Heatmap' },
  { key: 'per_lipid_bars', label: 'Per-lipid bars' },
  { key: 'lipid_classes', label: 'Lipid classes' },
  { key: 'chain_space', label: 'Chain space' },
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

const LINKAGE_COLORS = [
  { value: '#2ca02c', label: 'Green' },
  { value: '#ff7f0e', label: 'Orange' },
  { value: '#1f77b4', label: 'Blue' },
  { value: '#d62728', label: 'Red' },
  { value: '#9467bd', label: 'Purple' },
  { value: '#000000', label: 'Black' },
  { value: '#808080', label: 'Gray' },
]

const LIPIDS_PER_PAGE = [4, 6, 8, 12, 16, 24, 32]

const FONT_OPTIONS = [
  { label: 'Default (system)', value: '' },
  { label: 'Helvetica', value: 'Helvetica' },
  { label: 'Times', value: 'Times' },
  { label: 'Courier', value: 'Courier' },
  { label: 'DejaVu', value: 'DejaVu' },
  { label: 'Liberation', value: 'Liberation' },
]

const COVER_STYLES = [
  { label: 'Classic Deep', value: 'classic' },
  { label: 'Clean Minimal', value: 'minimal' },
  { label: 'Ocean Teal', value: 'teal' },
  { label: 'Split Panel', value: 'split' },
  { label: 'LipidOne', value: 'lipidone' },
]

const ALL_PLOT_KEYS = [
  { key: 'pca', label: 'PCA' },
  { key: 'pls_da', label: 'PLS-DA' },
  { key: 'opls_da', label: 'OPLS-DA' },
  { key: 'biomarker', label: 'Biomarkers' },
  { key: 'permanova', label: 'PERMANOVA' },
  { key: 'volcano', label: 'Volcano (labels reflect current tab settings)' },
  { key: 'heatmap', label: 'Heatmap' },
  { key: 'per_lipid_bars', label: 'Per-lipid bars' },
  { key: 'lipid_classes', label: 'Lipid classes' },
  { key: 'chain_space', label: 'Chain space' },
  { key: 'outlier', label: 'Outlier' },
  { key: 'functional', label: 'Functional lipid indices' },
  { key: 'food_profile', label: 'Lipid food profile' },
]

export default function Visualize() {
  const { selectedDataset, projectId, datasetId } = useWorkspace()
  const { style, reportTitle, setReportTitle, includePlots, setIncludePlots } = usePlotConfig()
  const [tab, _setTab] = useState(localStorage.getItem(VISUALIZE_TAB_KEY) || 'volcano')
  const tabRef = useRef(tab)
  useEffect(() => { tabRef.current = tab }, [tab])
  const setTab = (key: string) => {
    _setTab(key)
    localStorage.setItem(VISUALIZE_TAB_KEY, key)
  }
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
  const [includedGroups, setIncludedGroups] = useState<Set<string>>(new Set())
  const [fcThreshold, setFcThreshold] = useState(1)
  const [pThreshold, setPThreshold] = useState(0.05)
  const [multipleTesting, setMultipleTesting] = useState('fdr_bh')
  const [showLabels, setShowLabels] = useState(true)
  const [topN, setTopN] = useState(15)

  const [heatmapType, setHeatmapType] = useState('abundance')
  const [heatmapScale, setHeatmapScale] = useState('row_zscore')
  const [heatmapMetric, setHeatmapMetric] = useState('euclidean')
  const [heatmapMethod, setHeatmapMethod] = useState('average')
  const [heatmapTopN, setHeatmapTopN] = useState(50)
  const [heatmapTopNInput, setHeatmapTopNInput] = useState('50')
  const [heatmapStyle, setHeatmapStyle] = useState<'default' | 'publication' | 'lipidone' | 'seaborn' | 'matplotlib'>('default')
  const [heatmapLinkageColor, setHeatmapLinkageColor] = useState('#2ca02c')
  const [rowCluster, setRowCluster] = useState(true)
  const [colCluster, setColCluster] = useState(true)
  const [groupOrder, setGroupOrder] = useState<string[]>([])
  const [selectedGroup, setSelectedGroup] = useState('')
  const [outlierGroupByGroup, setOutlierGroupByGroup] = useState(false)
  const [outlierGroupOrder, setOutlierGroupOrder] = useState<string[]>([])
  const [selectedOutlierGroup, setSelectedOutlierGroup] = useState('')
  const [renameSamples, setRenameSamples] = useState(false)
  const [biomarkerComparisons, setBiomarkerComparisons] = useState<{ id: number; group_a: string; group_b: string }[]>([])

  const [lipidsPerPage, setLipidsPerPage] = useState(8)
  const [allLipids, setAllLipids] = useState(false)
  const [perLipidTest, setPerLipidTest] = useState('t_test')

  const [showContents, setShowContents] = useState(false)
  const [groupFilterOpen, setGroupFilterOpen] = useState(true)
  const [reportOpen, setReportOpen] = useState(false)
  const [reportSections, setReportSections] = useState<any[]>([])
  const [reportLoading, setReportLoading] = useState(false)
  const [zipLoading, setZipLoading] = useState(false)
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrStatus, setOcrStatus] = useState('')
  const [pdfPreparedBy, setPdfPreparedBy] = useState('Metabolomics Platform')
  const [pdfCoverStyle, setPdfCoverStyle] = useState('classic')
  const [pdfFontFamily, setPdfFontFamily] = useState('')
  const [s3Configured, setS3Configured] = useState(false)
  const [saveReportToS3, setSaveReportToS3] = useState(false)
  const reportRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setGroupA(groups[0] || '')
    setGroupB(groups[1] || '')
    setIncludedGroups(new Set(groups))
    setGroupOrder([...groups].sort())
    setOutlierGroupOrder([...groups].sort())
    if (biomarkerComparisons.length === 0) {
      setBiomarkerComparisons([{ id: 0, group_a: groups[0] || '', group_b: groups[1] || '' }])
    }
    setReady(true)
    if (groups.length <= 2 && (perLipidTest === 'anova' || perLipidTest === 'kruskal')) {
      setPerLipidTest('t_test')
    }
  }, [groups, perLipidTest])

  useEffect(() => {
    getSettings()
      .then((res: any) => {
        const defaultPrepared = res.data?.pdf_prepared_by
        if (defaultPrepared) {
          setPdfPreparedBy(defaultPrepared)
        }
        setS3Configured(!!res.data?.s3_configured)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    setIncludedGroups((prev) => new Set([...Array.from(prev), groupA, groupB].filter(Boolean)))
  }, [groupA, groupB])

  // Debounce heatmap Top N so typing "25" doesn't fire a request for "2" first
  useEffect(() => {
    const n = parseInt(heatmapTopNInput, 10)
    if (isNaN(n) || n < 1) return
    const timer = setTimeout(() => setHeatmapTopN(n), 400)
    return () => clearTimeout(timer)
  }, [heatmapTopNInput])

  const backendStyle = styleToBackend(style)
  const excludedGroups = useMemo(() => groups.filter((g) => !includedGroups.has(g)), [groups, includedGroups])

  const generate = async () => {
    if (!projectId || !datasetId || !groupA) return
    if (tab !== 'chain_space' && !groupB) return
    const requestTab = tabRef.current
    setLoading(true)
    setFigure(null)
    setFigures([])
    try {
      const base = { projectId: Number(projectId), datasetId: Number(datasetId) }
      const withExcluded = (p: any) => ({ ...p, excluded_groups: excludedGroups, rename_samples: renameSamples })
      if (tab === 'pca') {
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'pca', parameters: withExcluded({ plot: 'score', title: reportTitle }), style: backendStyle })
        if (tabRef.current === requestTab) setFigure(res.data)
      } else if (tab === 'pls_da') {
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'pls_da', parameters: withExcluded({ group_a: groupA, group_b: groupB, title: reportTitle }), style: backendStyle })
        if (tabRef.current === requestTab) setFigure(res.data)
      } else if (tab === 'opls_da') {
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'opls_da', parameters: withExcluded({ group_a: groupA, group_b: groupB, title: reportTitle }), style: backendStyle })
        if (tabRef.current === requestTab) setFigure(res.data)
      } else if (tab === 'biomarker') {
        const comparisons = biomarkerComparisons.filter(c => c.group_a && c.group_b).map(c => ({ group_a: c.group_a, group_b: c.group_b }))
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'biomarker', parameters: withExcluded({ group_a: groupA, group_b: groupB, title: reportTitle, comparisons }), style: backendStyle })
        if (tabRef.current === requestTab) {
          if (Array.isArray(res.data)) setFigures(res.data)
          else setFigure(res.data)
        }
      } else if (tab === 'permanova') {
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'permanova', parameters: withExcluded({ group_a: groupA, group_b: groupB, metric: 'braycurtis', title: reportTitle }), style: backendStyle })
        if (tabRef.current === requestTab) setFigure(res.data)
      } else if (tab === 'volcano') {
        const statsRes = await runStats(base.projectId, base.datasetId, { test: 't_test', group_a: groupA, group_b: groupB, paired: false, multiple_testing: multipleTesting, alpha: pThreshold })
        const res = await generatePlot(base.projectId, base.datasetId, {
          plot_type: 'volcano',
          parameters: withExcluded({ stats: statsRes.data.results, fc_threshold: fcThreshold, p_threshold: pThreshold, show_labels: showLabels, top_n: topN, group_a: groupA, group_b: groupB, title: reportTitle }),
          style: backendStyle,
        })
        if (tabRef.current === requestTab) setFigure(res.data)
      } else if (tab === 'heatmap') {
        const res = await generatePlot(base.projectId, base.datasetId, {
          plot_type: 'heatmap',
          parameters: withExcluded({
            heatmap_type: heatmapType,
            heatmap_style: heatmapStyle,
            top_n: heatmapTopN,
            scale: heatmapScale,
            metric: heatmapMetric,
            method: heatmapMethod,
            linkage_color: heatmapLinkageColor,
            cluster_rows: rowCluster,
            cluster_cols: colCluster,
            group_order: groupOrder,
          }),
          style: backendStyle,
        })
        if (tabRef.current === requestTab) setFigure(res.data)
      } else if (tab === 'per_lipid_bars') {
        const selectedGroups = Array.from(includedGroups).filter(g => groups.includes(g))
        const statsRes = await runStats(base.projectId, base.datasetId, { test: perLipidTest, group_a: groupA, group_b: groupB, selected_groups: selectedGroups, paired: false, multiple_testing: multipleTesting, alpha: pThreshold })
        const res = await generatePlot(base.projectId, base.datasetId, {
          plot_type: 'per_lipid_bars',
          parameters: withExcluded({ stats: statsRes.data.results, group_a: groupA, group_b: groupB, groups: selectedGroups, test: perLipidTest, top_n: allLipids ? 1000 : lipidsPerPage }),
          style: backendStyle,
        })
        if (tabRef.current === requestTab) {
          if (Array.isArray(res.data)) setFigures(res.data)
          else setFigure(res.data)
        }
      } else if (tab === 'lipid_classes') {
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'lipid_class', parameters: withExcluded({}), style: backendStyle })
        if (tabRef.current === requestTab) setFigure(res.data)
      } else if (tab === 'chain_space') {
        const selectedGroups = Array.from(includedGroups).filter(g => groups.includes(g))
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'chain_space', parameters: withExcluded({ group_a: groupA, group_b: groupB, selected_groups: selectedGroups, title: reportTitle }), style: backendStyle })
        if (tabRef.current === requestTab) {
          if (Array.isArray(res.data)) setFigures(res.data)
          else setFigure(res.data)
        }
      } else if (tab === 'outlier') {
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'outlier', parameters: withExcluded({ title: reportTitle, group_samples_by_group: outlierGroupByGroup, group_order: outlierGroupOrder }), style: backendStyle })
        if (tabRef.current === requestTab) setFigure(res.data)
      } else if (tab === 'functional') {
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'functional', parameters: withExcluded({ group_a: groupA, group_b: groupB, title: reportTitle, fc_threshold: fcThreshold, p_threshold: pThreshold }), style: backendStyle })
        if (tabRef.current === requestTab) setFigure(res.data)
      } else if (tab === 'food_profile') {
        const res = await generatePlot(base.projectId, base.datasetId, { plot_type: 'food_profile', parameters: withExcluded({ group_a: groupA, group_b: groupB, title: reportTitle, fc_threshold: fcThreshold, p_threshold: pThreshold }), style: backendStyle })
        if (tabRef.current === requestTab) setFigure(res.data)
      }
    } catch (err: any) {
      console.error(err)
    } finally {
      if (tabRef.current === requestTab) setLoading(false)
    }
  }

  // Generate when the active tab, dataset, groups, or included groups change (ignore the initial ready flag flip)
  const didInitRef = useRef(false)
  useEffect(() => {
    const hasGroupB = groupB || tab === 'chain_space'
    if (selectedDataset && groupA && hasGroupB) {
      if (didInitRef.current || ready) {
        didInitRef.current = true
        generate()
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, selectedDataset, groupA, groupB, includedGroups])

  useEffect(() => {
    if (ready && selectedDataset && groupA && (groupB || tab === 'chain_space')) {
      didInitRef.current = true
      generate()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready])

  useEffect(() => {
    if ((figure || figures.length) && !loading) generate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [style, fcThreshold, pThreshold, multipleTesting, heatmapTopN, heatmapStyle, heatmapLinkageColor, rowCluster, colCluster, heatmapScale, heatmapMetric, heatmapMethod, heatmapType, groupOrder, perLipidTest, lipidsPerPage, allLipids, includedGroups, outlierGroupByGroup, outlierGroupOrder, renameSamples, biomarkerComparisons])

  const toggleInclude = (key: string) => {
    setIncludePlots((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const toggleGroup = (g: string) => {
    setIncludedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(g)) next.delete(g)
      else next.add(g)
      return next
    })
  }

  const setAllGroups = (include: boolean) => {
    setIncludedGroups(include ? new Set(groups) : new Set([groupA, groupB].filter(Boolean)))
  }

  const addBiomarkerComparison = () => {
    setBiomarkerComparisons((prev) => [...prev, { id: Date.now(), group_a: groups[0] || '', group_b: groups[1] || '' }])
  }

  const removeBiomarkerComparison = (id: number) => {
    setBiomarkerComparisons((prev) => prev.filter((c) => c.id !== id))
  }

  const updateBiomarkerComparison = (id: number, field: 'group_a' | 'group_b', value: string) => {
    setBiomarkerComparisons((prev) => prev.map((c) => (c.id === id ? { ...c, [field]: value } : c)))
  }

  const setBiomarkerPairwise = () => {
    const selected = Array.from(includedGroups).filter(g => groups.includes(g))
    const next: { id: number; group_a: string; group_b: string }[] = []
    for (let i = 0; i < selected.length; i++) {
      for (let j = i + 1; j < selected.length; j++) {
        next.push({ id: Date.now() + i * selected.length + j, group_a: selected[i], group_b: selected[j] })
      }
    }
    setBiomarkerComparisons(next.length ? next : [{ id: Date.now(), group_a: groups[0] || '', group_b: groups[1] || '' }])
  }

  const setBiomarkerOneVsReference = () => {
    const selected = Array.from(includedGroups).filter(g => groups.includes(g))
    const ref = groupA || selected[0]
    const next = selected.filter(g => g !== ref).map((g, i) => ({ id: Date.now() + i, group_a: ref, group_b: g }))
    setBiomarkerComparisons(next.length ? next : [{ id: Date.now(), group_a: groups[0] || '', group_b: groups[1] || '' }])
  }

  const buildReportParams = () => ({
    test: perLipidTest,
    group_a: groupA,
    group_b: groupB,
    selected_groups: Array.from(includedGroups).filter(g => groups.includes(g)),
    paired: false,
    multiple_testing: multipleTesting,
    alpha: pThreshold,
    fc_threshold: fcThreshold,
    p_threshold: pThreshold,
    show_labels: showLabels,
    top_n: topN,
    heatmap_top_n: heatmapTopN,
    heatmap_style: heatmapStyle === 'default' ? undefined : heatmapStyle,
    heatmap_linkage_color: heatmapLinkageColor,
    scale: heatmapScale,
    metric: heatmapMetric,
    method: heatmapMethod,
    cluster_rows: rowCluster,
    cluster_cols: colCluster,
    group_order: groupOrder,
    per_lipid_top_n: lipidsPerPage,
    all_lipids: allLipids,
    excluded_groups: excludedGroups,
    outlier_group_by_group: outlierGroupByGroup,
    outlier_group_order: outlierGroupOrder,
    rename_samples: renameSamples,
    biomarker_comparisons: biomarkerComparisons.filter(c => c.group_a && c.group_b).map(c => ({ group_a: c.group_a, group_b: c.group_b })),
  })

  const loadScript = (src: string) =>
    new Promise<void>((resolve, reject) => {
      const existing = document.querySelector(`script[src="${src}"]`)
      if (existing) {
        resolve()
        return
      }
      const s = document.createElement('script')
      s.src = src
      s.async = true
      s.onload = () => resolve()
      s.onerror = () => reject(new Error(`Failed to load ${src}`))
      document.body.appendChild(s)
    })

  const applyOcrLayer = async (element: HTMLElement) => {
    setOcrLoading(true)
    setOcrStatus('Loading OCR engine...')
    try {
      await Promise.all([
        loadScript('https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js'),
        loadScript('https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js'),
      ])

      const html2canvasLib = (window as any).html2canvas as (el: HTMLElement, opts?: any) => Promise<HTMLCanvasElement>
      const Tesseract = (window as any).Tesseract as any
      if (!html2canvasLib || !Tesseract) {
        throw new Error('OCR libraries failed to load')
      }

      setOcrStatus('Capturing report for OCR...')
      const canvas = await html2canvasLib(element, { scale: 2, useCORS: true, backgroundColor: '#ffffff', logging: false })

      setOcrStatus('Running OCR (this may take a moment)...')
      const worker = await Tesseract.createWorker('eng')
      const { data } = await worker.recognize(canvas)
      await worker.terminate()

      const cWidth = canvas.width || 1
      const cHeight = canvas.height || 1

      const overlay = document.createElement('div')
      overlay.className = 'ocr-text-layer print-only'
      overlay.style.position = 'absolute'
      overlay.style.top = '0'
      overlay.style.left = '0'
      overlay.style.width = '100%'
      overlay.style.height = '100%'
      overlay.style.zIndex = '9999'
      overlay.style.pointerEvents = 'none'
      overlay.style.overflow = 'hidden'

      const cssHeight = cHeight / 2
      for (const word of data.words || []) {
        const bbox = word.bbox
        const left = (bbox.x0 / cWidth) * 100
        const top = (bbox.y0 / cHeight) * 100
        const width = ((bbox.x1 - bbox.x0) / cWidth) * 100
        const heightPct = ((bbox.y1 - bbox.y0) / cHeight) * 100
        if (width <= 0 || heightPct <= 0 || !word.text?.trim()) continue
        const pxHeight = Math.max(8, (bbox.y1 - bbox.y0) / 2)
        const span = document.createElement('span')
        span.textContent = word.text
        span.style.position = 'absolute'
        span.style.left = `${left}%`
        span.style.top = `${top}%`
        span.style.width = `${Math.max(width, 0.5)}%`
        span.style.height = `${Math.max(heightPct, 0.5)}%`
        span.style.color = 'rgba(0,0,0,0.01)'
        span.style.fontSize = `${pxHeight}px`
        span.style.lineHeight = `${pxHeight}px`
        span.style.whiteSpace = 'nowrap'
        span.style.overflow = 'hidden'
        span.style.fontFamily = 'sans-serif'
        overlay.appendChild(span)
      }

      element.style.position = 'relative'
      element.appendChild(overlay)
      setOcrStatus('Finalizing PDF...')
      setTimeout(() => {
        window.print()
        setTimeout(() => overlay.remove(), 500)
      }, 200)
    } catch (err: any) {
      console.error('OCR failed:', err)
      setOcrStatus('OCR failed, printing without text layer.')
      window.print()
    } finally {
      setOcrLoading(false)
      setOcrStatus('')
    }
  }

  const PDF_SECTIONS: Record<string, string[]> = {
    pca: ['pca_score', 'pca_loadings', 'pca_scree'],
    pls_da: ['pls_da'],
    opls_da: ['opls_da'],
    biomarker: ['biomarker'],
    permanova: ['permanova'],
    volcano: ['volcano'],
    heatmap: ['heatmap_clustered', 'heatmap_unclustered'],
    per_lipid_bars: ['per_lipid_bars'],
    lipid_classes: ['lipid_class'],
    chain_space: ['chain_space'],
    outlier: ['outlier'],
    functional: ['functional'],
    food_profile: ['food_profile'],
  }

  const exportReport = async () => {
    if (!projectId || !datasetId || !groupA || !groupB) return
    setReportLoading(true)
    try {
      const reportParams = buildReportParams()
      const sections = ['summary', ...ALL_PLOT_KEYS.filter((p) => includePlots[p.key]).flatMap((p) => PDF_SECTIONS[p.key] || [])]
      const res = await generatePDFReport(Number(projectId), Number(datasetId), {
        title: reportTitle || `${selectedDataset?.name || 'Dataset'} Report`,
        subtitle: `${groupB} vs ${groupA}`,
        prepared_by: pdfPreparedBy,
        group_a: groupA,
        group_b: groupB,
        sections,
        top_n: topN,
        n_perm: 50,
        fc_threshold: reportParams.fc_threshold,
        p_threshold: reportParams.p_threshold,
        test: reportParams.test,
        multiple_testing: reportParams.multiple_testing,
        show_labels: reportParams.show_labels,
        parameters: reportParams,
        style: { ...backendStyle, cover_style: pdfCoverStyle, font_family: pdfFontFamily || backendStyle.font_family },
        save_to_s3: saveReportToS3,
      })
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${(reportTitle || `${selectedDataset?.name || 'report'}`).replace(/\s+/g, '_')}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      console.error(err)
      alert(err.response?.data?.detail || 'Failed to generate PDF')
    } finally {
      setReportLoading(false)
    }
  }

  const downloadZip = async () => {
    const figs = figures.length ? figures : figure ? [figure] : []
    if (!figs.length) return
    setZipLoading(true)
    try {
      const zip = new JSZip()
      const baseName = (reportTitle || `${tab}_plots`).replace(/[^\w\-]+/g, '_')
      for (let i = 0; i < figs.length; i++) {
        const f = figs[i]
        const layout = f.layout || {}
        const titleText = typeof layout.title === 'string' ? layout.title : layout.title?.text
        const plotName = (titleText || `${tab}_${i + 1}`).replace(/[^\w\-]+/g, '_').slice(0, 80)
        const width = Math.max(400, layout.width || 1200)
        const height = Math.max(300, layout.height || (tab === 'heatmap' ? 900 : 650))
        const exportLayout = { ...layout, width, height }
        const dataUrl = await Plotly.toImage({ data: f.data, layout: exportLayout }, { format: 'png', width, height, scale: 2 })
        const base64 = dataUrl.split(',')[1]
        const fileName = figs.length === 1 ? `${plotName}.png` : `${String(i + 1).padStart(2, '0')}_${plotName}.png`
        zip.file(fileName, base64, { base64: true })
      }
      const blob = await zip.generateAsync({ type: 'blob' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${baseName}.zip`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      console.error(err)
      alert('Failed to generate ZIP: ' + (err.message || 'unknown error'))
    } finally {
      setZipLoading(false)
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
        <div className="grid grid-cols-2 md:grid-cols-8 gap-3 items-end">
          <div><label className="label-like">Group A</label><select value={groupA} onChange={(e) => setGroupA(e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
          <div><label className="label-like">Group B</label><select value={groupB} onChange={(e) => setGroupB(e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
          <div><label className="label-like">log2FC cutoff</label><input type="number" step="0.1" value={fcThreshold} onChange={(e) => setFcThreshold(Number(e.target.value))} className="input" /></div>
          <div><label className="label-like">p-value cutoff</label><input type="number" step="0.01" value={pThreshold} onChange={(e) => setPThreshold(Number(e.target.value))} className="input" /></div>
          <div>
            <label className="label-like">Multiple testing</label>
            <select value={multipleTesting} onChange={(e) => setMultipleTesting(e.target.value)} className="input">
              <option value="fdr_bh">Benjamini-Hochberg (FDR)</option>
              <option value="bonferroni">Bonferroni</option>
              <option value="holm">Holm</option>
              <option value="none">None</option>
            </select>
          </div>
          <div className="flex items-center gap-2 pb-2"><input type="checkbox" id="labels" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} /><label htmlFor="labels">Label top</label></div>
          <div><input type="number" min={1} max={50} value={topN} onChange={(e) => setTopN(Number(e.target.value))} className="input" /></div>
          <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
        </div>
      )
    }
    if (tab === 'heatmap') {
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-10 gap-3 items-end">
            <div><label className="label-like">Type</label><select value={heatmapType} onChange={(e) => setHeatmapType(e.target.value)} className="input"><option value="abundance">Abundance</option><option value="correlation">Correlation</option></select></div>
            <div><label className="label-like">Style</label><select value={heatmapStyle} onChange={(e) => setHeatmapStyle(e.target.value as any)} className="input"><option value="default">Default</option><option value="publication">Publication</option><option value="lipidone">LipidOne</option><option value="seaborn">Seaborn</option><option value="matplotlib">Matplotlib</option></select></div>
            {(heatmapStyle === 'seaborn' || heatmapStyle === 'matplotlib') && (
              <div><label className="label-like">Linkage color</label><select value={heatmapLinkageColor} onChange={(e) => setHeatmapLinkageColor(e.target.value)} className="input">{LINKAGE_COLORS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}</select></div>
            )}
            <div><label className="label-like">Scale</label><select value={heatmapScale} onChange={(e) => setHeatmapScale(e.target.value)} className="input">{SCALES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}</select></div>
            <div><label className="label-like">Distance</label><select value={heatmapMetric} onChange={(e) => setHeatmapMetric(e.target.value)} className="input">{METRICS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}</select></div>
            <div><label className="label-like">Linkage</label><select value={heatmapMethod} onChange={(e) => setHeatmapMethod(e.target.value)} className="input">{METHODS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}</select></div>
            <div><label className="label-like">Top N</label><input type="number" min={5} value={heatmapTopNInput} onChange={(e) => setHeatmapTopNInput(e.target.value)} onBlur={() => { const n = parseInt(heatmapTopNInput, 10); if (!isNaN(n) && n >= 1) { setHeatmapTopNInput(String(n)); setHeatmapTopN(n) } }} className="input" /></div>
            <div className="flex items-center gap-2 pb-2"><input type="checkbox" id="rowCluster" checked={rowCluster} onChange={(e) => setRowCluster(e.target.checked)} /><label htmlFor="rowCluster">Rows</label></div>
            <div className="flex items-center gap-2 pb-2"><input type="checkbox" id="colCluster" checked={colCluster} onChange={(e) => setColCluster(e.target.checked)} /><label htmlFor="colCluster">Cols</label></div>
            <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="label-like">Group order</label>
              <select
                size={Math.min(5, groupOrder.length)}
                value={selectedGroup}
                onChange={(e) => setSelectedGroup(e.target.value)}
                className="input min-w-[10rem]"
              >
                {groupOrder.map((g, i) => <option key={g} value={g}>{i + 1}. {g}</option>)}
              </select>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  const idx = groupOrder.indexOf(selectedGroup)
                  if (idx > 0) {
                    const next = [...groupOrder]
                    ;[next[idx - 1], next[idx]] = [next[idx], next[idx - 1]]
                    setGroupOrder(next)
                  }
                }}
                className="btn-secondary px-2 py-1"
              >Up</button>
              <button
                onClick={() => {
                  const idx = groupOrder.indexOf(selectedGroup)
                  if (idx >= 0 && idx < groupOrder.length - 1) {
                    const next = [...groupOrder]
                    ;[next[idx], next[idx + 1]] = [next[idx + 1], next[idx]]
                    setGroupOrder(next)
                  }
                }}
                className="btn-secondary px-2 py-1"
              >Down</button>
              <button onClick={() => { setGroupOrder([...groups].sort()); setSelectedGroup('') }} className="btn-secondary px-2 py-1">Reset</button>
            </div>
          </div>
        </div>
      )
    }
    if (tab === 'per_lipid_bars') {
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-8 gap-3 items-end">
            <div><label className="label-like">Group A</label><select value={groupA} onChange={(e) => setGroupA(e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
            <div><label className="label-like">Group B</label><select value={groupB} onChange={(e) => setGroupB(e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
            <div><label className="label-like">Test</label><select value={perLipidTest} onChange={(e) => setPerLipidTest(e.target.value)} className="input"><option value="t_test">t-test</option><option value="welch">Welch</option><option value="mannwhitney">Mann-Whitney</option>{groups.length > 2 && <><option value="anova">ANOVA</option><option value="kruskal">Kruskal-Wallis</option></>}</select></div>
            <div><label className="label-like">Lipids/page</label><select value={lipidsPerPage} onChange={(e) => setLipidsPerPage(Number(e.target.value))} className="input">{LIPIDS_PER_PAGE.map(n => <option key={n} value={n}>{n}</option>)}</select></div>
            <div className="flex items-center gap-2 pb-2"><input type="checkbox" id="allLipids" checked={allLipids} onChange={(e) => setAllLipids(e.target.checked)} /><label htmlFor="allLipids">All lipids</label></div>
            <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="label-like">Groups to display:</span>
            {groups.map((g) => (
              <label key={g} className={`flex items-center gap-1 ${(g === groupA || g === groupB) ? 'text-slate-400 dark:text-slate-500' : 'text-slate-700 dark:text-slate-200'}`}>
                <input
                  type="checkbox"
                  checked={includedGroups.has(g)}
                  disabled={g === groupA || g === groupB}
                  onChange={() => toggleGroup(g)}
                />
                {g}
              </label>
            ))}
          </div>
        </div>
      )
    }
    if (tab === 'functional' || tab === 'food_profile') {
      return (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3 items-end">
          <div><label className="label-like">Group A</label><select value={groupA} onChange={(e) => setGroupA(e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
          <div><label className="label-like">Group B</label><select value={groupB} onChange={(e) => setGroupB(e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
          <div><label className="label-like">log2FC cutoff</label><input type="number" step="0.1" value={fcThreshold} onChange={(e) => setFcThreshold(Number(e.target.value))} className="input" /></div>
          <div><label className="label-like">p-value cutoff</label><input type="number" step="0.01" value={pThreshold} onChange={(e) => setPThreshold(Number(e.target.value))} className="input" /></div>
          <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
        </div>
      )
    }
    if (tab === 'chain_space') {
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 items-end">
            <div><label className="label-like">Reference group: {groupA || '—'}</label><select value={groupA} onChange={(e) => setGroupA(e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
            <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Two or more groups must be included. When more than two groups are selected, one Chain Space chart is generated for each non-reference group vs <strong>{groupA || 'the reference'}</strong>.
          </p>
        </div>
      )
    }
    if (tab === 'outlier') {
      return (
        <div className="space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex items-center gap-2 pb-2">
              <input type="checkbox" id="outlierGroupByGroup" checked={outlierGroupByGroup} onChange={(e) => setOutlierGroupByGroup(e.target.checked)} />
              <label htmlFor="outlierGroupByGroup">Group samples by group</label>
            </div>
            <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
          </div>
          {outlierGroupByGroup && (
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <label className="label-like">Group order (top to bottom)</label>
                <select
                  size={Math.min(5, outlierGroupOrder.length)}
                  value={selectedOutlierGroup}
                  onChange={(e) => setSelectedOutlierGroup(e.target.value)}
                  className="input min-w-[12rem]"
                >
                  {outlierGroupOrder.map((g, i) => <option key={g} value={g}>{i + 1}. {g}</option>)}
                </select>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    const idx = outlierGroupOrder.indexOf(selectedOutlierGroup)
                    if (idx > 0) {
                      const next = [...outlierGroupOrder]
                      ;[next[idx - 1], next[idx]] = [next[idx], next[idx - 1]]
                      setOutlierGroupOrder(next)
                    }
                  }}
                  className="btn-secondary px-2 py-1"
                >Up</button>
                <button
                  onClick={() => {
                    const idx = outlierGroupOrder.indexOf(selectedOutlierGroup)
                    if (idx >= 0 && idx < outlierGroupOrder.length - 1) {
                      const next = [...outlierGroupOrder]
                      ;[next[idx], next[idx + 1]] = [next[idx + 1], next[idx]]
                      setOutlierGroupOrder(next)
                    }
                  }}
                  className="btn-secondary px-2 py-1"
                >Down</button>
                <button onClick={() => { setOutlierGroupOrder([...groups].sort()); setSelectedOutlierGroup('') }} className="btn-secondary px-2 py-1">Reset</button>
              </div>
            </div>
          )}
          <p className="text-xs text-slate-500 dark:text-slate-400">
            When grouping is enabled, samples are clustered by group and ordered by Mahalanobis distance within each group. Use the list above to set which group appears at the top.
          </p>
        </div>
      )
    }
    if (tab === 'biomarker') {
      return (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={addBiomarkerComparison} className="btn-secondary text-sm">+ Add comparison</button>
            <button onClick={setBiomarkerPairwise} className="btn-secondary text-sm">All pairwise</button>
            <button onClick={setBiomarkerOneVsReference} className="btn-secondary text-sm">Each vs {groupA || 'reference'}</button>
            <button onClick={generate} disabled={loading} className="btn-primary"><LuRefreshCw className={loading ? 'animate-spin' : ''} /> Generate</button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {biomarkerComparisons.map((comp) => (
              <div key={comp.id} className="flex items-end gap-2">
                <div className="flex-1"><label className="label-like">Group A</label><select value={comp.group_a} onChange={(e) => updateBiomarkerComparison(comp.id, 'group_a', e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
                <div className="flex-1"><label className="label-like">Group B</label><select value={comp.group_b} onChange={(e) => updateBiomarkerComparison(comp.id, 'group_b', e.target.value)} className="input">{groups.map(g => <option key={g}>{g}</option>)}</select></div>
                <button onClick={() => removeBiomarkerComparison(comp.id)} className="btn-secondary text-sm px-2 py-1" disabled={biomarkerComparisons.length === 1}>Remove</button>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Configure one or more group comparisons. Each comparison produces a separate biomarker discovery panel. Use the <em>All pairwise</em> or <em>Each vs reference</em> buttons to auto-fill from the currently included groups.
          </p>
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
                <div>
                  <label className="label-like">PDF cover style</label>
                  <select value={pdfCoverStyle} onChange={(e) => setPdfCoverStyle(e.target.value)} className="input text-sm">
                    {COVER_STYLES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label-like">PDF font</label>
                  <select value={pdfFontFamily} onChange={(e) => setPdfFontFamily(e.target.value)} className="input text-sm">
                    {FONT_OPTIONS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
                  </select>
                </div>
                {s3Configured && (
                  <div className="flex items-center h-10 gap-2">
                    <input id="viz-save-to-s3" type="checkbox" checked={saveReportToS3} onChange={(e) => setSaveReportToS3(e.target.checked)} className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
                    <label htmlFor="viz-save-to-s3" className="text-sm text-slate-700 dark:text-slate-300">Save a copy to S3</label>
                  </div>
                )}
                {tab === 'per_lipid_bars' && (
                  <>
                    <div><label className="label-like">Lipids/page</label><select value={lipidsPerPage} onChange={(e) => setLipidsPerPage(Number(e.target.value))} className="input">{LIPIDS_PER_PAGE.map(n => <option key={n} value={n}>{n}</option>)}</select></div>
                    <div className="flex items-center gap-2 pb-2"><input type="checkbox" id="allLipidsTop" checked={allLipids} onChange={(e) => setAllLipids(e.target.checked)} /><label htmlFor="allLipidsTop">All lipids</label></div>
                  </>
                )}
                <button onClick={downloadZip} disabled={zipLoading || !figure && !figures.length} className="btn-secondary text-sm"><LuFileDown /> {zipLoading ? 'Zipping...' : 'ZIP plots'}</button>
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

              <div className="card p-0 overflow-hidden">
                <button onClick={() => setGroupFilterOpen((s) => !s)} className="w-full flex items-center justify-between p-3 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700">
                  <span className="flex items-center gap-2"><LuFilter /> Groups to include ({includedGroups.size} of {groups.length})</span>
                  {groupFilterOpen ? <LuChevronUp /> : <LuChevronDown />}
                </button>
                {groupFilterOpen && (
                  <div className="border-t border-slate-200 dark:border-slate-700 p-4 space-y-3">
                    <div className="flex flex-wrap gap-2">
                      <button onClick={() => setAllGroups(true)} className="btn-secondary text-xs px-2 py-1">Select all</button>
                      <button onClick={() => setAllGroups(false)} className="btn-secondary text-xs px-2 py-1">Comparison only</button>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                      {groups.map((g) => {
                        const disabled = g === groupA || g === groupB
                        const checked = includedGroups.has(g) || disabled
                        return (
                          <label key={g} className={`flex items-center gap-2 text-sm ${disabled ? 'text-slate-400 dark:text-slate-500' : 'text-slate-700 dark:text-slate-200'}`}>
                            <input type="checkbox" checked={checked} disabled={disabled} onChange={() => toggleGroup(g)} />
                            {g} {disabled && <span className="text-xs">(selected)</span>}
                          </label>
                        )
                      })}
                    </div>
                    <div className="flex items-center gap-2 pt-2 border-t border-slate-200 dark:border-slate-700">
                      <input id="rename-samples" type="checkbox" checked={renameSamples} onChange={(e) => setRenameSamples(e.target.checked)} className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
                      <label htmlFor="rename-samples" className="text-sm text-slate-700 dark:text-slate-200">Rename samples to group_R#</label>
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Unchecked groups are excluded from plots and PDF reports. Selected comparison groups cannot be excluded.</p>
                  </div>
                )}
              </div>

              <div className="card p-4">
                {tabControls()}
              </div>

              {figure && !figures.length && (
                <div className="card p-5">
                  <PlotWithDownload
                    data={figure.data}
                    layout={figure.layout}
                    style={{ width: '100%', height: figure.layout?.height ? `${figure.layout.height}px` : (tab === 'heatmap' ? '800px' : ['pls_da','opls_da','biomarker','permanova','chain_space'].includes(tab) ? '700px' : ['functional','food_profile'].includes(tab) ? '650px' : '550px') }}
                    filename={`${tab}_${reportTitle.replace(/\s+/g, '_')}`}
                  />
                </div>
              )}

              {figures.length > 0 && (
                <div className={`grid grid-cols-1 ${tab !== 'chain_space' && tab !== 'biomarker' ? 'xl:grid-cols-2' : ''} gap-4`}>
                  {figures.map((f, i) => (
                    <div key={i} className="card p-4">
                      <PlotWithDownload
                        data={f.data}
                        layout={f.layout}
                        style={{ width: '100%', height: f.layout?.height ? `${f.layout.height}px` : (tab === 'chain_space' || tab === 'biomarker' ? '650px' : '360px') }}
                        filename={`${tab}_${reportTitle.replace(/\s+/g, '_')}_${i}`}
                      />
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
              {ocrStatus && <span className="text-sm text-slate-500 dark:text-slate-400">{ocrStatus}</span>}
              {ocrLoading && <span className="inline-block w-4 h-4 border-2 border-slate-300 border-t-blue-500 rounded-full animate-spin" />}
              <button onClick={() => reportRef.current ? applyOcrLayer(reportRef.current) : window.print()} disabled={ocrLoading} className="btn-primary"><LuPrinter /> Print / Save PDF</button>
              <button onClick={() => setReportOpen(false)} className="btn-secondary"><LuX /> Close</button>
            </div>
          </div>
          <div ref={reportRef} className="max-w-6xl mx-auto space-y-6 relative">
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
