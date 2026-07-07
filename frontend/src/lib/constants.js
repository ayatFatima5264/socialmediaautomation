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

// ---- Business onboarding options (mirror backend schemas.business_profile) --
export const INDUSTRIES = [
  'Technology', 'Marketing', 'Recruitment', 'Healthcare', 'Education',
  'Finance', 'Real Estate', 'E-commerce', 'Agency', 'Other',
]

export const TARGET_AUDIENCES = [
  'Small Businesses', 'Startups', 'Recruiters', 'Developers',
  'Students', 'Enterprise', 'Other',
]

export const BRAND_VOICES = [
  'Professional', 'Friendly', 'Educational', 'Conversational', 'Bold', 'Luxury',
]

export const BUSINESS_GOALS = [
  'Generate Leads', 'Increase Sales', 'Brand Awareness', 'Grow Followers',
  'Drive Website Traffic', 'Promote Products or Services',
]

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

// ---- AI Content Planner (mirror backend app/services/planner/constants.py) --
export const PLANNER_DURATIONS = [
  { value: 7, label: 'Next 7 Days', hint: 'A focused week' },
  { value: 14, label: 'Next 14 Days', hint: 'Two weeks ahead' },
  { value: 30, label: 'Next 30 Days', hint: 'A full month' },
]

export const PLANNER_FREQUENCIES = [
  { value: 'daily', label: 'Daily', hint: '7 posts / week' },
  { value: '5_week', label: '5× per week', hint: 'Weekdays' },
  { value: '3_week', label: '3× per week', hint: 'Steady cadence' },
  { value: 'custom', label: 'Custom', hint: 'Choose your own' },
]

export const PLANNER_CONTENT_TYPES = [
  'Educational', 'Promotional', 'Tips', 'Engagement', 'Industry News',
  'Case Study', 'Behind the Scenes', 'Testimonial', 'Product Update',
  'Story', 'Inspirational',
]

export const PLANNER_GOALS = [
  'Generate Leads', 'Increase Sales', 'Brand Awareness', 'Grow Followers',
  'Drive Website Traffic', 'Educate Audience', 'Build Community',
]

// A small, friendly timezone list; users on other zones can still type via the
// business profile. Values are IANA names understood by the backend.
export const PLANNER_TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Dubai',
  'Asia/Karachi',
  'Asia/Kolkata',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Sydney',
]

// Badge colors per planned content type (light + dark).
export const CONTENT_TYPE_STYLES = {
  Educational: 'bg-sky-500/15 text-sky-600 dark:text-sky-300',
  Promotional: 'bg-rose-500/15 text-rose-600 dark:text-rose-300',
  Tips: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300',
  Engagement: 'bg-amber-500/15 text-amber-600 dark:text-amber-300',
  'Industry News': 'bg-indigo-500/15 text-indigo-600 dark:text-indigo-300',
  'Case Study': 'bg-violet-500/15 text-violet-600 dark:text-violet-300',
  'Behind the Scenes': 'bg-teal-500/15 text-teal-600 dark:text-teal-300',
  Testimonial: 'bg-pink-500/15 text-pink-600 dark:text-pink-300',
  'Product Update': 'bg-cyan-500/15 text-cyan-600 dark:text-cyan-300',
  Story: 'bg-orange-500/15 text-orange-600 dark:text-orange-300',
  Inspirational: 'bg-fuchsia-500/15 text-fuchsia-600 dark:text-fuchsia-300',
}

export const STATUS_STYLES = {
  draft: 'bg-slate-500/15 text-slate-500 dark:text-slate-300',
  scheduled: 'bg-amber-500/15 text-amber-600 dark:text-amber-300',
  publishing: 'bg-sky-500/15 text-sky-600 dark:text-sky-300',
  published: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300',
  failed: 'bg-rose-500/15 text-rose-600 dark:text-rose-300',
}

// ---- Connected social account statuses (mirror backend AccountStatus) ------
// Each entry drives the card's status badge: a label, the pill colors, and the
// leading dot color. Light + dark variants included.
export const ACCOUNT_STATUS = {
  not_connected: {
    label: 'Not Connected',
    badge: 'bg-slate-500/15 text-slate-500 dark:text-slate-300',
    dot: 'bg-slate-400',
  },
  connected: {
    label: 'Connected',
    badge: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300',
    dot: 'bg-emerald-400',
  },
  token_expired: {
    label: 'Token Expired',
    badge: 'bg-amber-500/15 text-amber-600 dark:text-amber-300',
    dot: 'bg-amber-400',
  },
  syncing: {
    label: 'Syncing',
    badge: 'bg-sky-500/15 text-sky-600 dark:text-sky-300',
    dot: 'bg-sky-400 animate-pulse',
  },
  error: {
    label: 'Error',
    badge: 'bg-rose-500/15 text-rose-600 dark:text-rose-300',
    dot: 'bg-rose-400',
  },
}
