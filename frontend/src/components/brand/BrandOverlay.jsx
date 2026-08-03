import { resolveLayer, sortLayers, textAlignFor, LAYER_TYPES } from '../../lib/brandKit/layers'

// ---------------------------------------------------------------------------
// SVG renderer for brand layers.
//
// Drawn as SVG rather than baked into the bitmap so text stays vector-sharp at
// any display size and every layer remains an addressable element — which is
// what a future editor needs in order to select, move, or restyle one.
//
// The SVG uses a viewBox matching the frame's aspect ratio and is stretched to
// fill its container, so one layer list renders identically in a 240px preview
// and a full-size view. Nothing here knows about pixels.
//
// `pointer-events: none` throughout: the overlay is decoration over an image,
// and must never intercept clicks meant for the image itself. An editor would
// re-enable this per layer.
// ---------------------------------------------------------------------------

const FRAME = { width: 1000, height: 1000 } // viewBox units; aspect set by caller

function LayerNode({ layer, frame, idPrefix }) {
  const box = resolveLayer(layer, frame)
  const opacity = layer.opacity ?? 1
  // Rotation is applied about the layer's own centre so a rotated box stays
  // where the user placed it instead of swinging away from the origin.
  const transform = layer.rotation
    ? `rotate(${layer.rotation} ${box.x + box.w / 2} ${box.y + box.h / 2})`
    : undefined

  if (layer.type === LAYER_TYPES.BACKGROUND) {
    const gid = `${idPrefix}-bg-${layer.id}`
    return (
      <>
        {layer.gradient && (
          <defs>
            <linearGradient
              id={gid}
              x1="0" y1="0"
              x2={layer.gradient.angle === 90 ? '1' : '0'}
              y2={layer.gradient.angle === 90 ? '0' : '1'}
            >
              <stop offset="0%" stopColor={layer.gradient.from} />
              <stop offset="100%" stopColor={layer.gradient.to} />
            </linearGradient>
          </defs>
        )}
        <rect
          x="0" y="0" width={frame.width} height={frame.height}
          fill={layer.gradient ? `url(#${gid})` : layer.fill || '#ffffff'}
        />
      </>
    )
  }

  if (layer.type === LAYER_TYPES.ELLIPSE) {
    return (
      <ellipse
        cx={box.x + box.w / 2} cy={box.y + box.h / 2}
        rx={box.w / 2} ry={box.h / 2}
        fill={layer.fill || '#1f8a5b'}
        stroke={layer.stroke}
        strokeWidth={(layer.strokeWidth ?? 0) * frame.width}
        opacity={opacity}
        transform={transform}
      />
    )
  }

  if (layer.type === LAYER_TYPES.LINE || layer.type === LAYER_TYPES.ARROW) {
    const y = box.y + box.h / 2
    const w = (layer.strokeWidth ?? 0.006) * frame.width
    const head = w * 3.5
    const isArrow = layer.type === LAYER_TYPES.ARROW
    return (
      <g opacity={opacity} transform={transform}>
        <line
          x1={box.x} y1={y}
          x2={isArrow ? box.x + box.w - head : box.x + box.w} y2={y}
          stroke={layer.stroke || '#ffffff'}
          strokeWidth={w}
          strokeLinecap="round"
        />
        {isArrow && (
          <polygon
            points={`${box.x + box.w},${y} ${box.x + box.w - head},${y - head * 0.6} ${box.x + box.w - head},${y + head * 0.6}`}
            fill={layer.stroke || '#ffffff'}
          />
        )}
      </g>
    )
  }

  if (layer.type === LAYER_TYPES.RECT) {
    const gradId = `${idPrefix}-grad-${layer.id}`
    return (
      <>
        {layer.gradient && (
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={layer.gradient.from} />
              <stop offset="100%" stopColor={layer.gradient.to} />
            </linearGradient>
          </defs>
        )}
        <rect
          x={box.x}
          y={box.y}
          width={box.w}
          height={box.h}
          rx={(layer.radius ?? 0) * frame.width}
          fill={layer.gradient ? `url(#${gradId})` : layer.fill}
          opacity={opacity}
          transform={transform}
        />
      </>
    )
  }

  if (layer.type === LAYER_TYPES.IMAGE) {
    return (
      <image
        href={layer.src}
        x={box.x}
        y={box.y}
        width={box.w}
        height={box.h}
        opacity={opacity}
        // Fit inside the box without distorting the logo's own proportions.
        preserveAspectRatio={layer.keepAspect === false ? 'none' : 'xMidYMid meet'}
        crossOrigin="anonymous"
        transform={transform}
      />
    )
  }

  if (layer.type === LAYER_TYPES.TEXT) {
    const align = textAlignFor(layer)
    // `size.h` is the font size as a fraction of frame height.
    const fontSize = (layer.size?.h ?? 0.04) * frame.height
    // Anchor x to the correct edge of the resolved box for the alignment.
    const x = align === 'right' ? box.x + box.w : align === 'center' ? box.x + box.w / 2 : box.x
    return (
      <text
        x={x}
        // Box y is the text's baseline band; shift so the glyphs sit inside it.
        y={box.y + fontSize * 0.82}
        fontSize={fontSize}
        fill={layer.fill || '#ffffff'}
        fontWeight={layer.weight || 600}
        opacity={opacity}
        textAnchor={align === 'right' ? 'end' : align === 'center' ? 'middle' : 'start'}
        fontFamily={layer.fontFamily || 'Inter, system-ui, sans-serif'}
        fontStyle={layer.italic ? 'italic' : undefined}
        transform={transform}
        style={{ letterSpacing: layer.tracking ? `${layer.tracking}em` : undefined }}
      >
        {layer.text}
      </text>
    )
  }

  return null
}

/**
 * @param {Array}  layers      from buildBrandLayers()
 * @param {number} aspect      width / height of the underlying image
 * @param {string} idPrefix    namespaces SVG ids — required when several
 *                             overlays render on one page, since SVG ids are
 *                             document-global and would otherwise collide.
 */
export default function BrandOverlay({ layers = [], aspect = 1, idPrefix = 'bo', className = '' }) {
  if (!layers.length) return null

  const frame = { width: FRAME.width, height: FRAME.width / (aspect || 1) }

  return (
    <svg
      viewBox={`0 0 ${frame.width} ${frame.height}`}
      preserveAspectRatio="none"
      className={`pointer-events-none absolute inset-0 h-full w-full ${className}`}
      aria-hidden="true"
    >
      {sortLayers(layers).map((layer) => (
        <LayerNode key={layer.id} layer={layer} frame={frame} idPrefix={idPrefix} />
      ))}
    </svg>
  )
}
