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

      {style.engine !== 'plotly' && (
        <div className="space-y-3 border border-slate-200 dark:border-slate-700 rounded-lg p-3">
          <div>
            <label className="label-like text-xs">R theme</label>
            <select value={style.rTheme} onChange={(e) => update('rTheme', e.target.value as any)} className="input text-sm mt-1">
              <option value="publication">Publication</option>
              <option value="minimal">Minimal</option>
              <option value="bw">Black & white</option>
            </select>
          </div>
          <div>
            <label className="label-like text-xs">R font</label>
            <select value={style.rFont} onChange={(e) => update('rFont', e.target.value)} className="input text-sm mt-1">
              <option value="Inter">Inter</option>
              <option value="Liberation Sans">Liberation Sans</option>
              <option value="Roboto">Roboto</option>
              <option value="Open Sans">Open Sans</option>
              <option value="Lato">Lato</option>
              <option value="Montserrat">Montserrat</option>
              <option value="Quicksand">Quicksand</option>
              <option value="Fira Code">Fira Code</option>
              <option value="JetBrains Mono">JetBrains Mono</option>
              <option value="Noto Sans">Noto Sans</option>
              <option value="Source Sans 3">Source Sans 3</option>
              <option value="Roboto Slab">Roboto Slab</option>
              <option value="DejaVu Sans">DejaVu Sans</option>
              <option value="FreeSans">FreeSans</option>
              <option value="Droid Sans Fallback">Droid Sans Fallback</option>
            </select>
            <div className="mt-2 p-2 rounded bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-center">
              <span style={{ fontFamily: style.rFont }} className="text-sm text-slate-800 dark:text-slate-100">AaBbYyZz 0123</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="rTitleBold"
              checked={style.rTitleBold}
              onChange={(e) => update('rTitleBold', e.target.checked)}
              className="rounded border-slate-300"
            />
            <label htmlFor="rTitleBold" className="text-sm text-slate-700 dark:text-slate-200">Bold compound title</label>
          </div>
          <div>
            <label className="label-like text-xs">R resolution (DPI)</label>
            <select value={style.rResolution} onChange={(e) => update('rResolution', Number(e.target.value) as any)} className="input text-sm mt-1">
              <option value={120}>120</option>
              <option value={150}>150</option>
              <option value={300}>300</option>
            </select>
          </div>
          <div>
            <div className="flex justify-between text-xs text-slate-600 dark:text-slate-300">
              <label className="label-like">Bar width</label>
              <span>{style.rBarWidth}</span>
            </div>
            <input
              type="range"
              min={0.2}
              max={0.9}
              step={0.05}
              value={style.rBarWidth}
              onChange={(e) => update('rBarWidth', Number(e.target.value))}
              className="w-full accent-slate-800"
            />
          </div>
        </div>
      )}

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
