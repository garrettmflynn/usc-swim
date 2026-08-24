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
