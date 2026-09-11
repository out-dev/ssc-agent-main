import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  envDir: '..',
  server: {
    proxy: {
      '/api': 'http://localhost:5080',
      '/openapi': 'http://localhost:5080',
    },
  },
})
