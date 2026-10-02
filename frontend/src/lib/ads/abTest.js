// ---------------------------------------------------------------------------
// A/B Testing — the parts of the tool that are real today.
//
// Two questions the page asks, kept out of the component so both can be tested
// without rendering anything:
//
//   1. Is the test actually set up? (Two creatives chosen.)
//   2. What does a report of it say?
//
// The second one is here because "Export report" used to be a button that
// could never be pressed, and the quickest way to make it pressable is to
// invent delivery numbers. It does not. A report that says the test has not run
// yet is still a true report of what was set up, and it is the thing the user
// actually needs before they go and build this test in the ad platform.
// ---------------------------------------------------------------------------

/** Why there is no winner column yet. Said in the file, not implied by it. */
export const NO_DELIVERY_DATA =
  'Delivery data is not connected, so this report covers the test setup only.'

/** Both variants chosen — the point at which Start Test has something to run. */
export function isTestReady(variants) {
  return Boolean(variants?.a && variants?.b)
}

function describeVariant(variant) {
  if (!variant) return 'Not chosen'
  const size = variant.width && variant.height ? ` (${variant.width}x${variant.height})` : ''
  return `${variant.title || 'Untitled'}${size}`
}

function slug(text) {
  return (
    String(text)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '') || 'ab-test'
  )
}

/**
 * The report file. `generatedAt` is a parameter so the content is testable.
 */
export function buildTestReport({
  campaign,
  variants,
  split,
  metric,
  duration,
  generatedAt,
} = {}) {
  const ready = isTestReady(variants)

  const content = [
    'A/B TEST REPORT',
    '',
    `Campaign:  ${campaign?.name || 'Not in a campaign'}`,
    `Split:     ${split || 'Not set'}`,
    `Decide on: ${metric || 'Not set'}`,
    `Run for:   ${duration || 'Not set'}`,
    `Generated: ${generatedAt || new Date().toISOString()}`,
    '',
    'VARIANTS',
    `  A: ${describeVariant(variants?.a)}`,
    `  B: ${describeVariant(variants?.b)}`,
    '',
    ready ? 'STATUS:  Ready to run.' : 'STATUS:  Not set up — both variants must be chosen.',
    '',
    'RESULTS',
    `  ${NO_DELIVERY_DATA}`,
    '',
  ].join('\n')

  return {
    filename: `${slug(campaign?.name || 'ab-test')}-ab-report.txt`,
    mediaType: 'text/plain;charset=utf-8',
    content,
  }
}
