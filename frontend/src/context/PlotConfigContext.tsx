import { createContext, useContext, useState, ReactNode } from 'react'

export interface PlotStyle {
  engine: 'plotly' | 'ggplot2' | 'publication'
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
}

export const DEFAULT_PLOT_STYLE: PlotStyle = {
  engine: 'plotly',
  fontFamily: 'Inter Tight, Inter, Arial, sans-serif',
  titleSize: 16,
  axisLabelSize: 12,
  tickSize: 11,
  markerSize: 10,
  showGridlines: true,
  paperBg: '#ffffff',
  plotBg: '#ffffff',
  upColor: '#c44e52',
  downColor: '#2e6575',
  notSignificantColor: '#a0aec0',
  groupColors: ['#2e6575', '#7eb5c9', '#e9a47f', '#f2cc8f', '#81b29a', '#9d8189'],
  heatmapColorscale: 'RdBu_r',
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
  return {
    engine: style.engine,
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
  }
}
