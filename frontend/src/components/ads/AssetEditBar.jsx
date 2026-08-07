import { Link } from 'react-router-dom'
import { campaignPath } from '../../lib/ads/tools'

// ---------------------------------------------------------------------------
// "You are re-doing this one, not making another."
//
// Shown at the top of a tool's controls whenever it was opened from an asset.
// Without it, edit mode is invisible: the workspace looks identical to the
// create case, the user presses Generate expecting a new banner, and one they
// were happy with is quietly overwritten.
//
// ---- The toggle -----------------------------------------------------------
// "Save as a new asset" is the explicit opt-out, and it is OFF by default
// because replacing is what "edit" means everywhere else in software. Both
// intentions are real — fixing a headline, and branching a variant to test
// against — so the choice sits next to the button that acts on it rather than
// being inferred.
// ---------------------------------------------------------------------------

export default function AssetEditBar({ asset, campaign, saveAsNew, onSaveAsNewChange }) {
  if (!asset) return null

  return (
    <div className="rounded-lg border border-accent-line bg-accent-soft p-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-accent">
          Editing
        </span>
        {campaign && (
          <Link
            to={campaignPath(campaign.id)}
            className="text-[11px] text-muted underline hover:text-accent"
          >
            Cancel
          </Link>
        )}
      </div>

      <p className="mt-0.5 truncate text-sm font-semibold text-body">{asset.title}</p>

      <label className="mt-2 flex items-start gap-2 text-xs leading-snug text-muted">
        <input
          type="checkbox"
          checked={saveAsNew}
          onChange={(e) => onSaveAsNewChange(e.target.checked)}
          style={{ accentColor: 'var(--accent)' }}
          className="mt-0.5 h-3.5 w-3.5 shrink-0"
        />
        <span>
          Save as a new asset
          <span className="block text-[11px] opacity-80">
            {saveAsNew
              ? 'The original is kept and this becomes a second asset.'
              : 'Generating replaces this asset in place.'}
          </span>
        </span>
      </label>
    </div>
  )
}
