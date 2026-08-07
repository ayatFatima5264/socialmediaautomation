import AdsPageHeader from '../AdsPageHeader.jsx'
import CampaignContextBar from '../CampaignContextBar.jsx'
import { campaignPath } from '../../../lib/ads/tools'

// ---------------------------------------------------------------------------
// The three-panel shell every ad tool works in.
//
//   controls (left)  →  stage (centre)  →  output (right)
//   what you set        what you get       what you do with it
//
// This is the app's `.split-shell` / `.split-grid` / `.split-pane` pattern from
// index.css, laid out exactly as the AI Generator, Create Post and Scheduler
// use it — the columns scroll INDEPENDENTLY, so scrolling a long list of
// generated versions never drags the Generate button off screen, and getting
// back to the controls is not a scroll to the top of the page.
//
// That independence is the whole reason the pattern exists, and it is why a
// workspace uses it while the Studio home does not: the home page is a single
// column, where the same markup would only nest one scroll area inside another.
//
// Below `lg` the three panels stack and the page scrolls once, which is what
// the pattern does everywhere else in the app — two nested scroll areas on a
// phone are worse than one page scroll.
//
// ---- The campaign ---------------------------------------------------------
// A tool opened from a campaign shows that campaign above the three panels and
// sends Back to it rather than to the Studio home. Both come from the one
// `campaign` prop, so a workspace cannot end up displaying a campaign it is not
// actually returning the user to.
// ---------------------------------------------------------------------------

export default function AdsWorkspace({
  title,
  description,
  campaign,
  controls,
  action,
  stage,
  output,
}) {
  return (
    <div className="split-shell -mt-1 gap-3 md:-mt-3 lg:h-[calc(100%+0.75rem)] lg:gap-4">
      <AdsPageHeader
        title={title}
        description={description}
        backLabel={campaign ? campaign.name : 'AI Ads Studio'}
        backTo={campaign ? campaignPath(campaign.id) : undefined}
      />

      {campaign && <CampaignContextBar campaign={campaign} />}

      <div className="split-grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)_290px]">
        {/* ---- Controls ------------------------------------------------ *
         * The settings scroll; the primary action does not. A long control
         * panel otherwise pushes Generate below the fold, so the one button
         * the page exists for is the one thing you have to go looking for.
         * The card is the flex column, the settings are the scrolling child,
         * and the action sits in a pinned footer under a divider.          */}
        <div className="card flex flex-col overflow-hidden lg:h-full lg:min-h-0">
          <div className="split-pane flex-1 space-y-4 p-4 lg:min-h-0">{controls}</div>

          {action && (
            <div className="shrink-0 border-t border-line bg-surface p-3">{action}</div>
          )}
        </div>

        {/* Stage */}
        <div className="split-pane lg:h-full lg:pr-1">{stage}</div>

        {/* Output */}
        <div className="card split-pane space-y-4 p-4 lg:h-full">{output}</div>
      </div>
    </div>
  )
}

/**
 * A labelled block inside the controls or output column.
 *
 * Exists so all six workspaces space and title their groups identically —
 * the thing that drifts first when six pages each write their own markup.
 */
export function Field({ label, hint, children }) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-body">{label}</span>
        {hint && <span className="text-xs text-muted">{hint}</span>}
      </div>
      {children}
    </div>
  )
}

/** A heading inside the right-hand output column. */
export function RailSection({ title, action, children }) {
  return (
    <section>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-body">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}
