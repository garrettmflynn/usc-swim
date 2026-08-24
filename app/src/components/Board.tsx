import { useMemo } from 'react'
import type { Latest, Row, Window } from '../types'
import { clock, hourLabel, shortDate } from '../lib/format'

const DAY_START = 5 * 60
const DAY_END = 20 * 60
const TICKS = [6, 8, 10, 12, 14, 16, 18]
const pct = (min: number) => ((min - DAY_START) / (DAY_END - DAY_START)) * 100

interface Block {
  window: Window
  pool: string
}

interface DayLane {
  date: string | null
  weekday: string
  blocks: Block[]
  /** True only when some pool explicitly said closed and none offered hours. */
  closed: boolean
  anomalies: string[]
}

/**
 * The posted week, one lane per day.
 *
 * Organised by day rather than by pool because the two pools sit beside each
 * other and never open at the same time — across every week on record their
 * hours don't overlap once, so "is anything open" is the question, and which
 * pool is a label on the answer rather than a separate schedule.
 */
export default function Board({ latest }: { latest: Latest }) {
  const lanes = useMemo(() => byDay(latest), [latest])
  if (!lanes.length) return null

  const today = latest.coverage.today
  const now = new Date()
  const nowMin = now.getHours() * 60 + now.getMinutes()
  const poolsShown = Array.from(new Set(lanes.flatMap((l) => l.blocks.map((b) => b.pool))))

  return (
    <section className="board">
      <div className="panel-head">
        <h2>The posted week</h2>
        <div className="poolkey">
          {poolsShown.map((p) => (
            <span key={p} className={`swatch ${slug(p)}`}>
              {p}
            </span>
          ))}
        </div>
      </div>

      <div className="ruler" aria-hidden="true">
        {TICKS.map((h) => (
          <span key={h} style={{ left: `${pct(h * 60)}%` }}>
            {hourLabel(h)}
          </span>
        ))}
      </div>

      {lanes.map((lane) => {
        const isToday = lane.date === today
        return (
          <div
            className={[
              'lane',
              isToday ? 'today' : '',
              lane.blocks.length ? '' : lane.closed ? 'closed' : 'unknown',
              lane.anomalies.length ? 'flagged' : '',
            ].join(' ')}
            key={`${lane.date}-${lane.weekday}`}
          >
            <div className="d">
              {lane.weekday} {lane.date ? shortDate(lane.date) : '—'}
              {lane.anomalies.length > 0 && (
                <b title={lane.anomalies.join(', ')} aria-label={lane.anomalies.join(', ')}>
                  !
                </b>
              )}
            </div>
            <div className="track">
              {lane.blocks.map((b) => {
                const width = Math.max(pct(b.window[1]) - pct(b.window[0]), 1.5)
                return (
                  <div
                    className={`bar ${slug(b.pool)}`}
                    key={`${b.pool}-${b.window[0]}`}
                    style={{ left: `${pct(b.window[0])}%`, width: `${width}%` }}
                    title={`${b.pool} · ${clock(b.window[0])}–${clock(b.window[1])}`}
                  >
                    {width > 13 && (
                      <span>
                        {clock(b.window[0])}–{clock(b.window[1])}
                      </span>
                    )}
                  </div>
                )
              })}
              {isToday && nowMin > DAY_START && nowMin < DAY_END && (
                <div className="now" style={{ left: `${pct(nowMin)}%` }} />
              )}
            </div>
          </div>
        )
      })}

      <p className="legend">
        Hatched means they said closed. Faint means the day isn’t on the board at
        all — which is not the same thing.
      </p>
    </section>
  )
}

function slug(pool: string): string {
  return pool.toLowerCase().replace(/[^a-z]+/g, '-')
}

/** Collapse per-pool rows into one lane per calendar day, in date order. */
function byDay(latest: Latest): DayLane[] {
  const lanes = new Map<string, DayLane>()
  for (const [pool, rows] of Object.entries(latest.parsed.pools)) {
    for (const row of rows as Row[]) {
      const id = row.date ?? `${row.weekday}-nodate`
      let lane = lanes.get(id)
      if (!lane) {
        lane = {
          date: row.date,
          weekday: row.weekday,
          blocks: [],
          closed: false,
          anomalies: [],
        }
        lanes.set(id, lane)
      }
      for (const w of row.windows) lane.blocks.push({ window: w, pool })
      if (row.closed === true) lane.closed = true
      for (const f of row.flags) {
        if (f !== 'not_mentioned' && !lane.anomalies.includes(f)) lane.anomalies.push(f)
      }
    }
  }
  return Array.from(lanes.values())
    .map((l) => ({
      ...l,
      blocks: l.blocks.sort((a, b) => a.window[0] - b.window[0]),
      closed: l.closed && l.blocks.length === 0,
    }))
    .sort((a, b) => (a.date ?? '').localeCompare(b.date ?? ''))
}
