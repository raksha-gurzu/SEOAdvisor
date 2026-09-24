import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The FastAPI backend runs on :8420; in production it serves web/dist itself.
export default defineConfig({
  plugins: [react()],
  // Fixed dev port (not Vite's default 5173); strictPort fails loudly instead of drifting.
  server: {
    port: 4280,
    strictPort: true,
    proxy: { '/api': 'http://localhost:8420' },
  },
  preview: { port: 4281, strictPort: true },
})
