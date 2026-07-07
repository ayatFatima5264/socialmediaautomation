import { Container } from './_ui.jsx'

// Shared shell for long-form legal documents (Privacy, Terms). Keeps both pages
// visually consistent and easy to maintain.
export default function LegalPage({ title, updated, sections }) {
  return (
    <section className="py-16">
      <Container className="max-w-3xl">
        <h1 className="text-3xl font-black tracking-tight md:text-4xl">{title}</h1>
        <p className="mt-2 text-sm text-slate-400">Last updated: {updated}</p>

        <div className="mt-10 space-y-8">
          {sections.map((s) => (
            <div key={s.heading}>
              <h2 className="text-xl font-bold">{s.heading}</h2>
              {s.body.map((p, i) => (
                <p key={i} className="mt-3 text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                  {p}
                </p>
              ))}
            </div>
          ))}
        </div>
      </Container>
    </section>
  )
}
