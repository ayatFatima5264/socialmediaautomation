// ---------------------------------------------------------------------------
// A tiny, dependency-free Markdown renderer sized for our blog articles.
//
// We deliberately avoid pulling in a full parser (react-markdown + remark is
// ~40 kB gzipped) because the article subset we author is small and known:
// H2/H3 headings, paragraphs, bullet + numbered lists, blockquotes, pipe
// tables, horizontal rules, and inline bold / italic / code / links.
//
// Headings get deterministic slug ids so the Table of Contents can anchor to
// them, and `extractHeadings` reuses the exact same slugifier — the TOC can
// never drift from the body it links to.
// ---------------------------------------------------------------------------

// "Why Consistency Beats Volume" -> "why-consistency-beats-volume"
export function slugify(text) {
  return String(text)
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
}

// ---- Inline formatting ----------------------------------------------------
// Handles `code`, **bold**, *italic*, and [label](href) in a single pass so
// nesting order can't produce mismatched fragments.
const INLINE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(\[[^\]]+\]\([^)]+\))/g

function renderInline(text, keyPrefix = 'i') {
  const nodes = []
  let last = 0
  let match
  let n = 0

  while ((match = INLINE.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index))
    const token = match[0]
    const key = `${keyPrefix}-${n++}`

    if (token.startsWith('`')) {
      nodes.push(
        <code
          key={key}
          className="rounded bg-inset px-1.5 py-0.5 text-[0.9em] font-medium text-accent"
        >
          {token.slice(1, -1)}
        </code>,
      )
    } else if (token.startsWith('**')) {
      nodes.push(
        <strong key={key} className="font-semibold text-body">
          {token.slice(2, -2)}
        </strong>,
      )
    } else if (token.startsWith('[')) {
      const [, label, href] = token.match(/\[([^\]]+)\]\(([^)]+)\)/)
      const external = /^https?:\/\//.test(href)
      nodes.push(
        <a
          key={key}
          href={href}
          className="link-accent font-medium"
          {...(external ? { target: '_blank', rel: 'noreferrer' } : {})}
        >
          {label}
        </a>,
      )
    } else {
      nodes.push(
        <em key={key} className="italic">
          {token.slice(1, -1)}
        </em>,
      )
    }
    last = match.index + token.length
  }

  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

// ---- Block parsing --------------------------------------------------------
// Walks the source line by line and emits a flat list of block descriptors.
export function parseMarkdown(source) {
  const lines = String(source).replace(/\r\n/g, '\n').split('\n')
  const blocks = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // Blank line — nothing to emit.
    if (!line.trim()) {
      i++
      continue
    }

    // Horizontal rule.
    if (/^---+\s*$/.test(line)) {
      blocks.push({ type: 'hr' })
      i++
      continue
    }

    // Headings (H2 / H3 only — the H1 is the page title, rendered by the page).
    const heading = line.match(/^(#{2,3})\s+(.*)$/)
    if (heading) {
      const level = heading[1].length
      const text = heading[2].trim()
      blocks.push({ type: `h${level}`, text, id: slugify(text) })
      i++
      continue
    }

    // Pipe table: a header row, a separator row, then body rows.
    if (line.trim().startsWith('|') && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1] || '')) {
      const cells = (row) =>
        row
          .trim()
          .replace(/^\||\|$/g, '')
          .split('|')
          .map((c) => c.trim())
      const head = cells(line)
      const rows = []
      i += 2
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        rows.push(cells(lines[i]))
        i++
      }
      blocks.push({ type: 'table', head, rows })
      continue
    }

    // Blockquote — consecutive "> " lines join into one quote.
    if (line.startsWith('> ')) {
      const parts = []
      while (i < lines.length && lines[i].startsWith('> ')) {
        parts.push(lines[i].slice(2).trim())
        i++
      }
      blocks.push({ type: 'quote', text: parts.join(' ') })
      continue
    }

    // Unordered list.
    if (/^[-*]\s+/.test(line)) {
      const items = []
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*]\s+/, ''))
        i++
      }
      blocks.push({ type: 'ul', items })
      continue
    }

    // Ordered list.
    if (/^\d+\.\s+/.test(line)) {
      const items = []
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s+/, ''))
        i++
      }
      blocks.push({ type: 'ol', items })
      continue
    }

    // Paragraph — greedily absorb following lines until a blank or a new block.
    const para = [line]
    i++
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{2,3}\s|[-*]\s|\d+\.\s|>\s|---+\s*$|\|)/.test(lines[i])
    ) {
      para.push(lines[i])
      i++
    }
    blocks.push({ type: 'p', text: para.join(' ') })
  }

  return blocks
}

// Pull the H2s out for the Table of Contents (H3s stay out so the TOC of a
// 2,000-word article remains scannable rather than becoming a second article).
export function extractHeadings(source) {
  return parseMarkdown(source)
    .filter((b) => b.type === 'h2')
    .map((b) => ({ id: b.id, text: b.text }))
}

// Strip inline markers so text can be used in JSON-LD / meta tags.
function plain(text) {
  return String(text)
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[*`]/g, '')
    .trim()
}

// Read the article's FAQ block back out of the Markdown so the page can emit
// FAQPage structured data. Every question is an H3 under the FAQ H2, and the
// answer is the prose that follows it. Deriving this from the body (rather than
// duplicating it in the registry) means the rich-result markup and the visible
// answers can never disagree.
export function extractFaq(source) {
  const blocks = parseMarkdown(source)
  const start = blocks.findIndex((b) => b.type === 'h2' && /frequently asked|^faq/i.test(b.text))
  if (start === -1) return []

  const faq = []
  let current = null

  for (let i = start + 1; i < blocks.length; i++) {
    const b = blocks[i]
    if (b.type === 'h2') break // FAQ section is over
    if (b.type === 'h3') {
      if (current) faq.push(current)
      current = { question: plain(b.text), answer: '' }
    } else if (current && (b.type === 'p' || b.type === 'quote')) {
      current.answer = `${current.answer} ${plain(b.text)}`.trim()
    } else if (current && (b.type === 'ul' || b.type === 'ol')) {
      current.answer = `${current.answer} ${b.items.map(plain).join('; ')}`.trim()
    }
  }
  if (current) faq.push(current)

  return faq.filter((f) => f.answer)
}

// ---- Renderer -------------------------------------------------------------
export default function Markdown({ source }) {
  const blocks = parseMarkdown(source)

  return (
    <div className="space-y-5">
      {blocks.map((b, idx) => {
        const key = `b${idx}`
        switch (b.type) {
          case 'h2':
            return (
              <h2
                key={key}
                id={b.id}
                className="scroll-mt-24 pt-6 text-2xl font-black tracking-tight md:text-3xl"
              >
                {renderInline(b.text, key)}
              </h2>
            )
          case 'h3':
            return (
              <h3 key={key} id={b.id} className="scroll-mt-24 pt-2 text-lg font-bold md:text-xl">
                {renderInline(b.text, key)}
              </h3>
            )
          case 'ul':
            return (
              <ul key={key} className="space-y-2 pl-1">
                {b.items.map((item, j) => (
                  <li key={j} className="flex gap-3 leading-relaxed text-muted">
                    <span aria-hidden="true" className="mt-[0.6em] h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                    <span>{renderInline(item, `${key}-${j}`)}</span>
                  </li>
                ))}
              </ul>
            )
          case 'ol':
            return (
              <ol key={key} className="space-y-2.5">
                {b.items.map((item, j) => (
                  <li key={j} className="flex gap-3 leading-relaxed text-muted">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-bold text-accent">
                      {j + 1}
                    </span>
                    <span className="pt-0.5">{renderInline(item, `${key}-${j}`)}</span>
                  </li>
                ))}
              </ol>
            )
          case 'quote':
            return (
              <blockquote
                key={key}
                className="rounded-r-xl border-l-4 border-accent bg-accent-soft/60 px-5 py-4 text-base font-medium leading-relaxed text-body"
              >
                {renderInline(b.text, key)}
              </blockquote>
            )
          case 'table':
            return (
              // The 32rem floor starts at `sm`. On a phone it forced a
              // three-column comparison table into a sideways scroll for the
              // sake of cells that read perfectly well wrapped over two lines.
              // Phones get `table-fixed` and tighter cell padding: with the
              // automatic layout, the widest phrase in each column set that
              // column's width, and three of those together ran past the screen
              // however narrow the article column was. Fixed layout splits the
              // width evenly and lets the phrases wrap instead. From `sm` up
              // there is room to size columns to their content again.
              <div key={key} className="overflow-x-auto">
                <table className="w-full table-fixed border-collapse text-left text-sm sm:table-auto sm:min-w-[32rem]">
                  <thead>
                    <tr className="border-b-2 border-line">
                      {/* The first column carries the row labels and is the
                          one that reads worst when broken mid-word, so under
                          `sm` it takes a larger share of the fixed layout. */}
                      {b.head.map((h, j) => (
                        <th
                          key={j}
                          className={`break-words px-2 py-2.5 font-bold text-body sm:px-3 ${
                            j === 0 ? 'w-2/5 sm:w-auto' : ''
                          }`}
                        >
                          {renderInline(h, `${key}-h${j}`)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {b.rows.map((row, j) => (
                      <tr key={j} className="border-b border-line last:border-0">
                        {row.map((cell, k) => (
                          <td
                            key={k}
                            className="break-words px-2 py-2.5 align-top text-muted sm:px-3"
                          >
                            {renderInline(cell, `${key}-${j}-${k}`)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          case 'hr':
            return <hr key={key} className="border-line" />
          default:
            return (
              <p key={key} className="leading-[1.75] text-muted">
                {renderInline(b.text, key)}
              </p>
            )
        }
      })}
    </div>
  )
}
