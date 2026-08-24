import type { Latest, Snapshot, Stats } from '../types'

/**
 * The dataset is fetched at runtime rather than imported at build time.
 *
 * The hourly workflow commits new JSON without rebuilding the app, so bundling
 * the data would pin the dashboard to whatever was true when it was last
 * built — the one thing this project must never do.
 */
async function get<T>(name: string): Promise<T> {
  const res = await fetch(`data/${name}.json`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`${name}.json — ${res.status}`)
  return res.json() as Promise<T>
}

export interface Dataset {
  latest: Latest
  history: Snapshot[]
  stats: Stats
}

export async function loadDataset(): Promise<Dataset> {
  const [latest, history, stats] = await Promise.all([
    get<Latest>('latest'),
    get<Snapshot[]>('history'),
    get<Stats>('stats'),
  ])
  return { latest, history, stats }
}
