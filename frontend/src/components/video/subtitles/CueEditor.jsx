import { useEffect, useRef, useState } from 'react'
import VideoIcon from '../VideoIcon.jsx'
import Spinner from '../../Spinner.jsx'

// ---------------------------------------------------------------------------
// The cue list — where subtitles are actually fixed.
//
// Every row is start, end and text, because that is what a cue is. The
// operations sit on the row they act on rather than in a toolbar: "split this
// one" needs to say which one, and a toolbar makes the user select first and
// act second for no gain.
//
// Timings are edited as text (`0:04.250`) rather than as number inputs. A
// subtitle is adjusted in tenths of a second and a spinner control cannot
// express that without a step so small the arrows become useless — and typing
// a timecode is what anyone who has edited subtitles before expects to do.
//
// Text edits are debounced and sent on blur, so a save is not fired per
// keystroke while still being impossible to lose by clicking away.
// ---------------------------------------------------------------------------

/** Seconds as `m:ss.mmm` — the form the inputs accept back. */
export function toTimecode(seconds) {
  const total = Math.max(0, Number(seconds) || 0)
  const minutes = Math.floor(total / 60)
  const rest = total - minutes * 60
  return `${minutes}:${rest.toFixed(3).padStart(6, '0')}`
}

/** Parse `m:ss.mmm`, `ss.mmm`, or `h:mm:ss.mmm`. Returns null if unreadable. */
export function fromTimecode(value) {
  const text = String(value || '').trim()
  if (!text) return null
  const parts = text.split(':').map((part) => part.trim())
  if (parts.some((part) => part === '' || Number.isNaN(Number(part)))) return null

  const numbers = parts.map(Number)
  if (numbers.some((n) => n < 0)) return null

  if (numbers.length === 1) return numbers[0]
  if (numbers.length === 2) return numbers[0] * 60 + numbers[1]
  if (numbers.length === 3) return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
  return null
}

function TimeField({ value, onCommit, label }) {
  const [draft, setDraft] = useState(toTimecode(value))
  const [invalid, setInvalid] = useState(false)

  // Follow the value when it changes underneath — a split, a shift or an undo
  // rewrites timings the user did not type.
  useEffect(() => {
    setDraft(toTimecode(value))
    setInvalid(false)
  }, [value])

  function commit() {
    const parsed = fromTimecode(draft)
    if (parsed === null) {
      setInvalid(true)
      return
    }
    setInvalid(false)
    if (Math.abs(parsed - value) > 0.0005) onCommit(parsed)
    else setDraft(toTimecode(value))
  }

  return (
    <input
      className={`input px-2 py-1 text-center text-xs tabular-nums ${
        invalid ? 'border-rose-400' : ''
      }`}
      style={{ width: '5.5rem' }}
      aria-label={label}
      value={draft}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === 'Enter') event.currentTarget.blur()
        if (event.key === 'Escape') {
          setDraft(toTimecode(value))
          setInvalid(false)
          event.currentTarget.blur()
        }
      }}
    />
  )
}

function CueRow({
  cue,
  index,
  selected,
  onToggleSelect,
  onUpdate,
  onSplit,
  onDelete,
  active,
  onSeek,
  busy,
}) {
  const [text, setText] = useState(cue.text)
  const areaRef = useRef(null)

  useEffect(() => setText(cue.text), [cue.text])

  const overRunning = cue.end - cue.start < 0.7
  const longLine = cue.text.split('\n').some((line) => line.length > 42)

  function commitText() {
    const cleaned = text
    if (cleaned.trim() && cleaned !== cue.text) onUpdate(index, { text: cleaned })
    else if (!cleaned.trim()) setText(cue.text)
  }

  return (
    <li
      className={`panel flex flex-col gap-2 p-2.5 transition-colors sm:flex-row sm:items-start ${
        active ? 'border-accent-line bg-accent-soft' : ''
      }`}
    >
      <div className="flex shrink-0 items-center gap-2 sm:flex-col sm:items-stretch">
        <label className="flex cursor-pointer items-center gap-2 text-xs text-muted">
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect(index)}
            className="accent-[var(--accent)]"
            aria-label={`Select subtitle ${index + 1}`}
          />
          <span className="tabular-nums">{index + 1}</span>
        </label>
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-1.5">
        <TimeField
          value={cue.start}
          label={`Start of subtitle ${index + 1}`}
          onCommit={(start) => onUpdate(index, { start })}
        />
        <span className="text-xs text-muted">→</span>
        <TimeField
          value={cue.end}
          label={`End of subtitle ${index + 1}`}
          onCommit={(end) => onUpdate(index, { end })}
        />
        {onSeek && (
          <button
            type="button"
            className="btn btn-ghost btn-sm px-2"
            onClick={() => onSeek(cue.start)}
            title="Play from here"
            aria-label={`Play from subtitle ${index + 1}`}
          >
            <VideoIcon name="play" className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <textarea
          ref={areaRef}
          className="input min-h-[3.25rem] resize-y py-1.5 text-sm leading-snug"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onBlur={commitText}
          aria-label={`Text of subtitle ${index + 1}`}
        />
        {(overRunning || longLine) && (
          <p className="mt-1 text-[11px] text-amber-700">
            {overRunning && 'Under 0.7s — too quick to read. '}
            {longLine && 'A line is longer than the 42-character reading limit.'}
          </p>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <button
          type="button"
          className="btn btn-ghost btn-sm px-2"
          onClick={() => onSplit(index)}
          disabled={busy}
          title="Split this subtitle in two"
          aria-label={`Split subtitle ${index + 1}`}
        >
          <VideoIcon name="scissors" className="h-4 w-4" />
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm px-2 text-rose-600"
          onClick={() => onDelete(index)}
          disabled={busy}
          title="Delete this subtitle"
          aria-label={`Delete subtitle ${index + 1}`}
        >
          <VideoIcon name="trash" className="h-4 w-4" />
        </button>
      </div>
    </li>
  )
}

export default function CueEditor({
  cues,
  busy,
  onUpdate,
  onInsert,
  onDelete,
  onSplit,
  onMerge,
  currentTime = 0,
  onSeek,
}) {
  const [selected, setSelected] = useState([])

  // A merge or a delete renumbers everything after it, so a selection held by
  // index is stale the moment the track changes.
  useEffect(() => setSelected([]), [cues])

  function toggle(index) {
    setSelected((current) =>
      current.includes(index) ? current.filter((i) => i !== index) : [...current, index].sort((a, b) => a - b),
    )
  }

  const activeIndex = cues.findIndex(
    (cue) => currentTime >= cue.start && currentTime < cue.end,
  )

  const contiguous =
    selected.length > 1 &&
    selected.every((value, position) => position === 0 || value === selected[position - 1] + 1)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          className="btn btn-secondary btn-sm"
          onClick={() => onInsert(cues.length ? cues.length - 1 : null)}
          disabled={busy}
        >
          <VideoIcon name="plus" className="h-4 w-4" />
          Add subtitle
        </button>

        <button
          className="btn btn-secondary btn-sm"
          onClick={() => onMerge(selected)}
          disabled={busy || !contiguous}
          title={
            selected.length < 2
              ? 'Select two or more subtitles to merge'
              : contiguous
                ? 'Merge the selected subtitles into one'
                : 'Only subtitles next to each other can be merged'
          }
        >
          Merge
          {selected.length > 1 ? ` ${selected.length}` : ''}
        </button>

        {selected.length > 0 && (
          <button className="btn btn-ghost btn-sm" onClick={() => setSelected([])}>
            Clear selection
          </button>
        )}

        {busy && (
          <span className="flex items-center gap-1.5 text-xs text-muted">
            <Spinner /> {busy}…
          </span>
        )}

        <span className="ml-auto text-xs text-muted">
          {cues.length} {cues.length === 1 ? 'subtitle' : 'subtitles'}
        </span>
      </div>

      <ul className="flex flex-col gap-2">
        {cues.map((cue, index) => (
          <CueRow
            key={`${index}-${cue.start}`}
            cue={cue}
            index={index}
            selected={selected.includes(index)}
            onToggleSelect={toggle}
            onUpdate={onUpdate}
            onSplit={onSplit}
            onDelete={onDelete}
            active={index === activeIndex}
            onSeek={onSeek}
            busy={Boolean(busy)}
          />
        ))}
      </ul>
    </div>
  )
}
