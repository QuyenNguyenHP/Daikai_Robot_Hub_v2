import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

// Exercise the real GLB decoder and shared cache, without requiring WebGL.
const binary = await readFile(new URL('../src/assets/r1-monitor.glb', import.meta.url))
const fetchBefore = globalThis.fetch
let calls = 0
globalThis.fetch = async () => { calls++; return new Response(binary) }
try {
  const { loadRobotGeometry } = await import('../src/services/robotModel.js')
  const started = performance.now()
  const [first, second] = await Promise.all([loadRobotGeometry(), loadRobotGeometry()])
  assert.equal(calls, 1, 'Concurrent viewers must share one download')
  assert.notEqual(first.attributes.position.array, second.attributes.position.array, 'Each viewer owns its GPU data')
  assert.ok(first.index.count / 3 <= 80000)
  assert.ok(first.attributes.normal, 'Precomputed normals avoid runtime reconstruction')
  first.computeBoundingBox()
  assert.ok(Math.abs(first.boundingBox.min.z + 0.72) < 0.001)
  assert.ok(first.boundingBox.max.z > 0.5 && first.boundingBox.max.z < 0.52)
  first.dispose()
  const third = await loadRobotGeometry()
  assert.equal(calls, 1, 'Navigation should reuse the decoded geometry')
  assert.equal(third.index.count, second.index.count)
  second.dispose(); third.dispose()
  let attempts = 0
  globalThis.fetch = async () => {
    attempts++
    return attempts === 1 ? new Response('', { status: 503 }) : new Response(binary)
  }
  const retry = await import('../src/services/robotModel.js?retry-test')
  await assert.rejects(retry.loadRobotGeometry(), /503/)
  const recovered = await retry.loadRobotGeometry()
  assert.equal(attempts, 2, 'Failed downloads must be retriable')
  recovered.dispose()
  console.log(`PASS: GLB decode, deduplication, independent geometry and failed-download recovery (${Math.round(performance.now() - started)} ms in Node; browser FPS not measured).`)
} finally {
  globalThis.fetch = fetchBefore
}
