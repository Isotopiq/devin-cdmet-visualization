import axios from 'axios'

const API = axios.create({
  baseURL: '/api',
})

API.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export default API

export const health = () => API.get('/health')
export const register = (data: { email: string; password: string }) => API.post('/auth/register', data)
export const login = (data: { username: string; password: string }) => API.post('/auth/token', data, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
export const me = () => API.get('/auth/me')

export const listProjects = () => API.get('/projects/')
export const createProject = (data: { name: string; description?: string }) => API.post('/projects/', data)
export const deleteProject = (id: number) => API.delete(`/projects/${id}`)

export const listFiles = (projectId: number) => API.get(`/files/${projectId}`)
export const uploadFile = (projectId: number, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return API.post(`/files/${projectId}/upload`, form)
}
export const deleteFile = (id: number) => API.delete(`/files/${id}`)

export const previewImport = (fileId: number, sheet?: string) => API.get(`/import/${fileId}/preview`, { params: { sheet } })
export const importDataset = (fileId: number, featureType: string) => API.post(`/import/${fileId}/import`, null, { params: { feature_type: featureType } })

export const listDatasets = (projectId: number) => API.get(`/analysis/${projectId}/datasets`)
export const preprocess = (projectId: number, datasetId: number, params: any) => API.post(`/analysis/${projectId}/dataset/${datasetId}/preprocess`, params)

export const runStats = (projectId: number, datasetId: number, params: any) => API.post(`/stats/${projectId}/dataset/${datasetId}/stats`, params)
export const generatePlot = (projectId: number, datasetId: number, params: any) => API.post(`/plots/${projectId}/dataset/${datasetId}/plot`, params)

export const runIsotope = (projectId: number, datasetId: number, params: any) => API.post(`/isotope/${projectId}/dataset/${datasetId}/isotope`, params)
export const buildPathway = (projectId: number, datasetId: number, params: any) => API.post(`/pathways/${projectId}/dataset/${datasetId}/pathway`, params)
