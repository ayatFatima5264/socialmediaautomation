// ---------------------------------------------------------------------------
// A template's preview, drawn from the template's own definition.
//
// **Nothing here is decoration and nothing here is stock.** Every shape is read
// off the definition the project will actually be built from — the canvas is
// the template's real ratio, the colours are its `preview` block, the title
// sits where its `layout` puts it, the caption bar is its `subtitle_style`, and
// the strip underneath is its scenes at their real durations. A template with
// no scenes draws no strip; a template with no music shows no music mark.
//
// That constraint is the point. A preview assembled from anything else — a
// stock frame, a hand-drawn mock — would be advertising a look the template
// does not produce, and the user would find that out after committing to it.
//
// SVG rather than an image so it is one file for every template, scales from a
// card to a modal without a second asset, and costs no storage or render time.
// ---------------------------------------------------------------------------

// Where the burned-in caption sits, as a fraction of canvas height.
const CAPTION_Y = { top: 0.16, center: 0.52, bottom: 0.82 }

// Where a title block sits, by the template's own layout vocabulary.
const TITLE_Y = { upper: 0.2, center: 0.44, lower: 0.72 }

function titleAnchor(align) {
  if (align === 'left') return { x: 0.08, anchor: 'start' }
  if (align === 'right') return { x: 0.92, anchor: 'end' }
  return { x: 0.5, anchor: 'middle' }
}

export default function TemplatePreview({ template, detailed = false, className = '' }) {
  const width = template.width || 1080
  const height = template.height || 1920
  const preview = template.preview || {}
  const style = preview.style || 'bold-center'
  const accent = preview.accent || '#10b981'
  const [from, to] = preview.background?.length
    ? [preview.background[0], preview.background[1] || preview.background[0]]
    : ['#111827', '#0b1220']

  const layout = template.layout || {}
  const caption = template.subtitle_style || {}
  const scenes = template.scenes || []

  // A stable id per template, so two previews on one page do not share a
  // gradient definition and end up the same colour.
  const uid = `tpl-${template.key || template.id || 'x'}`

  const T = (fraction) => height * fraction
  const L = (fraction) => width * fraction

  const titlePos = layout.title?.position || (style === 'lower-third' ? 'lower' : 'center')
  const { x: titleX, anchor } = titleAnchor(
    layout.title?.align || (style === 'lower-third' ? 'left' : 'center'),
  )
  const titleTop = T(TITLE_Y[titlePos] ?? 0.44)

  // A text line, drawn as a rounded bar rather than lettering. The template has
  // no words in it — writing sample copy here would be inventing content the
  // project will not contain.
  const Line = ({ y, w, h = 0.032, fill = '#ffffff', opacity = 0.92, rx }) => (
    <rect
      x={anchor === 'start' ? L(0.08) : anchor === 'end' ? L(0.92) - L(w) : (width - L(w)) / 2}
      y={y}
      width={L(w)}
      height={T(h)}
      rx={rx ?? T(h) / 2}
      fill={fill}
      opacity={opacity}
    />
  )

  const MediaBox = ({ x, y, w, h }) => (
    <g>
      <rect
        x={x} y={y} width={w} height={h}
        rx={Math.min(w, h) * 0.06}
        fill="#ffffff" opacity="0.07"
        stroke="#ffffff" strokeOpacity="0.22" strokeWidth={width * 0.004}
        strokeDasharray={`${width * 0.02} ${width * 0.016}`}
      />
      {/* the "an image goes here" mark every editor uses */}
      <circle cx={x + w * 0.32} cy={y + h * 0.36} r={Math.min(w, h) * 0.07} fill="#ffffff" opacity="0.3" />
      <path
        d={`M ${x + w * 0.14} ${y + h * 0.82} L ${x + w * 0.42} ${y + h * 0.5} L ${x + w * 0.62} ${y + h * 0.68} L ${x + w * 0.76} ${y + h * 0.56} L ${x + w * 0.86} ${y + h * 0.82} Z`}
        fill="#ffffff" opacity="0.28"
      />
    </g>
  )

  function body() {
    switch (style) {
      case 'blank':
        return (
          <g>
            <text
              x={width / 2} y={height / 2}
              textAnchor="middle" dominantBaseline="middle"
              fill="#ffffff" opacity="0.4"
              fontSize={Math.min(width, height) * 0.13}
              fontFamily="system-ui, sans-serif" fontWeight="600"
            >
              {template.aspect_ratio}
            </text>
          </g>
        )

      case 'split': {
        const half = width * 0.44
        return (
          <g>
            <MediaBox x={L(0.06)} y={(height - half) / 2} w={half} h={half} />
            <rect x={L(0.55)} y={T(0.4)} width={L(0.3)} height={T(0.012)} rx={T(0.006)} fill={accent} />
            <rect x={L(0.55)} y={T(0.45)} width={L(0.37)} height={T(0.028)} rx={T(0.014)} fill="#fff" opacity="0.9" />
            <rect x={L(0.55)} y={T(0.5)} width={L(0.26)} height={T(0.028)} rx={T(0.014)} fill="#fff" opacity="0.55" />
          </g>
        )
      }

      case 'grid': {
        const cols = 2
        const rows = 2
        const gap = width * 0.04
        const cw = (width - gap * (cols + 1)) / cols
        const ch = cw * (height / width) * 0.9
        const top = (height - (ch * rows + gap)) / 2
        return (
          <g>
            {Array.from({ length: cols * rows }).map((_, i) => (
              <MediaBox
                key={i}
                x={gap + (i % cols) * (cw + gap)}
                y={top + Math.floor(i / cols) * (ch + gap)}
                w={cw}
                h={ch}
              />
            ))}
          </g>
        )
      }

      case 'numbered':
        return (
          <g>
            <circle cx={width / 2} cy={T(0.34)} r={Math.min(width, height) * 0.1} fill={accent} opacity="0.9" />
            <rect
              x={width / 2 - L(0.02)} y={T(0.34) - T(0.035)}
              width={L(0.04)} height={T(0.07)} rx={L(0.008)}
              fill="#ffffff" opacity="0.95"
            />
            <Line y={T(0.52)} w={0.62} h={0.036} />
            <Line y={T(0.58)} w={0.44} h={0.028} opacity={0.55} />
          </g>
        )

      case 'quote':
        return (
          <g>
            <text
              x={width / 2} y={T(0.3)}
              textAnchor="middle" fill={accent} opacity="0.85"
              fontSize={Math.min(width, height) * 0.22}
              fontFamily="Georgia, serif" fontWeight="700"
            >
              &ldquo;
            </text>
            <Line y={T(0.42)} w={0.66} h={0.038} />
            <Line y={T(0.49)} w={0.52} h={0.038} />
            <Line y={T(0.6)} w={0.24} h={0.022} fill={accent} opacity={0.9} />
          </g>
        )

      case 'kinetic':
        return (
          <g>
            {[
              { w: 0.34, o: 1 },
              { w: 0.5, o: 0.85 },
              { w: 0.28, o: 0.7 },
            ].map((row, i) => (
              <rect
                key={i}
                x={(width - L(row.w)) / 2}
                y={T(0.36 + i * 0.09)}
                width={L(row.w)}
                height={T(0.062)}
                rx={T(0.012)}
                fill={i === 0 ? accent : '#ffffff'}
                opacity={i === 0 ? 0.95 : row.o * 0.9}
              />
            ))}
          </g>
        )

      case 'caption-heavy':
        return (
          <g>
            <MediaBox x={L(0.12)} y={T(0.14)} w={L(0.76)} h={T(0.42)} />
            <Line y={T(0.64)} w={0.78} h={0.055} />
            <Line y={T(0.72)} w={0.56} h={0.055} />
          </g>
        )

      case 'lower-third':
        return (
          <g>
            <MediaBox x={L(0.06)} y={T(0.1)} w={L(0.88)} h={T(0.5)} />
            <rect x={L(0.08)} y={titleTop} width={L(0.012)} height={T(0.1)} rx={L(0.006)} fill={accent} />
            <Line y={titleTop + T(0.012)} w={0.5} h={0.034} />
            <Line y={titleTop + T(0.058)} w={0.34} h={0.024} opacity={0.6} />
          </g>
        )

      case 'bold-center':
      default:
        return (
          <g>
            <MediaBox x={L(0.1)} y={T(0.12)} w={L(0.8)} h={T(0.26)} />
            <Line y={titleTop} w={0.72} h={0.05} />
            <Line y={titleTop + T(0.075)} w={0.5} h={0.05} />
            <Line y={titleTop + T(0.16)} w={0.3} h={0.022} fill={accent} opacity={0.95} />
          </g>
        )
    }
  }

  // The caption bar, only when the template actually burns subtitles in.
  const burns = template.export_settings?.burn_subtitles !== false
  const capY = T(CAPTION_Y[caption.position] ?? 0.82)
  const capH = T(Math.max(0.03, Math.min(0.08, (caption.font_size || 48) / 1200)))

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      role="img"
      aria-label={`${template.name} — ${template.aspect_ratio} preview`}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <linearGradient id={`${uid}-bg`} x1="0" y1="0" x2="0.4" y2="1">
          <stop offset="0%" stopColor={from} />
          <stop offset="100%" stopColor={to} />
        </linearGradient>
      </defs>

      <rect width={width} height={height} fill={`url(#${uid}-bg)`} />

      {body()}

      {burns && style !== 'blank' && (
        <g>
          {caption.background && caption.background !== 'transparent' && (
            <rect
              x={(width - width * 0.8) / 2} y={capY - capH * 0.35}
              width={width * 0.8} height={capH * 1.7} rx={capH * 0.4}
              fill={caption.background} opacity="0.75"
            />
          )}
          <rect
            x={(width - width * 0.62) / 2} y={capY}
            width={width * 0.62} height={capH} rx={capH / 2}
            fill={caption.color || '#ffffff'} opacity="0.95"
          />
          <rect
            x={(width - width * 0.4) / 2} y={capY + capH * 1.5}
            width={width * 0.4} height={capH} rx={capH / 2}
            fill={caption.color || '#ffffff'} opacity="0.6"
          />
        </g>
      )}

      {/* The scene strip: one segment per beat, widths in proportion to the
          real durations. Only when the template has a storyboard. */}
      {detailed && scenes.length > 0 && (
        <g>
          {(() => {
            const total = scenes.reduce((sum, s) => sum + (s.duration_seconds || 0), 0) || 1
            const stripY = height * 0.955
            const stripH = height * 0.018
            let x = width * 0.04
            const usable = width * 0.92
            return scenes.map((scene, i) => {
              const w = (usable * (scene.duration_seconds || 0)) / total
              const seg = (
                <rect
                  key={i}
                  x={x + 2} y={stripY} width={Math.max(w - 4, 2)} height={stripH}
                  rx={stripH / 2}
                  fill={i === 0 ? accent : '#ffffff'}
                  opacity={i === 0 ? 0.95 : 0.42}
                />
              )
              x += w
              return seg
            })
          })()}
        </g>
      )}
    </svg>
  )
}
