import { execSync } from 'node:child_process'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

/**
 * Stamp the build so a running page can be compared against what was shipped.
 *
 * Service workers make "am I looking at the current build?" a real question —
 * a cached bundle is indistinguishable from a fresh one until something looks
 * wrong. Baking the commit and build time in makes the answer checkable
 * instead of a guess.
 */
function gitInfo() {
  const run = (cmd: string) => {
    try {
      return execSync(cmd, { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim()
    } catch {
      return ''
    }
  }
  // GitHub Actions checks out a detached HEAD, so prefer its own env vars.
  const sha = process.env.GITHUB_SHA || run('git rev-parse HEAD')
  return {
    sha: sha || 'unknown',
    short: (sha || 'unknown').slice(0, 7),
    branch: process.env.GITHUB_REF_NAME || run('git rev-parse --abbrev-ref HEAD') || 'unknown',
    dirty: process.env.GITHUB_SHA ? false : run('git status --porcelain') !== '',
    builtAt: new Date().toISOString(),
  }
}

const BUILD = gitInfo()

// Builds into ../docs, which is what GitHub Pages serves.
//
// emptyOutDir is off on purpose: docs/data/*.json is the dataset, written by
// the watcher and committed. Wiping the output directory on every build would
// delete the history this whole project exists to collect.
export default defineConfig({
  define: {
    __BUILD__: JSON.stringify(BUILD),
  },
  plugins: [
    react(),
    VitePWA({
      // autoUpdate: a new build should just be there. 'prompt' left the new
      // worker waiting for a message nothing sent.
      registerType: 'autoUpdate',
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
