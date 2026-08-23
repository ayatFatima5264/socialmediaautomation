import { useCallback, useState } from 'react'
import Modal from './Modal.jsx'
import Spinner from '../Spinner.jsx'

// ---------------------------------------------------------------------------
// Rename and delete dialogs, plus the state that drives them.
//
// Both the Overview and the Projects page need the same three actions on a
// project card, so the dialogs and their open/close state live together here
// rather than being written twice. `useProjectDialogs` takes the mutation
// functions from `useVideoProjects`, so the dialogs never call the API
// themselves — one place owns the requests and the list reconciliation.
//
// Duplicate has no dialog: it is not destructive and it is undoable by
// deleting the copy, so a confirmation would be a click for nothing.
// ---------------------------------------------------------------------------

export function useProjectDialogs({ rename, duplicate, remove }) {
  const [renaming, setRenaming] = useState(null)
  const [deleting, setDeleting] = useState(null)

  return {
    renaming,
    deleting,
    openRename: useCallback((project) => setRenaming(project), []),
    closeRename: useCallback(() => setRenaming(null), []),
    openDelete: useCallback((project) => setDeleting(project), []),
    closeDelete: useCallback(() => setDeleting(null), []),
    confirmDuplicate: useCallback(
      (project) => duplicate(project).catch(() => {}),
      [duplicate],
    ),
    rename,
    remove,
  }
}

function RenameDialog({ project, onClose, onRename }) {
  const [name, setName] = useState(project?.name || '')
  const [busy, setBusy] = useState(false)

  const trimmed = name.trim()
  const unchanged = trimmed === project?.name

  async function submit(event) {
    event.preventDefault()
    if (!trimmed || busy) return
    setBusy(true)
    try {
      await onRename(project, trimmed)
      onClose()
    } catch {
      // The hook has already shown the error; keep the dialog open so the
      // name the user typed is not thrown away with it.
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      title="Rename project"
      onClose={busy ? () => {} : onClose}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            type="submit"
            form="rename-project-form"
            className="btn btn-primary"
            disabled={busy || !trimmed || unchanged}
          >
            {busy && <Spinner />}
            {busy ? 'Saving…' : 'Save'}
          </button>
        </>
      }
    >
      <form id="rename-project-form" onSubmit={submit}>
        <label className="label" htmlFor="project-name">
          Project name
        </label>
        <input
          id="project-name"
          className="input"
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={200}
          autoFocus
          disabled={busy}
        />
      </form>
    </Modal>
  )
}

function DeleteDialog({ project, onClose, onDelete }) {
  const [busy, setBusy] = useState(false)

  async function confirm() {
    setBusy(true)
    try {
      await onDelete(project)
      onClose()
    } catch {
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      title="Delete this project?"
      description={`“${project.name}” will be removed. This cannot be undone.`}
      onClose={busy ? () => {} : onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-danger" onClick={confirm} disabled={busy}>
            {busy && <Spinner />}
            {busy ? 'Deleting…' : 'Delete project'}
          </button>
        </>
      }
    >
      {/* Stated because it is the part people worry about, and because it is
          genuinely true: assets are owned by the account, not the project. */}
      <p className="panel p-3 text-sm text-muted">
        Any voice-overs, uploads or renders you made stay in your library — only
        the project itself is deleted.
      </p>
    </Modal>
  )
}

export default function ProjectDialogs({
  renaming,
  deleting,
  closeRename,
  closeDelete,
  rename,
  remove,
}) {
  return (
    <>
      {renaming && (
        <RenameDialog
          // Keyed so switching straight from one project's dialog to another's
          // reinitialises the field instead of showing the previous name.
          key={renaming.id}
          project={renaming}
          onClose={closeRename}
          onRename={rename}
        />
      )}
      {deleting && (
        <DeleteDialog project={deleting} onClose={closeDelete} onDelete={remove} />
      )}
    </>
  )
}
