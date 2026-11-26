import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

// Load the API module with the same origin/env globals supplied by Vite.
globalThis.window = { location: { origin: 'http://localhost', hostname: 'localhost', protocol: 'http:' } }
const source = (await readFile(new URL('../src/services/api.js', import.meta.url), 'utf8'))
  .replaceAll('import.meta.env', '({})')
const api = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))

test('stop returns the backend status', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({
    ok: true, json: async () => ({ views: { depth: false } }),
  }))
  assert.deepEqual(await api.stopRobotStereoView('depth'), { views: { depth: false } })
})

test('unresponsive stop expires after eight seconds with an actionable error', async (t) => {
  let requestedTimeout
  t.mock.method(globalThis, 'setTimeout', (callback, delay) => {
    requestedTimeout = delay
    queueMicrotask(callback)
    return 1
  })
  t.mock.method(globalThis, 'clearTimeout', () => {})
  t.mock.method(globalThis, 'fetch', (_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  }))
  await assert.rejects(api.stopRobotStereoView('depth'), /No response from backend.*may still be pending/)
  assert.equal(requestedTimeout, 8000)
})

test('robot rejection remains visible', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({
    ok: false, status: 409, json: async () => ({ detail: 'Robot control is busy.' }),
  }))
  await assert.rejects(api.stopRobotAutoWalk(), /Robot control is busy/)
})
