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

API.interceptors.response.use(
  (res) => res,
  (error) => {
    const status = error?.response?.status
    const url = error?.config?.url
    if (status === 401 && url && !['/auth/me', '/auth/token'].includes(url.split('?')[0])) {
      localStorage.removeItem('token')
      delete API.defaults.headers.common['Authorization']
      window.location.href = '/'
    }
    return Promise.reject(error)
  }
)

export default API

export const health = () => API.get('/health')
export const register = (data: { email: string; password: string }) => API.post('/auth/register', data)
export const login = (data: { username: string; password: string }) => {
  const params = new URLSearchParams()
  params.append('username', data.username)
  params.append('password', data.password)
  return API.post('/auth/token', params, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
}
export const me = () => API.get('/auth/me')
export const updateMe = (data: { email?: string; name?: string; password?: string }) => API.patch('/auth/me', data)
export const uploadAvatar = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return API.post('/auth/me/avatar', form)
}
export const getAvatar = (userId: number, rev?: string) =>
  API.get(`/auth/avatar/${userId}`, { params: rev ? { v: rev } : {}, responseType: 'blob' })

export const listProjects = () => API.get('/projects/')
export const createProject = (data: { name: string; description?: string }) => API.post('/projects/', data)
export const updateProject = (id: number, data: { name?: string; description?: string }) => API.patch(`/projects/${id}`, data)
export const deleteProject = (id: number) => API.delete(`/projects/${id}`)

export const listFiles = (projectId: number) => API.get(`/files/${projectId}`)
export const uploadFile = (projectId: number, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return API.post(`/files/${projectId}/upload`, form)
}
export const deleteFile = (id: number) => API.delete(`/files/${id}`)

export const previewImport = (fileId: number, sheet?: string, alignmentFileId?: number) => API.get(`/import/${fileId}/preview`, { params: { sheet, alignment_file_id: alignmentFileId } })
export const importDataset = (fileId: number, featureType: string, alignmentFileId?: number, sheet?: string) => API.post(`/import/${fileId}/import`, null, { params: { feature_type: featureType, alignment_file_id: alignmentFileId, sheet } })

export const listDatasets = (projectId: number) => API.get(`/analysis/${projectId}/datasets`)
export const listAllDatasets = (params?: { project_ids?: number[]; limit?: number; offset?: number }) => {
  const qs = new URLSearchParams()
  if (params?.project_ids) {
    params.project_ids.forEach((id) => qs.append('project_ids', String(id)))
  }
  if (params?.limit !== undefined) qs.append('limit', String(params.limit))
  if (params?.offset !== undefined) qs.append('offset', String(params.offset))
  return API.get(`/analysis/datasets/all?${qs.toString()}`)
}
export const combineDatasets = (projectId: number, data: any) =>
  API.post(`/analysis/${projectId}/datasets/combine`, data)
export const getDataset = (projectId: number, datasetId: number) => API.get(`/analysis/${projectId}/dataset/${datasetId}`)
export const deleteDataset = (projectId: number, datasetId: number) => API.delete(`/analysis/${projectId}/dataset/${datasetId}`)
export const preprocess = (projectId: number, datasetId: number, params: any) => API.post(`/analysis/${projectId}/dataset/${datasetId}/preprocess`, params)
export const updateSampleGroups = (projectId: number, datasetId: number, sampleMetadata: Record<string, string>) =>
  API.put(`/analysis/${projectId}/dataset/${datasetId}/sample_groups`, { sample_metadata: sampleMetadata })

export const listAnalyses = (projectId: number) => API.get(`/analysis/${projectId}/analyses`)
export const deleteAnalysis = (projectId: number, analysisId: number) => API.delete(`/analysis/${projectId}/analyses/${analysisId}`)

export const runStats = (projectId: number, datasetId: number, params: any) => API.post(`/stats/${projectId}/dataset/${datasetId}/stats`, params)
export const generatePlot = (projectId: number, datasetId: number, params: any) => API.post(`/plots/${projectId}/dataset/${datasetId}/plot`, params)
export const generateReport = (projectId: number, datasetId: number, params: any) => API.post(`/plots/${projectId}/dataset/${datasetId}/report`, params)

export const runIsotope = (projectId: number, datasetId: number, params: any) => API.post(`/isotope/${projectId}/dataset/${datasetId}/isotope`, params)
export const searchBiGGModels = (q?: string, limit: number = 20) => API.get('/isotope/bigg_models', { params: { q, limit } })
export const searchGEMModels = (q?: string, limit: number = 20) => API.get('/isotope/gem_models', { params: { q, limit } })
export const loadModelNetwork = (source: string, modelId: string) => API.get(`/isotope/models/${source}/${modelId}/network`)
export const buildPathway = (projectId: number, datasetId: number, params: any) => API.post(`/pathways/${projectId}/dataset/${datasetId}/pathway`, params)
export const getPathwayJob = (jobId: string) => API.get(`/pathways/job/${jobId}`)

export const getSettings = () => API.get('/admin/settings')
export const updateSettings = (data: any) => API.put('/admin/settings', data)
export const uploadLogo = (logoType: 'login' | 'dashboard', file: File) => {
  const form = new FormData()
  form.append('file', file)
  return API.post(`/admin/logo/${logoType}`, form)
}
export const uploadFavicon = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return API.post('/admin/favicon', form)
}
export const getSMTPSettings = () => API.get('/admin/settings/smtp')
export const testSMTP = (data: any) => API.post('/admin/settings/smtp/test', data)
export const forgotPassword = (email: string) => API.post('/auth/forgot-password', { email })
export const resetPassword = (token: string, newPassword: string) => API.post('/auth/reset-password', { token, new_password: newPassword })
export const listUsers = () => API.get('/admin/users')
export const createUser = (data: { email: string; name?: string; password: string; is_admin?: boolean; is_active?: boolean }) => API.post('/admin/users', data)
export const updateUser = (id: number, data: any) => API.patch(`/admin/users/${id}`, data)
export const deleteUser = (id: number) => API.delete(`/admin/users/${id}`)
export const listLogs = (userId?: number) => API.get('/admin/logs', { params: userId ? { user_id: userId } : {} })
export const clearLogs = (userId?: number) => API.delete('/admin/logs', { params: userId ? { user_id: userId } : {} })
export const getAnalysisCount = () => API.get('/admin/analyses/count')
export const resetAnalyses = () => API.post('/admin/analyses/reset')
export const exportDataset = (projectId: number, datasetId: number, format: 'metaboanalyst' | 'lipidone') =>
  API.get(`/analysis/${projectId}/dataset/${datasetId}/export`, { params: { format }, responseType: 'blob' })
export const getQC = (projectId: number, datasetId: number, selectedGroups: string[] = []) => {
  const params = new URLSearchParams()
  selectedGroups.forEach((g) => params.append('selected_groups', g))
  return API.get(`/analysis/${projectId}/dataset/${datasetId}/qc`, { params })
}
export const exportQCExcel = (projectId: number, datasetId: number, selectedGroups: string[] = []) => {
  const params = new URLSearchParams()
  selectedGroups.forEach((g) => params.append('selected_groups', g))
  return API.get(`/analysis/${projectId}/dataset/${datasetId}/qc/excel`, { params, responseType: 'blob' })
}
export const exportQCPdf = (projectId: number, datasetId: number, data: { selected_groups?: string[]; primary_comparison?: string; prepared_for?: string; prepared_by?: string; report_contents?: string; report_type?: string; subtitle?: string; description?: string; cover_style?: string; font_family?: string; plot_layout?: Record<string, string> }) =>
  API.post(`/analysis/${projectId}/dataset/${datasetId}/qc/pdf`, data, { responseType: 'blob' })
export const generatePDFReport = (projectId: number, datasetId: number, data: any) =>
  API.post(`/plots/${projectId}/dataset/${datasetId}/report/pdf`, data, { responseType: 'blob' })
