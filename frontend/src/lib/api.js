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
    return d.map((e) => e.msg || JSON.stringify(e)).join('; ')
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

export const api = {
  // auth
  register: (body) => request('/auth/register', { method: 'POST', body, auth: false }),
  login: (email, password) =>
    request('/auth/login', { method: 'POST', form: { username: email, password }, auth: false }),
  me: () => request('/auth/me'),
  updateMe: (body) => request('/auth/me', { method: 'PATCH', body }),
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

  // marketing contact form (public). Backend endpoint POST /api/contact is
  // not implemented yet — gated behind VITE_CONTACT_API in the Contact page.
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

  // business profile + onboarding
  getBusinessProfile: () => request('/api/business-profile'),
  updateBusinessProfile: (body) =>
    request('/api/business-profile', { method: 'PUT', body }),
  completeOnboarding: () => request('/api/onboarding/complete', { method: 'POST' }),
}
