import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import seo from './plugins/seo.js'

// Dev server proxies API calls to the FastAPI backend on :8000,
// so the frontend can call /api and /auth with no CORS friction.
//
// `seo()` runs on build only: it prerenders per-route meta tags and generates
// robots.txt / sitemap.xml / ads.txt from the app's own route data.
export default defineConfig({
  plugins: [react(), tailwindcss(), seo()],
  build: {
    // Split the vendor libraries out of the app chunk so a content change
    // doesn't invalidate React for returning visitors.
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/auth': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
