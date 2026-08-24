import { useMemo, useState } from 'react'
import type { Snapshot } from '../types'
import {
  DAYS,
  activeHours,
  corpus,
  hourBlocks,
  poolRhythm,
  pools,
  slots,
} from '../lib/analysis'

// Labels the parsers use when the page names no pool. They are bookkeeping,
// not places you can swim, so they never appear as a filter.
const SYNTHETIC = new Set(['Unattributed', 'Unlabeled', 'Uytengsu'])
import { hourLabel } from '../lib/format'

interface Props {
  history: Snapshot[]
}

/**
 * How often each weekday/hour has actually been swimmable.
 *
 * This is the question the dataset exists to answer — "is there ever a 6am
 * Monday swim?" — so the counts are shown alongside the rate. A rate with a
 * hidden denominator invites reading 100% off two observations.
 */
export default function Patterns({ history }: Props) {
  const names = useMemo(() => pools(history), [history])
  const [pool, setPool] = useState<string>('')
  const data = useMemo(() => slots(history, pool || undefined), [history, pool])
  const hours = useMemo(() => activeHours(data), [data])
  const stats = useMemo(() => corpus(history), [history])
  const rhythm = useMemo(() => poolRhythm(history), [history])

  const best = useMemo(
    () =>
      [...data]
        .filter((s) => s.known >= 4 && s.open > 0)
        .sort((a, b) => b.rate - a.rate || a.weekday - b.weekday || a.hour - b.hour)
        .slice(0, 6),
    [data],
  )

  const cell = (weekday: number, hour: number) => {
    const s = data.find((d) => d.weekday === weekday && d.hour === hour)
    if (!s || !s.known) {
      return <td key={hour} className="cell none" title="never observed" />
    }
    const level = s.rate === 0 ? 0 : Math.ceil(s.rate * 4)
    return (
      <td
        key={hour}
        className={`cell l${level}`}
        title={`${DAYS[weekday]} ${hourLabel(hour)} — open in ${s.open} of ${s.known} observed weeks`}
      >
        <span className="sr">{Math.round(s.rate * 100)}%</span>
      </td>
    )
  }

  return (
    <div className="view">
    <section className="panel">
      <div className="panel-head">
        <h2>When is it actually open?</h2>
        <div className="seg" role="group" aria-label="Filter by pool">
          <button
            type="button"
            className={pool === '' ? 'on' : ''}
            onClick={() => setPool('')}
          >
            Either pool
          </button>
          {names
            .filter((n) => !SYNTHETIC.has(n))
            .map((n) => (
              <button
                key={n}
                type="button"
                className={pool === n ? 'on' : ''}
                onClick={() => setPool(n)}
              >
                {n.replace(' Pool', '')}
              </button>
            ))}
        </div>
      </div>

      <p className="lede">
        Share of observed weeks with a swim window open, across{' '}
        <b>{stats.weeksObserved} weeks</b> of posted schedules
        {stats.firstWeek ? ` since ${stats.firstWeek.slice(0, 7)}` : ''}.
      </p>

      <div className="scroller">
        <table className="grid">
          <thead>
            <tr>
              <th className="corner" scope="col">
                <span className="sr">Weekday</span>
              </th>
              {hours.map((h) => (
                <th key={h} scope="col">
                  {hourLabel(h)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {DAYS.map((label, weekday) => (
              <tr key={label}>
                <th scope="row">{label}</th>
                {hours.map((h) => cell(weekday, h))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="key">
        <span>never</span>
        <i className="cell l0" />
        <i className="cell l1" />
        <i className="cell l2" />
        <i className="cell l3" />
        <i className="cell l4" />
        <span>every week</span>
      </div>

      {best.length > 0 && (
        <>
          <h3>Most dependable slots</h3>
          <ol className="best">
            {best.map((s) => (
              <li key={`${s.weekday}:${s.hour}`}>
                <span className="when">
                  {DAYS[s.weekday]} {hourLabel(s.hour)}
                </span>
                <span className="bar" aria-hidden="true">
                  <i style={{ width: `${s.rate * 100}%` }} />
                </span>
                <span className="count">
                  {s.open}/{s.known}
                </span>
              </li>
            ))}
          </ol>
        </>
      )}

      {rhythm.datesObserved > 0 && rhythm.overlapDates.length === 0 && (
        <p className="insight">
          <b>The pools take turns.</b> Across {rhythm.datesObserved} days on record
          they are never open at the same moment. Each mostly owns a slice of the
          day
          {Object.keys(rhythm.hoursByPool).length > 1 && (
            <>
              {' — '}
              {Object.entries(rhythm.hoursByPool)
                .filter(([p]) => !SYNTHETIC.has(p))
                .sort((a, b) => a[1][0]! - b[1][0]!)
                .map(
                  ([p, hrs]) =>
                    `${p.replace(' Pool', '')} ` +
                    hourBlocks(hrs)
                      .map(([s, e]) => `${hourLabel(s)}–${hourLabel(e)}`)
                      .join(', '),
                )
                .join('; ')}
            </>
          )}
          . So “is anything open” is the question; which pool follows from the time.
        </p>
      )}

      <p className="caveat">
        Captures are roughly monthly, not a random sample, and they span
        semesters and summer closures — so read these as “how often it has been
        open when we looked”, not a forecast.
        {stats.backfilled > 0 && (
          <>
            {' '}
            {stats.backfilled} of {history.length} snapshots were recovered from
            the Internet Archive.
          </>
        )}
      </p>
    </section>
    </div>
  )
}
