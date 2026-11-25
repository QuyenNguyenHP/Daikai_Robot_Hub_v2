import { HudIcon } from './HudIcon'
import { useEffect, useRef, useState } from 'react'
import { enrollFace, getEnrolledPeople } from '../services/api'

export function FaceEnrollmentDialog({ onClose }) {
  const dialog = useRef(null)
  const fileInput = useRef(null)
  const submitting = useRef(false)
  const [name, setName] = useState('')
  const [files, setFiles] = useState([])
  const [previews, setPreviews] = useState([])
  const [people, setPeople] = useState([])
  const [peopleError, setPeopleError] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    const element = dialog.current
    element.showModal()
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    let active = true
    getEnrolledPeople().then((data) => { if (active) setPeople(data.people) }).catch((failure) => { if (active) setPeopleError(failure.message) })
    return () => { active = false; document.body.style.overflow = overflow; element.close() }
  }, [])

  useEffect(() => {
    const items = files.map((file) => ({ file, url: URL.createObjectURL(file) }))
    setPreviews(items)
    return () => items.forEach(({ url }) => URL.revokeObjectURL(url))
  }, [files])

  const addFiles = (event) => {
    const selected = [...event.target.files]
    event.target.value = ''
    setError('')
    setResult(null)
    const combined = [...files]
    for (const file of selected) {
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { setError('Use JPG, PNG or WebP photos.'); return }
      if (file.size === 0 || file.size > 5 * 1024 * 1024) { setError('Each photo must be non-empty and at most 5 MB.'); return }
      if (!combined.some((item) => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified)) combined.push(file)
    }
    if (combined.length > 10) { setError('Select at most 10 photos per registration.'); return }
    if (combined.reduce((total, file) => total + file.size, 0) > 25 * 1024 * 1024) { setError('The total upload must be at most 25 MB.'); return }
    setFiles(combined)
  }

  const submit = async (event) => {
    event.preventDefault()
    if (submitting.current || !name.trim() || !files.length) return
    submitting.current = true
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const data = await enrollFace(name.trim(), files)
      setResult(data)
      if (data.saved) {
        setFiles((current) => current.filter((file) => !data.accepted_files.includes(file.name)))
        try {
          const updated = await getEnrolledPeople()
          setPeople(updated.people)
          setPeopleError('')
        } catch (failure) { setPeopleError(failure.message) }
      }
    } catch (failure) {
      setError(failure.message)
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  const close = () => { if (!submitting.current) onClose() }
  return (
    <dialog className="face-enrollment-dialog" ref={dialog} aria-labelledby="enroll-title" aria-describedby="enroll-description" onCancel={(event) => { event.preventDefault(); close() }} onClick={(event) => { if (event.target === dialog.current) { const rect = dialog.current.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) close() } }}>
      <div className="face-enrollment-content">
        <div className="panel-heading">
          <div><p className="eyebrow">VISION / FACE REGISTRATION</p><h2 id="enroll-title"><HudIcon name="face" /> Register a face</h2></div>
          <button type="button" className="dialog-close" aria-label="Close face registration" disabled={busy} onClick={close}><HudIcon name="close" /></button>
        </div>
        <p id="enroll-description" className="enroll-description">Add clear photos of one person. Vision will recognize them by the name you enter.</p>
        <form onSubmit={submit}>
          <label htmlFor="enroll-name" className="field-label">Person’s name</label>
          <input id="enroll-name" className="text-input" type="text" maxLength={80} value={name} disabled={busy} autoFocus required onChange={(event) => setName(event.target.value)} placeholder="e.g. Nguyen An" />
          <div className="enroll-photo-picker">
            <span className="enroll-photo-icon" aria-hidden="true"><HudIcon name="image" /></span>
            <strong>Photos of this person</strong>
            <p>JPG, PNG or WebP · 1–10 photos · 5 MB each · 25 MB total</p>
            <button type="button" className="button secondary" disabled={busy || files.length >= 10} onClick={() => fileInput.current.click()}><HudIcon name="upload" /> Choose photos</button>
            <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={busy} onChange={addFiles} aria-label="Choose face photos" className="enroll-file-input" />
          </div>
          {files.length > 0 && <div className="enroll-preview-grid">{previews.map(({ file, url }, index) => <div className="enroll-preview" key={`${file.name}-${file.lastModified}-${file.size}`}><img src={url} alt={`Selected photo: ${file.name}`} /><button type="button" disabled={busy} aria-label={`Remove ${file.name}`} onClick={() => { setFiles((items) => items.filter((_, i) => i !== index)); setResult(null) }}><HudIcon name="close" /></button><span title={file.name}>{file.name}</span></div>)}</div>}
          <p className="mode-detail">Use well-lit photos with exactly one visible face. Multiple photos can show slightly different angles. Existing samples are kept when you use the same name.</p>
          <div aria-live="polite">
            {error && <p className="error-message">{error}</p>}
            {result && <div className={result.saved ? 'success-message' : 'error-message'}><strong>{result.saved ? `${result.name}: ${result.accepted} photo(s) saved.` : 'Registration was not saved.'}</strong><p>{result.saved ? 'Vision updates automatically. You can close this window.' : 'Choose a clearer photo and try again.'}</p>{result.rejected.length > 0 && <ul>{result.rejected.map((item, index) => <li key={index}>{item.file}: {item.reason}</li>)}</ul>}</div>}
          </div>
          <div className="enroll-dialog-actions"><button type="button" className="button secondary" disabled={busy} onClick={close}>{result?.saved ? 'Done' : 'Cancel'}</button><button type="submit" className="button primary" disabled={busy || !name.trim() || files.length === 0}>{busy ? 'Registering…' : `Register face${files.length ? ` · ${files.length} photo(s)` : ''}`}</button></div>
        </form>
        <div className="enroll-people"><p className="eyebrow">REGISTERED PEOPLE <span>{people.length}</span></p>{people.length > 0 ? <div className="enroll-people-list">{people.map((person) => <span key={person.name}>{person.name}</span>)}</div> : <p className="mode-detail">{peopleError || 'No registered people yet.'}</p>}</div>
      </div>
    </dialog>
  )
}
