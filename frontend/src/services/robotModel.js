import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { Vector3 } from 'three'

const MODEL_URL = new URL('../assets/r1-monitor.glb', import.meta.url).href
let geometryPromise

// Share one fetch and parse across navigation and React StrictMode remounts.
// Each viewer owns a clone, so its cleanup never disposes the cached geometry.
export function loadRobotGeometry() {
  if (!geometryPromise) {
    geometryPromise = fetch(MODEL_URL)
      .then((response) => {
        if (!response.ok) throw new Error(`Model request failed (${response.status})`)
        return response.arrayBuffer()
      })
      .then((buffer) => new GLTFLoader().parseAsync(buffer, ''))
      .then((gltf) => {
        let geometry
        gltf.scene.traverse((object) => {
          if (!object.isMesh) return
          geometry = object.geometry
          const materials = Array.isArray(object.material) ? object.material : [object.material]
          materials.forEach((material) => material.dispose())
        })
        if (!geometry) throw new Error('The optimized R1 asset contains no mesh.')
        geometry.computeBoundingBox()
        const bounds = geometry.boundingBox
        const center = bounds.getCenter(new Vector3())
        geometry.translate(-center.x, -center.y, -bounds.min.z - 0.72)
        return geometry
      })
      .catch((error) => { geometryPromise = undefined; throw error })
  }
  return geometryPromise.then((geometry) => geometry.clone())
}
