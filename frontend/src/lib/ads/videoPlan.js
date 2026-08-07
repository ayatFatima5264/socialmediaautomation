// ---------------------------------------------------------------------------
// A shot plan as plain text.
//
// Two tools produce plans — Text to Video and Product Showcase Video — and both
// need the same string twice over: once for the clipboard, once for the copy
// saved into the campaign library. Written inline in each, the two drift and
// the asset a user reads back stops matching what they copied.
//
// No video provider is configured, so a plan is what the video tools genuinely
// produce. It is saved as a `video` asset with no url, which is the honest
// shape: a record of the film, not the film.
// ---------------------------------------------------------------------------

export function planToText(plan) {
  if (!plan?.scenes?.length) return ''

  const lines = [
    plan.hook ? `HOOK: ${plan.hook}` : '',
    ...plan.scenes.map((s) =>
      [
        `${s.start}s (${s.seconds}s) — ${s.shot}`,
        s.on_screen ? `  On screen: ${s.on_screen}` : '',
        s.voiceover ? `  VO: ${s.voiceover}` : '',
      ]
        .filter(Boolean)
        .join('\n'),
    ),
    plan.cta ? `CTA: ${plan.cta}` : '',
  ]

  return lines.filter(Boolean).join('\n')
}
