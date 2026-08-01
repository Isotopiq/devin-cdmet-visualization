import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listProjects, createProject, deleteProject } from '../api'
import { useWorkspace } from '../context/WorkspaceContext'
import { Project } from '../types'
import { LuPlus, LuTrash2, LuFolderOpen, LuSearch, LuArrowRight } from 'react-icons/lu'

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [search, setSearch] = useState('')
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
                  <td className="p-3 text-right">
                    <button onClick={() => del(p.id)} className="p-2 rounded-lg text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20" title="Delete"><LuTrash2 /></button>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && <tr><td colSpan={4} className="p-6 text-center text-slate-500 dark:text-slate-400">No projects found.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
