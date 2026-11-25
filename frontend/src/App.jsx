import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { AppHeader } from './components/AppHeader'
import { FirstPage } from './pages/FirstPage'
import { SystemServicesPage } from './pages/SystemServicesPage'
import { TeleoperationPage } from './pages/TeleoperationPage'
import { ObjectDistancePage } from './pages/ObjectDistancePage'
import { getHealth } from './services/api'


const MonitorPage = lazy(() => import('./pages/MonitorPage'))

export default function App() {
  const [page, setPage] = useState('monitor')
  const [health, setHealth] = useState(null)
  const [connectionError, setConnectionError] = useState('')

  const refreshData = useCallback(async () => {
    try {
      const healthResult = await getHealth()
      setHealth(healthResult)
      setConnectionError('')
    } catch (error) {
      setHealth(null)
      setConnectionError(error.message)
    }
  }, [])

  useEffect(() => {
    refreshData()
    const timer = window.setInterval(refreshData, 5000)
    return () => window.clearInterval(timer)
  }, [refreshData])

  return (
    <div className="app-shell">
      <AppHeader currentPage={page} health={health} onNavigate={setPage} />
      <main className={page === 'monitor' ? 'monitor-main' : ''}>
        {connectionError && (
          <div className="connection-banner">
            Cannot reach the FastAPI backend: {connectionError}
          </div>
        )}
        {page === 'monitor' && <Suspense fallback={<p className="monitor-loading">Loading robot monitor…</p>}><MonitorPage /></Suspense>}
        {page === 'console' && <FirstPage />}
        {page === 'teleoperation' && <TeleoperationPage />}
        {page === 'object-distance' && <ObjectDistancePage />}
        {page === 'services' && <SystemServicesPage />}
      </main>
      <footer>DAIKAI ROBOT HUB</footer>
    </div>
  )
}
