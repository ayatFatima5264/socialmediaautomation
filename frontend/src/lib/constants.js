// Platform display metadata. Character limits mirror the backend PLATFORM_SPECS.
export const PLATFORMS = {
  instagram: { label: 'Instagram', limit: 2200, color: '#E1306C', initial: 'Ig' },
  facebook: { label: 'Facebook', limit: 63206, color: '#1877F2', initial: 'Fb' },
  twitter: { label: 'Twitter / X', limit: 280, color: '#38BDF8', initial: 'X' },
  linkedin: { label: 'LinkedIn', limit: 3000, color: '#0A66C2', initial: 'in' },
  threads: { label: 'Threads', limit: 500, color: '#64748B', initial: '@' },
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

export const STATUS_STYLES = {
  draft: 'bg-slate-500/15 text-slate-500 dark:text-slate-300',
  scheduled: 'bg-amber-500/15 text-amber-600 dark:text-amber-300',
  publishing: 'bg-sky-500/15 text-sky-600 dark:text-sky-300',
  published: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300',
  failed: 'bg-rose-500/15 text-rose-600 dark:text-rose-300',
}
