import { Link } from 'react-router-dom'
import Seo from '../components/Seo.jsx'
import { useAuth } from '../context/AuthContext.jsx'

// Custom 404 — rendered inside the public PublicLayout so nav + footer stay
// available. Excluded from search indexing via <Seo noindex>.
export default function NotFound() {
  const { user } = useAuth()
  return (
    <section className="grid min-h-[60vh] place-items-center px-4 py-20 text-center">
      <Seo title="Page Not Found" noindex />
      <div>
        <div className="bg-gradient-to-r from-indigo-500 to-violet-500 bg-clip-text text-7xl font-black text-transparent md:text-8xl">
          404
        </div>
        <h1 className="mt-4 text-2xl font-bold md:text-3xl">Oops!</h1>
        <p className="mx-auto mt-3 max-w-md text-slate-500 dark:text-slate-400">
          The page you're looking for doesn't exist or may have been moved.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link to="/" className="btn btn-primary px-6 py-2.5">
            Go Home
          </Link>
          {user && (
            <Link to="/dashboard" className="btn btn-ghost px-6 py-2.5">
              Go to Dashboard
            </Link>
          )}
        </div>
      </div>
    </section>
  )
}
