import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { loadRobotGeometry } from '../services/robotModel'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'


export function RobotModel({ imu, connected }) {
  const host = useRef(null)
  const telemetry = useRef({ imu, connected })
  telemetry.current = { imu, connected }
  const actions = useRef({})
  const [load, setLoad] = useState('Loading optimized R1 model…')
  const [error, setError] = useState('')
  const [wireframe, setWireframe] = useState(false)
  const wire = useRef(false)
  wire.current = wireframe

  useEffect(() => {
    const element = host.current
    let disposed = false
    let renderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    } catch {
      setError('3D view requires WebGL. Battery and IMU telemetry remain available.')
      return
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    element.appendChild(renderer.domElement)
    const scene = new THREE.Scene()
    scene.fog = new THREE.Fog(0x070d17, 5, 12)
    const camera = new THREE.PerspectiveCamera(36, 1, 0.01, 30)
    const controls = new OrbitControls(camera, renderer.domElement)
    const reset = () => {
      camera.position.set(2.0, 1.1, 2.1)
      controls.target.set(0, 0.66, 0)
      controls.update()
    }
    controls.enableDamping = true
    controls.enablePan = false
    controls.minDistance = 1.5
    controls.maxDistance = 4.5
    controls.maxPolarAngle = Math.PI * 0.49
    reset()
    actions.current.reset = reset
    scene.add(new THREE.HemisphereLight(0xccecff, 0x16283d, 2))
    const key = new THREE.DirectionalLight(0xffffff, 2.4)
    key.position.set(2, 4, 3)
    scene.add(key)
    const rim = new THREE.DirectionalLight(0x4fc3f7, 2.5)
    rim.position.set(-3, 2, -2)
    scene.add(rim)
    scene.add(new THREE.GridHelper(8, 64, 0x29577a, 0x10263f))
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.56, 0.568, 96), new THREE.MeshBasicMaterial({ color: 0x4fc3f7, side: THREE.DoubleSide, transparent: true, opacity: 0.6 }))
    ring.rotation.x = -Math.PI / 2
    ring.position.y = 0.004
    scene.add(ring)
    const ticks = new THREE.InstancedMesh(
      new THREE.PlaneGeometry(0.005, 0.025),
      new THREE.MeshBasicMaterial({ color: 0x4fc3f7, side: THREE.DoubleSide }), 36,
    )
    const tick = new THREE.Object3D()
    for (let i = 0; i < 36; i++) {
      const angle = i / 36 * Math.PI * 2
      tick.position.set(Math.sin(angle) * 0.61, 0.006, Math.cos(angle) * 0.61)
      tick.rotation.set(-Math.PI / 2, 0, -angle)
      tick.scale.set(1, i % 9 ? 1 : 2.4, 1)
      tick.updateMatrix()
      ticks.setMatrixAt(i, tick.matrix)
    }
    scene.add(ticks)
    // The supplied STL is in metres, Z-up; Unitree IMU quaternions are WXYZ.
    const zUp = new THREE.Group()
    zUp.rotation.x = -Math.PI / 2
    scene.add(zUp)
    const attitude = new THREE.Group()
    attitude.position.z = 0.72
    zUp.add(attitude)
    const material = new THREE.MeshStandardMaterial({ color: 0x9fb6d0, metalness: 0.6, roughness: 0.35, transparent: true, opacity: 0.92 })
    const acceleration = new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1), new THREE.Vector3(), 0.3, 0xff5d6c, 0.05, 0.025)
    attitude.add(acceleration)
    acceleration.visible = false
    const axes = new THREE.AxesHelper(0.2)
    attitude.add(axes)
    axes.visible = false
    const heading = new THREE.Group()
    const needle = new THREE.Mesh(new THREE.ConeGeometry(0.025, 0.1, 3), new THREE.MeshBasicMaterial({ color: 0xffb547 }))
    needle.rotation.x = Math.PI / 2
    needle.position.set(0, 0.015, -0.69)
    heading.add(needle)
    scene.add(heading)
    loadRobotGeometry()
      .then((geometry) => {
        if (disposed) { geometry.dispose(); return }
        attitude.add(new THREE.Mesh(geometry, material))
        setLoad('')
        schedule()
      })
      .catch((failure) => {
        if (!disposed) setError(`Could not load the R1 model. ${failure.message}`)
      })
    let frame = null
    let lastRender = 0
    let inViewport = true
    function schedule() {
      if (!disposed && frame === null && !document.hidden && inViewport) frame = requestAnimationFrame(draw)
    }
    actions.current.invalidate = schedule
    controls.addEventListener('change', schedule)
    const visibility = () => { if (!document.hidden) schedule() }
    document.addEventListener('visibilitychange', visibility)
    const intersection = new IntersectionObserver(([entry]) => {
      inViewport = entry.isIntersecting
      if (inViewport) schedule()
    })
    intersection.observe(element)
    const resize = () => {
      const { width, height } = element.getBoundingClientRect()
      if (!width || !height) return
      renderer.setSize(width, height)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
      schedule()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(element)
    resize()
    const target = new THREE.Quaternion()
    const accelerationVector = new THREE.Vector3()
    function draw(time) {
      frame = null
      if (disposed || document.hidden || !inViewport) return
      // Render at most 30 fps and only while telemetry or orbit controls move.
      if (time - lastRender < 1000 / 30) { schedule(); return }
      const elapsed = Math.min(time - lastRender, 100)
      lastRender = time
      let moving = false
      const data = telemetry.current
      const q = data.imu?.quaternion_wxyz
      const valid = data.connected && q?.length === 4 && q.every(Number.isFinite) && Math.hypot(...q) > 0.01
      if (valid) {
        target.set(q[1], q[2], q[3], q[0]).normalize()
        moving = attitude.quaternion.angleTo(target) > 0.001
        if (moving) attitude.quaternion.slerp(target, 1 - Math.exp(-elapsed / 65))
        else attitude.quaternion.copy(target)
      }
      material.wireframe = wire.current
      material.opacity = valid ? 0.95 : 0.4
      heading.visible = Boolean(valid)
      if (valid) heading.rotation.y = -(data.imu.rpy_deg?.[2] || 0) * Math.PI / 180
      const acc = data.imu?.accelerometer_m_s2
      acceleration.visible = Boolean(valid && acc?.length === 3 && acc.every(Number.isFinite) && Math.hypot(...acc) > 0.01)
      axes.visible = Boolean(valid)
      if (acceleration.visible) {
        accelerationVector.set(...acc)
        acceleration.setLength(Math.min(accelerationVector.length() / 30, 0.6), 0.05, 0.025)
        acceleration.setDirection(accelerationVector.normalize())
      }
      controls.update()
      renderer.render(scene, camera)
      if (moving) schedule()
    }
    schedule()
    return () => {
      disposed = true
      if (frame !== null) cancelAnimationFrame(frame)
      document.removeEventListener('visibilitychange', visibility)
      intersection.disconnect()
      controls.removeEventListener('change', schedule)
      observer.disconnect()
      controls.dispose()
      const geometries = new Set()
      const materials = new Set([material])
      scene.traverse((object) => {
        if (object.geometry) geometries.add(object.geometry)
        if (object.material) (Array.isArray(object.material) ? object.material : [object.material]).forEach((item) => materials.add(item))
      })
      geometries.forEach((geometry) => geometry.dispose())
      materials.forEach((item) => item.dispose())
      renderer.dispose()
      renderer.domElement.remove()
      actions.current = {}
    }
  }, [])

  useEffect(() => { actions.current.invalidate?.() }, [imu, connected, wireframe])

  return (
    <section className="robot-stage" aria-label="Interactive R1 3D body orientation">
      <div className="robot-canvas" ref={host} />
      <div className="stage-topline"><span className="eyebrow">UNITREE R1 / BODY ATTITUDE</span><span className={connected ? 'model-signal live' : 'model-signal'}>{connected ? '● IMU LIVE' : '○ NO IMU SIGNAL'}</span></div>
      {(load || error) && <div className={`model-loading ${error ? 'error-message' : ''}`} role="status">{error || load}</div>}
      {!connected && !load && !error && <span className="stage-no-signal">NO SIGNAL</span>}
      <div className="stage-bottomline">
        <span>Drag to orbit · Scroll to zoom<br /><small>Rigid body orientation from IMU</small></span>
        <div className="stage-controls"><button type="button" aria-pressed={wireframe} onClick={() => setWireframe((value) => !value)}>Wireframe</button><button type="button" onClick={() => actions.current.reset?.()}>Reset view</button></div>
      </div>
    </section>
  )
}
