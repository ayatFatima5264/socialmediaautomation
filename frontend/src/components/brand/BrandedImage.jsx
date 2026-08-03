import { useMemo } from 'react'
import BrandOverlay from './BrandOverlay.jsx'
import { buildBrandLayers } from '../../lib/brandKit/templates'
import { hasBrandAssets } from '../../lib/brandKit/layers'

// ---------------------------------------------------------------------------
// An image with its brand layers composited on top.
//
// The single component every surface should use to display a generated image —
// Generator cards, Create Post previews, the Content Planner — so branding
// appears consistently without each caller re-implementing the overlay.
//
// The overlay is positioned, not baked in: the underlying <img> is untouched,
// so switching branding off is instant and costs no regeneration.
// ---------------------------------------------------------------------------

export default function BrandedImage({
  src,
  alt = '',
  brandKit,
  settings,
  aspect = 1,
  className = '',
  imgClassName = 'h-full w-full object-cover',
  onClick,
  children,
}) {
  const layers = useMemo(() => {
    if (!settings?.enabled || !hasBrandAssets(brandKit)) return []
    return buildBrandLayers(brandKit, settings)
  }, [brandKit, settings])

  // Namespace the SVG gradient ids per image — several branded images render
  // side by side in the Generator, and SVG ids are document-global.
  const idPrefix = useMemo(
    () => `bo-${String(src || '').slice(-24).replace(/[^a-z0-9]/gi, '')}`,
    [src],
  )

  return (
    <div className={`relative overflow-hidden ${className}`} onClick={onClick}>
      <img src={src} alt={alt} className={imgClassName} crossOrigin="anonymous" loading="lazy" />
      <BrandOverlay layers={layers} aspect={aspect} idPrefix={idPrefix} />
      {children}
    </div>
  )
}
