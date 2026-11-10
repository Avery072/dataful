import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// API target defaults to the FastAPI backend on :8000; override with DATAFUL_API=http://localhost:8001
const target = process.env.DATAFUL_API ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': target },
  },
})
