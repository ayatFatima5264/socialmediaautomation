import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import AssetEditBar from '../../../components/ads/AssetEditBar.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import CreativeResults from '../../../components/ads/workspace/CreativeResults.jsx'
import useCampaignContext from '../../../hooks/useCampaignContext'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'
import {
  campaignSubject,
  campaignType,
  stylePrompt,
  stylesFor,
} from '../../../lib/ads/campaignTypes'
import { campaignToolPath, CAMPAIGN_NEW_PATH } from '../../../lib/ads/tools'

// ---------------------------------------------------------------------------
// Website Promotion — what a website campaign actually needs.
//
// This is the tool that was missing. A campaign promoting a blog was being
// offered Product Ads, which opens by asking for a product photo, a background
// preset and a scene — none of which a blog has. So it exists in Product Ads'
// place for Website / Blog campaigns, and asks for none of that.
//
// ---- Why formats rather than one image -----------------------------------
// Promoting a page is never one picture. It is the hero at the top, the cover
// on the article, the square that survives a thumbnail, and the Open Graph
// image that decides whether a shared link gets clicked at all. Each has a
// different shape and a different job, and generating them one at a time — with
// the user re-picking the ratio each time and remembering which they had
// already done — is the workflow this replaces.
//
// Each format is generated at its OWN aspect ratio in its own request, run
// together. A single generation cropped into eight shapes is the "stretched
// crop" problem the Banner Generator exists to avoid, and it would be no better
// here.
// ---------------------------------------------------------------------------

const TOOL = 'Website Promotion'
const PHASE = 2

// The eight things a website campaign needs, each with the shape it is used at
// and the framing instruction that makes it usable at that shape. `hint` is
// what the format is FOR — the answer to "which of these do I actually need?".
const FORMATS = [
  {
    key: 'hero',
    label: 'Hero Banner',
    hint: 'Top of the landing page',
    ratio: '16:9',
    prompt: 'as a wide hero banner for the top of a web page, the subject to one side and a clear empty band for a headline',
  },
  {
    key: 'blog-banner',
    label: 'Blog Banner',
    hint: 'Header strip on an article',
    ratio: '16:9',
    prompt: 'as a wide editorial banner for the top of an article, calm and uncluttered',
  },
  {
    key: 'feature',
    label: 'Feature Graphic',
    hint: 'One feature, stated boldly',
    ratio: '16:9',
    prompt: 'as a bold feature graphic carrying one idea, flat background, generous room for a short title',
  },
  {
    key: 'thumbnail',
    label: 'Website Thumbnail',
    hint: 'Card and grid listings',
    ratio: '1:1',
    prompt: 'as a square thumbnail that still reads at small size, one strong central subject, no fine detail',
  },
  {
    key: 'blog-cover',
    label: 'Blog Cover',
    hint: 'Portrait cover image',
    ratio: '4:5',
    prompt: 'as a portrait editorial cover image for an article, photographic, uncluttered',
  },
  {
    key: 'social',
    label: 'Social Preview',
    hint: 'In-feed share card',
    ratio: '16:9',
    prompt: 'as a social share card, the subject centred with generous margins on every side',
  },
  {
    key: 'link',
    label: 'Link Preview',
    hint: 'Chat and messaging unfurls',
    ratio: '16:9',
    prompt: 'as a link preview card that stays legible when scaled down in a feed, high contrast, no small text',
  },
  {
    key: 'og',
    label: 'Open Graph Image',
    hint: 'What Facebook and X show',
    ratio: '16:9',
    prompt: 'as an Open Graph share image, wide 1.91:1 framing, one large clear subject, no small text',
  },
]

const DEFAULT_FORMATS = ['hero', 'social']

export default function WebsitePromotion() {
  const { campaign, editingAsset, saveAssets } = useCampaignContext()
  const toast = useToast()

  const type = campaignType(campaign?.campaignType)
  const styles = stylesFor(campaign?.campaignType)

  const [chosen, setChosen] = useState(DEFAULT_FORMATS)
  const [style, setStyle] = useState(styles[0].label)
  const [headline, setHeadline] = useState('')
  const [url, setUrl] = useState('')
  const [subject, setSubject] = useState('')
  const [running, setRunning] = useState(false)
  const [results, setResults] = useState(null)
  const [saveAsNew, setSaveAsNew] = useState(false)

  // Editing one asset means editing ONE FORMAT — a card in the library is a
  // hero banner or an Open Graph image, not the set. Its format is selected and
  // the others are cleared, so Generate re-does exactly what was opened.
  const prefilled = useRef(false)
  useEffect(() => {
    if (!editingAsset || prefilled.current) return
    prefilled.current = true
    const m = editingAsset.meta || {}
    if (m.format && FORMATS.some((f) => f.key === m.format)) setChosen([m.format])
    if (m.style) setStyle(m.style)
    if (m.headline) setHeadline(m.headline)
    if (m.url) setUrl(m.url)
  }, [editingAsset])

  const activeStyle = styles.some((s) => s.label === style) ? style : styles[0].label

  function toggle(key) {
    setChosen((list) =>
      list.includes(key) ? list.filter((k) => k !== key) : [...list, key],
    )
  }

  async function generate() {
    const base = campaign ? campaignSubject(campaign) : subject.trim()
    if (base.length < 2) {
      toast.error('Describe the website or article first.')
      return
    }
    if (!chosen.length) {
      toast.error('Pick at least one format.')
      return
    }

    setRunning(true)
    const wanted = FORMATS.filter((f) => chosen.includes(f.key))

    try {
      // allSettled, not all: eight requests against a rate-limited image host
      // will sometimes lose one, and losing the whole set because the seventh
      // failed would throw away six good images.
      const settled = await Promise.allSettled(
        wanted.map((format) =>
          api.adCreative({
            subject: [
              base,
              stylePrompt(campaign?.campaignType, activeStyle),
              format.prompt,
            ]
              .filter(Boolean)
              .join(' '),
            headline: headline.trim() || null,
            aspect_ratio: format.ratio,
            count: 1,
          }),
        ),
      )

      const made = []
      settled.forEach((outcome, i) => {
        if (outcome.status !== 'fulfilled') return
        const image = outcome.value?.images?.[0]
        if (!image) return
        made.push({
          format: wanted[i],
          url: image,
          source: outcome.value?.sources?.[0],
        })
      })

      if (!made.length) {
        toast.error('Nothing came back — the image host may be rate-limiting. Try again.')
        return
      }

      const failed = wanted.length - made.length
      if (failed > 0) {
        toast.info(`${made.length} of ${wanted.length} formats generated. Try again for the rest.`)
      }

      setResults(made)

      await saveAssets(
        made.map((item) => ({
          kind: 'banner',
          title: editingAsset && !saveAsNew
            ? editingAsset.title
            : `${item.format.label}${headline.trim() ? ` — ${headline.trim()}` : ''}`,
          url: item.url,
          tool: TOOL,
          meta: {
            format: item.format.key,
            formatLabel: item.format.label,
            ratio: item.format.ratio,
            style: activeStyle,
            headline: headline.trim(),
            url: url.trim(),
          },
        })),
        { saveAsNew },
      )
    } catch (err) {
      toast.error(err?.message || 'Generation failed. Try again.')
    } finally {
      setRunning(false)
    }
  }

  // Reachable by hand-typed URL from any campaign. Rather than refuse, it says
  // what it is for and points at the campaign type that fits — a dead end here
  // would be worse than a tool that still works.
  const mismatched = campaign && type.creativeTool !== 'website-promotion'

  return (
    <AdsWorkspace
      title={TOOL}
      campaign={campaign}
      description="Hero banners, blog covers, thumbnails and the Open Graph image that decides whether a shared link gets clicked."
      controls={
        <>
          <AssetEditBar
            asset={editingAsset}
            campaign={campaign}
            saveAsNew={saveAsNew}
            onSaveAsNewChange={setSaveAsNew}
          />

          {mismatched && (
            <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs leading-relaxed text-amber-700">
              This campaign is a {type.label}. Website Promotion is built for Website /
              Blog campaigns — it still works here, but{' '}
              <Link to={campaignToolPath(type.creativeTool || 'banner-generator', campaign.id)} className="underline">
                the tools made for this campaign type
              </Link>{' '}
              will fit better.
            </p>
          )}

          {!campaign && (
            <>
              <Field label="What you are promoting" hint="Or open this from a campaign">
                <textarea
                  rows={3}
                  className="input resize-none"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="An AI marketing blog for small business owners"
                />
              </Field>
              <p className="text-[11px] leading-relaxed text-muted">
                <Link to={CAMPAIGN_NEW_PATH} className="text-accent underline">
                  Start a campaign
                </Link>{' '}
                and this — plus the tone, audience and platforms — is filled in for you and
                everything you make is kept.
              </p>
            </>
          )}

          <Field label="Formats" hint={`${chosen.length} selected`}>
            <div className="space-y-1.5">
              {FORMATS.map((format) => {
                const on = chosen.includes(format.key)
                return (
                  <button
                    key={format.key}
                    type="button"
                    onClick={() => toggle(format.key)}
                    aria-pressed={on}
                    className={`flex w-full items-baseline justify-between gap-2 rounded-lg border px-2.5 py-2 text-left transition ${
                      on
                        ? 'border-accent bg-accent-soft'
                        : 'border-line hover:border-accent'
                    }`}
                  >
                    <span className="min-w-0">
                      <span
                        className={`block text-xs font-semibold ${on ? 'text-accent' : 'text-body'}`}
                      >
                        {format.label}
                      </span>
                      <span className="block text-[11px] text-muted">{format.hint}</span>
                    </span>
                    <span className="shrink-0 text-[10px] text-muted">{format.ratio}</span>
                  </button>
                )
              })}
            </div>
          </Field>

          <Field label="Headline" hint="Optional">
            <input
              className="input"
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
              placeholder="The 7 ad mistakes costing you clicks"
            />
          </Field>

          <Field label="Page URL" hint="Optional">
            <input
              className="input"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/blog/ad-mistakes"
            />
            <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
              Kept with each asset so you know which page it belongs to. Screenshots of a
              live URL need a capture service, which is not wired up — the Website
              Screenshot style generates a website-like image instead.
            </p>
          </Field>

          <Field label="Visual treatment" hint={type.label}>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {styles.map((s) => (
                <button
                  key={s.label}
                  type="button"
                  onClick={() => setStyle(s.label)}
                  aria-pressed={activeStyle === s.label}
                  className={`rounded-lg border px-2.5 py-2 text-left text-xs font-medium transition ${
                    activeStyle === s.label
                      ? 'border-accent bg-accent-soft text-accent'
                      : 'border-line text-muted hover:border-accent'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </Field>
        </>
      }
      action={
        <GenerateButton
          label={
            editingAsset && !saveAsNew
              ? 'Replace This Format'
              : `Generate ${chosen.length} Format${chosen.length === 1 ? '' : 's'}`
          }
          toolName={TOOL}
          phase={PHASE}
          onClick={generate}
          loading={running}
        />
      }
      stage={
        results ? (
          <div className="card flex min-h-[320px] flex-col p-4 lg:min-h-full">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-sm font-semibold text-body">Generated formats</h2>
              <span className="text-xs text-muted">{results.length} images</span>
            </div>
            <CreativeResults
              images={results.map((r) => r.url)}
              labels={results.map((r) => r.format.label)}
              sources={results.map((r) => r.source)}
              columns={3}
            />
            <p className="mt-3 text-xs leading-relaxed text-muted">
              {campaign
                ? `Saved to ${campaign.name}. Each was generated at its own aspect ratio, not cropped from one image.`
                : 'Each was generated at its own aspect ratio, not cropped from one image. Open this tool from a campaign to keep them.'}
            </p>
          </div>
        ) : (
          <PreviewStage
            hint={
              campaign
                ? `An example. This tool already has ${campaign.name}'s brief — pick the formats you need and press Generate.`
                : 'An example. Describe the page, pick the formats you need, and press Generate.'
            }
            art="bannerAd"
            ratio="wide"
            toolName={TOOL}
            caption={`${chosen.length} format${chosen.length === 1 ? '' : 's'} selected`}
          />
        )
      }
      output={
        <>
          <RailSection title="Why eight shapes">
            <p className="text-xs leading-relaxed text-muted">
              A hero, a thumbnail and an Open Graph card are three different jobs at three
              different sizes. Each is generated at its own ratio — cropping one image into
              all of them is what makes shared links look broken.
            </p>
          </RailSection>

          <RailSection title="Selected">
            <ul className="space-y-1.5">
              {FORMATS.filter((f) => chosen.includes(f.key)).map((f) => (
                <li key={f.key} className="flex items-center justify-between gap-2 text-xs">
                  <span className="text-body">{f.label}</span>
                  <span className="text-muted">{f.ratio}</span>
                </li>
              ))}
              {!chosen.length && (
                <li className="text-xs text-muted">Nothing selected yet.</li>
              )}
            </ul>
          </RailSection>
        </>
      }
    />
  )
}
