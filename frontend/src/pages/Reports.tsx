import { useEffect, useState } from 'react'
import { listProjects } from '../api'
import { Project } from '../types'

export default function Reports() {
  const [projects, setProjects] = useState<Project[]>([])

  useEffect(() => { listProjects().then((r) => setProjects(r.data)) }, [])

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4 text-gray-900 dark:text-white">Reports</h1>
      <p className="text-gray-600 dark:text-gray-300 mb-4">Project-level reports combining import summary, processing history, statistical results, and exported plots will be generated here.</p>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
        <h3 className="font-semibold mb-2 text-gray-900 dark:text-white">Available Projects</h3>
        {projects.map((p) => <div key={p.id} className="py-2 border-b last:border-0 text-gray-800 dark:text-gray-200">{p.name}</div>)}
      </div>
    </div>
  )
}
