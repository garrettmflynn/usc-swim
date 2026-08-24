import type { Latest, Snapshot } from '../types'

/**
 * Surfaces parser trouble, which is otherwise invisible: a scraper that has
 * drifted off its source keeps returning plausible, emptier answers rather
 * than raising anything.
 */
export default function Health({
  latest,
  history,
}: {
  latest: Latest
  history: Snapshot[]
}) {
  const h = latest.parse_health
  if (!h || h.status === 'ok') return null

  const bits: string[] = []
  if (h.unconsumed_total)
    bits.push(
      `${h.unconsumed_total} line${h.unconsumed_total === 1 ? '' : 's'} it didn’t recognise`,
    )
  if (h.unattributed_windows)
    bits.push(
      `${h.unattributed_windows} window${h.unattributed_windows === 1 ? '' : 's'} with no pool named`,
    )

  const unhealthy = history.filter(
    (e) => e.parse_health && e.parse_health.status !== 'ok',
  ).length

  return (
    <aside className={`health ${h.status}`} role="status">
      <p>
        <b>
          {h.status === 'failed'
            ? 'The parser understood nothing on this check.'
            : 'Parsed with warnings.'}
        </b>{' '}
        {bits.join(', ')}
        {bits.length ? '. ' : ''}
        Read {h.rows} rows across {h.pools} pool{h.pools === 1 ? '' : 's'},{' '}
        {h.windows} swim windows.
      </p>
      {h.unconsumed.length > 0 && (
        <p className="lines">
          {h.unconsumed.map((line) => (
            <code key={line}>{line}</code>
          ))}
        </p>
      )}
      <p className="why">
        {unhealthy} of {history.length} recorded snapshots parsed less than
        cleanly. Every snapshot keeps its raw HTML, so a fixed parser can replay
        the whole history rather than losing it.
      </p>
      {h.anomaly_rows > 0 && (
        <p className="why">
          Separately, {h.anomaly_rows} row{h.anomaly_rows === 1 ? '' : 's'} look
          wrong at the source — a date that doesn’t match its weekday, or one
          from another week. Those are their typos, not a parser fault.
        </p>
      )}
    </aside>
  )
}
