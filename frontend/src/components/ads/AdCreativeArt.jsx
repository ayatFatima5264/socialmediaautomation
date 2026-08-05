// ---------------------------------------------------------------------------
// Ad-creative artwork.
//
// These are not diagrams of what a tool does — they are stand-ins for the thing
// it produces. A card for Product Ads should show something that looks like a
// product ad, so the grid reads as a portfolio rather than an icon set.
//
// Drawn in SVG rather than shipped as images: nothing to load, crisp at any
// size, no licensing, and each scene re-colours from one palette. When real
// generated creatives exist, these become the placeholder behind them.
//
// The palette is warm neutral — cream, sand, sage — because that is what
// product photography looks like, and a card is meant to read as a photo. The
// app's own tokens (--line, --surface) still draw the UI chrome INSIDE a scene:
// the mock browser frames, the button pills, the slide dividers. That keeps the
// artwork feeling like this app rather than stock clipart.
// ---------------------------------------------------------------------------

const SURFACE = 'var(--surface)'

// The scenes' own backdrop tone. Applied to the box behind a `meet` render so
// the bands letterboxing leaves read as part of the picture rather than as a
// gap — which is what lets a caller use `meet` in a square or portrait tile
// without it looking broken.
export const ART_BACKDROP = '#F3EDE3'

// One shared ground so every scene sits in the same room.
function Backdrop({ id, from = '#F3EDE3', to = '#E4E9DF' }) {
  return (
    <>
      <defs>
        <linearGradient id={`${id}-bg`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={from} />
          <stop offset="100%" stopColor={to} />
        </linearGradient>
        <linearGradient id={`${id}-glass`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#5F7A63" />
          <stop offset="55%" stopColor="#41613F" />
          <stop offset="100%" stopColor="#2F4A32" />
        </linearGradient>
      </defs>
      <rect width="200" height="120" fill={`url(#${id}-bg)`} />
    </>
  )
}

// The product itself — an amber-glass dropper bottle, the most photographed
// object in advertising. Scaled and positioned by the caller.
function Bottle({ id, x, y, scale = 1, shadow = true }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`}>
      {shadow && <ellipse cx="0" cy="34" rx="17" ry="4" fill="#000" opacity="0.13" />}
      <rect x="-11" y="-14" width="22" height="48" rx="5" fill={`url(#${id}-glass)`} />
      <rect x="-7" y="-9" width="5" height="30" rx="2.5" fill="#fff" opacity="0.22" />
      <rect x="-5.5" y="-22" width="11" height="9" rx="2" fill="#2B3E2C" />
      <rect x="-3" y="-28" width="6" height="7" rx="1.5" fill="#3C523B" />
      <rect x="-8" y="4" width="16" height="13" rx="2" fill="#F6F1E7" opacity="0.92" />
      <rect x="-5" y="8" width="10" height="1.6" rx="0.8" fill="#6E7B66" />
      <rect x="-5" y="12" width="7" height="1.4" rx="0.7" fill="#9AA394" />
    </g>
  )
}

// A stone podium — the other half of the product-photography grammar.
function Podium({ cx, cy, rx = 30 }) {
  return (
    <>
      <ellipse cx={cx} cy={cy} rx={rx} ry={rx * 0.26} fill="#D9D2C4" />
      <ellipse cx={cx} cy={cy - 3} rx={rx} ry={rx * 0.26} fill="#EFE9DC" />
    </>
  )
}

function Leaves({ x, y, scale = 1, flip = false }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${flip ? -scale : scale} ${scale})`} opacity="0.85">
      <path d="M0 0c9-3 17-11 19-21C10-19 2-11 0 0z" fill="#6C8B63" />
      <path d="M2 6c10 1 20-3 25-11-9-4-20-1-25 11z" fill="#84A277" />
    </g>
  )
}

// A call-to-action pill, drawn the way the real ad would carry it.
function Pill({ x, y, w = 40, h = 13, label, dark = false }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={h / 2} fill={dark ? '#2F4A32' : SURFACE} />
      <text
        x={x + w / 2}
        y={y + h / 2 + 2.6}
        textAnchor="middle"
        fontSize="6"
        fontWeight="700"
        letterSpacing="0.4"
        fill={dark ? '#F6F1E7' : '#2F4A32'}
      >
        {label}
      </text>
    </g>
  )
}

// A play control, for anything that renders to video.
function Play({ cx, cy, r = 14 }) {
  return (
    <g>
      <circle cx={cx} cy={cy} r={r} fill="#fff" opacity="0.94" />
      <path
        d={`M${cx - r * 0.28} ${cy - r * 0.4}l${r * 0.72} ${r * 0.4}l${-r * 0.72} ${r * 0.4}z`}
        fill="#2F4A32"
      />
    </g>
  )
}

// ---------------------------------------------------------------------------
// Scenes
// ---------------------------------------------------------------------------

const SCENES = {
  // The hero image: a finished skincare ad.
  heroAd: (id) => (
    <>
      <Backdrop id={id} />
      <circle cx="132" cy="52" r="40" fill="#fff" opacity="0.4" />
      <Leaves x={40} y={104} scale={0.9} />
      <Leaves x={186} y={40} scale={1.05} flip />
      <Podium cx={132} cy={92} rx={34} />
      <Bottle id={id} x={132} y={54} scale={1.15} />
      <text x="20" y="42" fontSize="13" fontWeight="800" letterSpacing="0.6" fill="#2F4A32">
        NATURAL
      </text>
      <text x="20" y="58" fontSize="13" fontWeight="800" letterSpacing="0.6" fill="#2F4A32">
        SKINCARE
      </text>
      <text x="20" y="72" fontSize="7" fill="#5B6B55">
        For a Radiant You
      </text>
      <Pill x={20} y={80} w={46} h={14} label="SHOP NOW" dark />
    </>
  ),

  // Product Ads — one product, fully composed.
  productAd: (id) => (
    <>
      <Backdrop id={id} />
      <circle cx="118" cy="50" r="36" fill="#fff" opacity="0.42" />
      <Leaves x={176} y={38} scale={0.85} flip />
      <Podium cx={118} cy={88} rx={30} />
      <Bottle id={id} x={118} y={52} />
      <text x="18" y="46" fontSize="10" fontWeight="800" letterSpacing="0.5" fill="#2F4A32">
        PURE GLOW
      </text>
      <text x="18" y="60" fontSize="6.5" fill="#5B6B55">
        Clinically proven
      </text>
      <Pill x={18} y={68} w={38} h={12} label="SHOP" dark />
    </>
  ),

  // Banner Generator — a wide sale banner.
  bannerAd: (id) => (
    <>
      <Backdrop id={id} from="#EFE4D2" to="#E2DAC6" />
      <Leaves x={30} y={112} scale={0.75} />
      <Podium cx={150} cy={92} rx={26} />
      <Bottle id={id} x={150} y={58} scale={0.86} />
      <text x="16" y="44" fontSize="15" fontWeight="900" letterSpacing="0.5" fill="#B4762E">
        SUMMER
      </text>
      <text x="16" y="60" fontSize="15" fontWeight="900" letterSpacing="0.5" fill="#B4762E">
        SALE
      </text>
      <text x="16" y="74" fontSize="8" fontWeight="700" fill="#2F4A32">
        UP TO 50% OFF
      </text>
      <Pill x={16} y={82} w={40} h={12} label="SHOP NOW" />
    </>
  ),

  // Carousel Ads — a sequence of slides.
  carouselAd: (id) => (
    <>
      <Backdrop id={id} from="#EDE6DA" to="#DFE5DA" />
      <g>
        <rect x="8" y="16" width="52" height="88" rx="6" fill="#F7F2E9" />
        <Podium cx={34} cy={82} rx={17} />
        <Bottle id={id} x={34} y={58} scale={0.62} shadow={false} />
        <rect x="18" y="26" width="32" height="4" rx="2" fill="#B9C0B2" />
      </g>
      <g>
        <rect x="66" y="10" width="60" height="100" rx="7" fill="#FFFFFF" />
        <circle cx="96" cy="52" r="24" fill="#EFE9DC" />
        <Bottle id={id} x={96} y={50} scale={0.78} />
        <text x="96" y="26" textAnchor="middle" fontSize="7.5" fontWeight="800" fill="#2F4A32">
          NOURISH
        </text>
        <Pill x={78} y={90} w={36} h={11} label="SHOP" dark />
      </g>
      <g opacity="0.9">
        <rect x="132" y="16" width="52" height="88" rx="6" fill="#F7F2E9" />
        <Podium cx={158} cy={82} rx={17} />
        <Bottle id={id} x={158} y={58} scale={0.62} shadow={false} />
        <rect x="142" y="26" width="32" height="4" rx="2" fill="#B9C0B2" />
      </g>
    </>
  ),

  // Image to Video — a still, now playing.
  imageVideo: (id) => (
    <>
      <Backdrop id={id} />
      <circle cx="100" cy="50" r="38" fill="#fff" opacity="0.4" />
      <Leaves x={34} y={106} scale={0.8} />
      <Podium cx={100} cy={88} rx={30} />
      <Bottle id={id} x={100} y={52} />
      <Play cx={100} cy={58} r={15} />
      <rect x="14" y="104" width="172" height="4" rx="2" fill="#fff" opacity="0.55" />
      <rect x="14" y="104" width="72" height="4" rx="2" fill="#2F4A32" opacity="0.75" />
    </>
  ),

  // Text to Video — a prompt becoming a shot.
  textVideo: (id) => (
    <>
      <Backdrop id={id} from="#E9E7F0" to="#DFE5DA" />
      <g>
        <rect x="12" y="26" width="70" height="52" rx="7" fill={SURFACE} />
        <rect x="20" y="36" width="52" height="4" rx="2" fill="#C3C7CE" />
        <rect x="20" y="45" width="46" height="4" rx="2" fill="#C3C7CE" />
        <rect x="20" y="54" width="54" height="4" rx="2" fill="#C3C7CE" />
        <rect x="20" y="63" width="30" height="4" rx="2" fill="#C3C7CE" />
        <path
          d="M74 62l1.7 4 4.3.4-3.3 2.9 1 4.2-3.7-2.2-3.7 2.2 1-4.2-3.3-2.9 4.3-.4z"
          fill="#7C6BD4"
        />
      </g>
      <path d="M88 52h12M96 47l5 5-5 5" stroke="#8A9186" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <g>
        <rect x="108" y="20" width="80" height="64" rx="7" fill="#EFE9DC" />
        <Podium cx={148} cy={70} rx={22} />
        <Bottle id={id} x={148} y={44} scale={0.72} />
        <Play cx={148} cy={52} r={12} />
      </g>
      <rect x="108" y="90" width="80" height="4" rx="2" fill="#fff" opacity="0.7" />
      <rect x="108" y="90" width="34" height="4" rx="2" fill="#7C6BD4" opacity="0.8" />
    </>
  ),

  // Product Showcase — the product turned through a shot.
  showcase: (id) => (
    <>
      <Backdrop id={id} from="#E6EEE9" to="#DCE6DE" />
      <path
        d="M46 74a54 34 0 0 1 108 0"
        stroke="#9FB4A3"
        strokeWidth="1.6"
        fill="none"
        strokeDasharray="4 4"
      />
      <Bottle id={id} x={60} y={62} scale={0.6} shadow={false} />
      <Bottle id={id} x={140} y={62} scale={0.6} shadow={false} />
      <Podium cx={100} cy={92} rx={30} />
      <Bottle id={id} x={100} y={54} scale={1.02} />
      <Play cx={100} cy={58} r={13} />
    </>
  ),

  // AI Ad Copy — the words, laid out as they will run.
  adCopy: (id) => (
    <>
      <Backdrop id={id} from="#F4EDE6" to="#EBE3DA" />
      <rect x="14" y="16" width="172" height="88" rx="8" fill={SURFACE} />
      <rect x="26" y="28" width="86" height="7" rx="3.5" fill="#2F4A32" />
      <rect x="26" y="42" width="120" height="4.5" rx="2.25" fill="#CFD5CB" />
      <rect x="26" y="52" width="104" height="4.5" rx="2.25" fill="#CFD5CB" />
      <rect x="26" y="62" width="116" height="4.5" rx="2.25" fill="#CFD5CB" />
      <Pill x={26} y={76} w={44} h={14} label="SHOP NOW" dark />
      <g opacity="0.55">
        <rect x="80" y="76" width="38" height="14" rx="7" fill="#EFE9DC" />
        <rect x="126" y="76" width="38" height="14" rx="7" fill="#EFE9DC" />
      </g>
      <path
        d="M162 30l2 4.6 5 .5-3.8 3.3 1.1 4.9-4.3-2.6-4.3 2.6 1.1-4.9-3.8-3.3 5-.5z"
        fill="#C98A3E"
      />
    </>
  ),
}

/**
 * A creative scene.
 *
 * `name` selects the scene; an unknown name draws the backdrop alone rather
 * than throwing, so a registry entry can reference art before it is drawn.
 *
 * Gradient ids are namespaced per instance: SVG ids are document-global, so
 * several cards on one page would otherwise share — and cross-wire — each
 * other's fills.
 */
export default function AdCreativeArt({ name, className = '', fit = 'slice' }) {
  const id = `art-${name}`
  const scene = SCENES[name]

  return (
    <div
      className={`overflow-hidden ${className}`}
      // Only under `meet`: `slice` fills the box, so a background would never
      // be seen and setting one would just override the caller's.
      style={fit === 'meet' ? { background: ART_BACKDROP } : undefined}
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 200 120"
        // `slice` fills the box and crops, which is right for the wide card
        // thumbnails. It is wrong for a portrait frame: the scene is 5:3, so
        // filling a 9:16 box scales it 3.5× and you get one enormous bottle.
        // `meet` fits the whole composition instead — the caller gives the box
        // a matching background so the letterbox does not read as a gap.
        preserveAspectRatio={`xMidYMid ${fit}`}
        className="h-full w-full"
        role="presentation"
      >
        {scene ? scene(id) : <Backdrop id={id} />}
      </svg>
    </div>
  )
}
