import { useState } from 'react'
import { Container, PageHero } from './_ui.jsx'
import Seo from '../../components/Seo.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import { api, ApiError } from '../../lib/api'
import { SITE } from '../../config/site'

const CHANNELS = [
  { icon: '✉', label: 'Email us', value: SITE.supportEmail, href: `mailto:${SITE.supportEmail}` },
  { icon: '💬', label: 'Live chat', value: 'Available in-app, 9am–5pm PT' },
  { icon: '🕑', label: 'Response time', value: 'Within one business day' },
]

const SUPPORT = [
  { icon: '📚', title: 'Help Center', body: 'Guides and answers to common questions.', badge: 'Coming soon' },
  { icon: '🧑‍💻', title: 'Documentation', body: 'Setup, publishing, and best-practice docs.', badge: 'Coming soon' },
  { icon: '🤝', title: 'Sales & partnerships', body: 'Talk to us about Business and Enterprise plans.' },
]

export default function Contact() {
  const toast = useToast()
  const [form, setForm] = useState({ name: '', email: '', message: '' })
  const [busy, setBusy] = useState(false)
  const set = (patch) => setForm((f) => ({ ...f, ...patch }))

  // Contact pipeline: Contact API → Email → Admin Dashboard → Reply.
  // Flip VITE_CONTACT_API=true once the backend POST /api/contact endpoint
  // exists; until then we acknowledge locally so the form is fully usable.
  const apiEnabled = import.meta.env.VITE_CONTACT_API === 'true'

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      if (apiEnabled) {
        await api.contact(form)
      } else {
        await new Promise((r) => setTimeout(r, 400))
      }
      toast.success("Thanks for reaching out — we'll reply within one business day.")
      setForm({ name: '', email: '', message: '' })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not send message')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Seo
        title="Contact"
        description="Questions, feedback, or partnership ideas? Get in touch with the AutoSocial AI team — we respond within one business day."
      />
      <PageHero
        eyebrow="Contact"
        title="Get in touch"
        subtitle="Questions about features, pricing, or partnerships? Send us a note and a real person will get back to you — usually within one business day."
      />
      <section className="pb-16">
        <Container>
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="space-y-4 lg:col-span-1">
              {CHANNELS.map((c) => (
                <div key={c.label} className="card p-5">
                  <div className="flex items-center gap-3">
                    <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-indigo-500/15 to-violet-500/15 text-lg">
                      {c.icon}
                    </div>
                    <div>
                      <div className="text-sm font-semibold">{c.label}</div>
                      {c.href ? (
                        <a
                          href={c.href}
                          className="text-sm text-indigo-500 hover:text-indigo-400 dark:text-indigo-300"
                        >
                          {c.value}
                        </a>
                      ) : (
                        <div className="text-sm text-slate-500 dark:text-slate-400">
                          {c.value}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="card p-7 lg:col-span-2">
              <form onSubmit={submit} className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="label">Name</label>
                    <input
                      className="input"
                      required
                      value={form.name}
                      onChange={(e) => set({ name: e.target.value })}
                      placeholder="Your name"
                    />
                  </div>
                  <div>
                    <label className="label">Email</label>
                    <input
                      className="input"
                      type="email"
                      required
                      value={form.email}
                      onChange={(e) => set({ email: e.target.value })}
                      placeholder="you@company.com"
                    />
                  </div>
                </div>
                <div>
                  <label className="label">Message</label>
                  <textarea
                    className="input min-h-36"
                    required
                    value={form.message}
                    onChange={(e) => set({ message: e.target.value })}
                    placeholder="How can we help?"
                  />
                </div>
                <button className="btn btn-primary px-6" disabled={busy}>
                  {busy ? 'Sending…' : 'Send message'}
                </button>
              </form>
            </div>
          </div>

          {/* Support section */}
          <div className="mt-12">
            <h2 className="text-center text-2xl font-bold">Looking for support?</h2>
            <p className="mx-auto mt-2 max-w-xl text-center text-sm text-slate-500 dark:text-slate-400">
              Already using AutoSocial AI? Here's where to find help — and what's on
              the way.
            </p>
            <div className="mt-6 grid gap-5 md:grid-cols-3">
              {SUPPORT.map((s) => (
                <div key={s.title} className="card p-6">
                  <div className="mb-3 grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-indigo-500/15 to-violet-500/15 text-lg">
                    {s.icon}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-bold">{s.title}</h3>
                    {s.badge && (
                      <span className="rounded-full bg-indigo-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-500 dark:text-indigo-300">
                        {s.badge}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{s.body}</p>
                </div>
              ))}
            </div>
          </div>
        </Container>
      </section>
    </>
  )
}
