import { useEffect, useState } from 'react'
import { listProjects, createProject, deleteProject } from '../api'
import { Project } from '../types'

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const load = async () => {
    const res = await listProjects()
    setProjects(res.data)
  }

  useEffect(() => { load() }, [])

  const create = async (e: React.FormEvent) => {
    e.preventDefault()
    await createProject({ name, description })
    setName('')
    setDescription('')
    load()
  }

  const del = async (id: number) => {
    await deleteProject(id)
    load()
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4 text-gray-900 dark:text-white">Projects</h1>
      <form onSubmit={create} className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow mb-6 grid grid-cols-1 md:grid-cols-3 gap-4">
        <input placeholder="Project name" value={name} onChange={(e) => setName(e.target.value)} className="border rounded-lg p-2" required />
        <input placeholder="Description" value={description} onChange={(e) => setDescription(e.target.value)} className="border rounded-lg p-2" />
        <button type="submit" className="bg-blue-600 text-white rounded-lg p-2 hover:bg-blue-700">Create Project</button>
      </form>
      <div className="space-y-3">
        {projects.map((p) => (
          <div key={p.id} className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow flex justify-between items-center">
            <div>
              <div className="font-semibold text-gray-900 dark:text-white">{p.name}</div>
              <div className="text-sm text-gray-500">{p.description}</div>
            </div>
            <button onClick={() => del(p.id)} className="text-red-600 hover:underline">Delete</button>
          </div>
        ))}
      </div>
    </div>
  )
}
