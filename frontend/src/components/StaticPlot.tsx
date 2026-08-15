import { useState } from 'react'
import { LuDownload } from 'react-icons/lu'

interface Props {
  figure: { image: string; width?: number; height?: number; keep_title?: boolean }
  filename?: string
}

export default function StaticPlot({ figure, filename = 'plot.png' }: Props) {
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)

  const download = () => {
    const a = document.createElement('a')
    a.href = figure.image
    a.download = filename.endsWith('.png') ? filename : `${filename}.png`
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <button onClick={download} className="btn-secondary text-xs"><LuDownload /> Download PNG</button>
      </div>
      {!loaded && !error && <div className="h-96 animate-pulse bg-slate-100 dark:bg-slate-800 rounded-lg" />}
      {error ? (
        <div className="text-sm text-red-600 dark:text-red-400">Failed to load static plot.</div>
      ) : (
        <img
          src={figure.image}
          alt="Generated plot"
          className="w-full h-auto rounded-lg border border-slate-200 dark:border-slate-700"
          onLoad={() => setLoaded(true)}
          onError={() => setError(true)}
        />
      )}
    </div>
  )
}
