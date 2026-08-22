/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'ForexCast',
        short_name: 'ForexCast',
        display: 'standalone',
        start_url: '/',
        theme_color: '#2563eb',
        background_color: '#f9fafb',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
  optimizeDeps: {
    include: ['libsodium-wrappers'],
  },
  build: {
    // libsodium-wrappers' ESM build uses a top-level `await` internally.
    // Vite's default esbuild transpile target (~es2020) predates
    // browser support for that syntax and fails to compile it; es2022
    // is the first target where esbuild leaves top-level await alone,
    // and is safely below every evergreen browser's baseline by now.
    target: 'es2022',
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
    env: {
      VITE_SUPABASE_URL: 'https://test.supabase.co',
      VITE_SUPABASE_ANON_KEY: 'test-anon-key',
      VITE_API_BASE_URL: 'http://localhost:8000',
    },
  },
})
