import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

function getVersion(): string {
  const paths = [
    path.resolve(__dirname, '../VERSION'),
    path.resolve(__dirname, 'VERSION'),
    path.resolve(__dirname, '../../VERSION'),
  ]
  for (const versionPath of paths) {
    if (fs.existsSync(versionPath)) {
      return fs.readFileSync(versionPath, 'utf-8').trim()
    }
  }
  throw new Error('VERSION file not found. Please create a VERSION file in the project root.')
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  define: {
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(getVersion()),
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          query: ['@tanstack/react-query', '@tanstack/react-table'],
          ui: ['lucide-react', 'sonner', 'react-hook-form'],
        },
      },
    },
  },
})
