// ---------------------------------------------------------------------------
// slug -> the page that implements it.
//
// The ONLY place routing decides whether a tool exists. `VideoToolRoute` looks
// a slug up here; a hit renders the workspace, a miss renders the placeholder
// generated from the registry entry. So shipping a tool is one line in this
// map — App.jsx never grows, and routing cannot disagree with what is built.
//
// Everything with a real page is listed here. The music library is the one
// tool still absent, and deliberately: adding a stub would make the
// placeholder stop rendering and put a blank page in its place.
// ---------------------------------------------------------------------------
import EditorPicker from '../EditorPicker.jsx'
import MediaLibrary from '../MediaLibrary.jsx'
import ScriptStudio from '../ScriptStudio.jsx'
import Repurpose from '../Repurpose.jsx'
import ThumbnailStudio from '../ThumbnailStudio.jsx'
import SubtitleStudio from '../SubtitleStudio.jsx'
import Templates from '../Templates.jsx'
import VoiceStudio from '../VoiceStudio.jsx'

const TOOL_PAGES = {
  // The editor edits a project, so its real route is
  // /video/projects/:id/edit. This entry is the "which project?" step for
  // somebody arriving from the Overview with nothing open.
  editor: EditorPicker,
  media: MediaLibrary,
  script: ScriptStudio,
  repurpose: Repurpose,
  templates: Templates,
  thumbnails: ThumbnailStudio,
  voice: VoiceStudio,
  subtitles: SubtitleStudio,
}

export function getToolPage(slug) {
  return TOOL_PAGES[slug] || null
}
