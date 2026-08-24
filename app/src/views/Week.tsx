import { useMemo, useState } from 'react'
import { ChevronDown, CircleSlash, Clock3, Sparkles } from 'lucide-react'
import type { Latest, Snapshot, Window } from '../types'
import { DAYS, outlook, type DayOutlook } from '../lib/analysis'
import { clock, todayISO } from '../lib/format'

const DAY_START = 5 * 60
const DAY_END = 20 * 60
const pct = (m: number) => ((m - DAY_START) / (DAY_END - DAY_START)) * 100

/** Home screen: the seven days ahead, posted where known, expected where not. */
export default function Week({
  latest,
  history,
}: {
  latest: Latest
  history: Snapshot[]
}) {
  // The device's date, not the check's — see todayISO.
  const todayIso = todayISO()
  const today = useMemo(() => new Date(`${todayIso}T12:00:00`), [todayIso])
  const days = useMemo(() => outlook(history, latest, today, 7), [history, latest, today])
  const [open, setOpen] = useState<string | null>(days[0]?.date ?? null)

  const nowMin = new Date().getHours() * 60 + new Date().getMinutes()
  const next = useMemo(() => nextSwim(days, nowMin), [days, nowMin])
  const unposted = days.filter((d) => d.source !== 'posted').length

  return (
    <div className="view">
      <section className="hero">
        <p className="kicker">
          <Clock3 size={12} strokeWidth={2} aria-hidden="true" />
          Next swim
        </p>
        {next ? (
          <>
            <h1>
              {next.when}
              <span className="hero-time">
                {clock(next.window[0])}–{clock(next.window[1])}
              </span>
            </h1>
            <p className={`hero-note ${next.source}`}>
              {next.source === 'posted' ? (
                'On the posted schedule.'
              ) : (
                <>
                  <Sparkles size={12} strokeWidth={2} aria-hidden="true" />
                  Expected — they haven’t posted this day yet.
                </>
              )}
            </p>
          </>
        ) : (
          <>
            <h1>Nothing ahead</h1>
            <p className="hero-note">No open windows in the next seven days.</p>
          </>
        )}
      </section>

      {unposted > 0 && (
        <p className="banner">
          <b>
            {unposted} of 7 days aren’t posted.
          </b>{' '}
          Those show what that weekday usually looks like.
        </p>
      )}

      <ol className="daylist">
        {days.map((day) => (
          <DayRow
            key={day.date}
            day={day}
            isToday={day.date === todayIso}
            expanded={open === day.date}
            onToggle={() => setOpen(open === day.date ? null : day.date)}
            nowMin={nowMin}
          />
        ))}
      </ol>
    </div>
  )
}

function DayRow({
  day,
  isToday,
  expanded,
  onToggle,
  nowMin,
}: {
  day: DayOutlook
  isToday: boolean
  expanded: boolean
  onToggle: () => void
  nowMin: number
}) {
  const d = new Date(`${day.date}T12:00:00`)
  const empty = day.windows.length === 0

  return (
    <li className={`dayrow ${day.source} ${expanded ? 'open' : ''} ${isToday ? 'today' : ''}`}>
      <button type="button" onClick={onToggle} aria-expanded={expanded}>
        <span className="dl">
          <b>{isToday ? 'Today' : DAYS[day.weekday]}</b>
          <em>{d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</em>
        </span>

        <span className="dtimes">
          {empty ? (
            <i className="muted">
              <CircleSlash size={12} strokeWidth={1.8} aria-hidden="true" />
              {day.source === 'posted' ? 'Closed' : 'Usually nothing'}
            </i>
          ) : (
            day.windows.map((w) => (
              <i key={w[0]}>
                {clock(w[0])}–{clock(w[1])}
              </i>
            ))
          )}
        </span>

        {day.source !== 'posted' && <span className="tag expected">expected</span>}
        <ChevronDown className="chev" size={16} strokeWidth={1.8} aria-hidden="true" />
      </button>

      <div className="dtrack" aria-hidden="true">
        {day.windows.map((w) => (
          <span
            key={w[0]}
            className="bar"
            style={{ left: `${pct(w[0])}%`, width: `${Math.max(pct(w[1]) - pct(w[0]), 2)}%` }}
          />
        ))}
        {isToday && nowMin > DAY_START && nowMin < DAY_END && (
          <span className="now" style={{ left: `${pct(nowMin)}%` }} />
        )}
      </div>

      {expanded && (
        <div className="detail">
          {day.source === 'posted' ? (
            <p>Posted by USC Rec Sports for this date.</p>
          ) : day.typical && day.typical.length > 0 ? (
            <>
              <p>
                How this weekday has gone across {day.known} observed week
                {day.known === 1 ? '' : 's'}:
              </p>
              <ul className="odds">
                {day.typical.map((t) => (
                  <li key={t.window[0]}>
                    <span>
                      {clock(t.window[0])}–{clock(t.window[1])}
                    </span>
                    <i className="mini">
                      <b style={{ width: `${(t.seen / t.known) * 100}%` }} />
                    </i>
                    <span className="n">
                      {t.seen}/{t.known}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p>No history for this weekday yet.</p>
          )}
        </div>
      )}
    </li>
  )
}

interface NextSwim {
  when: string
  window: Window
  source: DayOutlook['source']
}

/** The soonest window that hasn't already ended. */
function nextSwim(days: DayOutlook[], nowMin: number): NextSwim | null {
  for (const [i, day] of days.entries()) {
    for (const w of day.windows) {
      if (i === 0 && w[1] <= nowMin) continue
      const when =
        i === 0 ? (w[0] <= nowMin ? 'Now' : 'Today') : i === 1 ? 'Tomorrow' : DAYS[day.weekday]!
      return { when, window: w, source: day.source }
    }
  }
  return null
}
