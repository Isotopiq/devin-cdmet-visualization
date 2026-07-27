import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { listProjects, listDatasets } from '../api'
import { Project, Dataset } from '../types'

interface WorkspaceCtx {
  projects: Project[]
  projectId: number | ''
  setProjectId: (id: number | '') => void
  datasets: Dataset[]
  datasetId: number | ''
  setDatasetId: (id: number | '') => void
  selectedDataset: Dataset | null
  loading: boolean
  refreshProjects: () => Promise<void>
  refreshDatasets: () => Promise<void>
}

const WorkspaceContext = createContext<WorkspaceCtx | undefined>(undefined)

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState<number | ''>(() => {
    const saved = localStorage.getItem('projectId')
    return saved ? Number(saved) : ''
  })
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [datasetId, setDatasetId] = useState<number | ''>(() => {
    const saved = localStorage.getItem('datasetId')
    return saved ? Number(saved) : ''
  })
  const [loading, setLoading] = useState(false)

  const refreshProjects = async () => {
    setLoading(true)
    try {
      const res = await listProjects()
      setProjects(res.data)
    } finally {
      setLoading(false)
    }
  }

  const refreshDatasets = async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const res = await listDatasets(Number(projectId))
      setDatasets(res.data)
      const exists = res.data.find((d: Dataset) => d.id === datasetId)
      if (!exists) setDatasetId('')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshProjects()
  }, [])

  useEffect(() => {
    if (projectId) {
      localStorage.setItem('projectId', String(projectId))
      setLoading(true)
      listDatasets(Number(projectId))
        .then((res) => {
          setDatasets(res.data)
          const exists = res.data.find((d: Dataset) => d.id === datasetId)
          if (!exists) setDatasetId('')
        })
        .finally(() => setLoading(false))
    } else {
      localStorage.removeItem('projectId')
      setDatasets([])
      setDatasetId('')
    }
  }, [projectId])

  useEffect(() => {
    if (datasetId) localStorage.setItem('datasetId', String(datasetId))
    else localStorage.removeItem('datasetId')
  }, [datasetId])

  const selectedDataset = datasets.find((d) => d.id === datasetId) || null

  return (
    <WorkspaceContext.Provider value={{
      projects, projectId, setProjectId,
      datasets, datasetId, setDatasetId,
      selectedDataset, loading, refreshProjects,
      refreshDatasets
    }}>
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext)
  if (!ctx) throw new Error('useWorkspace must be used within WorkspaceProvider')
  return ctx
}
