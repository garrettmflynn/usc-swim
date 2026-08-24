import { useEffect, useState } from 'react'
import { Bell, BellOff, Check, Copy, Info, Palette } from 'lucide-react'
import type { Prefs } from '../lib/prefs'
import { applyTheme, savePrefs } from '../lib/prefs'
import {
  currentState,
  getSubscription,
  subscribe,
  unsubscribe,
  type PushState,
} from '../lib/push'

/** Compile-time config, set by VITE_VAPID_PUBLIC_KEY at build time. */
const VAPID = import.meta.env.VITE_VAPID_PUBLIC_KEY as string | undefined

export default function Settings({
  prefs,
  onPrefs,
}: {
  prefs: Prefs
  onPrefs: (next: Prefs) => void
}) {
  const [state, setState] = useState<PushState | 'working'>('ready')
  const [payload, setPayload] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void currentState().then(setState)
    void getSubscription().then((s) => s && setPayload(JSON.stringify(s.toJSON())))
  }, [])

  async function enable() {
    setError(null)
    if (!VAPID) {
      setError('This build has no VAPID public key, so push can’t be set up yet.')
      return
    }
    setState('working')
    try {
      const sub = await subscribe(VAPID)
      setPayload(JSON.stringify(sub.toJSON()))
      setState('subscribed')
    } catch (e) {
      setError((e as Error).message)
      setState(await currentState())
    }
  }

  async function disable() {
    setState('working')
    await unsubscribe()
    setPayload(null)
    setState(await currentState())
  }

  async function copy() {
    if (!payload) return
    try {
      await navigator.clipboard.writeText(payload)
      setCopied(true)
      setTimeout(() => setCopied(false), 2200)
    } catch {
      setError('Couldn’t reach the clipboard — select the text below and copy it.')
    }
  }

  return (
    <div className="view">
      <section className="panel">
        <h2><Bell size={15} strokeWidth={2} aria-hidden="true" />Notifications</h2>
        <p className="lede">
          Get told when USC posts a new schedule, rather than checking. Email
          reaches everyone with no setup; push has to be turned on once per
          device.
        </p>

        {state === 'needs-install' && (
          <p className="note">
            <b>Add USC Swim to your home screen first.</b> On iPhone, tap Share
            then <b>Add to Home Screen</b>, and open it from there — iOS only
            allows notifications for installed apps.
          </p>
        )}

        {state === 'unsupported' && (
          <p className="note">This browser doesn’t support push notifications.</p>
        )}

        {state === 'denied' && (
          <p className="note warn">
            Notifications are blocked for this site. Re-allow them in your
            browser’s site settings, then come back.
          </p>
        )}

        {(state === 'ready' || state === 'working') && (
          <button className="primary" type="button" onClick={enable} disabled={state === 'working'}>
            <Bell size={14} strokeWidth={2} aria-hidden="true" />
            {state === 'working' ? 'Working…' : 'Turn on notifications'}
          </button>
        )}

        {state === 'subscribed' && (
          <>
            <p className="ok">
              <Check size={14} strokeWidth={2.4} aria-hidden="true" />
              This device is subscribed.
            </p>
            <p className="lede">
              One last step, once per device: send this to whoever manages the
              repo, so it can go in the <code>PUSH_SUBSCRIPTIONS</code> secret.
              There’s no server to register it automatically.
            </p>
            <div className="copyrow">
              <button className="primary" type="button" onClick={copy}>
                {copied ? <Check size={14} strokeWidth={2.4} /> : <Copy size={14} strokeWidth={2} />}
                {copied ? 'Copied' : 'Copy subscription'}
              </button>
              <button type="button" onClick={disable}>
                <BellOff size={14} strokeWidth={2} aria-hidden="true" />
                Turn off
              </button>
            </div>
            <textarea readOnly value={payload ?? ''} rows={4} spellCheck={false} />
          </>
        )}

        {error && <p className="note warn">{error}</p>}
      </section>

      <section className="panel">
        <h2><Palette size={15} strokeWidth={2} aria-hidden="true" />Appearance</h2>
        <div className="seg">
          {(['system', 'light', 'dark'] as const).map((t) => (
            <button
              key={t}
              type="button"
              className={prefs.theme === t ? 'on' : ''}
              onClick={() => {
                applyTheme(t)
                onPrefs(savePrefs({ theme: t }))
              }}
            >
              {t[0]!.toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2><Info size={15} strokeWidth={2} aria-hidden="true" />About</h2>
        <p className="lede">
          USC Swim reads the Rec Sports operating-hours page and records what it
          says. When next week isn’t posted, it falls back to what that weekday
          has historically looked like — always labelled, never blended with a
          posted time.
        </p>
        <p className="lede">
          <a href="data/history.json">history.json</a> is the dataset;{' '}
          <a href="data/latest.json">latest.json</a> is the most recent check.
          Source:{' '}
          <a href="https://recsports.usc.edu/rec-facilities/operating-hours/">
            USC Rec Sports
          </a>
          . Not affiliated with USC.
        </p>
      </section>
    </div>
  )
}
