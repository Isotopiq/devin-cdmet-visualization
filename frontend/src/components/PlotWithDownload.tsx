import { useState, useCallback } from 'react'
import Plot from 'react-plotly.js'
import Plotly from 'plotly.js/dist/plotly'
import { LuDownload } from 'react-icons/lu'

interface Props {
  data: any[]
  layout?: any
  style?: React.CSSProperties
  filename?: string
  config?: any
}

function parseDim(value: any): number | null {
  if (typeof value === 'number' && !Number.isNaN(value) && value > 0) {
    return value
  }
  if (typeof value === 'string') {
    const px = value.match(/^(\d+(?:\.\d+)?)px?$/i)
    if (px) return parseFloat(px[1])
  }
  return null
}

export default function PlotWithDownload({ data, layout, style, filename = 'plot.png', config }: Props) {
  const [graphDiv, setGraphDiv] = useState<HTMLDivElement | null>(null)

  const downloadPng = useCallback(async () => {
    if (!graphDiv) return
    try {
      const rect = graphDiv.getBoundingClientRect()
      const width = parseDim(layout?.width) || parseDim(style?.width) || Math.round(rect.width) || 1200
      const height = parseDim(layout?.height) || parseDim(style?.height) || Math.round(rect.height) || 700

      const url = await Plotly.toImage(graphDiv, {
        format: 'png',
        width,
        height,
        scale: 2,
      })

      const a = document.createElement('a')
      a.href = url
      a.download = filename.endsWith('.png') ? filename : `${filename}.png`
      document.body.appendChild(a)
      a.click()
      a.remove()
    } catch (err) {
      console.error('PNG export failed', err)
    }
  }, [graphDiv, layout, style, filename])

  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <button onClick={downloadPng} disabled={!graphDiv} className="btn-secondary text-xs"><LuDownload /> Download PNG</button>
      </div>
      <Plot
        data={data}
        layout={layout}
        style={style}
        config={config}
        onInitialized={(_figure: any, gd: any) => setGraphDiv(gd)}
      />
    </div>
  )
}
