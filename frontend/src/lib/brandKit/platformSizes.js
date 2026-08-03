// ---------------------------------------------------------------------------
// Platform sizes.
//
// One place mapping a named platform format to the aspect ratio the image
// pipeline already understands. Every ratio here is a key in ASPECT_RATIOS on
// both the frontend and app/services/image_service.py, so choosing a size
// needs no backend change — it just selects an existing dimension pair.
//
// Templates declare a `defaultSize`; picking a template sets the size, and the
// user can still override it. Layers are fractional (see layers.js), so a
// layout composed for one size renders correctly at any other — changing size
// never requires repositioning anything.
// ---------------------------------------------------------------------------

export const PLATFORM_SIZES = [
  {
    id: 'ig-square',
    label: 'Instagram Square',
    platform: 'instagram',
    aspectRatio: '1:1',
    dimensions: [1080, 1080],
    hint: 'Classic feed post',
  },
  {
    id: 'ig-portrait',
    label: 'Instagram Portrait',
    platform: 'instagram',
    aspectRatio: '4:5',
    dimensions: [1080, 1350],
    hint: 'Takes more feed height',
  },
  {
    id: 'story',
    label: 'Story / Reel',
    platform: 'instagram',
    aspectRatio: '9:16',
    dimensions: [1080, 1920],
    hint: 'Full-screen vertical',
  },
  {
    id: 'facebook',
    label: 'Facebook',
    platform: 'facebook',
    aspectRatio: '1:1',
    dimensions: [1080, 1080],
    hint: 'Feed post',
  },
  {
    id: 'linkedin',
    label: 'LinkedIn',
    platform: 'linkedin',
    aspectRatio: '16:9',
    dimensions: [1920, 1080],
    hint: 'Landscape feed image',
  },
  {
    id: 'twitter',
    label: 'Twitter / X',
    platform: 'twitter',
    aspectRatio: '16:9',
    dimensions: [1920, 1080],
    hint: 'In-stream image',
  },
  {
    id: 'pinterest',
    label: 'Pinterest Pin',
    platform: 'pinterest',
    aspectRatio: '2:3',
    dimensions: [1080, 1620],
    hint: 'Tall pin',
  },
]

export const DEFAULT_SIZE = 'ig-square'

export function getSize(id) {
  return PLATFORM_SIZES.find((s) => s.id === id) || PLATFORM_SIZES.find((s) => s.id === DEFAULT_SIZE)
}

/** Numeric aspect (width / height) for a size id — what the renderers need. */
export function aspectOf(id) {
  const [w, h] = getSize(id).dimensions
  return w / h
}

/** The first size matching a platform, used when a platform is chosen first. */
export function sizeForPlatform(platform) {
  return PLATFORM_SIZES.find((s) => s.platform === platform) || getSize(DEFAULT_SIZE)
}
