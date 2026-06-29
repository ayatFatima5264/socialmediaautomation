// Tiny fetch wrapper around the FastAPI backend.
// Calls go to /api and /auth (proxied to :8000 by Vite in dev).

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
    res = await fetch(path, opts)
  } catch {
    throw new ApiError('Network error — is the backend running on :8000?', 0, null)
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

  // generation
  meta: () => request('/api/meta', { auth: false }),
  generate: (body) => request('/api/generate-post', { method: 'POST', body }),
  generateImage: (body) => request('/api/generate-image', { method: 'POST', body, auth: false }),
  generateImages: (body) => request('/api/generate-images', { method: 'POST', body, auth: false }),

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
  instagramProfile: () => request('/instagram/profile', { auth: false }),
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

  // connected social accounts
  listAccounts: () => request('/api/accounts'),
  connectInstagram: (body) =>
    request('/api/accounts/instagram/connect', { method: 'POST', body }),
  disconnectAccount: (platform) =>
    request(`/api/accounts/${platform}`, { method: 'DELETE' }),
}
