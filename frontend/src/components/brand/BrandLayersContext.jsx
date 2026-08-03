import { createContext, useContext, useMemo } from 'react'
import { buildBrandLayers } from '../../lib/brandKit/templates'
import { buildContentLayers, getLayout } from '../../lib/brandKit/contentTemplates'
import { hasBrandAssets } from '../../lib/brandKit/layers'
import { validateLayers } from '../../lib/brandKit/validateLayout'

// ---------------------------------------------------------------------------
// Supplies the layer stack to every image renderer beneath it.
//
// Two kinds of layers compose here:
//
//   brand layers   — logo, name, contact. Identical for every image on the
//                    page, so they are memoised once rather than rebuilt per
//                    card.
//   content layers — headline, subtext, CTA. Different per card, because each
//                    draft has its own generated copy, so these are built on
//                    demand through `compose(content)`.
//
// Content sits under branding: a logo overlapping a headline is a bug, and
// keeping brand z-indices above content z-indices makes that ordering a
// property of the system rather than something each template must remember.
//
// The two are validated together after merging, not just individually. A
// content template and a brand template are chosen independently and neither
// can see the other's geometry, so collisions between them — a CTA under a
// footer bar, a logo on a headline — only become visible once both are in the
// same list.
//
// Images render several levels below where these are configured. Prop-drilling
// would mean every intermediate card gaining props it does not use — and a new
// image surface rendering unbranded if someone forgot one.
// ---------------------------------------------------------------------------

const RenderContext = createContext({
  brandLayers: [],
  compose: () => [],
  layout: getLayout(undefined),
})

export function BrandLayersProvider({ brandKit, settings, templateId, children }) {
  const value = useMemo(() => {
    const brandLayers =
      settings?.enabled && hasBrandAssets(brandKit) ? buildBrandLayers(brandKit, settings) : []
    const layout = getLayout(templateId)

    // `content` is a card's generated slot values; `slideIndex` numbers a
    // carousel slide; `placement` is what reading the generated image found
    // (see smartLayout.js) and `aspect` the frame's shape. All optional — with
    // none of them this returns branding only, which is exactly the Phase 1
    // behaviour.
    const compose = (content, slideIndex, placement, aspect = 1) => {
      if (!content) return validateLayers(brandLayers, { aspect, layout })
      const contentLayers = buildContentLayers(templateId, content, {
        brandKit,
        slideIndex,
        placement,
        aspect,
      })
      return validateLayers([...contentLayers, ...brandLayers], { aspect, layout })
    }

    return { brandLayers, compose, layout }
  }, [brandKit, settings, templateId])

  return <RenderContext.Provider value={value}>{children}</RenderContext.Provider>
}

/** Brand-only layers. Safe outside a provider. */
export function useBrandLayers() {
  return useContext(RenderContext).brandLayers
}

/** Compose content + brand layers for one image. Safe outside a provider. */
export function useComposeLayers() {
  return useContext(RenderContext).compose
}

/**
 * The active template's layout rules — safe zone, margins, budgets.
 * Image surfaces need these to work out where text can go on the artwork they
 * just loaded. Safe outside a provider.
 */
export function useLayout() {
  return useContext(RenderContext).layout
}
