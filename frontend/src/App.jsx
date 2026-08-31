import { useCallback, useEffect, useState } from 'react'
import { AppHeader } from './components/AppHeader'
import { FirstPage } from './pages/FirstPage'
import { SystemServicesPage } from './pages/SystemServicesPage'
import { TeleoperationPage } from './pages/TeleoperationPage'
import { getHealth } from './services/api'


export default function App() {
  const [page, setPage] = useState('console')
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
  }, [refreshData])

  return (
    <div className="app-shell">
      <AppHeader currentPage={page} health={health} onNavigate={setPage} />
      <main>
        {connectionError && (
          <div className="connection-banner">
            Cannot reach the FastAPI backend: {connectionError}
          </div>
        )}
        {page === 'console' && <FirstPage />}
        {page === 'teleoperation' && <TeleoperationPage />}
        {page === 'services' && <SystemServicesPage />}
      </main>
      <footer>DAIKAI ROBOT HUB</footer>
    </div>
  )
}
