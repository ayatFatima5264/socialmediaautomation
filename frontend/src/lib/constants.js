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

// Image styles. `group` drives the <optgroup> split in the dropdown: visual
// treatments describe how an image looks, sector presets describe what it shows.
// Values must match the IMAGE_STYLES keys in app/services/image_service.py.
export const IMAGE_STYLES = [
  { value: 'corporate', label: 'Modern Corporate', group: 'Visual style' },
  { value: 'realistic', label: 'Realistic', group: 'Visual style' },
  { value: 'illustration', label: 'Flat Illustration', group: 'Visual style' },
  { value: 'minimal', label: 'Minimal', group: 'Visual style' },
  { value: '3d', label: '3D', group: 'Visual style' },
  { value: 'cartoon', label: 'Cartoon', group: 'Visual style' },
  { value: 'watercolor', label: 'Watercolor', group: 'Visual style' },
  { value: 'luxury', label: 'Luxury', group: 'Visual style' },
  { value: 'anime', label: 'Anime', group: 'Visual style' },
  { value: 'startup', label: 'Startup', group: 'Industry' },
  { value: 'healthcare', label: 'Healthcare', group: 'Industry' },
  { value: 'restaurant', label: 'Restaurant', group: 'Industry' },
  { value: 'real_estate', label: 'Real Estate', group: 'Industry' },
  { value: 'fitness', label: 'Fitness', group: 'Industry' },
  { value: 'ecommerce', label: 'E-commerce', group: 'Industry' },
]

export const IMAGE_STYLE_GROUPS = ['Visual style', 'Industry']

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
  style: 'corporate',
  quality: 'standard',
  negative: '',
  promptEnhancer: false,
  // Independent of the post prompt. When blank, the image prompt is derived
  // from the post content as before — so the existing flow is unchanged for
  // anyone who never touches this field.
  imagePrompt: '',
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

// Badge colors per planned content type.
export const CONTENT_TYPE_STYLES = {
  Educational: 'bg-sky-500/15 text-sky-600',
  Promotional: 'bg-rose-500/15 text-rose-600',
  Tips: 'bg-emerald-500/15 text-emerald-600',
  Engagement: 'bg-amber-500/15 text-amber-600',
  'Industry News': 'bg-indigo-500/15 text-indigo-600',
  'Case Study': 'bg-violet-500/15 text-violet-600',
  'Behind the Scenes': 'bg-teal-500/15 text-teal-600',
  Testimonial: 'bg-pink-500/15 text-pink-600',
  'Product Update': 'bg-cyan-500/15 text-cyan-600',
  Story: 'bg-orange-500/15 text-orange-600',
  Inspirational: 'bg-fuchsia-500/15 text-fuchsia-600',
}

export const STATUS_STYLES = {
  draft: 'bg-slate-500/15 text-slate-500',
  scheduled: 'bg-amber-500/15 text-amber-600',
  publishing: 'bg-sky-500/15 text-sky-600',
  published: 'bg-emerald-500/15 text-emerald-600',
  failed: 'bg-rose-500/15 text-rose-600',
}

// ---- Connected social account statuses (mirror backend AccountStatus) ------
// Each entry drives the card's status badge: a label, the pill colors, and the
// leading dot color.
export const ACCOUNT_STATUS = {
  not_connected: {
    label: 'Not Connected',
    badge: 'bg-slate-500/15 text-slate-500',
    dot: 'bg-slate-400',
  },
  connected: {
    label: 'Connected',
    badge: 'bg-emerald-500/15 text-emerald-600',
    dot: 'bg-emerald-400',
  },
  token_expired: {
    label: 'Token Expired',
    badge: 'bg-amber-500/15 text-amber-600',
    dot: 'bg-amber-400',
  },
  syncing: {
    label: 'Syncing',
    badge: 'bg-sky-500/15 text-sky-600',
    dot: 'bg-sky-400 animate-pulse',
  },
  error: {
    label: 'Error',
    badge: 'bg-rose-500/15 text-rose-600',
    dot: 'bg-rose-400',
  },
}
