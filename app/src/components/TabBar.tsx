import { Activity, CalendarDays, Settings2, Waves } from 'lucide-react'

export type Tab = 'week' | 'patterns' | 'activity' | 'settings'

const TABS = [
  { id: 'week', label: 'Week', Icon: CalendarDays },
  { id: 'patterns', label: 'Patterns', Icon: Waves },
  { id: 'activity', label: 'Activity', Icon: Activity },
  { id: 'settings', label: 'Settings', Icon: Settings2 },
] as const satisfies ReadonlyArray<{ id: Tab; label: string; Icon: typeof Waves }>

export default function TabBar({
  active,
  onChange,
}: {
  active: Tab
  onChange: (t: Tab) => void
}) {
  return (
    <nav className="tabbar" aria-label="Sections">
      {TABS.map(({ id, label, Icon }) => (
        <button
          key={id}
          type="button"
          className={active === id ? 'on' : ''}
          aria-current={active === id ? 'page' : undefined}
          onClick={() => onChange(id)}
        >
          <Icon size={20} strokeWidth={active === id ? 2.2 : 1.7} aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  )
}
