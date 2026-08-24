/**
 * Web Push enrollment.
 *
 * There is no backend: the site is static on GitHub Pages. So a subscription
 * is created here and then has to reach the sender by hand, once per device —
 * the Settings view shows it for copying, and it goes into the repository
 * secret the notify workflow reads. Two people with a couple of devices each
 * is entirely workable; a Cloudflare Worker would be the upgrade if this ever
 * needs to be self-serve.
 */

export type PushState =
  | 'unsupported'
  | 'needs-install'
  | 'denied'
  | 'ready'
  | 'subscribed'

export function pushSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

/** iOS only exposes Push once the site is installed to the home screen. */
export function needsInstall(): boolean {
  const iOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
  const standalone =
    window.matchMedia('(display-mode: standalone)').matches ||
    (navigator as { standalone?: boolean }).standalone === true
  return iOS && !standalone
}

export async function currentState(): Promise<PushState> {
  if (!pushSupported()) return needsInstall() ? 'needs-install' : 'unsupported'
  if (needsInstall()) return 'needs-install'
  if (Notification.permission === 'denied') return 'denied'
  const reg = await navigator.serviceWorker.getRegistration()
  const sub = await reg?.pushManager.getSubscription()
  return sub ? 'subscribed' : 'ready'
}

function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=')
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'))
  const bytes = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i)
  return bytes
}

export async function subscribe(vapidPublicKey: string): Promise<PushSubscription> {
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') throw new Error(`Notifications ${permission}`)

  const reg = await navigator.serviceWorker.ready
  const existing = await reg.pushManager.getSubscription()
  if (existing) return existing

  return reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
  })
}

export async function unsubscribe(): Promise<void> {
  const reg = await navigator.serviceWorker.getRegistration()
  const sub = await reg?.pushManager.getSubscription()
  await sub?.unsubscribe()
}

export async function getSubscription(): Promise<PushSubscription | null> {
  const reg = await navigator.serviceWorker.getRegistration()
  return (await reg?.pushManager.getSubscription()) ?? null
}
