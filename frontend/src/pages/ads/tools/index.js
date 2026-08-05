import AbTesting from './AbTesting.jsx'
import AdCopy from './AdCopy.jsx'
import BannerGenerator from './BannerGenerator.jsx'
import CarouselAds from './CarouselAds.jsx'
import CtaGenerator from './CtaGenerator.jsx'
import HeadlineGenerator from './HeadlineGenerator.jsx'
import ImageToVideo from './ImageToVideo.jsx'
import MediaLibraryPage from './MediaLibraryPage.jsx'
import ProductAds from './ProductAds.jsx'
import ProductShowcaseVideo from './ProductShowcaseVideo.jsx'
import SlideshowVideo from './SlideshowVideo.jsx'
import TemplatesPage from './TemplatesPage.jsx'
import TextToVideo from './TextToVideo.jsx'

// ---------------------------------------------------------------------------
// Which tools have a page of their own.
//
// Keyed by the slug in lib/ads/tools.js. A tool absent from this map falls
// through to AdToolPlaceholder, so shipping a page is one line here and nothing
// in App.jsx — the module keeps a single dynamic route rather than growing one
// <Route> per tool as the phases land.
//
// `brand-kit` is deliberately absent: it carries a `to` in the registry and
// links straight to the business profile, which is the real page.
// ---------------------------------------------------------------------------

export const TOOL_PAGES = {
  // Create Ads
  'product-ads': ProductAds,
  'banner-generator': BannerGenerator,
  'carousel-ads': CarouselAds,

  // Video Ads
  'image-to-video': ImageToVideo,
  'text-to-video': TextToVideo,
  'product-showcase-video': ProductShowcaseVideo,
  'slideshow-video': SlideshowVideo,

  // AI Tools
  'ad-copy': AdCopy,
  'headline-generator': HeadlineGenerator,
  'cta-generator': CtaGenerator,
  'ab-testing': AbTesting,

  // Assets
  'media-library': MediaLibraryPage,
  templates: TemplatesPage,
}

export function getToolPage(slug) {
  return TOOL_PAGES[slug] || null
}
