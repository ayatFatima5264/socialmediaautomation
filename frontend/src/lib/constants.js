// Platform display metadata. Character limits mirror the backend PLATFORM_SPECS.
export const PLATFORMS = {
  instagram: { label: 'Instagram', limit: 2200, color: '#E1306C', initial: 'Ig' },
  facebook: { label: 'Facebook', limit: 63206, color: '#1877F2', initial: 'Fb' },
  twitter: { label: 'Twitter / X', limit: 280, color: '#38BDF8', initial: 'X' },
  linkedin: { label: 'LinkedIn', limit: 3000, color: '#0A66C2', initial: 'in' },
  threads: { label: 'Threads', limit: 500, color: '#64748B', initial: '@' },
  pinterest: { label: 'Pinterest', limit: 500, color: '#E60023', initial: 'P' },
}

export const PLATFORM_KEYS = Object.keys(PLATFORMS)

export const TONES = [
  'professional',
  'casual',
  'funny',
  'inspirational',
  'bold',
  'friendly',
  'informative',
  'promotional',
]

// ---- AI image composition options (mirror the backend) --------------------
export const ASPECT_RATIOS = [
  { value: '1:1', label: 'Square (1:1)' },
  { value: '4:5', label: 'Portrait (4:5)' },
  { value: '9:16', label: 'Story / Reel (9:16)' },
  { value: '16:9', label: 'Landscape (16:9)' },
  { value: '2:3', label: 'Tall / Pin (2:3)' },
]

export const IMAGE_STYLES = [
  { value: 'realistic', label: 'Realistic' },
  { value: 'minimal', label: 'Minimal' },
  { value: 'illustration', label: 'Illustration' },
  { value: '3d', label: '3D' },
  { value: 'cartoon', label: 'Cartoon' },
  { value: 'watercolor', label: 'Watercolor' },
  { value: 'anime', label: 'Anime' },
]

export const IMAGE_QUALITIES = [
  { value: 'standard', label: 'Standard' },
  { value: 'hd', label: 'HD' },
]

export const CAROUSEL_SLIDE_OPTIONS = [2, 3, 4, 5, 6, 7, 8, 9, 10]

// Recommended aspect ratio per platform — applied when a platform is first
// selected, but the user can always change it (globally or via an override).
export const PLATFORM_ASPECT_DEFAULT = {
  instagram: '1:1',
  facebook: '1:1',
  twitter: '16:9',
  linkedin: '16:9',
  threads: '4:5',
  pinterest: '2:3',
}

// Global image settings the composer starts with.
export const DEFAULT_IMAGE_SETTINGS = {
  aiImage: true,
  aspectRatio: '1:1',
  carousel: false,
  slides: 5,
  style: 'realistic',
  quality: 'standard',
  negative: '',
  promptEnhancer: false,
}

export const STATUS_STYLES = {
  draft: 'bg-slate-500/15 text-slate-500 dark:text-slate-300',
  scheduled: 'bg-amber-500/15 text-amber-600 dark:text-amber-300',
  publishing: 'bg-sky-500/15 text-sky-600 dark:text-sky-300',
  published: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300',
  failed: 'bg-rose-500/15 text-rose-600 dark:text-rose-300',
}
