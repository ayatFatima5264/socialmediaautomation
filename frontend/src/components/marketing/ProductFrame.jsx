// ---------------------------------------------------------------------------
// The frame every product screenshot on the marketing site sits in.
//
// One component so the presentation can never drift shot to shot: same chrome,
// same border, same radius, same shadow, same caption treatment. The label in
// the chrome bar is the real route the screenshot was taken on, which is also
// what stops these reading as decorative mockups.
//
// Screenshots are captured from the running application at 2× and shipped as
// WebP. `width`/`height` are the file's intrinsic pixels — always pass them, or
// the image reserves no space and the page reflows as it loads.
//
// `mobileSrc` is a separately-captured portrait screenshot, not a scaled-down
// desktop one: a 1500px-wide screen shrunk into a 360px column is unreadable.
//
// MOBILE FALLBACK — for the shots that have no `mobileSrc`. They used to be
// rendered at the column's full width and nothing more, which on a 390px phone
// meant a 1600px screenshot at 356px: 4.5 source pixels per CSS pixel, so every
// label inside the product turned to grey mush and the shot read as a broken
// crop rather than a screen. Below `md` those images instead keep a floor of
// 680px and the frame pans sideways, which is 2.4 source pixels per CSS pixel —
// the same density as the hand-captured portrait shots, i.e. actually legible.
// ---------------------------------------------------------------------------

export default function ProductFrame({
  src,
  mobileSrc,
  alt,
  width,
  height,
  mobileWidth,
  mobileHeight,
  label,
  caption,
  priority = false,
  className = '',
}) {
  // No portrait capture for this screen, so the desktop one has to stay
  // readable on a phone by panning instead of shrinking.
  const pans = !mobileSrc

  const img = (
    <img
      src={src}
      alt={alt}
      width={width}
      height={height}
      loading={priority ? 'eager' : 'lazy'}
      // The hero shot is the LCP element, so it must not wait in the lazy queue
      // or be decoded off the critical path.
      fetchPriority={priority ? 'high' : undefined}
      decoding={priority ? 'sync' : 'async'}
      className={`block h-auto w-full ${pans ? 'min-w-[680px] md:min-w-0' : ''}`}
    />
  )

  return (
    // min-w-0: the panning image below has a 680px min-content width, and a
    // grid or flex item defaults to `min-width: auto` — without this the frame
    // would stretch its own column to 680px instead of scrolling inside it.
    <figure className={`m-0 min-w-0 ${className}`}>
      <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-[0_1px_2px_rgba(22,40,31,0.06),0_18px_40px_-24px_rgba(22,40,31,0.35)]">
        {/* Browser chrome. Decorative, so it is hidden from assistive tech —
            the alt text on the image below carries the meaning. */}
        <div
          className="flex items-center gap-2 border-b border-line bg-inset px-3 py-2"
          aria-hidden="true"
        >
          <span className="flex gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full border border-line bg-surface" />
            <span className="h-2.5 w-2.5 rounded-full border border-line bg-surface" />
            <span className="h-2.5 w-2.5 rounded-full border border-line bg-surface" />
          </span>
          {label && (
            <span className="ml-2 truncate rounded-md bg-surface px-2 py-0.5 text-[11px] font-medium text-muted">
              {label}
            </span>
          )}
        </div>

        {mobileSrc ? (
          <picture>
            <source
              media="(max-width: 767px)"
              srcSet={mobileSrc}
              width={mobileWidth}
              height={mobileHeight}
            />
            {img}
          </picture>
        ) : (
          <div className="overflow-x-auto md:overflow-x-visible">{img}</div>
        )}
      </div>

      {(caption || pans) && (
        <figcaption className="mt-3 text-sm text-muted">
          {pans && (
            <span className="mr-1.5 md:hidden" aria-hidden="true">
              Swipe across the screenshot to see the rest.
            </span>
          )}
          {caption}
        </figcaption>
      )}
    </figure>
  )
}
