import type { Latest, Snapshot, Stats } from '../types'
import { shortDate, stamp, pct } from '../lib/format'
import Health from '../components/Health'
import Board from '../components/Board'
import Deviations from '../components/Deviations'

/** What they've posted, what changed, and whether the parser still works. */
export default function Activity({
  latest,
  history,
  stats,
}: {
  latest: Latest
  history: Snapshot[]
  stats: Stats
}) {
  const lag = stats.median_post_lag_hours
  const measured = stats.weeks.filter((w) => !w.censored).length

  const tiles = [
    {
      label: 'Median post lag',
      value: lag == null ? '—' : (lag / 24).toFixed(1),
      unit: lag == null ? 'not measurable yet' : `days · ${measured} week${measured === 1 ? '' : 's'}`,
    },
    {
      label: 'Covers today',
      value: stats.coverage_rate == null ? '—' : pct(stats.coverage_rate),
      unit: `of ${stats.checks_total} check${stats.checks_total === 1 ? '' : 's'}`,
    },
    {
      label: 'Schedules seen',
      value: String(stats.changes_total),
      unit: 'distinct postings',
    },
  ]

  return (
    <div className="view">
      <Health latest={latest} history={history} />
      <Deviations latest={latest} history={history} />
      <Board latest={latest} />

      <section className="tiles">
        {tiles.map((t) => (
          <div className="tile" key={t.label}>
            <dt>{t.label}</dt>
            <dd>
              {t.value}
              <small>{t.unit}</small>
            </dd>
          </div>
        ))}
      </section>

      <section className="log">
        <h2>Every change they’ve made</h2>
        <ol>
          {[...history].reverse().slice(0, 40).map((h) => (
            <li key={`${h.checked_at}-${h.content_hash}`}>
              <time dateTime={h.checked_at}>{stamp(h.checked_at)}</time>
              <span className={h.coverage.today_covered ? '' : 'miss'}>
                through{' '}
                {h.coverage.posted_through ? shortDate(h.coverage.posted_through) : '—'}
              </span>
              {h.origin === 'wayback' && (
                <em title="recovered from the Internet Archive">archived</em>
              )}
              {h.parse_health && h.parse_health.status !== 'ok' && (
                <b className={h.parse_health.status}>{h.parse_health.status}</b>
              )}
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
