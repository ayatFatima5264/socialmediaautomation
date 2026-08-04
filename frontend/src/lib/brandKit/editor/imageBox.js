// ---------------------------------------------------------------------------
// Sizing an image layer
//
// Layer geometry is per-axis fractions: size.w is a share of the frame's WIDTH
// and size.h a share of its HEIGHT. So equal fractions are only a square on a
// square frame, and a box's on-screen ratio is (w / h) * (frameW / frameH).
// Every helper here solves that equation for the shape the picture actually
// is, which is what stops an image letterboxing inside its own holder.
//
// This lives outside the editor components because both of them need the same
// answer: ImageEditor sizes a box when an image arrives, and EditorCanvas has
// to hold that same shape while a corner handle is dragged.
// ---------------------------------------------------------------------------

/** The box h/w that makes a picture of `natural` proportions fill it exactly. */
export const boxRatio = (natural, frame) => {
  const frameAspect = frame.width / frame.height
  const imgAspect = natural.w / natural.h
  return frameAspect > 0 && imgAspect > 0 ? frameAspect / imgAspect : 1
}

/** A fresh box with the picture's proportions, bounded so it lands visible. */
export function boxForImage(natural, frame, max = 0.6) {
  const ratio = boxRatio(natural, frame)
  let w = max
  let h = w * ratio
  if (h > max) {
    h = max
    w = h / ratio
  }
  return { w, h }
}

/**
 * The same shape, keeping the box's existing width so it stays anchored.
 *
 * Bounded like `boxForImage`, and for the same reason: the kept width is the
 * OLD picture's, so a much taller replacement solves to a height past the
 * frame — a box 1.78 frames tall crops away most of the image it was resized
 * to show. When that happens height leads instead and width follows it.
 */
export function refitBox(size, natural, frame, max = 1) {
  const ratio = boxRatio(natural, frame)
  let w = Math.min(size?.w ?? 0.4, max)
  let h = w * ratio
  if (h > max) {
    h = max
    w = h / ratio
  }
  return { w, h }
}

/** The picture's own pixel dimensions, read from the decoded source. */
export function measureImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight })
    img.onerror = () => reject(new Error('Could not read that image.'))
    img.src = src
  })
}
