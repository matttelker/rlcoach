import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // `rlcoach serve` keeps the API under /api, beside the built dashboard
    proxy: {
      '/api': {
        target: process.env.RLCOACH_API ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
