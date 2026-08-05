import AdCreativeArt from '../AdCreativeArt.jsx'

// ---------------------------------------------------------------------------
// The centre column BEFORE anything has been produced.
//
// Every tool that uses this now works, so this panel is an empty state, not a
// "coming soon" notice: it shows an example of the output and tells the user
// what to do to get their own. It must never claim the feature is unbuilt —
// that message outlived the placeholders and ended up contradicting the rail
// beside it, which correctly said the tool renders.
//
// Once a tool has a result, the caller replaces this panel entirely rather
// than layering the real output over the sample. Mixing the two is how a user
// ends up unsure which image is theirs.
//
// ---- Sizing ---------------------------------------------------------------
// The frame is sized by its HEIGHT, with the width derived from the aspect
// ratio — not the other way round. Constraining width is what made a 9:16
// preview 910px tall inside a 512px-wide box, which overflowed the column and
// gave it a scrollbar of its own.
// ---------------------------------------------------------------------------

// Ratio VALUES rather than Tailwind aspect-* classes: the width is computed
// from these, and a utility class cannot be read back to do that.
const RATIOS = {
  square: '1 / 1',
  landscape: '16 / 9',
  portrait: '4 / 5',
  story: '9 / 16',
  wide: '1200 / 628',
  banner: '728 / 90',
}

// Matches the artwork's own backdrop, so the bands `meet` leaves around a
// portrait scene read as part of the image rather than as empty space.
const FRAME_BG = '#F3EDE3'

export default function PreviewStage({
  art,
  ratio = 'square',
  toolName,
  caption,
  /** What the user should do next. Says nothing about phases or roadmaps. */
  hint,
  children,
}) {
  return (
    <div className="card flex min-h-[320px] flex-col p-4 lg:min-h-full">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-body">Preview</h2>
        {caption && <span className="text-xs text-muted">{caption}</span>}
      </div>

      <div className="flex flex-1 flex-col items-center justify-center gap-3">
        <div
          className="relative shrink-0 overflow-hidden rounded-xl border border-line"
          style={{
            aspectRatio: RATIOS[ratio] || RATIOS.square,
            height: 'min(46vh, 400px)',
            width: 'auto',
            maxWidth: '100%',
            background: FRAME_BG,
          }}
        >
          <AdCreativeArt name={art} fit="meet" className="h-full w-full" />

          {/* A corner badge rather than a full-frame scrim: the sample is the
              point of the panel, and washing it out to carry a caption left
              nothing to look at. The badge sits ON the image, so a screenshot
              of the preview carries the label with it. */}
          <span className="badge badge-accent absolute left-2.5 top-2.5 bg-surface shadow-sm">
            Example
          </span>
        </div>

        <p className="max-w-sm text-center text-xs leading-relaxed text-muted">
          {hint || `An example of what ${toolName} produces. Fill in the settings on the left, then press the button below them to make your own.`}
        </p>

        {children && <div className="w-full">{children}</div>}
      </div>
    </div>
  )
}
