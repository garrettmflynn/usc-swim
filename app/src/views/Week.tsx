import { useMemo, useState } from 'react'
import {
  BadgeCheck,
  ChevronDown,
  CircleSlash,
  Clock3,
  Sparkles,
  TriangleAlert,
} from 'lucide-react'
import type { Latest, Snapshot, Window } from '../types'
import {
  DAYS,
  DAY_NAMES,
  deviations,
  outlook,
  type DayOutlook,
  type Deviation,
} from '../lib/analysis'
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
  // Deviations belong to the day they concern. As a block above the list they
  // pushed the schedule off screen, which is the one thing this view is for.
  const devByDate = useMemo(() => {
    const map = new Map<string, Deviation[]>()
    for (const d of deviations(history, latest)) {
      map.set(d.date, [...(map.get(d.date) ?? []), d])
    }
    return map
  }, [history, latest])
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
            {7 - unposted} of the next 7 days {7 - unposted === 1 ? 'is' : 'are'}{' '}
            posted.
          </b>{' '}
          The rest are projected from past weeks and marked on each day.
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
            devs={devByDate.get(day.date) ?? []}
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
  devs,
}: {
  day: DayOutlook
  isToday: boolean
  expanded: boolean
  onToggle: () => void
  nowMin: number
  devs: Deviation[]
}) {
  const missing = devs.filter((d) => d.kind === 'missing')
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

        <ChevronDown className="chev" size={16} strokeWidth={1.8} aria-hidden="true" />
      </button>

      <p className={`provenance ${day.source}`}>
        {day.source === 'posted' ? (
          <>
            <BadgeCheck size={12} strokeWidth={2} aria-hidden="true" />
            <span><b>Posted by USC</b> for this date</span>
          </>
        ) : day.source === 'expected' ? (
          <>
            <Sparkles size={12} strokeWidth={2} aria-hidden="true" />
            <span>
              <b>Projected</b>, not posted — from {day.known} past{' '}
              {DAY_NAMES[day.weekday]}
              {day.known === 1 ? '' : 's'}
            </span>
          </>
        ) : (
          <>
            <CircleSlash size={12} strokeWidth={2} aria-hidden="true" />
            <span><b>Unknown</b> — not posted, and no history for this weekday</span>
          </>
        )}
      </p>

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

      {missing.length > 0 && !expanded && (
        <p className="daydev">
          <TriangleAlert size={12} strokeWidth={2} aria-hidden="true" />
          {missing.length} usual slot{missing.length === 1 ? '' : 's'} not posted
        </p>
      )}

      {expanded && (
        <div className="detail">
          {devs.length > 0 && (
            <ul className="devlist">
              {devs.map((d) => (
                <li className={d.kind} key={`${d.kind}-${d.window[0]}`}>
                  <span className="w">
                    {clock(d.window[0])}–{clock(d.window[1])}
                  </span>
                  <span>
                    {d.kind === 'missing'
                      ? `usually here ${d.seen} of ${d.known} weeks`
                      : d.seen === 0
                        ? `new — never seen in ${d.known} weeks`
                        : `unusual — ${d.seen} of ${d.known} weeks`}
                  </span>
                </li>
              ))}
            </ul>
          )}
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
