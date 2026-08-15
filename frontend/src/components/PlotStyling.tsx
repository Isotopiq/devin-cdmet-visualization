import { usePlotConfig } from '../context/PlotConfigContext'

export default function PlotStyling() {
  const { style, setStyle } = usePlotConfig()

  const update = (key: keyof typeof style, value: any) => {
    setStyle((s) => ({ ...s, [key]: value }))
  }

  const updateGroupColor = (i: number, color: string) => {
    const next = [...style.groupColors]
    next[i] = color
    setStyle((s) => ({ ...s, groupColors: next }))
  }

  const addGroupColor = () => setStyle((s) => ({ ...s, groupColors: [...s.groupColors, '#999999'] }))

  const engines = [
    { value: 'plotly', label: 'Plotly' },
    { value: 'r', label: 'R (static)' },
    { value: 'publication', label: 'Publication' },
    { value: 'ggplot2', label: 'Ggplot2' },
  ]

  const colorscales = [
    { value: 'RdBu_r', label: 'Red-Blue (MetaboAnalyst)' },
    { value: 'RdBu', label: 'Red-Blue' },
    { value: 'Viridis', label: 'Viridis' },
    { value: 'Plasma', label: 'Plasma' },
    { value: 'Blues', label: 'Blues' },
    { value: 'YlOrRd', label: 'Yellow-Orange-Red' },
  ]

  return (
    <div className="card p-4 space-y-4 w-full lg:w-72 flex-shrink-0">
      <div className="flex items-center gap-2">
        <span className="text-slate-500 text-lg">🎨</span>
        <h3 className="font-semibold text-slate-900 dark:text-white">Plot styling</h3>
      </div>

      <div>
        <label className="label-like text-xs">Plotting engine</label>
        <div className="flex rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden mt-1">
          {engines.map((e) => (
            <button
              key={e.value}
              onClick={() => update('engine', e.value)}
              className={`flex-1 text-xs py-1.5 ${style.engine === e.value ? 'bg-slate-800 text-white' : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300'}`}
            >
              {e.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="label-like text-xs">Font family</label>
        <select value={style.fontFamily} onChange={(e) => update('fontFamily', e.target.value)} className="input text-sm mt-1">
          <option value="Inter Tight, Inter, Arial, sans-serif">Inter Tight</option>
          <option value="Arial, sans-serif">Arial</option>
          <option value="Georgia, serif">Georgia</option>
          <option value="Courier New, monospace">Courier New</option>
        </select>
      </div>

      {[
        { key: 'titleSize', label: 'Title size', min: 10, max: 28 },
        { key: 'axisLabelSize', label: 'Axis label size', min: 8, max: 20 },
        { key: 'tickSize', label: 'Tick size (max)', min: 8, max: 18 },
        { key: 'markerSize', label: 'Marker size', min: 4, max: 24 },
      ].map(({ key, label, min, max }) => (
        <div key={key}>
          <div className="flex justify-between text-xs text-slate-600 dark:text-slate-300">
            <label className="label-like">{label}</label>
            <span>{(style as any)[key]}</span>
          </div>
          <input
            type="range"
            min={min}
            max={max}
            value={(style as any)[key]}
            onChange={(e) => update(key as any, Number(e.target.value))}
            className="w-full accent-slate-800"
          />
        </div>
      ))}

      <div>
        <label className="label-like text-xs">Heatmap colorscale</label>
        <select value={style.heatmapColorscale} onChange={(e) => update('heatmapColorscale', e.target.value)} className="input text-sm mt-1">
          {colorscales.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="gridlines"
          checked={style.showGridlines}
          onChange={(e) => update('showGridlines', e.target.checked)}
          className="rounded border-slate-300"
        />
        <label htmlFor="gridlines" className="text-sm text-slate-700 dark:text-slate-200">Show gridlines</label>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label-like text-xs">Paper BG</label>
          <input type="color" value={style.paperBg} onChange={(e) => update('paperBg', e.target.value)} className="w-full h-8 mt-1" />
        </div>
        <div>
          <label className="label-like text-xs">Plot BG</label>
          <input type="color" value={style.plotBg} onChange={(e) => update('plotBg', e.target.value)} className="w-full h-8 mt-1" />
        </div>
      </div>

      <div>
        <label className="label-like text-xs">Group colors</label>
        <div className="flex flex-wrap gap-2 mt-1">
          {style.groupColors.map((c, i) => (
            <input key={i} type="color" value={c} onChange={(e) => updateGroupColor(i, e.target.value)} className="w-8 h-8" />
          ))}
          <button onClick={addGroupColor} className="w-8 h-8 rounded border border-slate-300 dark:border-slate-600 text-slate-500 flex items-center justify-center">+</button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div>
          <label className="label-like text-xs">Up</label>
          <input type="color" value={style.upColor} onChange={(e) => update('upColor', e.target.value)} className="w-full h-8 mt-1" />
        </div>
        <div>
          <label className="label-like text-xs">Down</label>
          <input type="color" value={style.downColor} onChange={(e) => update('downColor', e.target.value)} className="w-full h-8 mt-1" />
        </div>
        <div>
          <label className="label-like text-xs">NS</label>
          <input type="color" value={style.notSignificantColor} onChange={(e) => update('notSignificantColor', e.target.value)} className="w-full h-8 mt-1" />
        </div>
      </div>
    </div>
  )
}
