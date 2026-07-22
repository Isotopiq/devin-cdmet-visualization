import { useState } from 'react'

export default function Settings() {
  const [theme, setTheme] = useState('light')

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4 text-gray-900 dark:text-white">Settings</h1>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 max-w-md">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Theme</label>
        <select value={theme} onChange={(e) => setTheme(e.target.value)} className="border rounded-lg p-2 mt-1 w-full">
          <option value="light">Light</option>
          <option value="dark">Dark</option>
        </select>
        <p className="text-sm text-gray-500 mt-2">User preferences and organizational defaults will be stored here.</p>
      </div>
    </div>
  )
}
