import drumsLogo from '../../photos/DRUMS_logo.png'


const NAV_ITEMS = [
  ['monitor', 'Robot Monitor'],
  ['console', 'Console'],
  ['teleoperation', 'Teleoperation'],
  ['object-distance', 'Autonomous Walk'],
  ['services', 'System Services'],
]


export function AppHeader({ currentPage, health, onNavigate }) {
  return (
    <header className="topbar">
      <button className="brand" onClick={() => onNavigate('monitor')}>
        <img className="brand-mark" src={drumsLogo} alt="" aria-hidden="true" />
        <span>DAIKAI<small>ROBOT HUB</small></span>
      </button>
      <nav aria-label="Main navigation">
        {NAV_ITEMS.map(([page, label]) => (
          <button
            aria-current={currentPage === page ? 'page' : undefined}
            className={currentPage === page ? 'active' : ''}
            key={page}
            onClick={() => onNavigate(page)}
          >
            {label}
          </button>
        ))}
      </nav>
      <div className={`api-status ${health ? 'online' : ''}`}>
        <i />
        {health ? 'API online' : 'API offline'}
      </div>
    </header>
  )
}
