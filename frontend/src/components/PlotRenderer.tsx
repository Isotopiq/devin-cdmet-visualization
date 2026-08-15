import PlotWithDownload from './PlotWithDownload'
import StaticPlot from './StaticPlot'

interface Props {
  figure: any
  filename?: string
  style?: React.CSSProperties
  className?: string
}

export function isStaticFigure(figure: any): boolean {
  return figure && typeof figure === 'object' && figure.format === 'png' && typeof figure.image === 'string'
}

export default function PlotRenderer({ figure, filename, style, className }: Props) {
  if (isStaticFigure(figure)) {
    return (
      <div className={className} style={style}>
        <StaticPlot figure={figure} filename={filename} />
      </div>
    )
  }
  return (
    <PlotWithDownload
      data={figure?.data || []}
      layout={figure?.layout || {}}
      style={style}
      filename={filename}
      config={figure?.config}
    />
  )
}
