import { useEffect, useState } from 'react'
import TabBar, { type Tab } from './components/TabBar'
import Activity from './views/Activity'
import Patterns from './views/Patterns'
import Settings from './views/Settings'
import Week from './views/Week'
import { loadDataset, type Dataset } from './lib/data'
import { applyTheme, loadPrefs, savePrefs, type Prefs } from './lib/prefs'
import { stamp } from './lib/format'

export default function App() {
  const [data, setData] = useState<Dataset | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('week')
  const [prefs, setPrefs] = useState<Prefs>(() => loadPrefs())

  useEffect(() => {
    applyTheme(prefs.theme)
  }, [prefs.theme])

  useEffect(() => {
    loadDataset()
      .then((d) => {
        setData(d)
        // Mark this schedule as seen, so "changed since you looked" is honest.
        setPrefs(savePrefs({ seenHash: d.latest.content_hash }))
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  if (error) {
    return (
      <Shell tab={tab} onTab={setTab} status={null}>
        <div className="view">
          <div className="empty">
            <p>
              <b>Couldn’t load the schedule.</b>
            </p>
            <p className="why">{error}</p>
            <button className="primary" type="button" onClick={() => location.reload()}>
              Try again
            </button>
          </div>
        </div>
      </Shell>
    )
  }

  if (!data) {
    return (
      <Shell tab={tab} onTab={setTab} status={null}>
        <div className="view">
          <p className="loading">Reading the board…</p>
        </div>
      </Shell>
    )
  }

  const { latest, history, stats } = data
  const changed = prefs.seenHash !== null && prefs.seenHash !== latest.content_hash

  return (
    <Shell tab={tab} onTab={setTab} status={stamp(latest.checked_at)} changed={changed}>
      {tab === 'week' && <Week latest={latest} history={history} />}
      {tab === 'patterns' && <Patterns history={history} />}
      {tab === 'activity' && <Activity latest={latest} history={history} stats={stats} />}
      {tab === 'settings' && <Settings prefs={prefs} onPrefs={setPrefs} latest={latest} />}
    </Shell>
  )
}

function Shell({
  tab,
  onTab,
  status,
  changed,
  children,
}: {
  tab: Tab
  onTab: (t: Tab) => void
  status: string | null
  changed?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="app">
      <header className="appbar">
        <span className="brand">
          <span className="dot" aria-hidden="true" />
          USC Swim
        </span>
        {status && (
          <span className="checked">
            {changed && <i className="new" aria-label="changed since you last looked" />}
            checked {status}
          </span>
        )}
      </header>
      <main>{children}</main>
      <TabBar active={tab} onChange={onTab} />
    </div>
  )
}
