import { Link } from 'react-router-dom'
import { Container } from './_ui.jsx'
import Seo from '../../components/Seo.jsx'
import { SITE } from '../../config/site'

// ---------------------------------------------------------------------------
// Data Deletion — the public, login-free page Meta requires as an app's "Data
// Deletion Instructions URL", and the page a user lands on when they want their
// data gone.
//
// Every instruction here describes a control that actually exists:
//   • "Disconnect"    → Social Accounts page, DELETE /api/social/{platform}
//   • "Delete Account"→ Settings → Danger Zone, DELETE /auth/me
//   • the Meta path   → /api/auth/{threads,meta}/{delete,deauthorize}
// If a control is ever removed, the matching paragraph has to go with it —
// a deletion page that describes a button which isn't there is worse than none.
// ---------------------------------------------------------------------------

function Section({ id, heading, children }) {
  return (
    <section id={id} className="scroll-mt-24">
      <h2 className="text-xl font-bold">{heading}</h2>
      <div className="mt-3 space-y-3 text-sm leading-relaxed text-muted">{children}</div>
    </section>
  )
}

function Steps({ children }) {
  return (
    <ol className="mt-3 list-decimal space-y-2 rounded-xl bg-inset p-4 pl-8 text-sm leading-relaxed text-muted">
      {children}
    </ol>
  )
}

export default function DataDeletion() {
  const mailto = `mailto:${SITE.supportEmail}?subject=${encodeURIComponent(
    'Data deletion request',
  )}`

  return (
    <>
      <Seo />
      <section className="py-16">
        <Container className="max-w-3xl">
          <h1 className="text-3xl font-black tracking-tight md:text-4xl">
            Data Deletion
          </h1>
          <p className="mt-2 text-sm text-muted">Last updated: August 16, 2026</p>

          <p className="mt-6 text-sm leading-relaxed text-body">
            This page explains what {SITE.name} stores, how to delete a single
            connected social account, and how to permanently delete your entire
            account and everything in it. Both actions are available inside the app
            and take effect immediately — there is no waiting period and no support
            ticket required.
          </p>

          <div className="mt-10 space-y-10">
            <Section id="what-we-store" heading="1. What we store">
              <p>When you use {SITE.name}, we hold the following:</p>
              <ul className="list-disc space-y-1.5 pl-5">
                <li>
                  <b>Your account</b> — email address, display name, an encrypted
                  password hash, your timezone, and the date you signed up.
                </li>
                <li>
                  <b>Your business profile</b> — the business details you enter so
                  the AI can write in your voice: business name, industry, audience,
                  tone, goals, brand colours, logo, and any contact details you add.
                </li>
                <li>
                  <b>Your content</b> — posts and drafts, content plans, schedules,
                  ad campaigns and their creatives, and the images you upload.
                </li>
                <li>
                  <b>Connected social accounts</b> — described in the next section.
                </li>
              </ul>
              <p>
                We do not sell your personal information. Our full{' '}
                <Link to="/privacy" className="link-accent font-medium">
                  Privacy Policy
                </Link>{' '}
                covers how this data is used.
              </p>
            </Section>

            <Section id="social-data" heading="2. What we store for a connected social account">
              <p>
                When you connect Facebook, Instagram, Threads, Pinterest, LinkedIn or
                X, we store only what is needed to publish on your behalf:
              </p>
              <ul className="list-disc space-y-1.5 pl-5">
                <li>
                  An <b>OAuth access token</b> (and a refresh token where the platform
                  issues one), so scheduled posts can publish when you are not
                  signed in. Tokens are encrypted at rest and are never sent to your
                  browser or shown anywhere in the app.
                </li>
                <li>
                  The <b>account identifiers</b> the platform uses — your account id,
                  and the linked Page or board id where one applies.
                </li>
                <li>
                  <b>Display details</b> shown on your Social Accounts page: username,
                  display name and profile picture.
                </li>
                <li>
                  The <b>permissions you granted</b> and the dates the account was
                  connected and last synced.
                </li>
              </ul>
              <p>
                We never store your password for any social platform — the connection
                is made through that platform's own login screen.
              </p>
            </Section>

            <Section id="disconnect" heading="3. Deleting one connected social account">
              <p>
                Disconnecting removes that platform's stored credentials and details
                from our database immediately. The rest of your {SITE.name} account —
                your posts, plans and other connections — is untouched.
              </p>
              <Steps>
                <li>Sign in and open <b>Social Accounts</b>.</li>
                <li>Find the platform you want to remove.</li>
                <li>
                  Click <b>Disconnect</b>. The stored access token, refresh token and
                  account details for that platform are deleted at once.
                </li>
              </Steps>
              <p>
                You can also revoke our access from the platform's own settings. For
                Facebook, Instagram and Threads, Meta notifies us when you remove the
                app, and we delete that connection automatically — see section 5.
              </p>
            </Section>

            <Section id="delete-account" heading="4. Deleting your entire account">
              <p>
                This permanently erases your {SITE.name} account and every record
                belonging to it. It is immediate and cannot be undone — we keep no
                copy and cannot restore the account afterwards.
              </p>
              <Steps>
                <li>Sign in and open <b>Settings</b>.</li>
                <li>Scroll to the <b>Danger Zone</b> section at the bottom.</li>
                <li>Click <b>Delete Account</b>.</li>
                <li>
                  Type <span className="font-mono font-semibold">DELETE</span> in the
                  confirmation box and confirm.
                </li>
              </Steps>
              <p>Deleting your account removes all of the following:</p>
              <ul className="list-disc space-y-1.5 pl-5">
                <li>Your profile, login credentials and business profile</li>
                <li>All posts, drafts, content plans, schedules and planner settings</li>
                <li>All ad campaigns and their creatives</li>
                <li>Every image you uploaded</li>
                <li>
                  Every connected social account, including its stored access and
                  refresh tokens
                </li>
              </ul>
              <p>
                You are signed out as soon as the deletion completes. Posts that were
                already published stay on the social platforms they were published to
                — those live in your own profiles, and deleting your {SITE.name}{' '}
                account does not reach into them. Remove those from each platform
                directly if you want them gone.
              </p>
            </Section>

            <Section id="meta" heading="5. Facebook, Instagram and Threads data">
              <p>
                Facebook, Instagram and Threads are connected through Meta. You can
                remove {SITE.name}'s access from Meta's side at any time:
              </p>
              <ul className="list-disc space-y-1.5 pl-5">
                <li>
                  <b>Facebook</b> — Settings &amp; Privacy → Settings → Apps and
                  Websites → remove {SITE.name}.
                </li>
                <li>
                  <b>Instagram</b> — Settings → Website Permissions → Apps and
                  Websites → remove {SITE.name}.
                </li>
                <li>
                  <b>Threads</b> — Settings → Account → Website Permissions → remove{' '}
                  {SITE.name}.
                </li>
              </ul>
              <p>
                When you do this, Meta sends us a deletion request identifying your
                account. We delete the matching Facebook, Instagram and Threads
                connections — including their stored access tokens — and return a
                confirmation code with a status URL you can open to verify the
                deletion completed. This happens automatically and immediately; no
                action is needed from you.
              </p>
              <p>
                Removing the app on Meta's side deletes those social connections. It
                does not delete your {SITE.name} account itself, because a Meta
                identity does not authorise erasing data tied to other platforms. To
                remove everything, use section 4.
              </p>
            </Section>

            <Section id="no-access" heading="6. If you cannot sign in">
              <p>
                If you have lost access to your account, you can ask us to delete it
                for you. First try the{' '}
                <Link to="/forgot-password" className="link-accent font-medium">
                  password reset
                </Link>
                , which lets you sign in and delete the account yourself — that is
                immediate, and it is the fastest route.
              </p>
              <p>If reset is not an option, contact us:</p>
              <ul className="list-disc space-y-1.5 pl-5">
                <li>
                  Email{' '}
                  <a href={mailto} className="link-accent font-medium">
                    {SITE.supportEmail}
                  </a>{' '}
                  with the subject "Data deletion request", or
                </li>
                <li>
                  Use our{' '}
                  <Link to="/contact" className="link-accent font-medium">
                    contact form
                  </Link>
                  .
                </li>
              </ul>
              <p>
                Send the request from the email address on the account and tell us
                which account to delete. We may ask one or two questions to confirm
                the account is yours before we act — we cannot delete an account on
                the word of someone we cannot identify as its owner.
              </p>
            </Section>

            <Section id="timeframe" heading="7. What happens after a request">
              <p>
                <b>Deleting from inside the app is immediate.</b> The records are
                removed from our live database as part of the request; there is no
                queue and no grace period.
              </p>
              <p>
                <b>Requests sent by email</b> are acknowledged within 5 business days
                and completed within 30 days, which is the maximum period required
                under GDPR. In practice they are usually done far sooner. We will
                email you to confirm once the deletion is complete.
              </p>
              <p>
                After deletion, your data is gone from our live systems. Residual
                copies may remain in our hosting provider's encrypted database
                backups for a short retention period, after which those backups are
                overwritten. Those backups are not accessible to the application and
                are never used to restore a deleted account.
              </p>
              <p>
                If you have any question about a deletion request, write to{' '}
                <a href={mailto} className="link-accent font-medium">
                  {SITE.supportEmail}
                </a>
                .
              </p>
            </Section>
          </div>
        </Container>
      </section>
    </>
  )
}
