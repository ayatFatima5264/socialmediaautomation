# Frontend Architecture

AutoSocial AI's frontend is split into **two clearly separated sections** that
share one design system, theme, authentication, and component library. This
separation is the contract for all future work.

```
                         ┌─────────────────────────────┐
   Visitor (no auth) ──▶ │     MARKETING WEBSITE       │
                         │  /  /features  /pricing     │
                         │  /about /contact            │
                         │  /privacy /terms  + 404     │
                         └──────────────┬──────────────┘
                                        │  Login / Sign Up
                                        ▼
                         ┌─────────────────────────────┐
                         │      AUTHENTICATION         │  /login  /register
                         └──────────────┬──────────────┘
                                        │ first login → Onboarding wizard
                                        ▼
                         ┌─────────────────────────────┐
   Authenticated user ─▶ │  AUTHENTICATED APPLICATION  │
                         │  /dashboard /generate       │
                         │  /create /scheduler /ads    │
                         │  /history /accounts         │
                         │  /settings /business-profile│
                         └─────────────────────────────┘
                                        │ Logout → /
                                        ▼
                                 Marketing Website
```

## Section boundaries

| Concern            | Marketing Website                         | Authenticated Application            |
| ------------------ | ----------------------------------------- | ------------------------------------ |
| Layout             | `components/marketing/PublicLayout.jsx`   | `components/Layout.jsx`              |
| Pages              | `pages/marketing/*`                       | `pages/*` (Dashboard, Generator, …) |
| Route guard        | none (public)                             | `ProtectedRoute` in `App.jsx`        |
| Access             | everyone, incl. logged-in users           | authenticated users only            |

Both are declared in `App.jsx`. The marketing routes live under a
`<PublicLayout>` layout route; the app routes live under a
`ProtectedRoute → RequireOnboarding → Layout` chain.

## Routing rules

- `/` is the marketing **Home**. The Dashboard lives at **`/dashboard`**.
- Every protected route redirects unauthenticated users to `/login`
  (`ProtectedRoute`). New users are sent through `/onboarding` before the
  dashboard (`RequireOnboarding`).
- Authenticated users are **not** force-redirected away from the marketing
  site — they can browse it freely (Notion/Vercel style). The public nav swaps
  Login/Sign Up for a user menu with **Go to Dashboard / Settings / Logout**.
- Logout returns the user to `/` (Home).
- Unknown paths render the custom **404** inside the public chrome.

## Shared foundations (used by both sections)

- **Design system** — Tailwind component classes in `index.css`
  (`card`, `btn`, `input`, `nav-link`, `app-bg`, brand gradient).
- **Auth** — `context/AuthContext.jsx` + `lib/api.js`. Never duplicated.
- **Toasts** — `context/ToastContext.jsx`.
- **Site config** — `config/site.js` (brand facts, nav, footer, SEO defaults).
- **SEO** — `components/Seo.jsx` (per-page `<head>` management).
- **Analytics** — `lib/analytics.js` (env-gated GA / Clarity).

## Adding a new feature (Billing, Stripe, Teams, Workspace, AI Images, …)

1. Add page(s) under `pages/` (the app section), not `pages/marketing/`.
2. Register the route **inside the protected `<Layout>` group** in `App.jsx`.
3. Add a sidebar entry in `components/Layout.jsx` `NAV` if it needs one.
4. Reuse the shared design-system classes and existing contexts.
5. If the feature has a public marketing angle (e.g. a pricing tier), update the
   **marketing** pages/config separately — the two sections stay decoupled.

> Rule of thumb: **application features never touch the marketing website, and
> marketing changes never touch the application.** Anything shared belongs in a
> context, `config/`, `lib/`, or a reusable component.

## Modules

A feature large enough to own several routes is a **module**: its own folder in
each of `pages/`, `components/`, and `lib/`, rather than more files in the
shared ones. **AI Ads Studio** (`/ads`) is the reference example.

```
pages/ads/            AdsStudio · AdToolRoute · AdToolPlaceholder
                      CampaignPlaceholder
pages/ads/tools/      one page per tool + index.js (slug → component)
components/ads/       AdsHero · AdToolCard · AdToolSection · AdCreativeArt
                      CampaignTable · CampaignStatTile · CampaignStatusBadge
                      AdsPageHeader · AdsEmptyState
components/ads/workspace/
                      AdsWorkspace · PreviewStage · UploadField · GenerateButton
lib/ads/              tools.js (registry) · constants.js · store.js
hooks/                useCampaigns.js
```

Four rules make a module extendable without edits rippling outward:

1. **One registry drives the module.** `lib/ads/tools.js` lists every feature,
   built or planned. The Quick Action cards, the routes in `App.jsx`, each
   placeholder page's copy, and the tab titles all read from it — so shipping a
   feature is an entry there plus a page, never a hunt for hardcoded strings.
   Keep it free of Vite syntax: `seo/pages.data.js` imports it, and that module
   is loaded by the Node-side build plugin.
2. **Storage sits behind a provider.** `lib/ads/store.js` exposes an async
   `list/get/create/update/remove` and is backed by localStorage today.
   `setCampaignProvider()` swaps in a `lib/api.js`-backed implementation with no
   component changes — the same seam `setMediaProvider` gives the Media Library.
3. **The module answers SEO questions about its own paths.** Nested and
   id-bearing routes cannot live in a flat list, so `tools.js` exports
   `isAdsPath()` and `adsRouteTitle()`, which `seo/pages.data.js` composes into
   `isPrivatePath()` and `privatePageTitle()`. One `Disallow: /ads` in
   robots.txt covers the whole subtree.
4. **One dynamic route, not one per feature.** `App.jsx` has a single
   `/ads/:slug` pointing at `AdToolRoute`, which looks the slug up in
   `pages/ads/tools/index.js`. A tool with a page renders it; one without falls
   through to `AdToolPlaceholder`, generated from the same registry entry. So
   shipping a workspace is one line in that map — `App.jsx` never grows, and
   routing cannot disagree with what exists.

Working pages use the `.split-shell` / `.split-grid` / `.split-pane` classes so
their columns scroll independently (`AdsWorkspace` wraps this). **Single-column
pages must not** — the app shell's `<main>` already scrolls, so a `.split-pane`
there nests a second scroll area and produces two scrollbars.

AI Ads Studio is a **separate workflow from the AI Generator**, not an extension
of it: the Generator produces one organic post, the Studio manages advertising
campaigns made of many creatives across several platforms. They share the design
system and contexts, and nothing else.

## Assets & SEO files

- `public/favicon.svg` — vector favicon.
- `public/og-image.png` — 1200×630 social-share image.
- `public/robots.txt`, `public/sitemap.xml` — update the domain if not
  deploying to `https://autosocial.ai`, and keep the sitemap in sync with
  `PUBLIC_ROUTES` in `config/site.js`.

## Environment

See `.env.example`: `VITE_SITE_URL`, `VITE_GA_ID`, `VITE_CLARITY_ID`,
`VITE_CONTACT_API`.
