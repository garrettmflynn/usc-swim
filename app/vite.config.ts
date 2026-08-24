import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// Builds into ../docs, which is what GitHub Pages serves.
//
// emptyOutDir is off on purpose: docs/data/*.json is the dataset, written by
// the watcher and committed. Wiping the output directory on every build would
// delete the history this whole project exists to collect.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'prompt',
      manifest: false, // hand-written in public/manifest.webmanifest
      injectRegister: null,
      srcDir: 'src',
      filename: 'sw.ts',
      strategies: 'injectManifest',
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,png,webmanifest}'],
        // The dataset is fetched fresh at runtime, never precached — a cached
        // schedule is a wrong schedule.
        globIgnores: ['**/data/**', '**/*.map'],
      },
      devOptions: { enabled: false },
    }),
  ],
  base: './',
  build: {
    outDir: '../docs',
    emptyOutDir: false,
    assetsDir: 'assets',
    // The built output is committed on every app change, so no source maps —
    // they were larger than the bundle itself and would bloat the history.
    // `npm run dev` still has full maps.
    sourcemap: false,
  },
  server: { port: 5173, fs: { allow: ['..'] } },
})
