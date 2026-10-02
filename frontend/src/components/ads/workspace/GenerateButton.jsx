import { useToast } from '../../../context/ToastContext.jsx'
import { formatElapsed } from '../../../lib/generationRun'

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
//
// While a generation runs it also shows how long it has been going and offers
// Cancel. BUG-10: the panel could sit on "Generating…" with no progress and no
// way to stop, and QA recorded a run that went past 90 seconds. A spinner with
// no clock and no off switch gives the user nothing to act on.
//
// Cancel appears only when the caller can actually honour it — a tool with no
// `onCancel` keeps the old behaviour rather than growing a button that does
// nothing, which is the same defect as the stub this file also avoids.
// ---------------------------------------------------------------------------

export default function GenerateButton({
  label = 'Generate',
  toolName,
  phase,
  onClick,
  onCancel,
  loading = false,
  disabled = false,
  elapsed = null,
}) {
  const toast = useToast()

  const handle =
    onClick ||
    (() =>
      toast.info(
        `${toolName} generation arrives in phase ${phase}. The workspace and its settings are ready for it.`,
      ))

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={handle}
        disabled={loading || disabled}
        // The state is announced rather than only shown, so a screen reader
        // hears that a generation started and how long it has been going.
        aria-busy={loading || undefined}
        className="btn btn-primary w-full"
      >
        {loading ? (
          <>
            <span className="inline-block animate-spin" aria-hidden="true">
              ◌
            </span>
            {elapsed === null || elapsed === undefined
              ? 'Generating…'
              : `Generating… ${formatElapsed(elapsed)}`}
          </>
        ) : (
          <>✦ {label}</>
        )}
      </button>

      {loading && onCancel && (
        <button
          type="button"
          onClick={onCancel}
          className="btn btn-ghost btn-sm w-full"
        >
          Cancel
        </button>
      )}
    </div>
  )
}
