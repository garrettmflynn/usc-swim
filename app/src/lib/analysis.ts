import type { Row, Snapshot, Window } from '../types'
import { localDate } from './format'

export const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const
/** The pool has never been open outside this range in any observed week. */
export const FIRST_HOUR = 5
export const LAST_HOUR = 22

export interface Slot {
  weekday: number
  hour: number
  /** Weeks where this hour was open in at least one pool. */
  open: number
  /** Weeks where we know what the schedule said for this day at all. */
  known: number
  rate: number
}

export interface DayRecord {
  date: string
  /** Hours open in any pool. */
  hours: Set<number>
  /** Hours open, per pool. */
  byPool: Record<string, Set<number>>
}

function covers(w: Window, hour: number): boolean {
  return w[0] < (hour + 1) * 60 && w[1] > hour * 60
}

/**
 * Collapse every snapshot to one record per calendar date.
 *
 * A date is only counted as observed when some pool actually stated something
 * for it — hours, or an explicit closure. A row the page never mentioned
 * (`closed === null`) carries no information, and letting it into the
 * denominator would quietly report "closed" as though it were observed.
 */
export function daysObserved(history: Snapshot[]): Map<string, DayRecord> {
  const days = new Map<string, DayRecord>()
  for (const snap of history) {
    for (const [pool, rows] of Object.entries(snap.parsed.pools)) {
      for (const row of rows as Row[]) {
        if (!row.date) continue
        if (row.flags.includes('outside_posted_week')) continue
        const stated = row.windows.length > 0 || row.closed === true
        if (!stated) continue

        let rec = days.get(row.date)
        if (!rec) {
          rec = { date: row.date, hours: new Set(), byPool: {} }
          days.set(row.date, rec)
        }
        rec.byPool[pool] ??= new Set()
        for (let h = FIRST_HOUR; h < LAST_HOUR; h++) {
          if (row.windows.some((w) => covers(w, h))) {
            rec.hours.add(h)
            rec.byPool[pool]!.add(h)
          }
        }
      }
    }
  }
  return days
}

/** How often each weekday/hour has actually been swimmable. */
export function slots(history: Snapshot[], pool?: string): Slot[] {
  const days = daysObserved(history)
  const open = new Map<string, number>()
  const known = new Map<string, number>()

  for (const rec of days.values()) {
    const weekday = (localDate(rec.date).getDay() + 6) % 7 // Monday = 0
    const hours = pool ? rec.byPool[pool] : rec.hours
    if (pool && !rec.byPool[pool]) continue
    for (let h = FIRST_HOUR; h < LAST_HOUR; h++) {
      const key = `${weekday}:${h}`
      known.set(key, (known.get(key) ?? 0) + 1)
      if (hours?.has(h)) open.set(key, (open.get(key) ?? 0) + 1)
    }
  }

  const out: Slot[] = []
  for (let weekday = 0; weekday < 7; weekday++) {
    for (let hour = FIRST_HOUR; hour < LAST_HOUR; hour++) {
      const key = `${weekday}:${hour}`
      const k = known.get(key) ?? 0
      const o = open.get(key) ?? 0
      out.push({ weekday, hour, open: o, known: k, rate: k ? o / k : 0 })
    }
  }
  return out
}

/** Hours that are open in at least one observed week — the rest are dead space. */
export function activeHours(slots: Slot[]): number[] {
  const live = slots.filter((s) => s.open > 0).map((s) => s.hour)
  if (!live.length) return [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]
  return Array.from(
    { length: Math.max(...live) - Math.min(...live) + 1 },
    (_, i) => Math.min(...live) + i,
  )
}

export function pools(history: Snapshot[]): string[] {
  const names = new Set<string>()
  for (const snap of history) for (const p of Object.keys(snap.parsed.pools)) names.add(p)
  return Array.from(names).sort()
}

export interface Coverage {
  weeksObserved: number
  daysObserved: number
  firstWeek: string | null
  lastWeek: string | null
  backfilled: number
}

export function corpus(history: Snapshot[]): Coverage {
  const days = daysObserved(history)
  const dates = Array.from(days.keys()).sort()
  const weeks = new Set(
    dates.map((d) => {
      const dt = localDate(d)
      dt.setDate(dt.getDate() - ((dt.getDay() + 6) % 7))
      return dt.toISOString().slice(0, 10)
    }),
  )
  return {
    weeksObserved: weeks.size,
    daysObserved: dates.length,
    firstWeek: dates[0] ?? null,
    lastWeek: dates[dates.length - 1] ?? null,
    backfilled: history.filter((h) => h.origin === 'wayback').length,
  }
}

// ---------------------------------------------------------------- prediction

export interface TypicalWindow {
  window: Window
  /** Weeks this exact window appeared, out of weeks observed for that weekday. */
  seen: number
  known: number
}

export interface DayOutlook {
  /** ISO date this outlook is for. */
  date: string
  weekday: number
  /** 'posted' when the page actually says; 'expected' when inferred from history. */
  source: 'posted' | 'expected' | 'unknown'
  windows: Window[]
  /** Only set when source === 'expected'. */
  typical?: TypicalWindow[]
  /** Weeks of history behind an expectation. */
  known?: number
  closed?: boolean
}

const key = (w: Window) => `${w[0]}:${w[1]}`

/**
 * The windows a given weekday usually has, by how often each exact window
 * recurs. Reported as counts rather than a blended average, because a schedule
 * is a set of discrete blocks — averaging 6-8am and 12-2pm into 9am-10am would
 * describe a swim time that has never once existed.
 */
export function typicalFor(history: Snapshot[], weekday: number): TypicalWindow[] {
  const days = daysObserved(history)
  const counts = new Map<string, { window: Window; seen: number }>()
  let known = 0

  for (const rec of days.values()) {
    if ((localDate(rec.date).getDay() + 6) % 7 !== weekday) continue
    known++
    const seenThisDay = new Set<string>()
    for (const snap of history) {
      for (const rows of Object.values(snap.parsed.pools)) {
        for (const row of rows as Row[]) {
          if (row.date !== rec.date) continue
          for (const w of row.windows) {
            if (seenThisDay.has(key(w))) continue
            seenThisDay.add(key(w))
            const entry = counts.get(key(w)) ?? { window: w, seen: 0 }
            entry.seen++
            counts.set(key(w), entry)
          }
        }
      }
    }
  }

  return Array.from(counts.values())
    .map((c) => ({ ...c, known }))
    .sort((a, b) => b.seen - a.seen || a.window[0] - b.window[0])
}

/**
 * What to expect for each of the next `span` days.
 *
 * Posted data always wins. History only fills days the page has not covered —
 * the Sunday-evening case, where next week simply isn't up yet — and every day
 * carries which of the two answered, so an expectation is never mistaken for
 * a posted time.
 */
export function outlook(
  history: Snapshot[],
  latest: Snapshot,
  from: Date,
  span = 7,
): DayOutlook[] {
  const posted = new Map<string, { windows: Window[]; closed: boolean }>()
  for (const rows of Object.values(latest.parsed.pools)) {
    for (const row of rows as Row[]) {
      if (!row.date || row.flags.includes('outside_posted_week')) continue
      const prev = posted.get(row.date) ?? { windows: [], closed: true }
      posted.set(row.date, {
        windows: [...prev.windows, ...row.windows],
        closed: prev.closed && row.windows.length === 0,
      })
    }
  }

  const out: DayOutlook[] = []
  for (let i = 0; i < span; i++) {
    const d = new Date(from)
    d.setDate(d.getDate() + i)
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    const weekday = (d.getDay() + 6) % 7
    const hit = posted.get(iso)

    if (hit) {
      out.push({
        date: iso,
        weekday,
        source: 'posted',
        windows: merge(hit.windows),
        closed: hit.closed,
      })
      continue
    }

    const typical = typicalFor(history, weekday)
    const likely = typical.filter((t) => t.known > 0 && t.seen / t.known >= 0.5)
    out.push({
      date: iso,
      weekday,
      source: typical.length ? 'expected' : 'unknown',
      windows: merge(likely.map((t) => t.window)),
      typical: typical.slice(0, 5),
      known: typical[0]?.known ?? 0,
    })
  }
  return out
}

/** Contiguous runs of hours, e.g. [6,7,11,12,16,17] -> [[6,8],[11,13],[16,18]]. */
export function hourBlocks(hours: number[]): Array<[number, number]> {
  const out: Array<[number, number]> = []
  for (const h of [...hours].sort((x, y) => x - y)) {
    const last = out[out.length - 1]
    if (last && h === last[1]) last[1] = h + 1
    else out.push([h, h + 1])
  }
  return out
}

/** Union overlapping windows so two pools' hours don't draw as duplicates. */
export function merge(windows: Window[]): Window[] {
  const sorted = [...windows].sort((a, b) => a[0] - b[0] || a[1] - b[1])
  const out: Window[] = []
  for (const w of sorted) {
    const last = out[out.length - 1]
    if (last && w[0] <= last[1]) last[1] = Math.max(last[1], w[1])
    else out.push([w[0], w[1]])
  }
  return out
}

// -------------------------------------------------------------- pool rhythm

export interface PoolRhythm {
  /** Dates where two pools had overlapping hours. Empty means they alternate. */
  overlapDates: string[]
  /**
   * Hours each pool *usually* covers — the hours where it accounts for more
   * openings than any other pool.
   *
   * Not every hour a pool has ever opened: a single stray Tuesday would
   * otherwise make its range overlap its neighbour's, which reads as a
   * contradiction next to "they never open together". Same-day exclusivity
   * and hours-ever-seen are different claims, and only the first is what
   * overlapDates measures.
   */
  hoursByPool: Record<string, number[]>
  datesObserved: number
}

/**
 * Whether the pools alternate or run together.
 *
 * Worth computing rather than assuming: if they never overlap, a combined
 * "is anything open" view loses nothing, and the pool name is just a
 * consequence of the time of day.
 */
export function poolRhythm(history: Snapshot[]): PoolRhythm {
  const perDate = new Map<string, Map<string, Set<number>>>()
  for (const snap of history) {
    for (const [pool, rows] of Object.entries(snap.parsed.pools)) {
      if (pool === 'Unattributed' || pool === 'Unlabeled') continue
      for (const row of rows as Row[]) {
        if (!row.date || row.flags.includes('outside_posted_week')) continue
        if (!row.windows.length) continue
        const byPool = perDate.get(row.date) ?? new Map<string, Set<number>>()
        const mins = byPool.get(pool) ?? new Set<number>()
        for (const w of row.windows) for (let m = w[0]; m < w[1]; m++) mins.add(m)
        byPool.set(pool, mins)
        perDate.set(row.date, byPool)
      }
    }
  }

  const overlapDates: string[] = []
  // hour -> pool -> how many days that pool was open in that hour
  const tally = new Map<number, Map<string, number>>()
  for (const [date, byPool] of perDate) {
    const sets = Array.from(byPool.entries())
    for (const [pool, mins] of sets) {
      const seen = new Set<number>()
      for (const m of mins) seen.add(Math.floor(m / 60))
      for (const h of seen) {
        const row = tally.get(h) ?? new Map<string, number>()
        row.set(pool, (row.get(pool) ?? 0) + 1)
        tally.set(h, row)
      }
    }
    for (let i = 0; i < sets.length; i++) {
      for (let j = i + 1; j < sets.length; j++) {
        const a = sets[i]![1]
        const b = sets[j]![1]
        if ([...a].some((m) => b.has(m))) {
          overlapDates.push(date)
          i = sets.length
          break
        }
      }
    }
  }

  const owned: Record<string, number[]> = {}
  for (const [hour, row] of tally) {
    let best: string | null = null
    let bestCount = 0
    for (const [pool, count] of row) {
      if (count > bestCount) {
        best = pool
        bestCount = count
      }
    }
    if (best) (owned[best] ??= []).push(hour)
  }
  for (const hours of Object.values(owned)) hours.sort((a, b) => a - b)

  return { overlapDates, hoursByPool: owned, datesObserved: perDate.size }
}

// --------------------------------------------------------------- deviations

/**
 * A posted day that departs from what that weekday normally looks like.
 *
 * The baseline is context; this is the part worth someone's attention. "Tuesday
 * usually has a 6am and this week doesn't" changes whether you set an alarm,
 * in a way that "Tuesday 6am is 83%" never does.
 */
export interface Deviation {
  date: string
  weekday: number
  kind: 'missing' | 'added'
  window: Window
  /** Weeks this window appeared, out of weeks observed for that weekday. */
  seen: number
  known: number
  rate: number
}

/** A window has to be this common before its absence counts as a deviation. */
const USUAL = 0.6
/** A posted window rarer than this counts as an unexpected addition. */
const UNUSUAL = 0.25

function sameWindow(a: Window, b: Window): boolean {
  return a[0] === b[0] && a[1] === b[1]
}

/** The day's windows as posted, without repeats across pools. */
function dedupe(windows: Window[]): Window[] {
  const seen = new Set<string>()
  const out: Window[] = []
  for (const w of windows) {
    const key = `${w[0]}:${w[1]}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push(w)
  }
  return out.sort((a, b) => a[0] - b[0])
}

/** Does any posted window cover this one's ground? Catches shortened slots. */
function covered(posted: Window[], w: Window): boolean {
  return posted.some((p) => p[0] <= w[0] && p[1] >= w[1])
}

/**
 * Compare each posted day against its own weekday's history.
 *
 * Only days the page actually posted are judged — an expectation can't deviate
 * from itself, and flagging unposted days would turn the whole of next week
 * into false alarms.
 */
export function deviations(history: Snapshot[], latest: Snapshot): Deviation[] {
  const out: Deviation[] = []
  const posted = new Map<string, Window[]>()

  for (const rows of Object.values(latest.parsed.pools)) {
    for (const row of rows as Row[]) {
      if (!row.date || row.flags.includes('outside_posted_week')) continue
      // A pool the page never mentioned states nothing; only real postings count.
      if (!row.windows.length && row.closed !== true) continue
      posted.set(row.date, [...(posted.get(row.date) ?? []), ...row.windows])
    }
  }

  for (const [date, windows] of posted) {
    // Merged for the coverage test below, but NOT for spotting additions:
    // merging 11am-12pm with 12pm-1pm invents an 11am-1pm block that no week
    // in history ever contained, which reads as a brand-new slot.
    const merged = merge(windows)
    const distinct = dedupe(windows)
    const weekday = (localDate(date).getDay() + 6) % 7
    // Exclude this same week from its own baseline, or a change that has been
    // up for several checks starts voting for itself.
    const typical = typicalFor(
      history.filter((h) => !coversDate(h, date)),
      weekday,
    )

    for (const t of typical) {
      const rate = t.known ? t.seen / t.known : 0
      if (rate >= USUAL && !covered(merged, t.window)) {
        out.push({ date, weekday, kind: 'missing', window: t.window,
                   seen: t.seen, known: t.known, rate })
      }
    }

    for (const w of distinct) {
      const match = typical.find((t) => sameWindow(t.window, w))
      const rate = match && match.known ? match.seen / match.known : 0
      if (rate < UNUSUAL) {
        out.push({ date, weekday, kind: 'added', window: w,
                   seen: match?.seen ?? 0, known: match?.known ?? typical[0]?.known ?? 0,
                   rate })
      }
    }
  }

  return out.sort((a, b) => a.date.localeCompare(b.date) || a.window[0] - b.window[0])
}

function coversDate(snap: Snapshot, date: string): boolean {
  for (const rows of Object.values(snap.parsed.pools)) {
    for (const row of rows as Row[]) if (row.date === date) return true
  }
  return false
}

// ------------------------------------------------------------ mid-week edits

export interface MidWeekEdit {
  /** Monday of the week that was edited. */
  weekOf: string
  /** When the edit was first seen. */
  seenAt: string
  /** Days into the week the edit landed (0 = Monday). */
  dayIntoWeek: number
  from: string
  to: string
}

/**
 * Schedules that changed after their week had already started.
 *
 * The ordinary rhythm is: post on Sunday or Monday, leave it alone. An edit on
 * Wednesday means something moved under a plan someone had already made, which
 * is the surprise most worth knowing about.
 */
export function midWeekEdits(history: Snapshot[]): MidWeekEdit[] {
  const byWeek = new Map<string, Snapshot[]>()

  for (const snap of history) {
    const dates = []
    for (const rows of Object.values(snap.parsed.pools)) {
      for (const row of rows as Row[]) {
        if (row.date && !row.flags.includes('outside_posted_week')) dates.push(row.date)
      }
    }
    if (!dates.length) continue
    const first = localDate(dates.sort()[0]!)
    first.setDate(first.getDate() - ((first.getDay() + 6) % 7))
    const week = todayKey(first)
    byWeek.set(week, [...(byWeek.get(week) ?? []), snap])
  }

  const edits: MidWeekEdit[] = []
  for (const [week, snaps] of byWeek) {
    const ordered = [...snaps].sort((a, b) => a.checked_at.localeCompare(b.checked_at))
    const monday = localDate(week)
    for (let i = 1; i < ordered.length; i++) {
      const previous = ordered[i - 1]!
      const current = ordered[i]!
      if (previous.content_hash === current.content_hash) continue
      const seen = new Date(current.checked_at)
      const dayIntoWeek = Math.floor(
        (localDate(todayKey(seen)).getTime() - monday.getTime()) / 86_400_000,
      )
      if (dayIntoWeek < 1 || dayIntoWeek > 6) continue // posted before the week began
      edits.push({
        weekOf: week,
        seenAt: current.checked_at,
        dayIntoWeek,
        from: previous.content_hash,
        to: current.content_hash,
      })
    }
  }
  return edits.sort((a, b) => b.seenAt.localeCompare(a.seenAt))
}

function todayKey(d: Date): string {
  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, '0'),
    String(d.getDate()).padStart(2, '0'),
  ].join('-')
}
