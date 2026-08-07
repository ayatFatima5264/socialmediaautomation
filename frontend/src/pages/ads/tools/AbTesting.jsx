import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import useCampaignContext from '../../../hooks/useCampaignContext'
import AdCreativeArt from '../../../components/ads/AdCreativeArt.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
import { useToast } from '../../../context/ToastContext.jsx'
import { getAdTool } from '../../../lib/ads/tools'

// ---------------------------------------------------------------------------
// A/B Testing — the workspace.
//
// The hard part of a creative test is not running it, it is knowing when to
// believe it. So the readout leads with whether the gap is significant yet, and
// the raw numbers sit under that — the opposite of a dashboard that shows two
// percentages side by side and lets the bigger one win.
//
// This tool depends on live delivery data, which arrives with the platform
// connections in phase 4 — the latest of the six, and the reason it says so
// plainly rather than showing a result.
// ---------------------------------------------------------------------------

const TOOL = 'A/B Testing'
const PHASE = 4

const METRICS = ['Click-through rate', 'Conversions', 'Cost per result', 'Reach']
const DURATIONS = ['3 days', '7 days', '14 days', 'Until significant']
const SPLITS = ['50 / 50', '70 / 30', '80 / 20']

export default function AbTesting() {
  // Nothing here generates, but a tool reached from a campaign must still
  // return to it — a Back button that jumps to the Studio home loses the thread.
  const { campaign } = useCampaignContext()

  const toast = useToast()
  const blocked = getAdTool('ab-testing')?.blocked
  const [metric, setMetric] = useState('Click-through rate')
  const [duration, setDuration] = useState('7 days')
  const [split, setSplit] = useState('50 / 50')

  return (
    <AdsWorkspace
      title={TOOL}
      campaign={campaign}
      description="Run creatives against each other with a split that holds, and get a readout that says whether the gap is real yet."
      controls={
        <>
          <Field label="Variant A">
            <div className="panel grid place-items-center px-3 py-5 text-center">
              <span className="text-xs text-muted">Pick a creative from your library</span>
              <button type="button" disabled className="btn btn-secondary btn-sm mt-2">
                Choose creative
              </button>
            </div>
          </Field>

          <Field label="Variant B">
            <div className="panel grid place-items-center px-3 py-5 text-center">
              <span className="text-xs text-muted">Pick a creative from your library</span>
              <button type="button" disabled className="btn btn-secondary btn-sm mt-2">
                Choose creative
              </button>
            </div>
          </Field>

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
          onClick={() => toast.info(`${blocked.needs} is required. ${blocked.why}`)}
        />
      }
      stage={
        <div className="card flex min-h-[320px] flex-col p-4 lg:min-h-full">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold text-body">Comparison</h2>
            <span className="badge badge-accent">Example</span>
          </div>

          {/* Stated before the controls are touched. Everything below is a
              worked example; nothing here can run until an ad account exists. */}
          <div className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3.5">
            <p className="text-xs font-bold text-amber-700">{blocked.needs} required</p>
            <p className="mt-1 text-xs leading-relaxed text-amber-700">{blocked.why}</p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {['A', 'B'].map((v, i) => (
              <div key={v} className="overflow-hidden rounded-xl border border-line">
                {/* `meet`, not `slice`: these tiles are 4:3 and the scenes are
                    5:3, so filling the box would crop the sides — exactly where
                    the headline and the CTA sit. */}
                <AdCreativeArt
                  name={i === 0 ? 'productAd' : 'bannerAd'}
                  fit="meet"
                  className="aspect-[4/3] w-full"
                />
                <div className="border-t border-line p-3">
                  <div className="text-xs font-bold text-body">Variant {v}</div>
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
              {['Promote winner', 'Export report'].map((action) => (
                <button
                  key={action}
                  type="button"
                  disabled
                  className="btn btn-secondary btn-sm w-full"
                  title="Available once a test has finished"
                >
                  {action}
                </button>
              ))}
            </div>
          </RailSection>
        </>
      }
    />
  )
}
