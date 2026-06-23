import { PLATFORMS } from '../lib/constants'

// Simplified branded chip (real SVG logos can be dropped in later).
export default function PlatformIcon({ platform, size = 32 }) {
  const meta = PLATFORMS[platform] || { color: '#6366f1', initial: '?' }
  return (
    <span
      title={meta.label}
      style={{ background: meta.color, width: size, height: size }}
      className="inline-grid shrink-0 place-items-center rounded-lg text-xs font-bold text-white"
    >
      {meta.initial}
    </span>
  )
}
