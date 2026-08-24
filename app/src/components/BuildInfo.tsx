import { useEffect, useState } from 'react'
import { CircleCheck, TriangleAlert, Wrench } from 'lucide-react'
import type { Latest } from '../types'
import { BUILD } from '../lib/build'

interface Deployed {
  app?: { sha?: string; short?: string; builtAt?: string; builtBy?: string }
}

/**
 * What's actually running, versus what's actually deployed.
 *
 * A service worker serves a cached bundle that looks identical to a fresh one,
 * so "is this the current build?" isn't answerable by looking. Comparing the
 * commit baked into the running JS against docs/version.json makes a stale tab
 * say so instead of quietly showing week-old code.
 */
export default function BuildInfo({ latest }: { latest: Latest }) {
  const [deployed, setDeployed] = useState<Deployed | null>(null)
  const [swState, setSwState] = useState<string>('checking…')
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    fetch(`version.json?t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then(setDeployed)
      .catch(() => setDeployed(null))

    navigator.serviceWorker
      ?.getRegistration()
      .then((reg) =>
        setSwState(reg?.active ? `active (${reg.active.state})` : 'not registered'),
      )
      .catch(() => setSwState('unavailable'))
  }, [])

  const deployedSha = deployed?.app?.sha
  const stale = Boolean(deployedSha && deployedSha !== BUILD.sha)

  async function refresh() {
    setChecking(true)
    const reg = await navigator.serviceWorker?.getRegistration()
    await reg?.update()
    for (const key of await caches.keys()) await caches.delete(key)
    location.reload()
  }

  // Measured on the device, because this class of layout bug is invisible
  // anywhere the safe-area inset is 0 and dvh is dependable — i.e. everywhere
  // I can test. Screenshot this and the numbers say what is actually wrong.
  const probe = document.createElement('div')
  probe.style.cssText =
    'position:fixed;bottom:0;height:env(safe-area-inset-bottom,0px);width:0'
  document.body.appendChild(probe)
  const inset = Math.round(probe.getBoundingClientRect().height)
  probe.remove()

  const app = document.querySelector('.app')?.getBoundingClientRect()
  const bar = document.querySelector('.tabbar')?.getBoundingClientRect()
  const standalone =
    window.matchMedia('(display-mode: standalone)').matches ||
    (navigator as { standalone?: boolean }).standalone === true

  const rows: Array<[string, string]> = [
    ['App commit', `${BUILD.short}${BUILD.dirty ? ' (uncommitted changes)' : ''}`],
    ['App built', when(BUILD.builtAt)],
    ['Deployed commit', deployed?.app?.short ?? 'unreachable'],
    ['Deployed built', deployed?.app?.builtAt ? when(deployed.app.builtAt) : '—'],
    ['Data written', latest.generator ? when(latest.generator.written_at) : '—'],
    [
      'Data written by',
      latest.generator
        ? `${latest.generator.tool} ${latest.generator.version} · ${latest.generator.git_sha ?? '—'}`
        : 'not stamped',
    ],
    ['Last checked', when(latest.checked_at)],
    ['Service worker', swState],
    ['Installed app', standalone ? 'yes (standalone)' : 'no (browser tab)'],
    ['Viewport', `${window.innerWidth}x${window.innerHeight}`],
    ['Screen', `${window.screen.width}x${window.screen.height}`],
    ['Safe area bottom', `${inset}px`],
    [
      'Shell height',
      app ? `${Math.round(app.height)}px (top ${Math.round(app.top)})` : '—',
    ],
    [
      'Gap under tab bar',
      bar ? `${Math.round(window.innerHeight - bar.bottom)}px` : '—',
    ],
  ]

  return (
    <section className="panel">
      <h2>
        <Wrench size={15} strokeWidth={2} aria-hidden="true" />
        Build
      </h2>

      <p className={`verdictline ${stale ? 'stale' : 'fresh'}`}>
        {stale ? (
          <>
            <TriangleAlert size={14} strokeWidth={2} aria-hidden="true" />
            This tab is running an older build than what’s deployed.
          </>
        ) : (
          <>
            <CircleCheck size={14} strokeWidth={2} aria-hidden="true" />
            {deployedSha ? 'Running the deployed build.' : 'Running a local build.'}
          </>
        )}
      </p>

      <dl className="kv">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>

      <button className="primary" type="button" onClick={refresh} disabled={checking}>
        {checking ? 'Reloading…' : 'Check for update'}
      </button>
    </section>
  )
}

function when(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const mins = Math.round((Date.now() - d.getTime()) / 60000)
  const ago =
    mins < 1 ? 'just now'
    : mins < 60 ? `${mins}m ago`
    : mins < 60 * 24 ? `${Math.round(mins / 60)}h ago`
    : `${Math.round(mins / 1440)}d ago`
  return `${d.toLocaleString('en-US', {
    month: 'numeric', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })} · ${ago}`
}
