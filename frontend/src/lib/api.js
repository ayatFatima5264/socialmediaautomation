// Tiny fetch wrapper around the FastAPI backend.
//
// Base URL resolution:
//   • Dev  — VITE_API_URL is unset, so API_BASE is "" and calls hit relative
//     paths like /auth and /api, which the Vite dev server proxies to :8000.
//   • Prod — set VITE_API_URL to the backend's public origin (e.g.
//     https://api.yourdomain.com) at build time; calls become absolute and go
//     straight to the backend. No trailing slash (it's stripped either way).
const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '')

const TOKEN_KEY = 'ss_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message)
    this.status = status
    this.data = data
  }
}

// Normalize FastAPI error bodies (string detail, or 422 validation arrays).
function extractDetail(data, fallback) {
  const d = data?.detail
  if (!d) return fallback
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    // Pydantic prefixes messages raised by a custom validator with
    // "Value error, ". That prefix is meaningful in a server log and noise in
    // front of a sentence written for the person filling in the form.
    return d
      .map((e) => (e.msg || JSON.stringify(e)).replace(/^Value error,\s*/i, ''))
      .join('; ')
  }
  return fallback
}

async function request(path, { method = 'GET', body, form, formData, auth = true, headers = {} } = {}) {
  const opts = { method, headers: { ...headers } }

  if (formData) {
    // Let the browser set the multipart boundary; don't set Content-Type.
    opts.body = formData
  } else if (form) {
    opts.body = new URLSearchParams(form)
    opts.headers['Content-Type'] = 'application/x-www-form-urlencoded'
  } else if (body !== undefined) {
    opts.body = JSON.stringify(body)
    opts.headers['Content-Type'] = 'application/json'
  }

  if (auth) {
    const t = getToken()
    if (t) opts.headers['Authorization'] = `Bearer ${t}`
  }

  let res
  try {
    res = await fetch(`${API_BASE}${path}`, opts)
  } catch {
    throw new ApiError('Network error — could not reach the API server.', 0, null)
  }

  if (res.status === 204) return null

  const data = await res.json().catch(() => null)

  if (!res.ok) {
    if (res.status === 401) setToken(null)
    throw new ApiError(extractDetail(data, res.statusText), res.status, data)
  }
  return data
}

// A request that returns binary rather than JSON.
//
// Separate from `request` because the two differ in every step after the fetch:
// there is no JSON to parse, the error body still IS JSON, and the caller wants
// a Blob. Folding a `raw: true` flag into `request` would make the happy path
// of every other call read around a branch it never takes.
async function requestBlob(path, { method = 'GET', body, headers = {} } = {}) {
  const opts = { method, headers: { ...headers } }

  // A POST that returns a blob still has a JSON request body. Dropping it here
  // sent the thumbnail preview as an empty POST, which the server rejected.
  if (body !== undefined) {
    opts.body = JSON.stringify(body)
    opts.headers['Content-Type'] = 'application/json'
  }

  const token = getToken()
  if (token) opts.headers['Authorization'] = `Bearer ${token}`

  let res
  try {
    res = await fetch(`${API_BASE}${path}`, opts)
  } catch {
    throw new ApiError('Network error — could not reach the API server.', 0, null)
  }

  if (!res.ok) {
    if (res.status === 401) setToken(null)
    // The failure body is still JSON even though the success body is not, so
    // the user gets the server's sentence rather than "500".
    const data = await res.json().catch(() => null)
    throw new ApiError(extractDetail(data, res.statusText), res.status, data)
  }

  return res.blob()
}

// A multipart POST that reports how much of the file has actually gone up.
//
// `fetch` cannot do this — it has no upload-progress event — and for a video
// upload that matters: the difference between "43% uploaded" and a spinner is
// the difference between waiting and wondering whether it has hung. XHR is the
// only API in the browser that reports it, so this one call site uses XHR and
// everything else stays on `fetch`.
//
// `onUploaded` fires when the last byte has been sent, which is the real
// boundary between "uploading" and "the server is working on it" — the two
// phases a caller wants to show separately.
function requestUpload(path, formData, { onProgress, onUploaded } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}${path}`)

    const token = getToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)

    if (onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)))
        }
      }
    }
    if (onUploaded) xhr.upload.onload = () => onUploaded()

    xhr.onload = () => {
      let data = null
      try {
        data = JSON.parse(xhr.responseText)
      } catch {
        data = null
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data)
        return
      }
      if (xhr.status === 401) setToken(null)
      reject(new ApiError(extractDetail(data, xhr.statusText || 'Upload failed.'), xhr.status, data))
    }
    xhr.onerror = () =>
      reject(new ApiError('Network error — could not reach the API server.', 0, null))
    xhr.onabort = () => reject(new ApiError('The upload was cancelled.', 0, null))

    xhr.send(formData)
  })
}

export const api = {
  // auth
  register: (body) => request('/auth/register', { method: 'POST', body, auth: false }),
  login: (email, password) =>
    request('/auth/login', { method: 'POST', form: { username: email, password }, auth: false }),
  me: () => request('/auth/me'),
  updateMe: (body) => request('/auth/me', { method: 'PATCH', body }),
  // Permanently deletes the signed-in account. The backend takes the user from
  // the bearer token — no id is sent — and re-checks the typed confirmation.
  deleteAccount: (confirmation) =>
    request('/auth/me', { method: 'DELETE', body: { confirmation } }),
  forgotPassword: (email) =>
    request('/auth/forgot-password', { method: 'POST', body: { email }, auth: false }),
  resetPassword: (token, password) =>
    request('/auth/reset-password', { method: 'POST', body: { token, password }, auth: false }),

  // generation
  meta: () => request('/api/meta', { auth: false }),
  generate: (body) => request('/api/generate-post', { method: 'POST', body }),
  generateImage: (body) => request('/api/generate-image', { method: 'POST', body, auth: false }),
  // Authenticated when a token exists (the endpoint treats the user as
  // optional): a signed-in user's business profile grounds the image brief in
  // their actual industry, which is what keeps the visual on topic.
  generateImages: (body) => request('/api/generate-images', { method: 'POST', body }),
  // Free stock-photo search (Openverse by default; Pexels/Pixabay/Unsplash if keyed).
  stockImages: (query, perPage = 12) =>
    request(`/api/stock-images?query=${encodeURIComponent(query)}&per_page=${perPage}`, { auth: false }),
  generateArticle: (body) => request('/api/generate-article', { method: 'POST', body }),
  // On-image text sized to a template's slots (Phase 2 template system).
  generateTemplateContent: (body) =>
    request('/api/generate-template-content', { method: 'POST', body }),
  // Natural-language image editing -> structured layer operations.
  imageEdit: (body) => request('/api/image-edit', { method: 'POST', body }),

  // AI text assist (in-place edits for the manual composer)
  assist: (body) => request('/api/assist', { method: 'POST', body, auth: false }),

  // "Create From" content extraction
  extractUrl: (url) => request('/api/extract', { method: 'POST', body: { url }, auth: false }),
  extractFile: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request('/api/extract-file', { method: 'POST', formData: fd, auth: false })
  },

  // instagram (Instagram Login API)
  instagramProfile: () => request('/instagram/profile'),
  publishInstagram: (body) =>
    request('/instagram/publish', { method: 'POST', body }),

  // posts
  listPosts: (status) => request(`/api/posts${status ? `?status=${status}` : ''}`),
  getPost: (id) => request(`/api/posts/${id}`),
  createPost: (body) => request('/api/posts', { method: 'POST', body }),
  updatePost: (id, body) => request(`/api/posts/${id}`, { method: 'PATCH', body }),
  deletePost: (id) => request(`/api/posts/${id}`, { method: 'DELETE' }),
  publishPost: (id) => request(`/api/posts/${id}/publish`, { method: 'POST' }),
  cancelPost: (id) => request(`/api/posts/${id}/cancel`, { method: 'POST' }),

  // connected social accounts (Social Accounts module)
  accountsOverview: () => request('/api/social/accounts'),
  getAccount: (platform) => request(`/api/social/${platform}`),
  connectAccount: (platform) =>
    request(`/api/social/${platform}/connect`, { method: 'POST' }),
  disconnectAccount: (platform) =>
    request(`/api/social/${platform}`, { method: 'DELETE' }),
  refreshAccount: (platform) =>
    request(`/api/social/${platform}/refresh`, { method: 'POST' }),
  // Upload an image and get back a public URL. Needed because platforms fetch
  // the image from a URL themselves — a local file preview can't be published.
  uploadMedia: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request('/api/media', { method: 'POST', formData: fd })
  },

  // Pinterest boards — every Pin must be saved to a board, so the composer and
  // the account card both read this list. Always fetched live, so calling it
  // again is exactly what "refresh boards" does.
  pinterestBoards: () => request('/api/social/pinterest/boards'),
  // Boards don't cross Pinterest environments, so an account with boards in
  // production starts with none in Sandbox — and every Pin needs one.
  createPinterestBoard: (name, privacy = 'PUBLIC') =>
    request('/api/social/pinterest/boards', {
      method: 'POST',
      body: { name, privacy },
    }),
  setPinterestDefaultBoard: (boardId) =>
    request('/api/social/pinterest/default-board', {
      method: 'PUT',
      body: { board_id: boardId },
    }),
  clearPinterestDefaultBoard: () =>
    request('/api/social/pinterest/default-board', { method: 'DELETE' }),
  // Multi-account selection (e.g. choosing one Instagram Business account).
  pendingConnection: (pendingId) =>
    request(`/api/social/connections/pending/${pendingId}`),
  selectAccount: (pendingId, accountId) =>
    request('/api/social/connections/select', {
      method: 'POST',
      body: { pending_id: pendingId, account_id: accountId },
    }),

  // Marketing contact form (public). The endpoint stores the message before it
  // attempts to email anyone, so a 200 means the message is safe even if mail
  // delivery later fails. 429 means the per-IP rate limit was hit.
  contact: (body) => request('/api/contact', { method: 'POST', body, auth: false }),

  // AI Content Planner
  plannerSettings: () => request('/api/planner/settings'),
  updatePlannerSettings: (body) =>
    request('/api/planner/settings', { method: 'PUT', body }),
  createStrategy: (body) =>
    request('/api/planner/strategy', { method: 'POST', body }),
  quickGenerate: () => request('/api/planner/quick-generate', { method: 'POST' }),
  listPlans: () => request('/api/planner'),
  getPlan: (id) => request(`/api/planner/${id}`),
  // Plan-level template / size / image-style defaults, applied to every post
  // that has not overridden them.
  updatePlanImageDefaults: (id, imageDefaults) =>
    request(`/api/planner/${id}/image-defaults`, {
      method: 'PATCH',
      body: { image_defaults: imageDefaults },
    }),
  updatePlanTopics: (id, topics) =>
    request(`/api/planner/${id}/topics`, { method: 'PATCH', body: { topics } }),
  regeneratePlanTopic: (id, topicId) =>
    request(`/api/planner/${id}/topics/regenerate`, {
      method: 'POST',
      body: { topic_id: topicId },
    }),
  generatePlan: (id, withImages = false) =>
    request(`/api/planner/${id}/generate`, { method: 'POST', body: { with_images: !!withImages } }),
  // Generate an AI image for one planner post (optional custom prompt).
  generatePlannerPostImage: (postId, body = {}) =>
    request(`/api/planner/posts/${postId}/image`, { method: 'POST', body }),
  updatePlannerPost: (postId, body) =>
    request(`/api/planner/posts/${postId}`, { method: 'PATCH', body }),
  regeneratePlannerPost: (postId) =>
    request(`/api/planner/posts/${postId}/regenerate`, { method: 'POST' }),
  deletePlannerPost: (postId) =>
    request(`/api/planner/posts/${postId}`, { method: 'DELETE' }),
  approvePlan: (id, body) =>
    request(`/api/planner/${id}/approve`, { method: 'POST', body }),
  deletePlan: (id) => request(`/api/planner/${id}`, { method: 'DELETE' }),

  // ---- AI Ads Studio ------------------------------------------------------
  // Text generation runs on the configured AI provider (groq). `adVideoPlan`
  // returns a shot plan, NOT a rendered video — its `renderable` flag is false
  // until a video provider exists, and callers must respect that.
  adCopy: (body) => request('/api/ads/copy', { method: 'POST', body }),
  adHeadlines: (body) => request('/api/ads/headlines', { method: 'POST', body }),
  adCtas: (body) => request('/api/ads/ctas', { method: 'POST', body }),
  adCreative: (body) => request('/api/ads/creative', { method: 'POST', body }),
  adVideoPlan: (body) => request('/api/ads/video-plan', { method: 'POST', body }),

  // Campaigns are the user's own data — these require a token, unlike the
  // generation endpoints above, which treat the user as optional.
  // Search, filter and sort happen in SQL — the query string carries them
  // rather than the client filtering a full download it would outgrow.
  listCampaigns: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.status) qs.set('status', params.status)
    if (params.q) qs.set('q', params.q)
    if (params.sort) qs.set('sort', params.sort)
    const suffix = qs.toString()
    return request(`/api/ads/campaigns${suffix ? `?${suffix}` : ''}`)
  },
  getCampaign: (id) => request(`/api/ads/campaigns/${id}`),
  createCampaign: (body) => request('/api/ads/campaigns', { method: 'POST', body }),
  updateCampaign: (id, body) =>
    request(`/api/ads/campaigns/${id}`, { method: 'PATCH', body }),
  duplicateCampaign: (id, withAssets = true) =>
    request(`/api/ads/campaigns/${id}/duplicate?with_assets=${withAssets}`, {
      method: 'POST',
    }),
  deleteCampaign: (id) => request(`/api/ads/campaigns/${id}`, { method: 'DELETE' }),

  // The creative library. Every generator saves what it produced against the
  // campaign it was opened from, so `createCampaignAssets` takes a whole set in
  // one request rather than one call per image.
  listCampaignAssets: (id) => request(`/api/ads/campaigns/${id}/assets`),
  createCampaignAssets: (id, body) =>
    request(`/api/ads/campaigns/${id}/assets`, { method: 'POST', body }),
  updateCampaignAsset: (id, assetId, body) =>
    request(`/api/ads/campaigns/${id}/assets/${assetId}`, { method: 'PATCH', body }),
  duplicateCampaignAsset: (id, assetId) =>
    request(`/api/ads/campaigns/${id}/assets/${assetId}/duplicate`, { method: 'POST' }),
  deleteCampaignAsset: (id, assetId) =>
    request(`/api/ads/campaigns/${id}/assets/${assetId}`, { method: 'DELETE' }),
  listRecentAssets: (limit = 12) => request(`/api/ads/assets?limit=${limit}`),

  // ---- Video Studio -------------------------------------------------------
  // What this deployment can actually do — presets, limits, whether storage is
  // persistent, whether ffmpeg is present. The UI reads this rather than
  // assuming, so a tool is never offered on a deployment that cannot run it.
  videoCapabilities: () => request('/api/video/capabilities'),
  // Returns { templates, categories } — one request, so the tab row and the
  // grid cannot be rendered from two different snapshots of the library.
  videoTemplates: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.category) qs.set('category', params.category)
    if (params.platform) qs.set('platform', params.platform)
    if (params.search) qs.set('search', params.search)
    if (params.ownedOnly) qs.set('owned_only', 'true')
    const suffix = qs.toString()
    return request(`/api/video/templates${suffix ? `?${suffix}` : ''}`)
  },
  // One template with its scene skeleton and caption style — what "Preview"
  // shows, because that is what the choice actually turns on.
  videoTemplate: (key) => request(`/api/video/templates/${key}`),
  saveVideoTemplate: (body) =>
    request('/api/video/templates', { method: 'POST', body }),
  deleteVideoTemplate: (key) =>
    request(`/api/video/templates/${key}`, { method: 'DELETE' }),

  // Search, filter and paging happen in SQL — the query string carries them
  // rather than the client filtering a full download it would outgrow.
  listVideoProjects: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.search) qs.set('search', params.search)
    if (params.platform) qs.set('platform', params.platform)
    if (params.status) qs.set('status', params.status)
    if (params.limit) qs.set('limit', params.limit)
    if (params.offset) qs.set('offset', params.offset)
    const suffix = qs.toString()
    return request(`/api/video/projects${suffix ? `?${suffix}` : ''}`)
  },
  getVideoProject: (id) => request(`/api/video/projects/${id}`),
  createVideoProject: (body) =>
    request('/api/video/projects', { method: 'POST', body }),
  // `expected_revision` makes a save a compare-and-set: the server answers 409
  // if the project changed in another tab since this one loaded it. Callers
  // must handle that rather than retrying blindly.
  updateVideoProject: (id, body) =>
    request(`/api/video/projects/${id}`, { method: 'PATCH', body }),
  renameVideoProject: (id, name) =>
    request(`/api/video/projects/${id}/rename`, { method: 'POST', body: { name } }),
  duplicateVideoProject: (id) =>
    request(`/api/video/projects/${id}/duplicate`, { method: 'POST' }),
  deleteVideoProject: (id) =>
    request(`/api/video/projects/${id}`, { method: 'DELETE' }),

  // ---- Voice Studio -------------------------------------------------------
  // Works with no project: nothing here takes a project id except `attach`,
  // which is the explicit "Add to Project" action.
  voiceCatalogue: () => request('/api/video/voice/catalogue'),
  // Speaks the first ~240 characters and stores NOTHING — the audio comes back
  // base64 in the JSON. A preview the user rejects must not leave a file in
  // their library.
  previewVoice: (body) => request('/api/video/voice/preview', { method: 'POST', body }),
  generateVoice: (body) => request('/api/video/voice/generate', { method: 'POST', body }),
  listVoiceTakes: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.projectId) qs.set('project_id', params.projectId)
    if (params.limit) qs.set('limit', params.limit)
    const suffix = qs.toString()
    return request(`/api/video/voice/takes${suffix ? `?${suffix}` : ''}`)
  },
  // Splits a script into the paragraph blocks that can be regenerated one at a
  // time. Server-side so the studio and the backend agree on where a section
  // starts — two implementations of "what is a paragraph" would put takes out
  // of step with the text they came from.
  voiceSegments: (text) =>
    request('/api/video/voice/segments', { method: 'POST', body: { text } }),
  attachVoiceTake: (assetId, projectId) =>
    request(`/api/video/voice/${assetId}/attach?project_id=${projectId}`, {
      method: 'POST',
    }),
  deleteVoiceTake: (assetId) =>
    request(`/api/video/voice/${assetId}`, { method: 'DELETE' }),
  // Returns a Blob, not JSON. The download route needs the bearer token, so a
  // plain <a href> cannot fetch it — the caller turns this into an object URL
  // and clicks it. See `downloadBlob` in lib/video/download.js.
  downloadVoiceTake: (assetId, format = 'mp3') =>
    requestBlob(`/api/video/voice/${assetId}/download?format=${format}`),

  // ---- Subtitle Studio ----------------------------------------------------
  // Independent of projects: only `attachSubtitles` takes a project id.
  //
  // Every edit sends the whole track and gets the whole track back. That is
  // deliberate — a split or a merge renumbers every cue after it, so a per-cue
  // patch API would be describing a track the client no longer has.
  subtitleStyles: () => request('/api/video/subtitles/styles'),
  subtitleFormats: () => request('/api/video/subtitles/formats'),

  transcribeMedia: (file, options = {}) => {
    const fd = new FormData()
    fd.append('file', file)
    if (options.language) fd.append('language', options.language)
    if (options.translateToEnglish) fd.append('translate_to_english', 'true')
    if (options.styleKey) fd.append('style_key', options.styleKey)
    if (options.storeSource === false) fd.append('store_source', 'false')
    // Uploaded over XHR rather than fetch so the studio can show real upload
    // progress on what may be a 200 MB video, and can tell "uploading" apart
    // from "transcribing".
    return requestUpload('/api/video/subtitles/transcribe', fd, {
      onProgress: options.onProgress,
      onUploaded: options.onUploaded,
    })
  },
  subtitlesFromScript: (body) =>
    request('/api/video/subtitles/from-script', { method: 'POST', body }),

  // A document is two inputs in one. On its own the `cues` are the answer;
  // alongside a recording the `text` is, and it goes to `alignSubtitles`.
  subtitlesFromDocument: (file, options = {}) => {
    const fd = new FormData()
    fd.append('file', file)
    if (options.durationSeconds) fd.append('duration_seconds', String(options.durationSeconds))
    if (options.wordsPerMinute) fd.append('words_per_minute', String(options.wordsPerMinute))
    if (options.styleKey) fd.append('style_key', options.styleKey)
    return request('/api/video/subtitles/from-document', { method: 'POST', formData: fd })
  },

  // Correct a timed track against the script it was read from. Timing is never
  // touched; only wording the two already agree on is taken from the script.
  alignSubtitles: (cues, script, styleKey) =>
    request('/api/video/subtitles/align', {
      method: 'POST',
      body: { cues, script, style_key: styleKey || null },
    }),
  importSubtitleFile: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request('/api/video/subtitles/import', { method: 'POST', formData: fd })
  },

  normalizeCues: (cues) =>
    request('/api/video/subtitles/normalize', { method: 'POST', body: { cues } }),
  updateCue: (cues, index, patch) =>
    request('/api/video/subtitles/edit/update', { method: 'POST', body: { cues, index, ...patch } }),
  insertCue: (cues, body = {}) =>
    request('/api/video/subtitles/edit/insert', { method: 'POST', body: { cues, ...body } }),
  deleteCue: (cues, index) =>
    request('/api/video/subtitles/edit/delete', { method: 'POST', body: { cues, index } }),
  splitCue: (cues, index, at = {}) =>
    request('/api/video/subtitles/edit/split', { method: 'POST', body: { cues, index, ...at } }),
  mergeCues: (cues, indices) =>
    request('/api/video/subtitles/edit/merge', { method: 'POST', body: { cues, indices } }),
  shiftCues: (cues, offsetSeconds) =>
    request('/api/video/subtitles/edit/shift', {
      method: 'POST',
      body: { cues, offset_seconds: offsetSeconds },
    }),
  searchReplaceCues: (cues, body) =>
    request('/api/video/subtitles/edit/search-replace', { method: 'POST', body: { cues, ...body } }),

  exportSubtitles: (body) =>
    request('/api/video/subtitles/export', { method: 'POST', body }),
  listSubtitleFiles: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.projectId) qs.set('project_id', params.projectId)
    const suffix = qs.toString()
    return request(`/api/video/subtitles/files${suffix ? `?${suffix}` : ''}`)
  },
  // Returns a Blob — the download route needs the bearer token, so a plain
  // <a href> cannot fetch it.
  downloadSubtitleFile: (assetId, format = 'srt') =>
    requestBlob(`/api/video/subtitles/files/${assetId}/download?format=${format}`),
  deleteSubtitleFile: (assetId) =>
    request(`/api/video/subtitles/files/${assetId}`, { method: 'DELETE' }),

  attachSubtitles: (body) =>
    request('/api/video/subtitles/attach', { method: 'POST', body }),
  listSubtitleTracks: (projectId) =>
    request(`/api/video/subtitles/tracks?project_id=${projectId}`),

  listVideoAssets: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.kind) qs.set('kind', params.kind)
    if (params.projectId) qs.set('project_id', params.projectId)
    if (params.limit) qs.set('limit', params.limit)
    const suffix = qs.toString()
    return request(`/api/video/assets${suffix ? `?${suffix}` : ''}`)
  },
  deleteVideoAsset: (id) =>
    request(`/api/video/assets/${id}`, { method: 'DELETE' }),

  // ---- Export, formats and publishing -------------------------------------
  // The manifest is cheap metadata — it says what is downloadable and, when
  // something is not, the next action to take. Files are only produced when
  // one is actually asked for.
  exportManifest: (projectId) =>
    request(`/api/video/projects/${projectId}/exports`),
  downloadExport: (projectId, kind) =>
    requestBlob(`/api/video/projects/${projectId}/exports/${kind}`),

  // Converting creates a new project; the original is never modified.
  projectFormats: (projectId) =>
    request(`/api/video/projects/${projectId}/formats`),
  convertProject: (projectId, body) =>
    request(`/api/video/projects/${projectId}/convert`, { method: 'POST', body }),

  // Publishing *prepares* — it creates a draft post and returns where to
  // review it. Nothing here reaches a platform.
  publishTargets: (projectId) =>
    request(`/api/video/projects/${projectId}/publish/targets`),
  prepareVideoPost: (projectId, body) =>
    request(`/api/video/projects/${projectId}/publish`, { method: 'POST', body }),

  // ---- Thumbnail Studio ---------------------------------------------------
  // `previewThumbnail` and `downloadThumbnail` hit the same renderer on the
  // server, so what is on screen is the file. Preview returns a Blob and
  // stores nothing.
  thumbnailOptions: () => request('/api/video/thumbnails/options'),
  thumbnailDesign: (body) =>
    request('/api/video/thumbnails/design', { method: 'POST', body }),
  // Generates a picture and stores it as a real asset, then returns it — the
  // studio sets it as the background, which keeps every other control the user
  // has already set.
  generateThumbnailBackground: (prompt, format = 'youtube') =>
    request('/api/video/thumbnails/background', {
      method: 'POST',
      body: { prompt, format },
    }),
  thumbnailVariations: (design, count = 4) =>
    request('/api/video/thumbnails/variations', {
      method: 'POST',
      body: { design, count },
    }),
  previewThumbnail: (design, { scale = 1, format = 'png' } = {}) =>
    requestBlob('/api/video/thumbnails/preview', {
      method: 'POST',
      body: { design, scale, format },
    }),
  saveThumbnail: (body) =>
    request('/api/video/thumbnails', { method: 'POST', body }),
  listThumbnails: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.projectId) qs.set('project_id', params.projectId)
    const suffix = qs.toString()
    return request(`/api/video/thumbnails${suffix ? `?${suffix}` : ''}`)
  },
  attachThumbnail: (id, projectId) =>
    request(`/api/video/thumbnails/${id}/attach?project_id=${projectId}`, {
      method: 'POST',
    }),
  downloadThumbnail: (id, format = 'png') =>
    requestBlob(`/api/video/thumbnails/${id}/download?format=${format}`),
  deleteThumbnail: (id) =>
    request(`/api/video/thumbnails/${id}`, { method: 'DELETE' }),

  // ---- Smart Repurpose ----------------------------------------------------
  // Three steps, and the middle one is a human: analyse proposes, the user
  // edits, and only then does `createShorts` make projects. Nothing here
  // renders and nothing here publishes.
  repurposeTargets: () => request('/api/video/repurpose/targets'),
  analyzeForRepurpose: (assetId, body = {}) =>
    request('/api/video/repurpose/analyze', {
      method: 'POST',
      body: { asset_id: assetId, ...body },
    }),
  createShorts: (body) =>
    request('/api/video/repurpose/shorts', { method: 'POST', body }),

  // ---- AI video creation --------------------------------------------------
  // The pipeline is one call per stage, and the expensive stages are one call
  // per *scene*. That is not chattiness for its own sake: generating eight
  // images inside one request is a request that times out, and "5 of 8
  // visuals" is a truthful progress report where a spinner is not.
  aiVideoOptions: () => request('/api/video/ai/options'),
  // A script with no project attached, so the user can read it before
  // committing to anything.
  writeVideoScript: (brief) =>
    request('/api/video/ai/script', { method: 'POST', body: brief }),
  // Creates the real project, its script and its storyboard. Stops there.
  createAIVideoProject: (brief) =>
    request('/api/video/ai/projects', { method: 'POST', body: brief }),

  getVideoScript: (projectId) => request(`/api/video/projects/${projectId}/script`),
  saveVideoScript: (projectId, script, expectedRevision) =>
    request(`/api/video/projects/${projectId}/script`, {
      method: 'PUT',
      body: { script, expected_revision: expectedRevision ?? null },
    }),
  regenerateVideoScript: (projectId, brief) =>
    request(`/api/video/projects/${projectId}/script/regenerate`, {
      method: 'POST',
      body: brief ?? null,
    }),
  // Rewrites one part of a script and returns the whole updated document.
  // Projectless, like writeVideoScript: whether the result gets saved onto a
  // project is the caller's business, so Script Studio and the AI flow share it.
  rewriteScriptSection: (script, section, pointId = '', brief = null) =>
    request('/api/video/ai/script/section', {
      method: 'POST',
      body: { script, section, point_id: pointId || '', brief },
    }),

  getStoryboard: (projectId) => request(`/api/video/projects/${projectId}/scenes`),
  generateScenes: (projectId, body = {}) =>
    request(`/api/video/projects/${projectId}/scenes/generate`, { method: 'POST', body }),
  updateScene: (projectId, sceneId, patch) =>
    request(`/api/video/projects/${projectId}/scenes/${sceneId}`, {
      method: 'PATCH',
      body: patch,
    }),
  reorderScenes: (projectId, sceneIds) =>
    request(`/api/video/projects/${projectId}/scenes/reorder`, {
      method: 'POST',
      body: { scene_ids: sceneIds },
    }),
  deleteScene: (projectId, sceneId) =>
    request(`/api/video/projects/${projectId}/scenes/${sceneId}`, { method: 'DELETE' }),

  generateSceneVisual: (projectId, sceneId, body = {}) =>
    request(`/api/video/projects/${projectId}/scenes/${sceneId}/visual`, {
      method: 'POST',
      body,
    }),
  generateSceneVoice: (projectId, sceneId, body = {}) =>
    request(`/api/video/projects/${projectId}/scenes/${sceneId}/voice`, {
      method: 'POST',
      body,
    }),
  buildAISubtitles: (projectId, body = {}) =>
    request(`/api/video/projects/${projectId}/ai/subtitles`, { method: 'POST', body }),
  // The last step: scenes become the project's timeline, and the editor opens
  // it like any other.
  buildAITimeline: (projectId, body = {}) =>
    request(`/api/video/projects/${projectId}/ai/build`, { method: 'POST', body }),

  // ---- Timeline editor ----------------------------------------------------
  // The editor sends *operations*, not results. `timelineOp` posts one edit
  // and gets the whole new document back, so there is one implementation of
  // the trim/split/overlap rules and it is the one the renderer reads. A
  // client that computed its own result would be a second rule engine, and the
  // two would disagree the first time either changed.
  getTimeline: (projectId) => request(`/api/video/projects/${projectId}/timeline`),
  // Full replacement — autosave, undo and redo. Undo is a document swap rather
  // than an inverse operation: a stack of documents cannot drift.
  saveTimeline: (projectId, body) =>
    request(`/api/video/projects/${projectId}/timeline`, { method: 'PUT', body }),
  timelineOp: (projectId, body) =>
    request(`/api/video/projects/${projectId}/timeline/op`, { method: 'POST', body }),

  // ---- Rendering ----------------------------------------------------------
  // 202 and a job id; everything after that is polling `getRender`.
  startRender: (projectId, body = {}) =>
    request(`/api/video/projects/${projectId}/render`, { method: 'POST', body }),
  listRenders: (projectId) => request(`/api/video/projects/${projectId}/renders`),
  getRender: (renderId) => request(`/api/video/renders/${renderId}`),
  cancelRender: (renderId) =>
    request(`/api/video/renders/${renderId}/cancel`, { method: 'POST' }),
  // A new attempt, not a reopened one — it snapshots the timeline as it is
  // now, which is what makes "fix the missing clip, then retry" work.
  retryRender: (renderId) =>
    request(`/api/video/renders/${renderId}/retry`, { method: 'POST' }),
  downloadRender: (renderId) =>
    requestBlob(`/api/video/renders/${renderId}/download`),

  // ---- Media Library ------------------------------------------------------
  // The library screen and every picker dialog go through these. `filter` is a
  // tab key ("images", "videos"), not a storage kind — the mapping is the
  // server's, so regrouping the tabs does not need a frontend release.
  mediaLibrary: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.filter && params.filter !== 'all') qs.set('filter', params.filter)
    if (params.search) qs.set('search', params.search)
    if (params.projectId) qs.set('project_id', params.projectId)
    if (params.unassigned) qs.set('unassigned', 'true')
    if (params.sort) qs.set('sort', params.sort)
    if (params.limit) qs.set('limit', params.limit)
    if (params.offset) qs.set('offset', params.offset)
    const suffix = qs.toString()
    return request(`/api/video/media${suffix ? `?${suffix}` : ''}`)
  },
  // Multipart, so `formData` — the browser sets the boundary itself.
  // De-duplicated server-side: the same file twice returns the first row.
  //
  // Named apart from the composer's `uploadMedia` deliberately: that one puts
  // an image in `media_assets` so a platform can fetch it by URL, this one
  // puts a file in Video Studio's object storage. They are different stores
  // for different jobs, and a shared name here silently sends one feature's
  // uploads to the other's endpoint.
  uploadVideoMedia: (file, { kind = 'upload', title, projectId } = {}) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('kind', kind)
    if (title) fd.append('title', title)
    if (projectId) fd.append('project_id', projectId)
    return request('/api/video/media/upload', { method: 'POST', formData: fd })
  },
  renameMedia: (id, title) =>
    request(`/api/video/media/${id}`, { method: 'PATCH', body: { title } }),
  attachMedia: (id, projectId) =>
    request(`/api/video/media/${id}/attach?project_id=${projectId}`, { method: 'POST' }),
  detachMedia: (id) =>
    request(`/api/video/media/${id}/detach`, { method: 'POST' }),
  // `force` is the user having seen the list of what uses this file and said
  // yes anyway. Without it the server answers 409 and names them.
  deleteMedia: (id, { force = false } = {}) =>
    request(`/api/video/media/${id}${force ? '?force=true' : ''}`, { method: 'DELETE' }),

  listComposerUploads: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.search) qs.set('search', params.search)
    if (params.limit) qs.set('limit', params.limit)
    if (params.offset) qs.set('offset', params.offset)
    const suffix = qs.toString()
    return request(`/api/video/media/uploads${suffix ? `?${suffix}` : ''}`)
  },
  importComposerUpload: (mediaId, projectId) =>
    request('/api/video/media/uploads/import', {
      method: 'POST',
      body: { media_id: mediaId, project_id: projectId ?? null },
    }),

  // ---- Music Library ------------------------------------------------------
  musicLibrary: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.search) qs.set('search', params.search)
    if (params.mood) qs.set('mood', params.mood)
    if (params.genre) qs.set('genre', params.genre)
    if (params.duration) qs.set('duration', params.duration)
    if (params.source) qs.set('source', params.source)
    if (params.limit) qs.set('limit', params.limit)
    if (params.offset) qs.set('offset', params.offset)
    const suffix = qs.toString()
    return request(`/api/video/music${suffix ? `?${suffix}` : ''}`)
  },
  musicFacets: () => request('/api/video/music/facets'),
  uploadMusic: (file, fields = {}) => {
    const fd = new FormData()
    fd.append('file', file)
    // Always sent, never defaulted: the server refuses an upload without it,
    // and a client that quietly supplied `true` would make the statement
    // meaningless. See TrackUpload in app/schemas/video_music.py.
    fd.append('confirmed_rights', fields.confirmedRights ? 'true' : 'false')
    for (const [key, value] of [
      ['title', fields.title],
      ['artist', fields.artist],
      ['mood', fields.mood],
      ['genre', fields.genre],
      ['source_url', fields.sourceUrl],
      ['attribution', fields.attribution],
    ]) {
      if (value) fd.append(key, value)
    }
    return request('/api/video/music/upload', { method: 'POST', formData: fd })
  },
  // 403 when the track's licence does not allow commercial use — the rule is
  // the server's, and the UI reports what it says rather than deciding.
  addMusicToProject: (trackId, body) =>
    request(`/api/video/music/${trackId}/add`, { method: 'POST', body }),
  deleteMusicTrack: (id) =>
    request(`/api/video/music/${id}`, { method: 'DELETE' }),
  projectMusicCredits: (projectId) =>
    request(`/api/video/music/credits/${projectId}`),

  // business profile + onboarding
  getBusinessProfile: () => request('/api/business-profile'),
  updateBusinessProfile: (body) =>
    request('/api/business-profile', { method: 'PUT', body }),
  completeOnboarding: () => request('/api/onboarding/complete', { method: 'POST' }),
}
