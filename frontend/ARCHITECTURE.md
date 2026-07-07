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
                         │  /create /scheduler         │
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
- **Theme** — `context/ThemeContext.jsx` (light/dark, persisted).
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

## Assets & SEO files

- `public/favicon.svg` — vector favicon.
- `public/og-image.png` — 1200×630 social-share image.
- `public/robots.txt`, `public/sitemap.xml` — update the domain if not
  deploying to `https://autosocial.ai`, and keep the sitemap in sync with
  `PUBLIC_ROUTES` in `config/site.js`.

## Environment

See `.env.example`: `VITE_SITE_URL`, `VITE_GA_ID`, `VITE_CLARITY_ID`,
`VITE_CONTACT_API`.
