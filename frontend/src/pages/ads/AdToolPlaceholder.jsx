import { Link, useParams } from 'react-router-dom'
import AdsPageHeader from '../../components/ads/AdsPageHeader.jsx'
import AdCreativeArt from '../../components/ads/AdCreativeArt.jsx'
import { ADS_BASE_PATH, getAdTool, toolArt } from '../../lib/ads/tools'

// ---------------------------------------------------------------------------
// The page behind a tool card, until its phase lands.
//
// One component serves every tool rather than a file each: everything shown
// here — name, description, artwork, the capability list — comes from the
// tool's entry in lib/ads/tools.js. Building the real feature means pointing
// that tool's route at its own page; nothing here needs unpicking first.
// ---------------------------------------------------------------------------

export default function AdToolPlaceholder() {
  const { slug } = useParams()
  const tool = getAdTool(slug)

  // An unknown slug renders a way back rather than a crash. Cards are generated
  // from the registry, so this is defensive — a hand-typed URL, or a stale link
  // after a slug is renamed.
  if (!tool) {
    return (
      <div className="space-y-6 pb-4">
        <AdsPageHeader
          title="Tool not found"
          description="That tool does not exist in AI Ads Studio."
          backLabel="Back to AI Ads Studio"
        />
        <Link to={ADS_BASE_PATH} className="btn btn-primary">
          Go to AI Ads Studio
        </Link>
      </div>
    )
  }

  // A tool that already lives elsewhere in the app is reachable now. Its card
  // links straight there, so this only runs for a hand-typed URL — but it must
  // send the user on rather than claim the feature is unbuilt.
  const shipped = tool.available && tool.to

  return (
    <div className="space-y-6 pb-4">
      <AdsPageHeader
        title={tool.name}
        description={tool.longDescription || tool.description}
        backLabel="AI Ads Studio"
      />

      <div className="card overflow-hidden">
        <div className="grid gap-6 p-5 md:grid-cols-[minmax(0,280px)_1fr] md:items-center md:p-6">
          <AdCreativeArt name={toolArt(tool.slug)} className="h-40 w-full rounded-[10px]" />

          <div className="min-w-0">
            <span className="badge badge-accent">
              {shipped ? 'Available now' : 'In development'}
            </span>

            <h2 className="mt-3 text-base font-bold text-body">
              {shipped
                ? `${tool.name} is ready to use`
                : `${tool.name} is coming in phase ${tool.phase}`}
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              {shipped
                ? `${tool.name} already ships as part of the app.`
                : `This is where ${tool.name} will live. The Studio, its routing and its campaign data are already in place, so this tool plugs straight in when it ships.`}
            </p>

            {tool.capabilities?.length > 0 && (
              <ul className="mt-4 space-y-2">
                {tool.capabilities.map((c) => (
                  <li key={c} className="flex items-start gap-2.5 text-sm">
                    <span aria-hidden="true" className="mt-0.5 text-accent">
                      ✓
                    </span>
                    <span className="min-w-0 text-muted">{c}</span>
                  </li>
                ))}
              </ul>
            )}

            <div className="mt-5 flex flex-wrap gap-2">
              {shipped && (
                <Link to={tool.to} className="btn btn-primary btn-sm">
                  Open {tool.name}
                </Link>
              )}
              <Link to={ADS_BASE_PATH} className="btn btn-secondary btn-sm">
                ← Back to AI Ads Studio
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
