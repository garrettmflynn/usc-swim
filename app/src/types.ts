/** Shapes written by scrape.py and backfill.py into docs/data/. */

export type Flag =
  | 'outside_posted_week'
  | 'weekday_date_mismatch'
  | 'unparsed_date'
  | 'not_mentioned'

/** Minutes past midnight, [start, end). */
export type Window = [number, number]

export interface Row {
  weekday: string
  date: string | null
  raw: string
  windows: Window[]
  /**
   * Three states, deliberately. `null` means the page never mentioned this
   * pool that day — which is not the same as it saying the pool was closed,
   * and must never be counted as evidence of a closure.
   */
  closed: boolean | null
  flags: Flag[]
}

export interface Parsed {
  updated_label: string | null
  pools: Record<string, Row[]>
  unconsumed?: string[]
}

export interface Coverage {
  today: string
  today_covered: boolean
  posted_through: string | null
  days_past_end: number | null
  swimmable_today: number | null
}

export interface ParseHealth {
  status: 'ok' | 'degraded' | 'failed'
  pools: number
  rows: number
  windows: number
  anomaly_rows: number
  unattributed_windows: number
  unconsumed: string[]
  unconsumed_total: number
}

/** Who wrote a data file, and when. Stamped by scrape.py / backfill.py. */
export interface Generator {
  tool: string
  version: string
  git_sha?: string
  written_at: string
}

export interface Snapshot {
  checked_at: string
  content_hash: string
  parsed: Parsed
  coverage: Coverage
  parse_health?: ParseHealth
  /** 'wayback' entries are recovered from the archive, not observed live. */
  origin?: 'live' | 'wayback'
  source?: string
}

export interface Latest extends Snapshot {
  source: string
  conditional_304: boolean
  raw_block?: string
  generator?: Generator
}

export interface WeekLag {
  week_of: string
  first_seen: string
  lag_hours: number
  censored: boolean
}

export interface Stats {
  checks_total: number
  changes_total: number
  checks_with_today_covered: number
  coverage_rate: number | null
  median_post_lag_hours: number | null
  weeks: WeekLag[]
}
