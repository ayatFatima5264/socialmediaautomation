import { useState } from 'react'

// Confirmation for permanent account deletion.
//
// Two deliberate acts are required: opening this dialog, and typing the word
// DELETE. The typed word exists because the action cannot be undone and there
// is no recovery window on the server — a single mis-aimed click should not be
// able to reach it. The backend re-checks the same word, so this dialog is a
// courtesy to the user rather than the control itself.
//
// The list below states exactly what goes, because "delete your account" is too
// vague for someone to consent to.
const CONFIRM_WORD = 'DELETE'

const WHAT_GOES = [
  'Your profile, login and business profile',
  'All posts, drafts, content plans and schedules',
  'All ad campaigns and their creatives',
  'Every uploaded image',
  'Every connected social account, including its stored access token',
]

export default function DeleteAccountModal({ email, busy, error, onConfirm, onClose }) {
  const [typed, setTyped] = useState('')
  const armed = typed.trim() === CONFIRM_WORD

  function submit(e) {
    e.preventDefault()
    if (armed && !busy) onConfirm()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-account-title"
    >
      <div className="card w-full max-w-md p-6">
        <div className="mb-1 flex items-center gap-2">
          <span
            className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-rose-500/20 text-lg"
            aria-hidden="true"
          >
            ⚠️
          </span>
          <h2 id="delete-account-title" className="text-lg font-bold text-rose-700">
            Delete your account
          </h2>
        </div>

        <p className="text-sm text-body">
          This permanently deletes <b>{email}</b> and everything in it. It cannot be
          undone, and we cannot restore it afterwards.
        </p>

        <ul className="mt-3 space-y-1 rounded-xl bg-inset p-3 text-xs text-muted">
          {WHAT_GOES.map((item) => (
            <li key={item} className="flex gap-2">
              <span aria-hidden="true">•</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>

        <p className="mt-3 text-xs text-muted">
          Posts already published to Facebook, Instagram, Threads, Pinterest, LinkedIn
          or X stay on those platforms — they live in your own profiles, and deleting
          your AutoSocial AI account does not reach into them. Remove those from each
          platform directly.
        </p>

        <form onSubmit={submit} className="mt-4">
          <label htmlFor="delete-confirm" className="label">
            Type <span className="font-mono font-bold">{CONFIRM_WORD}</span> to confirm
          </label>
          <input
            id="delete-confirm"
            className="input font-mono"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={CONFIRM_WORD}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck="false"
            disabled={busy}
            autoFocus
          />

          {error && (
            <p role="alert" className="mt-2 text-sm text-rose-700">
              {error}
            </p>
          )}

          <div className="mt-5 flex gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="btn btn-ghost flex-1"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!armed || busy}
              className="btn btn-danger flex-1"
            >
              {busy ? 'Deleting…' : 'Delete my account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
