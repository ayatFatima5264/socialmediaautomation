// Branded full-screen loader — shown while authentication is being resolved so
// users never see a blank white screen on refresh. Reuses the app's design
// tokens (app-bg, brand gradient) and is theme-aware.
export default function FullScreenLoader({ message = 'Loading AutoSocial AI…' }) {
  return (
    <div className="app-bg grid min-h-screen place-items-center p-4">
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="grid h-14 w-14 animate-pulse place-items-center rounded-2xl bg-accent text-2xl font-black text-accent-contrast">
          A
        </div>
        <div className="flex items-center gap-2 text-sm text-muted">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
          {message}
        </div>
      </div>
    </div>
  )
}
