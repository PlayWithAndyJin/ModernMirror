import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: '/ui/',
  plugins: [react()],
  server: {
    proxy: {
      '/admin': 'http://localhost:8800',
      '/auth': 'http://localhost:8800',
      '/api': 'http://localhost:8800',
      '/pkg': 'http://localhost:8800',
      '/simple': 'http://localhost:8800',
      '/proxy': 'http://localhost:8800',
      '/templates': 'http://localhost:8800',
      '/skill': 'http://localhost:8800',
      '/docs': 'http://localhost:8800',
      '/openapi.json': 'http://localhost:8800'
    }
  }
})
