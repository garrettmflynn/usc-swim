/// <reference lib="webworker" />
import { cleanupOutdatedCaches, precacheAndRoute } from 'workbox-precaching'

declare const self: ServiceWorkerGlobalScope

cleanupOutdatedCaches()
precacheAndRoute(self.__WB_MANIFEST)

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') void self.skipWaiting()
})

/**
 * The dataset is never served from cache — a stale schedule is worse than no
 * schedule. Network first, and only fall back to the last response if the
 * device is offline, in which case the UI shows how old it is.
 */
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  if (event.request.method !== 'GET' || !url.pathname.includes('/data/')) return

  event.respondWith(
    (async () => {
      const cache = await caches.open('swimwatch-data')
      try {
        const fresh = await fetch(event.request, { cache: 'no-store' })
        if (fresh.ok) await cache.put(event.request, fresh.clone())
        return fresh
      } catch (err) {
        const cached = await cache.match(event.request)
        if (cached) return cached
        throw err
      }
    })(),
  )
})

interface PushBody {
  title?: string
  body?: string
  url?: string
  tag?: string
}

self.addEventListener('push', (event) => {
  let payload: PushBody = {}
  try {
    payload = (event.data?.json() as PushBody) ?? {}
  } catch {
    payload = { body: event.data?.text() }
  }

  event.waitUntil(
    self.registration.showNotification(payload.title ?? 'Swim hours changed', {
      body: payload.body ?? 'They posted a new schedule.',
      icon: 'icon-192.png',
      badge: 'icon-192.png',
      tag: payload.tag ?? 'swimwatch-change',
      renotify: true,
      data: { url: payload.url ?? './' },
    } as NotificationOptions),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = (event.notification.data as { url?: string } | undefined)?.url ?? './'
  event.waitUntil(
    (async () => {
      const clients = await self.clients.matchAll({
        type: 'window',
        includeUncontrolled: true,
      })
      for (const client of clients) {
        if ('focus' in client) return client.focus()
      }
      return self.clients.openWindow(target)
    })(),
  )
})
