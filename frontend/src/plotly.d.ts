declare module 'react-plotly.js' {
  import * as React from 'react'
  import { Layout, Config, Data } from 'plotly.js'

  export interface PlotParams {
    data: Data[]
    layout?: Partial<Layout>
    config?: Partial<Config>
    style?: React.CSSProperties
    className?: string
    useResizeHandler?: boolean
    onInitialized?: (figure: any, graphDiv: any) => void
    onUpdate?: (figure: any, graphDiv: any) => void
    onPurge?: (figure: any, graphDiv: any) => void
    onError?: (err: Error) => void
  }

  export default class Plot extends React.Component<PlotParams> {}
}
