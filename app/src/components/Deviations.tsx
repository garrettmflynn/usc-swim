import { useMemo } from 'react'
import { ArrowDownRight, ArrowUpRight, CalendarClock } from 'lucide-react'
import type { Latest, Snapshot } from '../types'
import { DAYS, deviations, midWeekEdits, type Deviation } from '../lib/analysis'
import { clock, longDate, stamp, todayISO } from '../lib/format'

/**
 * Where the posted week departs from its own history.
 *
 * The percentages elsewhere are background; this is the part that changes a
 * decision. "Tuesday usually has a 6am and this week doesn't" is worth an
 * alert. "Tuesday 6am is 83%" never was.
 */
export default function Deviations({
  latest,
  history,
  /** Only judge days from today on — a past day can't change a plan. */
  upcomingOnly = false,
}: {
  latest: Latest
  history: Snapshot[]
  upcomingOnly?: boolean
}) {
  const today = todayISO()
  const all = useMemo(() => deviations(history, latest), [history, latest])
  const shown = upcomingOnly ? all.filter((d) => d.date >= today) : all
  // Whether ANY day in scope was posted at all. Without this the panel says
  // "matches its usual shape" when the truth is that nothing is posted yet —
  // agreement and absence are not the same claim.
  const judged = useMemo(
    () =>
      Object.values(latest.parsed.pools)
        .flat()
        .some(
          (r) =>
            r.date &&
            !r.flags.includes('outside_posted_week') &&
            (r.windows.length > 0 || r.closed === true) &&
            (!upcomingOnly || r.date >= today),
        ),
    [latest, upcomingOnly, today],
  )
  const edits = useMemo(() => midWeekEdits(history), [history])
  const recentEdit = edits[0]

  // Nothing posted in scope and no edit to report: there is nothing to say,
  // and saying "matches its usual shape" would be a claim about data we do
  // not have.
  if (!shown.length && !judged && !recentEdit) return null

  const byDate = new Map<string, Deviation[]>()
  for (const d of shown) byDate.set(d.date, [...(byDate.get(d.date) ?? []), d])

  const missing = shown.filter((d) => d.kind === 'missing').length

  return (
    <section className="panel deviations">
      <h2>
        <CalendarClock size={15} strokeWidth={2} aria-hidden="true" />
        What’s different this week
      </h2>

      {shown.length > 0 ? (
        <p className="lede">
          {missing > 0 ? (
            <>
              The posted week drops <b>{missing}</b> slot{missing === 1 ? '' : 's'} that
              this weekday usually has.
            </>
          ) : (
            <>The posted week adds hours that rarely appear.</>
          )}{' '}
          Compared against every other week on record, that week excluded.
        </p>
      ) : judged ? (
        <p className="lede">
          The posted days match what those weekdays usually look like.
        </p>
      ) : (
        <p className="lede">
          Nothing is posted for the days ahead yet, so there is nothing to
          compare. This fills in once USC puts the week up.
        </p>
      )}

      {[...byDate.entries()].map(([date, items]) => (
        <div className="devday" key={date}>
          <h3>
            {DAYS[items[0]!.weekday]} · {longDate(date).replace(/^\w+,\s*/, '')}
          </h3>
          <ul>
            {items.map((d) => (
              <li className={d.kind} key={`${d.kind}-${d.window[0]}`}>
                {d.kind === 'missing' ? (
                  <ArrowDownRight size={14} strokeWidth={2} aria-hidden="true" />
                ) : (
                  <ArrowUpRight size={14} strokeWidth={2} aria-hidden="true" />
                )}
                <span className="w">
                  {clock(d.window[0])}–{clock(d.window[1])}
                </span>
                <span className="why">
                  {d.kind === 'missing'
                    ? `not posted — usually here ${d.seen} of ${d.known} weeks`
                    : d.seen === 0
                      ? `new — never seen in ${d.known} weeks`
                      : `unusual — seen ${d.seen} of ${d.known} weeks`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}

      {recentEdit && (
        <p className="note">
          <b>They have changed a schedule mid-week.</b> The week of{' '}
          {longDate(recentEdit.weekOf).replace(/^\w+,\s*/, '')} was edited on its{' '}
          {DAYS[recentEdit.dayIntoWeek]}, seen {stamp(recentEdit.seenAt)}.
          {edits.length > 1 && ` ${edits.length} such edits on record.`}
        </p>
      )}

      <p className="caveat">
        Mid-week edits are only visible where two checks landed inside the same
        week. The archived history is roughly one capture a week, so this mostly
        starts accruing from now on, as the watcher runs.
      </p>
    </section>
  )
}
