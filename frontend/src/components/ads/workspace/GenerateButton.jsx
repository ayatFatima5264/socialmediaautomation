import { useToast } from '../../../context/ToastContext.jsx'

// ---------------------------------------------------------------------------
// The Generate control every workspace ends its control panel with.
//
// Two modes, decided by whether the caller passes `onClick`:
//
//   Wired    — the tool has a real endpoint. Runs it, and disables itself while
//              the request is in flight so a second click cannot queue a second
//              generation against the same form.
//   Not yet  — no endpoint exists for this tool. Pressing it says so, rather
//              than doing nothing or faking a result. A button that silently
//              does nothing reads as a bug; one that fakes a result is worse,
//              because the user cannot tell which outputs are real.
// ---------------------------------------------------------------------------

export default function GenerateButton({
  label = 'Generate',
  toolName,
  phase,
  onClick,
  loading = false,
  disabled = false,
}) {
  const toast = useToast()

  const handle =
    onClick ||
    (() =>
      toast.info(
        `${toolName} generation arrives in phase ${phase}. The workspace and its settings are ready for it.`,
      ))

  return (
    <button
      type="button"
      onClick={handle}
      disabled={loading || disabled}
      className="btn btn-primary w-full"
    >
      {loading ? (
        <>
          <span className="inline-block animate-spin" aria-hidden="true">
            ◌
          </span>
          Generating…
        </>
      ) : (
        <>✦ {label}</>
      )}
    </button>
  )
}
