import { useCallback, useMemo } from 'react'
import { api } from '../lib/api'
import useBrandKit from './useBrandKit'
import {
  buildBrandRequest,
  buildTemplateRequest,
  composeLayers,
} from '../lib/brandKit/imageRequest'
import {
  getContentTemplate,
  maxCharsFor,
  DEFAULT_TEMPLATE_ID,
} from '../lib/brandKit/contentTemplates'
import { getSize, DEFAULT_SIZE } from '../lib/brandKit/platformSizes'
import { DEFAULT_IMAGE_SETTINGS } from '../lib/constants'

// ---------------------------------------------------------------------------
// The image studio: one pipeline, two pages.
//
// This hook deliberately does NOT own the settings. The AI Generator keeps its
// settings in localStorage-backed page state; the Content Planner resolves
// them per post from a plan default plus an optional override. Making the hook
// the state owner would have forced one of those shapes onto the other, so it
// takes resolved settings as input and returns the derived request shapes, the
// layer composer, and the generate call.
//
// The consequence that matters: a planner post and a generator draft built from
// the same settings hit the same endpoint with the same body, so they cannot
// drift apart.
// ---------------------------------------------------------------------------

/** The settings an image is generated from. Missing keys fall back to defaults. */
export function resolveStudioSettings(partial) {
  return {
    templateId: partial?.templateId ?? DEFAULT_TEMPLATE_ID,
    sizeId: partial?.sizeId ?? DEFAULT_SIZE,
    ...DEFAULT_IMAGE_SETTINGS,
    ...(partial?.img || {}),
  }
}

/** The settings object as stored — what a plan default or post override holds. */
export function studioValue(partial) {
  return {
    templateId: partial?.templateId ?? DEFAULT_TEMPLATE_ID,
    sizeId: partial?.sizeId ?? DEFAULT_SIZE,
    img: { ...DEFAULT_IMAGE_SETTINGS, ...(partial?.img || {}) },
    brand: partial?.brand ?? null,
  }
}

/**
 * Merge a plan-level default with a per-post override. `override.enabled`
 * decides: off means the post is the plan's, on means only the keys the post
 * actually set diverge — so turning an override on and changing one field does
 * not silently reset the other four.
 */
export function mergeStudioSettings(planDefaults, override) {
  const base = studioValue(planDefaults)
  if (!override?.enabled) return base
  return {
    templateId: override.templateId ?? base.templateId,
    sizeId: override.sizeId ?? base.sizeId,
    img: { ...base.img, ...(override.img || {}) },
    brand: override.brand ?? base.brand,
  }
}

export default function useImageStudio(settings) {
  const s = useMemo(() => resolveStudioSettings(settings), [settings])

  const {
    brandKit,
    settings: globalBrand,
    setSettings: setBrandSettings,
    available: brandAvailable,
  } = useBrandKit()

  // A settings object may carry its own brand preference. The planner uses this
  // so one post can drop the branding without changing it for the whole plan;
  // the generator passes nothing and keeps the user's global preference.
  const brandSettings = useMemo(
    () => (settings?.brand ? { ...globalBrand, ...settings.brand } : globalBrand),
    [globalBrand, settings?.brand],
  )

  const brandRequest = useMemo(
    () => buildBrandRequest(brandKit, brandSettings, brandAvailable),
    [brandKit, brandSettings, brandAvailable],
  )

  const templateRequest = useMemo(
    () => buildTemplateRequest(s.templateId),
    [s.templateId],
  )

  // Same composition the renderer performs. Handed to the editor so it opens on
  // exactly what the user is looking at.
  const composeForEditor = useCallback(
    (content, slideIndex, placement) =>
      composeLayers({
        templateId: s.templateId,
        sizeId: s.sizeId,
        content,
        brandKit,
        brandSettings,
        brandAvailable,
        slideIndex,
        placement,
      }),
    [s.templateId, s.sizeId, brandKit, brandSettings, brandAvailable],
  )

  /**
   * Write the on-image copy for the current template. Optional by design: a
   * failure here leaves an unlayered image rather than no image at all.
   */
  const generateTemplateCopy = useCallback(
    async ({ topic, tone, audience }) => {
      const template = getContentTemplate(s.templateId)
      try {
        const r = await api.generateTemplateContent({
          topic,
          template_label: template.label,
          slots: template.slots,
          max_chars: maxCharsFor(s.templateId),
          tone,
          audience: audience || null,
        })
        return r.content
      } catch {
        return null
      }
    },
    [s.templateId],
  )

  /**
   * Generate artwork for one post. Returns { images, templateContent }.
   *
   * The headline is fetched first because it briefs the artwork — the design's
   * message should shape the picture, not be pasted onto an unrelated one.
   */
  const generateImages = useCallback(
    async ({
      prompt,
      platform,
      tone,
      audience,
      headline,
      skipCopy = false,
      // Per-call setting overrides. The AI Generator resolves per-platform
      // overrides before it asks, so one card can be a carousel while another
      // is a single 4:5 image — without the page-level settings changing.
      settings: perCall,
    } = {}) => {
      const eff = perCall ? { ...s, ...perCall } : s
      const copy = skipCopy ? null : await generateTemplateCopy({ topic: prompt, tone, audience })

      const res = await api.generateImages({
        prompt,
        platform: platform || undefined,
        aspect_ratio: eff.aspectRatio,
        carousel: eff.carousel,
        slides: eff.carousel ? eff.slides : 1,
        style: eff.style,
        quality: eff.quality,
        negative_prompt: eff.negative || null,
        prompt_enhancer: eff.promptEnhancer,
        ...brandRequest,
        ...templateRequest,
        headline: headline ?? copy?.headline ?? null,
      })

      return { images: res.images, templateContent: copy }
    },
    [s, brandRequest, templateRequest, generateTemplateCopy],
  )

  return {
    settings: s,
    size: getSize(s.sizeId),
    template: getContentTemplate(s.templateId),
    brandKit,
    brandSettings,
    setBrandSettings,
    brandAvailable,
    brandRequest,
    templateRequest,
    composeForEditor,
    generateTemplateCopy,
    generateImages,
  }
}
