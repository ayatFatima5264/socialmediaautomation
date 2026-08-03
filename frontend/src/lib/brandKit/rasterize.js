// ---------------------------------------------------------------------------
// Flatten a base image + brand layers into a single bitmap.
//
// The SVG overlay is what the user sees, but social platforms need one real
// image file — so at publish/download time the same layer list is replayed
// onto a Canvas at full resolution.
//
// Two consumers, one layer list, no second source of truth: if the preview and
// the exported file ever disagree, it is a bug in one of the two renderers
// rather than a difference in what they were told to draw.
//
// CORS: Pollinations serves `Access-Control-Allow-Origin: *`, so loading the
// base image with crossOrigin="anonymous" leaves the canvas untainted and
// toBlob/toDataURL work. A logo supplied as a data: URL is same-origin by
// definition. A logo from a third-party host WITHOUT CORS headers would taint
// the canvas — so that case is caught and reported rather than throwing an
// opaque SecurityError at export time.
// ---------------------------------------------------------------------------

import { resolveLayer, sortLayers, textAlignFor, LAYER_TYPES } from './layers.js'

export class RasterizeError extends Error {}

function loadImage(src, { crossOrigin = true } = {}) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    // Data URLs must not carry crossOrigin — some browsers reject the combo.
    if (crossOrigin && !String(src).startsWith('data:')) img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new RasterizeError(`Could not load image: ${String(src).slice(0, 80)}`))
    img.src = src
  })
}

// Rotate about the layer's centre, matching the SVG transform exactly.
function withRotation(ctx, layer, box, draw) {
  if (!layer.rotation) return draw()
  ctx.save()
  ctx.translate(box.x + box.w / 2, box.y + box.h / 2)
  ctx.rotate((layer.rotation * Math.PI) / 180)
  ctx.translate(-(box.x + box.w / 2), -(box.y + box.h / 2))
  draw()
  ctx.restore()
}

function drawBackground(ctx, layer, frame) {
  ctx.save()
  if (layer.gradient) {
    const g =
      layer.gradient.angle === 90
        ? ctx.createLinearGradient(0, 0, frame.width, 0)
        : ctx.createLinearGradient(0, 0, 0, frame.height)
    g.addColorStop(0, layer.gradient.from)
    g.addColorStop(1, layer.gradient.to)
    ctx.fillStyle = g
  } else {
    ctx.fillStyle = layer.fill || '#ffffff'
  }
  ctx.fillRect(0, 0, frame.width, frame.height)
  ctx.restore()
}

function drawEllipse(ctx, layer, box) {
  ctx.save()
  ctx.globalAlpha = layer.opacity ?? 1
  ctx.beginPath()
  ctx.ellipse(box.x + box.w / 2, box.y + box.h / 2, box.w / 2, box.h / 2, 0, 0, Math.PI * 2)
  ctx.fillStyle = layer.fill || '#1f8a5b'
  ctx.fill()
  if (layer.stroke && layer.strokeWidth) {
    ctx.strokeStyle = layer.stroke
    ctx.lineWidth = layer.strokeWidth * box.w
    ctx.stroke()
  }
  ctx.restore()
}

function drawLine(ctx, layer, box, frame, isArrow) {
  const y = box.y + box.h / 2
  const w = (layer.strokeWidth ?? 0.006) * frame.width
  const head = w * 3.5
  ctx.save()
  ctx.globalAlpha = layer.opacity ?? 1
  ctx.strokeStyle = layer.stroke || '#ffffff'
  ctx.fillStyle = layer.stroke || '#ffffff'
  ctx.lineWidth = w
  ctx.lineCap = 'round'
  ctx.beginPath()
  ctx.moveTo(box.x, y)
  ctx.lineTo(isArrow ? box.x + box.w - head : box.x + box.w, y)
  ctx.stroke()
  if (isArrow) {
    ctx.beginPath()
    ctx.moveTo(box.x + box.w, y)
    ctx.lineTo(box.x + box.w - head, y - head * 0.6)
    ctx.lineTo(box.x + box.w - head, y + head * 0.6)
    ctx.closePath()
    ctx.fill()
  }
  ctx.restore()
}

function drawRect(ctx, layer, box, frame) {
  ctx.save()
  ctx.globalAlpha = layer.opacity ?? 1

  if (layer.gradient) {
    const g = ctx.createLinearGradient(box.x, box.y, box.x, box.y + box.h)
    g.addColorStop(0, layer.gradient.from)
    g.addColorStop(1, layer.gradient.to)
    ctx.fillStyle = g
  } else {
    ctx.fillStyle = layer.fill || '#000000'
  }

  const r = (layer.radius ?? 0) * frame.width
  if (r > 0 && typeof ctx.roundRect === 'function') {
    ctx.beginPath()
    ctx.roundRect(box.x, box.y, box.w, box.h, r)
    ctx.fill()
  } else {
    ctx.fillRect(box.x, box.y, box.w, box.h)
  }
  ctx.restore()
}

function drawText(ctx, layer, box, frame) {
  const align = textAlignFor(layer)
  const fontSize = (layer.size?.h ?? 0.04) * frame.height

  ctx.save()
  ctx.globalAlpha = layer.opacity ?? 1
  ctx.fillStyle = layer.fill || '#ffffff'
  const style = layer.italic ? 'italic ' : ''
  const family = layer.fontFamily || 'Inter, system-ui, sans-serif'
  ctx.font = `${style}${layer.weight || 600} ${fontSize}px ${family}`
  ctx.textAlign = align === 'right' ? 'right' : align === 'center' ? 'center' : 'left'
  ctx.textBaseline = 'alphabetic'

  const x = align === 'right' ? box.x + box.w : align === 'center' ? box.x + box.w / 2 : box.x
  // Same baseline rule as the SVG renderer, so the two agree pixel-for-pixel.
  ctx.fillText(layer.text ?? '', x, box.y + fontSize * 0.82)
  ctx.restore()
}

function drawImageLayer(ctx, layer, box, img) {
  ctx.save()
  ctx.globalAlpha = layer.opacity ?? 1

  if (layer.keepAspect === false) {
    ctx.drawImage(img, box.x, box.y, box.w, box.h)
  } else {
    // Reproduce SVG's preserveAspectRatio="xMidYMid meet": contain + centre.
    const scale = Math.min(box.w / img.naturalWidth, box.h / img.naturalHeight)
    const w = img.naturalWidth * scale
    const h = img.naturalHeight * scale
    ctx.drawImage(img, box.x + (box.w - w) / 2, box.y + (box.h - h) / 2, w, h)
  }
  ctx.restore()
}

/**
 * Compose a branded bitmap.
 *
 * @param {string} baseUrl   the generated image
 * @param {Array}  layers    from buildBrandLayers()
 * @param {object} opts      { width, height, type, quality }
 * @returns {Promise<{dataUrl:string, width:number, height:number}>}
 */
export async function rasterizeBranded(baseUrl, layers = [], opts = {}) {
  if (typeof document === 'undefined') {
    throw new RasterizeError('Rasterizing requires a browser environment.')
  }

  // An editor document carries its own background and image layers, so there
  // is no separate base to draw underneath them.
  const base = baseUrl ? await loadImage(baseUrl) : null

  // Export at the base image's natural size unless told otherwise, so
  // branding never costs resolution.
  const width = opts.width || base?.naturalWidth || 1080
  const height = opts.height || base?.naturalHeight || 1080

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new RasterizeError('Canvas 2D context unavailable.')

  if (base) ctx.drawImage(base, 0, 0, width, height)

  const frame = { width, height }
  const ordered = sortLayers(layers)

  // Preload image layers first — drawing must happen in z-order, which an
  // await inside the loop would not preserve reliably.
  const sources = new Map()
  for (const layer of ordered) {
    if (layer.type === LAYER_TYPES.IMAGE && layer.src && !sources.has(layer.src)) {
      try {
        sources.set(layer.src, await loadImage(layer.src))
      } catch {
        sources.set(layer.src, null) // skip this layer, keep the rest
      }
    }
  }

  for (const layer of ordered) {
    const box = resolveLayer(layer, frame)
    if (layer.type === LAYER_TYPES.BACKGROUND) {
      drawBackground(ctx, layer, frame)
    } else if (layer.type === LAYER_TYPES.RECT) {
      withRotation(ctx, layer, box, () => drawRect(ctx, layer, box, frame))
    } else if (layer.type === LAYER_TYPES.ELLIPSE) {
      withRotation(ctx, layer, box, () => drawEllipse(ctx, layer, box))
    } else if (layer.type === LAYER_TYPES.LINE || layer.type === LAYER_TYPES.ARROW) {
      withRotation(ctx, layer, box, () =>
        drawLine(ctx, layer, box, frame, layer.type === LAYER_TYPES.ARROW),
      )
    } else if (layer.type === LAYER_TYPES.TEXT) {
      withRotation(ctx, layer, box, () => drawText(ctx, layer, box, frame))
    } else if (layer.type === LAYER_TYPES.IMAGE) {
      const img = sources.get(layer.src)
      if (img) withRotation(ctx, layer, box, () => drawImageLayer(ctx, layer, box, img))
    }
  }

  try {
    return {
      dataUrl: canvas.toDataURL(opts.type || 'image/jpeg', opts.quality ?? 0.92),
      width,
      height,
    }
  } catch {
    // Thrown when a layer image came from a host that sends no CORS headers.
    throw new RasterizeError(
      'The logo could not be exported because its host does not allow cross-origin use. ' +
        'Upload the logo file instead of linking to it.',
    )
  }
}

/** Trigger a browser download of the branded image. */
export async function downloadBranded(baseUrl, layers, filename = 'branded.jpg', opts = {}) {
  const { dataUrl } = await rasterizeBranded(baseUrl, layers, opts)
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}
