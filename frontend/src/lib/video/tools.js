// ---------------------------------------------------------------------------
// Video Studio — the module's feature registry.
//
// One list drives everything: the tool cards on the Overview, the sidebar's
// expandable section, the module's routes in App.jsx, each placeholder page's
// copy, and the private route/title entries in seo/pages.data.js. Shipping a
// tool means pointing its entry at a real page in pages/video/tools/index.js —
// App.jsx never grows, and routing cannot disagree with what exists.
//
// This is the same shape lib/ads/tools.js uses, and for the same reason. It is
// deliberately dependency-free and free of Vite-specific syntax (no
// import.meta, no JSX, no ?raw globs): seo/pages.data.js imports it, and that
// module is loaded by the Node-side build plugin.
//
// `built: false` is not decoration. It is what makes the Overview show a tool
// as "Coming soon" instead of offering a button that goes nowhere — the
// placeholder is generated from the same entry, so a tool cannot be advertised
// as working before it is.
// ---------------------------------------------------------------------------

export const VIDEO_BASE_PATH = '/video'

// ---------------------------------------------------------------------------
// Sections
// ---------------------------------------------------------------------------
// The Overview groups cards rather than listing eight of them flat: ungrouped,
// the user has no answer to "what do I do first". Order here is the order on
// the page — creating comes before polishing.

export const VIDEO_CATEGORIES = [
  {
    key: 'create',
    label: 'Create',
    description: 'Start a video from an idea, a script, a recording or nothing at all.',
  },
  {
    key: 'produce',
    label: 'Produce',
    description: 'The pieces a finished video is made of — voice, captions, the edit.',
  },
  {
    key: 'assets',
    label: 'Assets',
    description: 'Templates, music and thumbnails you can reuse across projects.',
  },
]

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------
// `to` sends a card at a specific page. `slug` is what /video/:slug resolves
// through. `tint` gives each card its own identity while staying inside the
// palette the app already uses — the mint accent stays the module's primary
// and these colour the icon tile only.

export const VIDEO_TOOLS = [
  // ---- Create -------------------------------------------------------------
  {
    slug: 'create',
    name: 'Create Video',
    description: 'Start a new project — from AI, a script, a recording, or a blank canvas.',
    category: 'create',
    tint: 'emerald',
    icon: 'sparkle',
    featured: true,
    built: true,
    to: '/video/create',
    longDescription:
      'Pick how you want to begin and the platform you are making for. Video Studio sets up the canvas, the caption style and the storyboard, and opens the project ready to work on.',
  },
  {
    slug: 'script',
    name: 'Script Studio',
    description: 'Write a script from a topic. Turn it into a video only if you want to.',
    category: 'create',
    tint: 'teal',
    icon: 'document',
    built: true,
    longDescription:
      'The eight things a script is written from — topic, language, tone, audience, length, platform, content type and your own instructions — and a script you can rewrite a section at a time. Nothing is saved until you ask for a project, so trying an idea costs nothing.',
    capabilities: [
      'Hook, introduction, main points, ending and call to action',
      'Rewrite one section without touching the rest',
      'Copy or download the script on its own',
      'Turn it into a video project, keeping your edits',
    ],
  },
  {
    slug: 'projects',
    name: 'Projects',
    description: 'Every video you are working on, searchable and filterable.',
    category: 'create',
    tint: 'slate',
    icon: 'grid',
    built: true,
    to: '/video/projects',
    longDescription:
      'Open, rename, duplicate or delete any project. Search by name and filter by platform or status.',
  },
  {
    slug: 'repurpose',
    name: 'Repurpose',
    description: 'Turn one long video into a set of shorts sized for each platform.',
    category: 'create',
    tint: 'amber',
    icon: 'scissors',
    built: true,
    longDescription:
      'Upload a long recording and Video Studio transcribes it, finds the moments worth clipping, and builds a short project from each one — already sized for Shorts, Reels and TikTok.',
    capabilities: [
      'Transcription with speaker detection',
      'AI-picked moments, each editable before rendering',
      'One project per clip, at the right aspect ratio',
    ],
  },

  // ---- Produce ------------------------------------------------------------
  {
    slug: 'voice',
    name: 'Voice Studio',
    description: 'Turn a script into a natural-sounding voice-over.',
    category: 'produce',
    tint: 'violet',
    icon: 'mic',
    built: true,
    featured: true,
    longDescription:
      'Type or paste a script, pick a voice and a language, and generate a voice-over you can download or add to a project. Works on its own — no project required.',
    capabilities: [
      'Voices in English, Urdu, Roman Urdu, Hindi and Arabic',
      'Speed, pitch and volume control with a live preview',
      'Download as MP3 or WAV, or add straight to a project',
    ],
  },
  {
    slug: 'subtitles',
    name: 'Subtitle Studio',
    description: 'Generate, edit and export subtitles from audio or video.',
    category: 'produce',
    tint: 'sky',
    icon: 'captions',
    built: true,
    featured: true,
    longDescription:
      'Upload a file and get timed captions back, or write them by hand. Edit the wording and the timing, pick a style, and export SRT or VTT — or burn them into the video.',
    capabilities: [
      'Transcription with automatic language detection',
      'Cue-by-cue editing with reading-speed limits applied',
      'SRT, VTT and plain-text export, plus translation',
    ],
  },
  {
    slug: 'editor',
    name: 'Video Editor',
    description: 'Arrange clips, audio and text on a timeline.',
    category: 'produce',
    tint: 'indigo',
    icon: 'timeline',
    built: true,
    featured: true,
    to: '/video/editor',
    longDescription:
      'The manual edit: one video track, one audio track and one text track, with drag, trim, split and reorder — and a preview drawn from the same timeline the export is rendered from.',
    capabilities: [
      'Video, audio and text tracks',
      'Trim, split, reorder, crop, scale, speed and volume',
      'Autosave and undo, with an MP4 export that matches the timeline',
    ],
  },

  // ---- Assets -------------------------------------------------------------
  {
    slug: 'media',
    name: 'Media Library',
    description: 'Every file Video Studio can use, in one place.',
    category: 'assets',
    tint: 'slate',
    icon: 'image',
    built: true,
    longDescription:
      'Search, preview and reuse every clip, image, voice-over, caption file and render you have. Deleting warns you first when a project is using the file.',
    capabilities: [
      'Search and filter by kind, with live counts',
      'Preview video, audio and images in place',
      'Reuse in any project, or delete with a warning when it is in use',
    ],
  },
  {
    slug: 'templates',
    name: 'Templates',
    description: 'Ready-made starting points for each platform and format.',
    category: 'assets',
    tint: 'teal',
    icon: 'layout',
    built: true,
    to: '/video/templates',
    longDescription:
      'Every template sets a canvas, a caption style and a storyboard. Pick one and it opens as a new project.',
  },
  {
    slug: 'music',
    name: 'Music Library',
    description: 'Licensed background tracks, searchable by mood and length.',
    category: 'assets',
    tint: 'rose',
    icon: 'music',
    built: false,
    longDescription:
      'A catalogue of tracks that are cleared for use, with the licence and attribution shown before you pick one.',
    capabilities: [
      'Filter by mood, genre and duration',
      'Licence and attribution recorded on the project',
      'Automatic ducking under a voice-over',
    ],
  },
  {
    slug: 'thumbnails',
    name: 'Thumbnail Studio',
    description: 'Design a thumbnail using your Brand Kit.',
    category: 'assets',
    tint: 'orange',
    icon: 'image',
    built: true,
    longDescription:
      'Compose a thumbnail from a frame of your video or an uploaded image, with your logo, colours and fonts already applied.',
    capabilities: [
      'Templates sized for YouTube and each vertical surface',
      'Brand Kit colours, logo and contact details applied',
      'Download as PNG or JPG, or set as the project thumbnail',
    ],
  },
]

const BY_SLUG = new Map(VIDEO_TOOLS.map((tool) => [tool.slug, tool]))

/** One tool by slug, or undefined. */
export function getTool(slug) {
  return BY_SLUG.get(slug)
}

/** Where a tool's card should link. Built tools have a page; others get the
 *  placeholder route, which explains what the tool will do. */
export function toolPath(tool) {
  return tool.to || `${VIDEO_BASE_PATH}/${tool.slug}`
}

/** The tools in one category, in registry order. */
export function toolsInCategory(key) {
  return VIDEO_TOOLS.filter((tool) => tool.category === key)
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------
// The expandable Video Studio section. Deliberately a separate, shorter list
// than the Overview's cards: a sidebar is for navigating to a place, so it
// names the destinations, while the Overview explains what each one does.

export const VIDEO_NAV = [
  { to: '/video', label: 'Overview', end: true },
  { to: '/video/projects', label: 'Projects' },
  { to: '/video/create', label: 'Create Video' },
  { to: '/video/script', label: 'Script Studio' },
  { to: '/video/voice', label: 'Voice Studio' },
  { to: '/video/subtitles', label: 'Subtitle Studio' },
  { to: '/video/editor', label: 'Video Editor' },
  { to: '/video/media', label: 'Media Library' },
  { to: '/video/templates', label: 'Templates' },
  { to: '/video/music', label: 'Music Library' },
  { to: '/video/thumbnails', label: 'Thumbnail Studio' },
]

// ---------------------------------------------------------------------------
// How a project is started
// ---------------------------------------------------------------------------
// These `key` values are the backend's `project_type` — see PROJECT_TYPES in
// app/models/video_project.py. They are sent verbatim, so the two lists must
// not drift; a value the server does not know is refused with a 422.

export const CREATE_MODES = [
  {
    key: 'ai',
    name: 'AI Video',
    description: 'Describe a topic and let AI write the script and build the scenes.',
    icon: 'sparkle',
    tint: 'emerald',
    ready: true,
    // Its own screen rather than this one's format picker: an AI video is
    // described in words (topic, tone, audience) before a canvas is chosen,
    // and the platform comes out of that brief.
    to: '/video/ai',
  },
  {
    key: 'blank',
    name: 'Blank Video',
    description: 'Start from an empty canvas and build it yourself.',
    icon: 'square',
    tint: 'slate',
    ready: true,
  },
  {
    key: 'script',
    name: 'From Script',
    description: 'Paste a script and turn each section into a scene.',
    icon: 'document',
    tint: 'sky',
    ready: true,
  },
  {
    key: 'existing_video',
    name: 'From Existing Video',
    description: 'Upload a video and edit, caption or resize it.',
    icon: 'film',
    tint: 'indigo',
    ready: false,
  },
  {
    key: 'audio',
    name: 'From Audio',
    description: 'Turn a recording or a voice-over into a captioned video.',
    icon: 'music',
    tint: 'violet',
    ready: false,
  },
  {
    key: 'repurpose',
    name: 'Repurpose Content',
    description: 'Cut a long video into shorts for every platform.',
    icon: 'scissors',
    tint: 'amber',
    ready: false,
  },
]

// ---------------------------------------------------------------------------
// SEO
// ---------------------------------------------------------------------------
// The module answers questions about its own paths, so seo/pages.data.js does
// not need to know the shape of a nested or id-bearing route. One
// `Disallow: /video` covers the whole subtree.

export function isVideoPath(path) {
  return path === VIDEO_BASE_PATH || path.startsWith(`${VIDEO_BASE_PATH}/`)
}

export function videoRouteTitle(path) {
  if (!isVideoPath(path)) return null
  if (path === VIDEO_BASE_PATH) return 'Video Studio'

  const rest = path.slice(VIDEO_BASE_PATH.length + 1)

  // /video/projects/123 — the id is not knowable at build time, so the title
  // names the section rather than pretending to know the project.
  if (rest.startsWith('projects/')) {
    if (rest.endsWith('/edit')) return 'Video Editor'
    if (rest.endsWith('/export')) return 'Export Video'
    return 'Video Project'
  }
  // Screens that are not tool slugs but have their own route.
  if (rest === 'ai') return 'AI Video'

  const tool = BY_SLUG.get(rest)
  return tool ? tool.name : 'Video Studio'
}
