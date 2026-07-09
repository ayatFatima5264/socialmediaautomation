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
  forgotPassword: (email) =>
    request('/auth/forgot-password', { method: 'POST', body: { email }, auth: false }),
  resetPassword: (token, password) =>
    request('/auth/reset-password', { method: 'POST', body: { token, password }, auth: false }),

  // generation
  meta: () => request('/api/meta', { auth: false }),
  generate: (body) => request('/api/generate-post', { method: 'POST', body }),
  generateImage: (body) => request('/api/generate-image', { method: 'POST', body, auth: false }),
  generateImages: (body) => request('/api/generate-images', { method: 'POST', body, auth: false }),
  // Free stock-photo search (Openverse by default; Pexels/Pixabay/Unsplash if keyed).
  stockImages: (query, perPage = 12) =>
    request(`/api/stock-images?query=${encodeURIComponent(query)}&per_page=${perPage}`, { auth: false }),
  generateArticle: (body) => request('/api/generate-article', { method: 'POST', body }),

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

  // business profile + onboarding
  getBusinessProfile: () => request('/api/business-profile'),
  updateBusinessProfile: (body) =>
    request('/api/business-profile', { method: 'PUT', body }),
  completeOnboarding: () => request('/api/onboarding/complete', { method: 'POST' }),
}
