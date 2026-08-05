import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './context/AuthContext.jsx'
import Layout from './components/Layout.jsx'
import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import ForgotPassword from './pages/ForgotPassword.jsx'
import ResetPassword from './pages/ResetPassword.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Generator from './pages/Generator.jsx'
import CreatePost from './pages/CreatePost.jsx'
import Scheduler from './pages/Scheduler.jsx'
import History from './pages/History.jsx'
import Accounts from './pages/Accounts.jsx'
import Settings from './pages/Settings.jsx'
import Onboarding from './pages/Onboarding.jsx'
import BusinessProfile from './pages/BusinessProfile.jsx'
import ContentPlanner from './pages/ContentPlanner.jsx'
// AI Ads Studio — a self-contained module for advertising campaigns. Separate
// from the AI Generator (organic posts) in pages, components, state and routes.
import AdsStudio from './pages/ads/AdsStudio.jsx'
import AdToolRoute from './pages/ads/AdToolRoute.jsx'
import CampaignBuilder from './pages/ads/CampaignBuilder.jsx'
import CampaignDetail from './pages/ads/CampaignDetail.jsx'
// Public marketing website — accessible without authentication.
import PublicLayout from './components/marketing/PublicLayout.jsx'
import Home from './pages/marketing/Home.jsx'
import Features from './pages/marketing/Features.jsx'
import Pricing from './pages/marketing/Pricing.jsx'
import About from './pages/marketing/About.jsx'
import Contact from './pages/marketing/Contact.jsx'
import Blog from './pages/marketing/Blog.jsx'
import BlogPost from './pages/marketing/BlogPost.jsx'
import Privacy from './pages/marketing/Privacy.jsx'
import Terms from './pages/marketing/Terms.jsx'
import Cookies from './pages/marketing/Cookies.jsx'
import NotFound from './pages/NotFound.jsx'
import FullScreenLoader from './components/FullScreenLoader.jsx'

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  // While the token is being validated, show a branded loader instead of a
  // blank screen or a premature redirect to /login.
  if (loading) {
    return <FullScreenLoader message="Checking authentication…" />
  }
  return user ? children : <Navigate to="/login" replace />
}

// New users must finish the onboarding wizard before reaching the app.
function RequireOnboarding({ children }) {
  const { user } = useAuth()
  if (user && !user.onboarding_completed) {
    return <Navigate to="/onboarding" replace />
  }
  return children
}

export default function App() {
  return (
    <Routes>
      {/* ---- Public marketing website (no auth required) ---------------- */}
      <Route element={<PublicLayout />}>
        <Route path="/" element={<Home />} />
        <Route path="/features" element={<Features />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/about" element={<About />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/blog" element={<Blog />} />
        <Route path="/blog/:slug" element={<BlogPost />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="/cookies" element={<Cookies />} />
        {/* Custom 404 — rendered with the public nav + footer. */}
        <Route path="*" element={<NotFound />} />
      </Route>

      {/* ---- Existing authentication pages (reused as-is) --------------- */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />

      {/* ---- Onboarding wizard (first login, before the dashboard) ------ */}
      <Route
        path="/onboarding"
        element={
          <ProtectedRoute>
            <Onboarding />
          </ProtectedRoute>
        }
      />

      {/* ---- Protected application (requires auth) ---------------------- */}
      <Route
        element={
          <ProtectedRoute>
            <RequireOnboarding>
              <Layout />
            </RequireOnboarding>
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/planner" element={<ContentPlanner />} />
        <Route path="/generate" element={<Generator />} />
        <Route path="/create" element={<CreatePost />} />
        <Route path="/scheduler" element={<Scheduler />} />
        <Route path="/history" element={<History />} />

        {/* ---- AI Ads Studio ------------------------------------------
            Static segments outrank the dynamic one in React Router's route
            ranking, so /ads/campaigns/new resolves to the campaign page and
            never to the tool placeholder. Tool slugs come from the registry
            in lib/ads/tools.js — one entry there is a routed page here. */}
        <Route path="/ads" element={<AdsStudio />} />
        <Route path="/ads/campaigns/new" element={<CampaignBuilder />} />
        <Route path="/ads/campaigns/:id" element={<CampaignDetail />} />
        <Route path="/ads/:slug" element={<AdToolRoute />} />

        <Route path="/accounts" element={<Accounts />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/business-profile" element={<BusinessProfile />} />
      </Route>
    </Routes>
  )
}
