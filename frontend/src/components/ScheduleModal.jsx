import { useState } from 'react'

// Minimum selectable time = now + 1 minute, formatted for datetime-local.
function minLocal() {
  const d = new Date(Date.now() + 60_000)
  d.setSeconds(0, 0)
  const tz = d.getTimezoneOffset()
  return new Date(d.getTime() - tz * 60_000).toISOString().slice(0, 16)
}

export default function ScheduleModal({ open, title = 'Schedule post', onClose, onConfirm }) {
  const [value, setValue] = useState(minLocal())
  const [busy, setBusy] = useState(false)

  if (!open) return null

  async function confirm() {
    if (!value) return
    setBusy(true)
    try {
      await onConfirm(value) // local datetime string
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div className="card w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-1 text-lg font-bold">{title}</h3>
        <p className="mb-4 text-sm text-muted">
          Pick a date & time (your local timezone). The scheduler publishes it automatically.
        </p>
        <label className="label">Publish at</label>
        <input
          type="datetime-local"
          className="input"
          value={value}
          min={minLocal()}
          onChange={(e) => setValue(e.target.value)}
        />
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={confirm} disabled={busy}>
            {busy ? 'Scheduling…' : 'Schedule'}
          </button>
        </div>
      </div>
    </div>
  )
}
