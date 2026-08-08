import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listProjects, createProject, updateProject, deleteProject, listReports, downloadReport, deleteReport } from '../api'
import { useWorkspace } from '../context/WorkspaceContext'
import { Project } from '../types'
import { LuPlus, LuTrash2, LuFolderOpen, LuSearch, LuArrowRight, LuPencil, LuCheck, LuX, LuFileText, LuFiles } from 'react-icons/lu'

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [reportsModalProject, setReportsModalProject] = useState<Project | null>(null)
  const [reports, setReports] = useState<any[]>([])
  const [reportsLoading, setReportsLoading] = useState(false)
  const { setProjectId, setDatasetId } = useWorkspace()
  const navigate = useNavigate()

  const load = async () => {
    const res = await listProjects()
    setProjects(res.data)
  }

  useEffect(() => { load() }, [])

  const create = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    await createProject({ name, description })
    setName('')
    setDescription('')
    load()
  }

  const del = async (id: number) => {
    if (!confirm('Delete this project and all its data?')) return
    await deleteProject(id)
    load()
  }

  const openProject = (p: Project) => {
    setProjectId(p.id)
    setDatasetId('')
    navigate('/data')
  }

  const startEdit = (p: Project) => {
    setEditing(p.id)
    setEditName(p.name)
    setEditDescription(p.description || '')
  }

  const cancelEdit = () => {
    setEditing(null)
    setEditName('')
    setEditDescription('')
  }

  const saveEdit = async (id: number) => {
    if (!editName.trim()) return
    await updateProject(id, { name: editName.trim(), description: editDescription })
    setEditing(null)
    load()
  }

  const openReports = async (p: Project) => {
    setReportsModalProject(p)
    setReportsLoading(true)
    try {
      const res = await listReports(p.id)
      setReports(res.data)
    } catch (err: any) {
      setReports([])
    } finally {
      setReportsLoading(false)
    }
  }

  const closeReports = () => {
    setReportsModalProject(null)
    setReports([])
  }

  const openReport = async (reportId: number) => {
    if (!reportsModalProject) return
    try {
      const res = await downloadReport(reportsModalProject.id, reportId)
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      window.open(url, '_blank')
    } catch (err: any) {
      alert('Failed to open report')
    }
  }

  const delReport = async (reportId: number) => {
    if (!reportsModalProject || !confirm('Delete this saved report?')) return
    try {
      await deleteReport(reportsModalProject.id, reportId)
      openReports(reportsModalProject)
    } catch (err: any) {
      alert('Failed to delete report')
    }
  }

  const filtered = projects.filter((p) => p.name.toLowerCase().includes(search.toLowerCase()) || (p.description || '').toLowerCase().includes(search.toLowerCase()))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Projects</h1>
        <p className="page-subtitle">Manage your metabolomics and lipidomics projects.</p>
      </div>

      <form onSubmit={create} className="card p-5">
        <h3 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2"><LuPlus /> Create Project</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <input placeholder="Project name" value={name} onChange={(e) => setName(e.target.value)} className="input" required />
          <input placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} className="input" />
          <button type="submit" className="btn-primary"><LuPlus /> Create</button>
        </div>
      </form>

      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-slate-900 dark:text-white">Your Projects</h3>
          <div className="relative">
            <LuSearch className="absolute left-3 top-2.5 text-slate-400" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search projects..." className="input pl-9 w-64" />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-700/50 text-slate-500 dark:text-slate-300 uppercase text-xs">
              <tr>
                <th className="text-left p-3 font-semibold">Project</th>
                <th className="text-left p-3 font-semibold">Description</th>
                <th className="text-left p-3 font-semibold">Created</th>
                <th className="text-right p-3 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
              {filtered.map((p) => (
                <tr key={p.id} className="group hover:bg-slate-50 dark:hover:bg-slate-700/30">
                  {editing === p.id ? (
                    <>
                      <td className="p-3">
                        <input value={editName} onChange={(e) => setEditName(e.target.value)} className="input w-full" autoFocus />
                      </td>
                      <td className="p-3">
                        <input value={editDescription} onChange={(e) => setEditDescription(e.target.value)} className="input w-full" />
                      </td>
                      <td className="p-3 text-slate-500 dark:text-slate-400">{new Date(p.created_at).toLocaleDateString()}</td>
                      <td className="p-3 text-right">
                        <button onClick={() => saveEdit(p.id)} className="p-2 rounded-lg text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 mr-1" title="Save"><LuCheck /></button>
                        <button onClick={cancelEdit} className="p-2 rounded-lg text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700" title="Cancel"><LuX /></button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="p-3">
                        <button
                          onClick={() => openProject(p)}
                          className="font-medium text-slate-900 dark:text-white flex items-center gap-2 hover:text-indigo-600 dark:hover:text-indigo-400"
                          title="Open project"
                        >
                          <LuFolderOpen className="text-indigo-500" /> {p.name} <LuArrowRight className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </button>
                      </td>
                      <td className="p-3 text-slate-600 dark:text-slate-300">{p.description || '-'}</td>
                      <td className="p-3 text-slate-500 dark:text-slate-400">{new Date(p.created_at).toLocaleDateString()}</td>
                      <td className="p-3 text-right opacity-0 group-hover:opacity-100 transition-opacity">
                        <button onClick={() => openReports(p)} className="p-2 rounded-lg text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 mr-1" title="Saved reports"><LuFiles /></button>
                        <button onClick={() => startEdit(p)} className="p-2 rounded-lg text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 mr-1" title="Rename"><LuPencil /></button>
                        <button onClick={() => del(p.id)} className="p-2 rounded-lg text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20" title="Delete"><LuTrash2 /></button>
                      </td>
                    </>
                  )}
                </tr>
              ))}
              {filtered.length === 0 && <tr><td colSpan={4} className="p-6 text-center text-slate-500 dark:text-slate-400">No projects found.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {reportsModalProject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white dark:bg-slate-900 rounded-xl shadow-xl w-full max-w-3xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-700">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2"><LuFileText /> Saved Reports: {reportsModalProject.name}</h3>
              <button onClick={closeReports} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700"><LuX /></button>
            </div>
            <div className="p-4 overflow-auto flex-1">
              {reportsLoading ? (
                <div className="text-center text-slate-500 dark:text-slate-400">Loading...</div>
              ) : reports.length === 0 ? (
                <div className="text-center text-slate-500 dark:text-slate-400 py-8">No saved reports yet.</div>
              ) : (
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50 dark:bg-slate-700/50 text-slate-500 dark:text-slate-300 uppercase text-xs">
                    <tr>
                      <th className="text-left p-2">Report</th>
                      <th className="text-left p-2">Type</th>
                      <th className="text-left p-2">Created</th>
                      <th className="text-right p-2">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                    {reports.map((r) => (
                      <tr key={r.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                        <td className="p-2 text-slate-900 dark:text-white">{r.name}</td>
                        <td className="p-2 text-slate-600 dark:text-slate-300 capitalize">{r.report_type}</td>
                        <td className="p-2 text-slate-500 dark:text-slate-400">{new Date(r.created_at).toLocaleString()}</td>
                        <td className="p-2 text-right">
                          <button onClick={() => openReport(r.id)} className="p-1.5 rounded-lg text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 mr-1" title="Open"><LuFileText /></button>
                          <button onClick={() => delReport(r.id)} className="p-1.5 rounded-lg text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20" title="Delete"><LuTrash2 /></button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
