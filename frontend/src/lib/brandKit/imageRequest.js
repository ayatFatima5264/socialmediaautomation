// ---------------------------------------------------------------------------
// The shared image-request vocabulary.
//
// Three pure builders that turn "which template, which brand kit, which size"
// into the shapes the rest of the system speaks: the extra fields sent to the
// image endpoint, and the layer list the renderer and the editor consume.
//
// These were inline in the AI Generator. They live here because the Content
// Planner needs the identical pipeline — a planner post and a generator draft
// must produce the same picture from the same settings, and the only way to
// guarantee that is for both to call this code rather than their own copy of it.
// ---------------------------------------------------------------------------

// Extensions are explicit throughout lib/brandKit so these modules stay
// runnable under plain Node — which is how the layout test suite exercises them.
import {
  backgroundHintFor,
  buildContentLayers,
  getContentTemplate,
  getLayout,
  safeZoneFor,
} from './contentTemplates.js'
import { buildBrandLayers } from './templates.js'
import { validateLayers } from './validateLayout.js'
import { aspectOf } from './platformSizes.js'

/**
 * Extra generation hints sent when branding is on: bias the palette toward the
 * brand colours and keep the overlay area clean. Returns {} when branding is
 * off, so spreading it into a request is always safe.
 */
export function buildBrandRequest(brandKit, brandSettings, available) {
  if (!brandSettings?.enabled || !available) return {}
  return {
    branded: true,
    brand_colors: brandKit?.brand_colors || [],
    brand_reserve: brandSettings.template === 'corner-logo' ? null : 'bottom',
  }
}

/**
 * What the chosen layout needs the artwork to be: the region it will fill with
 * text, and what kind of graphic it is. Sent with every image request so the
 * scene is composed around the design instead of fighting it.
 */
export function buildTemplateRequest(templateId) {
  return {
    background_hint: backgroundHintFor(templateId),
    safe_zone: safeZoneFor(templateId),
    template_label: getContentTemplate(templateId).label,
  }
}

/**
 * The exact layer stack the renderer draws, computed outside the render tree so
 * the editor can be handed precisely what is on screen — including the
 * placement chosen for that specific image, or the design would shift the
 * moment the user opened it.
 */
export function composeLayers({
  templateId,
  sizeId,
  content,
  brandKit,
  brandSettings,
  brandAvailable,
  slideIndex,
  placement,
}) {
  const aspect = aspectOf(sizeId)
  const layers = [
    ...(content
      ? buildContentLayers(templateId, content, { brandKit, slideIndex, placement, aspect })
      : []),
    ...(brandSettings?.enabled && brandAvailable ? buildBrandLayers(brandKit, brandSettings) : []),
  ]
  return validateLayers(layers, { aspect, layout: getLayout(templateId) })
}
