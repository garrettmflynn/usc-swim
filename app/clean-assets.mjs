/**
 * Remove previously built assets before a build.
 *
 * The build can't use Vite's emptyOutDir: docs/ also holds docs/data/*.json,
 * which is the dataset and must survive. So clear exactly what the build
 * regenerates, and nothing else.
 */
import { readdir, rm } from 'node:fs/promises'
import { join } from 'node:path'

const DOCS = new URL('../docs/', import.meta.url).pathname
const GENERATED = [/^index\.html$/, /^sw\.js(\.map)?$/, /^sw\.mjs(\.map)?$/,
                   /^manifest\.webmanifest$/, /^icon-.*\.png$/,
                   /^apple-touch-icon\.png$/, /^registerSW\.js$/, /^workbox-.*\.js$/]

await rm(join(DOCS, 'assets'), { recursive: true, force: true })

let entries = []
try {
  entries = await readdir(DOCS, { withFileTypes: true })
} catch {
  process.exit(0) // nothing built yet
}

for (const entry of entries) {
  if (entry.isDirectory()) continue
  if (GENERATED.some((re) => re.test(entry.name))) {
    await rm(join(DOCS, entry.name), { force: true })
  }
}
console.log('cleaned previously built assets (docs/data left alone)')
