// Local SVG symbols share one stroke style and inherit the HUD accent color.
const paths = {
  robot: ['M9 5V3h6v2M6 8h12v11H6zM3 11v5m18-5v5M9 12h.01M15 12h.01M9 16h6'],
  refresh: ['M20 7v5h-5M4 17v-5h5', 'M6.1 7a7 7 0 0 1 11.5-1L20 9M4 15l2.4 3A7 7 0 0 0 18 17'],
  volume: ['M11 5 6 9H3v6h3l5 4z', 'M15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14'],
  face: ['M8 3H4v4m12-4h4v4M4 17v4h4m12-4v4h-4', 'M15.5 9a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0M6.5 18a5.5 5.5 0 0 1 11 0'],
  image: ['M3 4h18v16H3z', 'M3 16l5-5 5 5 3-3 5 5M16 8h.01'],
  upload: ['M12 16V3m-4 4 4-4 4 4M4 15v5h16v-5'],
  close: ['m6 6 12 12M6 18 18 6'],
  release: ['M8 4H4v4m12-4h4v4M4 16v4h4m12-4v4h-4', 'm9 9-3-3m9 3 3-3m-9 9-3 3m9-3 3 3'],
  clap: ['m10 5-3 6 3 8-4-2-3-7 3-6m8 1 3 6-3 8 4-2 3-7-3-6', 'M12 2v2m-2 17h4'],
  handshake: ['m3 8 4-3 5 2 5-2 4 3-4 9-4 3-7-5z', 'm7 5 4 2-3 4 3 2 3-3 4 4m-9 0 5 4'],
  kiss: ['M4 16h9l4-4-3-2-4 3H7M4 12v8h3l7 1 7-6', 'M13 4h7m-3-3 3 3-3 3'],
  heart: ['M12 20 4 12a5 5 0 0 1 8-6 5 5 0 0 1 8 6z'],
  hug: ['M15 5a3 3 0 1 1-6 0 3 3 0 0 1 6 0M7 21v-8h10v8', 'M7 10 3 13l4 4m10-7 4 3-4 4M9 17h6'],
  hand: ['M8 13V5a1.5 1.5 0 0 1 3 0v6-8a1.5 1.5 0 0 1 3 0v8-6a1.5 1.5 0 0 1 3 0v7-4a1.5 1.5 0 0 1 3 0v7l-3 6H9l-5-7a1.5 1.5 0 0 1 2-2z'],
  wave: ['M8 15V7a1.5 1.5 0 0 1 3 0v5-8a1.5 1.5 0 0 1 3 0v8-6a1.5 1.5 0 0 1 3 0v7-3a1.5 1.5 0 0 1 3 0v6l-3 5H9l-4-6 2-1z', 'M4 8a9 9 0 0 1 1-5m16 1 1 3'],
  raised: ['M14 5a2 2 0 1 1-4 0 2 2 0 0 1 4 0M8 21v-9L4 8V3m12 18v-9l4-4V3M8 12h8'],
  refuse: ['M14 5a2 2 0 1 1-4 0 2 2 0 0 1 4 0M8 21v-6m8 6v-6', 'm5 9 14 7M5 16l14-7'],
  ray: ['m4 8 8 4-8 4m8-4h9m-5-5 5 5-5 5M7 4l2 3m-2 13 2-3'],
  punch: ['M4 10h6v7H4zM10 10l3-5h5l3 6-3 6h-8M14 5v5m3-5v5M2 7V4h3m14 16h3v-3'],
  dance: ['M14 4a2 2 0 1 1-4 0 2 2 0 0 1 4 0M12 8l-3 6 5 3-3 5M9 14l-5 3m8-9 5 3 4-4M9 10 4 7'],
  bow: ['M18 8a2 2 0 1 1-4 0 2 2 0 0 1 4 0M13 11l-6 2 3 4-3 5M7 13l-2-5m8 3 4 5 3-1'],
  up: ['M12 20V4m-6 6 6-6 6 6'],
  down: ['M12 4v16m-6-6 6 6 6-6'],
  left: ['M20 12H4m6-6-6 6 6 6'],
  right: ['M4 12h16m-6-6 6 6-6 6'],
  turnLeft: ['M19 19v-6a6 6 0 0 0-6-6H4m5-5L4 7l5 5'],
  turnRight: ['M5 19v-6a6 6 0 0 1 6-6h9m-5-5 5 5-5 5'],
  stop: ['M6 6h12v12H6z'],
  vision: ['M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12', 'M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0'],
}

export function HudIcon({ name = 'robot', className = '', ...props }) {
  return <svg className={`hud-icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...props}>{(paths[name] || paths.robot).map((path, index) => <path d={path} key={index} />)}</svg>
}
