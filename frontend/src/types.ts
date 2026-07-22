export interface User {
  id: number
  email: string
  is_active: boolean
  created_at: string
}

export interface Project {
  id: number
  name: string
  description?: string
  owner_id: number
  created_at: string
  updated_at: string
}

export interface UploadedFile {
  id: number
  project_id: number
  original_name: string
  stored_name: string
  file_type?: string
  detected_format?: string
  sheets: string[]
  selected_sheet?: string
  status: string
  created_at: string
}

export interface Dataset {
  id: number
  project_id: number
  source_file_id?: number
  name: string
  feature_type: string
  data_matrix?: Record<string, any>
  sample_metadata?: Record<string, string>
  feature_metadata?: any[]
  processing_history?: any[]
  created_at: string
}

export interface Analysis {
  id: number
  project_id: number
  dataset_id: number
  name: string
  analysis_type: string
  created_at: string
}

export interface ImportPreview {
  detected_format?: string
  sheets: string[]
  columns: string[]
  sample_columns: string[]
  feature_columns: string[]
  row_count: number
  suggested_mapping: Record<string, string>
}
