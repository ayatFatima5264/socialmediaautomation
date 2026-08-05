import AdCreativeArt from '../AdCreativeArt.jsx'

// ---------------------------------------------------------------------------
// The centre column — where the result appears.
//
// Nothing is generated yet, so the stage shows a dimmed example of the output
// behind a label that says exactly that. Two things it deliberately does not
// do: pretend a real creative was produced, and sit empty. A blank rectangle
// tells the user nothing about what this tool returns; a faded sample with an
// honest caption tells them the shape of the answer without claiming it is
// theirs.
//
// ---- Sizing ---------------------------------------------------------------
// The frame is sized by its HEIGHT, with the width derived from the aspect
// ratio — not the other way round. Constraining width is what made a 9:16
// preview 910px tall inside a 512px-wide box, which overflowed the column and
// gave it a scrollbar of its own.
//
// So: a capped height, `width: auto`, and `aspect-ratio` to compute the width.
// The frame is a flex item, which is what lets width:auto shrink-to-fit rather
// than filling the column. The cap is the smaller of a share of the viewport
// and a fixed ceiling, so it stays bounded on a tall monitor too.
// ---------------------------------------------------------------------------

// Kept as ratio VALUES rather than Tailwind aspect-* classes: the width is
// computed from these, and a utility class cannot be read back to do that.
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
  phase,
  toolName,
  caption,
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

          {/* A corner badge rather than a full-screen scrim. Washing the whole
              frame out to carry the caption left nothing to look at — and the
              sample is the point of the panel. The badge still sits ON the
              image, so a screenshot of the preview carries the disclaimer. */}
          <span className="badge badge-accent absolute left-2.5 top-2.5 bg-surface shadow-sm">
            Example output
          </span>
        </div>

        <p className="max-w-sm text-center text-xs leading-relaxed text-muted">
          {toolName} generation arrives in phase {phase}. This is the shape of the result —
          not a creative made from your settings.
        </p>

        {children && <div className="w-full">{children}</div>}
      </div>
    </div>
  )
}
