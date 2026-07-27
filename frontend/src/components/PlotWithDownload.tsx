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

export default function PlotWithDownload({ data, layout, style, filename = 'plot.png', config }: Props) {
  const [graphDiv, setGraphDiv] = useState<any>(null)

  const downloadPng = useCallback(async () => {
    if (!graphDiv) return
    const width = layout?.width || (style?.width ? Number(style.width) : 1200)
    const height = layout?.height || (style?.height ? Number(style.height) : 700)
    try {
      const url = await Plotly.toImage(graphDiv, { format: 'png', width, height })
      const a = document.createElement('a')
      a.href = url
      a.download = filename.endsWith('.png') ? filename : `${filename}.png`
      a.click()
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
        onInitialized={(figure: any, gd: any) => setGraphDiv(gd)}
      />
    </div>
  )
}
