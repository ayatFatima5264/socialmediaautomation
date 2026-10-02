import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import useCampaignContext from '../../../hooks/useCampaignContext'
import AdCreativeArt from '../../../components/ads/AdCreativeArt.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
import MediaLibraryModal from '../../../components/media/MediaLibraryModal.jsx'
import { useToast } from '../../../context/ToastContext.jsx'
import { getAdTool } from '../../../lib/ads/tools'
import { buildTestReport, isTestReady } from '../../../lib/ads/abTest'

// ---------------------------------------------------------------------------
// A/B Testing — the workspace.
//
// The hard part of a creative test is not running it, it is knowing when to
// believe it. So the readout leads with whether the gap is significant yet, and
// the raw numbers sit under that — the opposite of a dashboard that shows two
// percentages side by side and lets the bigger one win.
//
// ---- What is wired, and what is not ----------------------------------------
// BUG-05 called this an inert shell: both "Choose creative" buttons and both
// result actions were hardcoded `disabled` with no explanation, while the split
// and metric controls worked. Choosing a creative needs no ad account — it reads
// the Media Library the rest of the product already uses — so both pickers are
// now live and return real assets.
//
// What genuinely cannot run is the test itself. Delivery numbers come from the
// ad platform, and the social connections in this app carry organic-publishing
// scopes only (see lib/ads/tools.js) — no ads_read, no ad account id. So Start
// Test says so, in the same words the tool card uses, and the two result
// actions are live in the only honest way available:
//
//   Export report   Writes a real file: the settings, both creatives, and a
//                   line stating that delivery data is not connected. That is
//                   the document you need before building the test in the
//                   platform, and it does not pretend to contain results.
//   Promote winner  Refuses, and says what is missing. There is no winner to
//                   promote until a test has run, and a button that picks one
//                   at random would be worse than one that explains itself.
// ---------------------------------------------------------------------------

const TOOL = 'A/B Testing'
const PHASE = 4

const METRICS = ['Click-through rate', 'Conversions', 'Cost per result', 'Reach']
const DURATIONS = ['3 days', '7 days', '14 days', 'Until significant']
const SPLITS = ['50 / 50', '70 / 30', '80 / 20']

const VARIANTS = [
  { key: 'a', label: 'Variant A', scene: 'productAd' },
  { key: 'b', label: 'Variant B', scene: 'bannerAd' },
]

export default function AbTesting() {
  // Nothing here generates, but a tool reached from a campaign must still
  // return to it — a Back button that jumps to the Studio home loses the thread.
  const { campaign } = useCampaignContext()

  const toast = useToast()
  const blocked = getAdTool('ab-testing')?.blocked
  const [metric, setMetric] = useState('Click-through rate')
  const [duration, setDuration] = useState('7 days')
  const [split, setSplit] = useState('50 / 50')
  // { a: <media asset>, b: <media asset> }
  const [variants, setVariants] = useState({})
  const [picking, setPicking] = useState(null)

  const ready = isTestReady(variants)

  function choose(key, _file, asset) {
    setVariants((current) => ({ ...current, [key]: asset }))
    setPicking(null)
  }

  function startTest() {
    if (!ready) {
      toast.error('Choose a creative for Variant A and Variant B first.')
      return
    }
    toast.info(`${blocked.needs} is required. ${blocked.why}`)
  }

  function exportReport() {
    const report = buildTestReport({ campaign, variants, split, metric, duration })
    const url = URL.createObjectURL(new Blob([report.content], { type: report.mediaType }))
    const link = document.createElement('a')
    link.href = url
    link.download = report.filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    toast.success(`Exported ${report.filename}.`)
  }

  function promoteWinner() {
    toast.info(`Nothing to promote yet. ${blocked.needs} is required. ${blocked.why}`)
  }

  return (
    <>
      <AdsWorkspace
        title={TOOL}
        campaign={campaign}
      description="Run creatives against each other with a split that holds, and get a readout that says whether the gap is real yet."
      controls={
        <>
          {VARIANTS.map(({ key, label }) => (
            <Field key={key} label={label}>
              <div className="panel grid place-items-center px-3 py-5 text-center">
                {variants[key] ? (
                  <>
                    <img
                      src={variants[key].url}
                      alt={variants[key].title || label}
                      className="mb-2 max-h-40 w-full rounded-lg object-contain"
                    />
                    <span className="text-xs font-semibold text-body">
                      {variants[key].title || 'Untitled'}
                    </span>
                    <span className="mb-2 text-xs text-muted">
                      {variants[key].width && variants[key].height
                        ? `${variants[key].width} × ${variants[key].height} px`
                        : 'Ready'}
                    </span>
                    <button
                      type="button"
                      onClick={() => setPicking(key)}
                      className="btn btn-secondary btn-sm"
                    >
                      Change creative
                    </button>
                  </>
                ) : (
                  <>
                    <span className="text-xs text-muted">Pick a creative from your library</span>
                    <button
                      type="button"
                      onClick={() => setPicking(key)}
                      className="btn btn-secondary btn-sm mt-2"
                    >
                      Choose creative
                    </button>
                  </>
                )}
              </div>
            </Field>
          ))}

          <Field label="Split">
            <ChipSelect options={SPLITS} value={split} onChange={setSplit} />
          </Field>

          <Field label="Decide on">
            <ChipSelect options={METRICS} value={metric} onChange={setMetric} />
          </Field>

          <Field label="Run for">
            <ChipSelect options={DURATIONS} value={duration} onChange={setDuration} />
          </Field>
        </>
      }
      action={
        <GenerateButton
          label="Start Test"
          toolName={TOOL}
          phase={PHASE}
          onClick={startTest}
          disabled={!ready}
        />
      }
      stage={
        <div className="card flex min-h-[320px] flex-col p-4 lg:min-h-full">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold text-body">Comparison</h2>
            <span className="badge badge-accent">{ready ? 'Ready to run' : 'Example'}</span>
          </div>

          {/* Stated before the controls are touched. Everything below is a
              worked example; nothing here can run until an ad account exists. */}
          <div className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3.5">
            <p className="text-xs font-bold text-amber-700">{blocked.needs} required</p>
            <p className="mt-1 text-xs leading-relaxed text-amber-700">{blocked.why}</p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {VARIANTS.map(({ key, label, scene }) => (
              <div key={key} className="overflow-hidden rounded-xl border border-line">
                {/* `meet`, not `slice`: these tiles are 4:3 and the scenes are
                    5:3, so filling the box would crop the sides — exactly where
                    the headline and the CTA sit. */}
                {variants[key] ? (
                  <img
                    src={variants[key].url}
                    alt={variants[key].title || label}
                    className="aspect-[4/3] w-full bg-inset object-contain"
                  />
                ) : (
                  <AdCreativeArt name={scene} fit="meet" className="aspect-[4/3] w-full" />
                )}
                <div className="border-t border-line p-3">
                  <div className="text-xs font-bold text-body">{label}</div>
                  <div className="mt-1 text-xs text-muted">
                    {metric} — awaiting delivery data
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="panel mt-4 p-3.5">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
              Readout
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-body">
              A finished test reports the winner, the size of the gap, and whether the
              result is significant yet — so a 0.2pt lead on 300 impressions is not
              mistaken for an answer.
            </p>
          </div>
        </div>
      }
      output={
        <>
          <RailSection title="Test settings">
            <dl className="space-y-2 text-xs">
              {[
                ['Split', split],
                ['Metric', metric],
                ['Duration', duration],
                ['Variant A', variants.a?.title || 'Not chosen'],
                ['Variant B', variants.b?.title || 'Not chosen'],
              ].map(([k, v]) => (
                <div key={k} className="flex items-baseline justify-between gap-2">
                  <dt className="text-muted">{k}</dt>
                  <dd className="font-semibold text-body">{v}</dd>
                </div>
              ))}
            </dl>
          </RailSection>

          <RailSection title="Actions">
            <div className="space-y-2">
              <button
                type="button"
                onClick={promoteWinner}
                className="btn btn-secondary btn-sm w-full"
                title="Needs a finished test — delivery data is not connected yet"
              >
                Promote winner
              </button>
              <button
                type="button"
                onClick={exportReport}
                className="btn btn-secondary btn-sm w-full"
                title="Writes the test setup to a file. Delivery data is not included."
              >
                Export report
              </button>
            </div>
            <p className="mt-2 text-xs text-muted">
              {ready
                ? 'Export writes the settings and both creatives to a file.'
                : 'Choose both creatives for the report to be complete.'}
            </p>
          </RailSection>
        </>
      }
    />

    {/* Rendered beside the workspace, not inside it: the modal portals to
        document.body, and AdsWorkspace has no slot for siblings. */}
    <MediaLibraryModal
      open={picking !== null}
      onCancel={() => setPicking(null)}
      title={
        picking === 'b' ? 'Choose a creative for Variant B' : 'Choose a creative for Variant A'
      }
      onSelect={(file, asset) => choose(picking, file, asset)}
    />
    </>
  )
}
