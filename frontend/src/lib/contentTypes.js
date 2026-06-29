// Content types and platform-capability rules, shared by the AI Generator and
// the Create Post composer so both behave identically.

export const CONTENT_TYPES = {
  post: { id: 'post', label: 'Social Post', icon: '📝' },
  image: { id: 'image', label: 'Image Post', icon: '🖼' },
  video: { id: 'video', label: 'Video Post', icon: '🎥' },
  carousel: { id: 'carousel', label: 'Carousel', icon: '📚' },
  link: { id: 'link', label: 'Link Post', icon: '🔗' },
  article: { id: 'article', label: 'LinkedIn Article', icon: '📰' },
}

export const CONTENT_TYPE_ORDER = ['post', 'image', 'video', 'carousel', 'link', 'article']
export const UNIVERSAL_TYPES = ['post', 'image', 'video']

// Which platforms support the gated content types.
export const CAROUSEL_PLATFORMS = new Set(['instagram', 'facebook', 'linkedin', 'twitter', 'threads'])
export const LINK_PLATFORMS = new Set(['facebook', 'linkedin', 'twitter', 'threads', 'pinterest'])

export function isLinkedInOnly(selected) {
  return selected.length === 1 && selected[0] === 'linkedin'
}

// Per-type { enabled, reason } for the current platform selection.
export function contentTypeStates(selected) {
  const states = {}
  for (const id of UNIVERSAL_TYPES) states[id] = { enabled: true }

  const hasSel = selected.length > 0
  states.carousel =
    hasSel && selected.every((p) => CAROUSEL_PLATFORMS.has(p))
      ? { enabled: true }
      : { enabled: false, reason: 'Carousel is not available for all selected platforms.' }

  states.link =
    hasSel && selected.every((p) => LINK_PLATFORMS.has(p))
      ? { enabled: true }
      : { enabled: false, reason: 'Link Posts are not fully supported across the selected platforms.' }

  states.article = isLinkedInOnly(selected)
    ? { enabled: true }
    : { enabled: false, reason: 'LinkedIn Articles can only be generated and published when LinkedIn is the only selected platform.' }

  return states
}
