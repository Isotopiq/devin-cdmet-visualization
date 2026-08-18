import { createContext, useContext, useState, ReactNode } from 'react'

export interface PlotStyle {
  engine: 'plotly' | 'r' | 'publication' | 'ggplot2'
  plotStyle: 'default' | 'publication' | 'lipidone'
  fontFamily: string
  titleSize: number
  axisLabelSize: number
  tickSize: number
  markerSize: number
  showGridlines: boolean
  paperBg: string
  plotBg: string
  upColor: string
  downColor: string
  notSignificantColor: string
  groupColors: string[]
  heatmapColorscale: string
  rTheme: 'publication' | 'minimal' | 'bw'
  rResolution: 120 | 150 | 300
  rBarWidth: number
  rFont: string
  rTitleBold: boolean
}

export const DEFAULT_PLOT_STYLE: PlotStyle = {
  engine: 'plotly',
  plotStyle: 'default',
  fontFamily: 'Inter Tight, Inter, Arial, sans-serif',
  titleSize: 16,
  axisLabelSize: 12,
  tickSize: 11,
  markerSize: 10,
  showGridlines: true,
  paperBg: '#ffffff',
  plotBg: '#ffffff',
  upColor: '#e15759',
  downColor: '#4e79a7',
  notSignificantColor: '#a0aec0',
  groupColors: ['#4e79a7', '#e15759', '#f28e2c', '#76b7b2', '#59a14f', '#edc949'],
  heatmapColorscale: 'RdBu_r',
  rTheme: 'publication',
  rResolution: 150,
  rBarWidth: 0.65,
  rFont: 'Liberation Sans',
  rTitleBold: true,
}

export const DEFAULT_INCLUDE_PLOTS: Record<string, boolean> = {
  pca: true,
  pls_da: true,
  opls_da: true,
  biomarker: true,
  permanova: true,
  volcano: true,
  heatmap: true,
  lipid_classes: true,
  per_lipid_bars: true,
  chain_space: true,
  outlier: true,
  functional: true,
  food_profile: true,
}

interface PlotConfigCtx {
  style: PlotStyle
  setStyle: (s: PlotStyle | ((prev: PlotStyle) => PlotStyle)) => void
  reportTitle: string
  setReportTitle: (t: string) => void
  includePlots: Record<string, boolean>
  setIncludePlots: React.Dispatch<React.SetStateAction<Record<string, boolean>>>
}

const PlotConfigContext = createContext<PlotConfigCtx | undefined>(undefined)

export function PlotConfigProvider({ children }: { children: ReactNode }) {
  const [style, setStyle] = useState<PlotStyle>(DEFAULT_PLOT_STYLE)
  const [reportTitle, setReportTitle] = useState('Untitled analysis')
  const [includePlots, setIncludePlots] = useState<Record<string, boolean>>(DEFAULT_INCLUDE_PLOTS)

  return (
    <PlotConfigContext.Provider value={{ style, setStyle, reportTitle, setReportTitle, includePlots, setIncludePlots }}>
      {children}
    </PlotConfigContext.Provider>
  )
}

export function usePlotConfig() {
  const ctx = useContext(PlotConfigContext)
  if (!ctx) throw new Error('usePlotConfig must be used inside PlotConfigProvider')
  return ctx
}

export function styleToBackend(style: PlotStyle): Record<string, any> {
  let engine = style.engine
  let plotStyle = style.plotStyle
  // Legacy engine values that combined renderer + style
  if (engine === 'publication') {
    engine = 'plotly'
    plotStyle = plotStyle === 'default' ? 'publication' : plotStyle
  } else if (engine === 'ggplot2') {
    engine = 'r'
    plotStyle = plotStyle === 'default' ? 'publication' : plotStyle
  }
  return {
    engine,
    plot_style: plotStyle,
    font_family: style.fontFamily,
    title_size: style.titleSize,
    axis_label_size: style.axisLabelSize,
    tick_size: style.tickSize,
    marker_size: style.markerSize,
    show_gridlines: style.showGridlines,
    paper_bgcolor: style.paperBg,
    plot_bgcolor: style.plotBg,
    up_color: style.upColor,
    down_color: style.downColor,
    non_significant_color: style.notSignificantColor,
    group_colors: style.groupColors,
    heatmap_colorscale: style.heatmapColorscale,
    r_theme: style.rTheme,
    r_resolution: style.rResolution,
    r_bar_width: style.rBarWidth,
    r_font: style.rFont,
    r_title_bold: style.rTitleBold,
  }
}
