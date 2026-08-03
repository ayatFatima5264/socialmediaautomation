import { useState } from 'react'
import BrandOverlay from '../brand/BrandOverlay.jsx'

// ---------------------------------------------------------------------------
// Natural-language editing.
//
// The prompt is interpreted server-side into structured operations, then
// executed client-side by aiOps.js. Most requests never touch the artwork —
// moving a logo or recolouring text is a layer edit, so it lands instantly and
// undoes like any manual change.
//
// Compare shows the document as it was when the editor opened against the
// current one, both rendered through the same layer pipeline, so the
// comparison is exact rather than a screenshot taken at a different moment.
// ---------------------------------------------------------------------------

const SUGGESTIONS = [
  'Move the logo to the top right',
  'Use my brand colours',
  'Add a CTA button',
  'Increase spacing',
  'Change to a dark theme',
  'Make it more premium',
]

function Thumb({ label, doc, aspect, idPrefix }) {
  return (
    <figure className="min-w-0 flex-1">
      <div
        className="relative overflow-hidden rounded-lg border border-line bg-inset"
        style={{ aspectRatio: `${doc.size.width} / ${doc.size.height}` }}
      >
        <BrandOverlay layers={doc.layers} aspect={aspect} idPrefix={idPrefix} />
      </div>
      <figcaption className="mt-1 text-center text-[11px] font-semibold text-muted">
        {label}
      </figcaption>
    </figure>
  )
}

export default function AiEditPanel({
  onApply,
  onRegenerate,
  onRevert,
  busy,
  lastResult,
  originalDocument,
  currentDocument,
  dirty,
  // `bare` drops the card chrome and heading: inside the editor's accordion
  // the section header already provides both, and a card inside a card reads
  // as a mistake.
  bare,
}) {
  const [prompt, setPrompt] = useState('')
  const [comparing, setComparing] = useState(false)

  const submit = (e) => {
    e?.preventDefault()
    const value = prompt.trim()
    if (value && !busy) onApply(value)
  }

  const aspect = currentDocument.size.width / currentDocument.size.height

  const Wrapper = bare ? 'div' : 'section'

  return (
    <Wrapper className={bare ? '' : 'card p-4'}>
      {!bare && <h2 className="text-sm font-bold">AI edit</h2>}
      <p className={`text-[11px] leading-relaxed text-muted ${bare ? '' : 'mt-1'}`}>
        Describe a change in plain English. Most edits adjust the layers directly, so the
        artwork is untouched.
      </p>

      <form onSubmit={submit} className="mt-2">
        <textarea
          className="min-h-14 w-full resize-y rounded-md border border-field-border bg-field px-2 py-1.5 text-xs text-body outline-none focus:border-accent"
          placeholder="e.g. Move the logo to the top right and use my brand colours"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            // Enter applies; Shift+Enter for a newline, as in a chat box.
            if (e.key === 'Enter' && !e.shiftKey) submit(e)
          }}
          maxLength={400}
          disabled={busy}
        />

        <div className="mt-2 flex gap-1.5">
          <button type="submit" className="btn btn-primary btn-sm flex-1 text-[11px]" disabled={busy || !prompt.trim()}>
            {busy ? 'Applying…' : 'Apply changes'}
          </button>
          <button
            type="button"
            onClick={onRegenerate}
            className="btn btn-secondary btn-sm text-[11px]"
            disabled={busy}
            title="Generate fresh artwork, keeping every layer in place"
          >
            Regenerate
          </button>
        </div>
      </form>

      {/* Suggestions — the fastest way to learn what the field understands. */}
      <div className="mt-2 flex flex-wrap gap-1">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setPrompt(s)}
            disabled={busy}
            className="rounded-full border border-line px-2.5 py-1 text-[11px] font-medium text-muted transition hover:border-accent-line hover:text-accent disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>

      {lastResult && (
        <div className="mt-2 rounded-md border border-line bg-inset p-2 text-[11px]">
          {lastResult.explanation && (
            <p className="font-medium text-body">{lastResult.explanation}</p>
          )}
          {lastResult.applied?.length > 0 && (
            <p className="mt-1 text-muted">
              Applied: <span className="font-mono">{lastResult.applied.join(', ')}</span>
            </p>
          )}
          {/* Skipped ops are surfaced, not swallowed: "move the logo" on an
              image with no logo should say so rather than appear to work. */}
          {lastResult.skipped?.length > 0 && (
            <p className="mt-1 text-amber-600">
              Nothing to change for:{' '}
              <span className="font-mono">{lastResult.skipped.join(', ')}</span>
            </p>
          )}
          {lastResult.operations?.length === 0 && (
            <p className="text-muted">
              That instruction wasn't clear enough to act on — try naming the element to
              change, e.g. "make the headline bigger".
            </p>
          )}
        </div>
      )}

      <div className="mt-3 flex gap-1.5 border-t border-line pt-2">
        <button
          type="button"
          onClick={() => setComparing((v) => !v)}
          className="btn btn-ghost btn-sm flex-1 text-[11px]"
          disabled={!dirty}
          title={dirty ? 'Compare with the original' : 'No changes yet'}
        >
          {comparing ? 'Hide comparison' : 'Compare'}
        </button>
        <button
          type="button"
          onClick={onRevert}
          className="btn btn-ghost btn-sm flex-1 text-[11px]"
          disabled={!dirty || busy}
        >
          Revert to original
        </button>
      </div>

      {comparing && dirty && (
        <div className="mt-2 flex gap-2">
          <Thumb label="Before" doc={originalDocument} aspect={aspect} idPrefix="cmp-before" />
          <Thumb label="After" doc={currentDocument} aspect={aspect} idPrefix="cmp-after" />
        </div>
      )}
    </Wrapper>
  )
}
