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
      className="block h-auto w-full"
    />
  )

  return (
    <figure className={`m-0 ${className}`}>
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
          img
        )}
      </div>

      {caption && (
        <figcaption className="mt-3 text-sm text-muted">{caption}</figcaption>
      )}
    </figure>
  )
}
