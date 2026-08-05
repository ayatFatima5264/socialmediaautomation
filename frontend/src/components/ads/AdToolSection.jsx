import AdToolCard from './AdToolCard.jsx'

// ---------------------------------------------------------------------------
// One category of tools on the Studio home.
//
// Fifteen cards in an undifferentiated grid gives the user no answer to "what
// do I do first". Grouping them under a heading that names the job — Create
// Ads, Video Ads, AI Tools, Assets — turns the page into four short decisions
// instead of one long one.
//
// A section renders nothing when its category is empty, so removing the last
// tool from a category cannot leave a heading floating above blank space.
// ---------------------------------------------------------------------------

export default function AdToolSection({ category, tools }) {
  if (!tools?.length) return null

  const headingId = `ads-section-${category.key}`

  return (
    <section aria-labelledby={headingId}>
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 id={headingId} className="font-semibold text-body">
          {category.label}
        </h2>
        {category.description && (
          <p className="text-xs text-muted">{category.description}</p>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {tools.map((tool) => (
          <AdToolCard key={tool.slug} tool={tool} />
        ))}
      </div>
    </section>
  )
}
