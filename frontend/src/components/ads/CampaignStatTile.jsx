// One Campaign Overview widget.
//
// Two sizes of the same tile. The full size matches the Dashboard's stat cards
// exactly — accent bar, oversized figure, muted label — so moving between the
// two pages does not feel like moving between two products.
//
// `compact` is for the Studio home, where the overview sits BELOW the creation
// sections and has to read as secondary. Same information, quieter: a smaller
// figure and the accent reduced to a dot, so it summarises without competing
// with the tools above it.
export default function CampaignStatTile({ label, value, accent, loading, compact = false }) {
  if (compact) {
    return (
      <div className="panel flex items-center gap-3 px-3.5 py-3">
        <span className={`h-2 w-2 shrink-0 rounded-full ${accent}`} aria-hidden="true" />
        <div className="min-w-0">
          <div className="text-lg font-extrabold leading-none text-body">
            {loading ? <span className="skeleton inline-block h-5 w-7 align-middle" /> : value}
          </div>
          <div className="mt-1 truncate text-xs text-muted">{label}</div>
        </div>
      </div>
    )
  }

  return (
    <div className="card p-4">
      <div className={`mb-3 h-1.5 w-10 rounded-full ${accent}`} />
      <div className="text-3xl font-extrabold text-body">
        {loading ? <span className="skeleton inline-block h-8 w-10" /> : value}
      </div>
      <div className="mt-1 text-sm text-muted">{label}</div>
    </div>
  )
}
