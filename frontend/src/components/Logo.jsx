// Shared brand mark — the AutoSocial AI network icon: three connected nodes on
// an emerald rounded-square badge. Single source of truth used by the app
// sidebar, auth screen, marketing header/footer, and loader. Change the file it
// points at and it updates everywhere. `size` is the square edge in px.
//
// The mark is the real brand asset (/public/logo.png) rather than a hand-drawn
// SVG copy of it, so there is one file to change when the logo changes and no
// second version to drift out of step. It is served from /public — the same
// file the favicon and apple-touch-icon use — so a page showing the logo and
// the browser tab beside it can never disagree.
//
// `width`/`height` are set as attributes as well as styles so the element
// reserves its space before the image loads and nothing shifts around it.
export default function Logo({ size = 36, className = '' }) {
  return (
    <img
      src="/logo.png"
      width={size}
      height={size}
      alt="AutoSocial AI"
      className={className}
      style={{ width: size, height: size }}
      // The mark is decorative wherever it sits next to the wordmark, but it is
      // the only branding on the loader and the auth screen, so it keeps a real
      // alt rather than being hidden from screen readers.
      decoding="async"
    />
  )
}
