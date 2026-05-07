import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/diagram/',
  build: {
    outDir: '../../static/diagram',
    emptyOutDir: true,
  },
})
