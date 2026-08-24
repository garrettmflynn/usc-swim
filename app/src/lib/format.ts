/** Minutes past midnight -> '6am', '1:30pm'. */
export function clock(min: number): string {
  const h = Math.floor(min / 60)
  const m = min % 60
  const suffix = h < 12 ? 'am' : 'pm'
  return `${h % 12 || 12}${m ? `:${String(m).padStart(2, '0')}` : ''}${suffix}`
}

export function hourLabel(hour: number): string {
  return `${hour % 12 || 12}${hour < 12 ? 'a' : 'p'}`
}

/**
 * Today, according to the device.
 *
 * Deliberately not `latest.coverage.today`: that records the date the *check*
 * ran, so once midnight passes — or the watcher is late — the data still says
 * yesterday. Reading the week from it shifts the whole schedule by a day and
 * labels yesterday "Today", which is exactly the mistake this app exists to
 * stop people making.
 */
export function todayISO(at: Date = new Date()): string {
  return [
    at.getFullYear(),
    String(at.getMonth() + 1).padStart(2, '0'),
    String(at.getDate()).padStart(2, '0'),
  ].join('-')
}

/** Whole days from an ISO date to today; negative means the date is past. */
export function daysFromToday(iso: string, at: Date = new Date()): number {
  const a = localDate(iso).getTime()
  const b = localDate(todayISO(at)).getTime()
  return Math.round((a - b) / 86_400_000)
}

/** Parse a bare ISO date as local noon, so time zones can't shift the day. */
export function localDate(iso: string): Date {
  return new Date(`${iso}T12:00:00`)
}

export function shortDate(iso: string): string {
  return localDate(iso).toLocaleDateString('en-US', { month: 'numeric', day: 'numeric' })
}

export function longDate(iso: string): string {
  return localDate(iso).toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
  })
}

export function stamp(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'numeric', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

export function pct(x: number): string {
  return `${Math.round(x * 100)}%`
}
