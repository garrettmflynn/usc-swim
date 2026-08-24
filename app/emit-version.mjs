/**
 * Write docs/version.json after a build.
 *
 * Same facts the app shows in Settings, but fetchable without opening a
 * browser — so a deploy can be confirmed with curl, and a stale service
 * worker can be told apart from a stale deploy.
 */
import { execSync } from 'node:child_process'
import { readdir, writeFile } from 'node:fs/promises'

const DOCS = new URL('../docs/', import.meta.url).pathname
const run = (cmd) => {
  try {
    return execSync(cmd, { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim()
  } catch {
    return ''
  }
}

const sha = process.env.GITHUB_SHA || run('git rev-parse HEAD') || 'unknown'
const assets = (await readdir(new URL('assets/', `file://${DOCS}`))).sort()

await writeFile(
  `${DOCS}version.json`,
  JSON.stringify(
    {
      app: {
        sha,
        short: sha.slice(0, 7),
        branch: process.env.GITHUB_REF_NAME || run('git rev-parse --abbrev-ref HEAD') || 'unknown',
        builtAt: new Date().toISOString(),
        builtBy: process.env.GITHUB_ACTIONS ? 'github-actions' : 'local',
        assets,
      },
    },
    null,
    2,
  ) + '\n',
)
console.log(`wrote docs/version.json (${sha.slice(0, 7)})`)
