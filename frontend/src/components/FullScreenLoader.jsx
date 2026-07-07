// Branded full-screen loader — shown while authentication is being resolved so
// users never see a blank white screen on refresh. Reuses the app's design
// tokens (app-bg, brand gradient) and is theme-aware.
export default function FullScreenLoader({ message = 'Loading AutoSocial AI…' }) {
  return (
    <div className="app-bg grid min-h-screen place-items-center p-4">
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="grid h-14 w-14 animate-pulse place-items-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 text-2xl font-black text-white">
          A
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-500/30 border-t-indigo-500" />
          {message}
        </div>
      </div>
    </div>
  )
}
