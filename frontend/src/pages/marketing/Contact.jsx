import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Container, PageHero, Section } from './_ui.jsx'
import Seo from '../../components/Seo.jsx'
import Icon from '../../components/marketing/Icon.jsx'
import { api, ApiError } from '../../lib/api'
import { SITE } from '../../config/site'

// ---------------------------------------------------------------------------
// Contact.
//
// The form now posts to POST /api/contact, which stores the message before it
// tries to email anyone. Previously this page faked a 400ms delay and showed a
// success toast without sending anything anywhere — every message a visitor
// wrote was discarded.
//
// Removed with the rewrite: a "live chat, 9am–5pm PT" channel that does not
// exist, "Help Center" and "Documentation" cards that were permanent
// placeholders, and a one-business-day response promise nothing backs.
// ---------------------------------------------------------------------------

const REASONS = [
  {
    icon: 'target',
    title: 'How something works',
    body: 'Questions about what the product does before you sign up, or how to get a particular result out of it once you have.',
  },
  {
    icon: 'megaphone',
    title: 'Business and Enterprise',
    body: 'Paid plans are arranged directly with us. Tell us roughly how many accounts and people are involved and we will take it from there.',
  },
  {
    icon: 'alert',
    title: 'Something is broken',
    body: 'A failed connection, a post that did not publish, or anything wrong with your account. Include the network involved and roughly when it happened.',
  },
]

const EMPTY = { name: '', email: '', message: '', website: '' }

export default function Contact() {
  const [form, setForm] = useState(EMPTY)
  const [busy, setBusy] = useState(false)
  // 'idle' | 'sent' | { error: string }
  const [status, setStatus] = useState('idle')

  const set = (patch) => {
    setForm((f) => ({ ...f, ...patch }))
    // Clearing a stale error as soon as the visitor starts fixing it.
    if (status !== 'idle') setStatus('idle')
  }

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setStatus('idle')
    try {
      await api.contact({
        name: form.name.trim(),
        email: form.email.trim(),
        message: form.message.trim(),
        website: form.website,
      })
      setStatus('sent')
      setForm(EMPTY)
    } catch (err) {
      // The endpoint answers 429 when an address has sent several messages in
      // an hour, and 422 with a per-field reason when something is malformed.
      // Both are worth showing verbatim; anything else gets a fallback that
      // still leaves the visitor a way to reach us.
      const message =
        err instanceof ApiError && err.message
          ? err.message
          : `Could not send your message. Please email ${SITE.supportEmail} instead.`
      setStatus({ error: message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Seo />
      <PageHero
        eyebrow="Contact"
        title="Talk to us"
        subtitle="One inbox, read by the people who build AutoSocial AI. Write in whatever detail you have — there is no ticket form to fill in first."
      />

      <Section>
        <div className="grid gap-10 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] lg:gap-16">
          {/* ---- What to write about ------------------------------------ */}
          <div>
            <div className="grid gap-3">
              <a
                href={`mailto:${SITE.supportEmail}`}
                className="flex items-center gap-3 rounded-xl border border-line bg-surface p-5 transition hover:border-accent-line"
              >
                <Icon name="mail" size={22} className="shrink-0 text-accent" />
                <span className="min-w-0">
                  <span className="block text-sm text-muted">Email us directly</span>
                  <span className="block break-all font-semibold text-body">
                    {SITE.supportEmail}
                  </span>
                </span>
              </a>
              {SITE.supportPhone && (
                <a
                  href={`tel:${SITE.supportPhone}`}
                  className="flex items-center gap-3 rounded-xl border border-line bg-surface p-5 transition hover:border-accent-line"
                >
                  <Icon name="phone" size={22} className="shrink-0 text-accent" />
                  <span>
                    <span className="block text-sm text-muted">Call or message us</span>
                    <span className="block font-semibold text-body">
                      {SITE.supportPhone}
                    </span>
                  </span>
                </a>
              )}
            </div>

            <h2 className="mt-10 text-xs font-semibold uppercase tracking-[0.14em] text-muted">
              What people write in about
            </h2>
            <ul className="mt-5 space-y-6">
              {REASONS.map((r) => (
                <li key={r.title}>
                  <h3 className="flex items-center gap-2 font-bold">
                    <Icon name={r.icon} size={18} className="text-accent" />
                    {r.title}
                  </h3>
                  <p className="mt-1.5 text-[15px] leading-relaxed text-muted">{r.body}</p>
                </li>
              ))}
            </ul>
          </div>

          {/* ---- Form ---------------------------------------------------- */}
          <div className="card p-6 md:p-8">
            <form onSubmit={submit} noValidate={false} className="space-y-5">
              <div className="grid gap-5 sm:grid-cols-2">
                <div>
                  <label className="label" htmlFor="contact-name">Name</label>
                  <input
                    id="contact-name"
                    className="input"
                    required
                    maxLength={120}
                    autoComplete="name"
                    value={form.name}
                    onChange={(e) => set({ name: e.target.value })}
                    placeholder="Your name"
                  />
                </div>
                <div>
                  <label className="label" htmlFor="contact-email">Email</label>
                  <input
                    id="contact-email"
                    className="input"
                    type="email"
                    required
                    autoComplete="email"
                    value={form.email}
                    onChange={(e) => set({ email: e.target.value })}
                    placeholder="you@company.com"
                  />
                </div>
              </div>

              <div>
                <label className="label" htmlFor="contact-message">Message</label>
                <textarea
                  id="contact-message"
                  className="input min-h-44 resize-y"
                  required
                  minLength={10}
                  maxLength={4000}
                  value={form.message}
                  onChange={(e) => set({ message: e.target.value })}
                  placeholder="What would you like to know?"
                />
                <p className="mt-1.5 text-xs text-muted">
                  {form.message.trim().length}/4000
                </p>
              </div>

              {/* Honeypot. Hidden from people and from assistive technology;
                  bots fill every field they find, and a filled one is discarded
                  server-side. Not `display:none`, which some bots skip. */}
              <div className="absolute -left-[9999px] h-0 w-0 overflow-hidden" aria-hidden="true">
                <label htmlFor="contact-website">Website</label>
                <input
                  id="contact-website"
                  name="website"
                  type="text"
                  tabIndex={-1}
                  autoComplete="off"
                  value={form.website}
                  onChange={(e) => set({ website: e.target.value })}
                />
              </div>

              <div className="flex flex-wrap items-center gap-4">
                <button className="btn btn-primary px-6 py-2.5" disabled={busy}>
                  {busy ? 'Sending…' : 'Send message'}
                </button>

                {/* Status is announced as well as shown: a screen-reader user
                    gets the same confirmation a sighted one does. */}
                <p role="status" aria-live="polite" className="text-sm">
                  {status === 'sent' && (
                    <span className="flex items-center gap-2 font-medium text-accent">
                      <Icon name="check" size={18} />
                      Message received. We will reply to the address you gave.
                    </span>
                  )}
                  {status !== 'idle' && status !== 'sent' && (
                    <span className="flex items-start gap-2 text-rose-600">
                      <Icon name="alert" size={18} className="mt-0.5 shrink-0" />
                      {status.error}
                    </span>
                  )}
                </p>
              </div>
            </form>
          </div>
        </div>
      </Section>

      <section className="border-t border-line py-12">
        <Container>
          <p className="max-w-2xl text-[15px] leading-relaxed text-muted">
            Already have an account and need to remove your data? The{' '}
            <Link to="/data-deletion" className="link-accent font-medium">
              data deletion page
            </Link>{' '}
            explains what gets deleted and how to request it.
          </p>
        </Container>
      </section>
    </>
  )
}
