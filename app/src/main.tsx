import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import App from './App'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

// Update in the background; the next launch gets the new build.
registerSW({ immediate: true })

/**
 * Refuse pinch- and double-tap-zoom.
 *
 * iOS Safari deliberately ignores `user-scalable=no` in the viewport meta, so
 * the gestures have to be declined here. `touch-action: pan-x pan-y` in the
 * stylesheet stops most of it; these cover Safari's own gesture events and the
 * double-tap, which touch-action alone doesn't catch on older iOS.
 *
 * This does remove the browser's zoom. It's a deliberate call for a
 * fixed-layout app that has to hold still while you read a schedule with wet
 * hands — the type is sized for phones rather than relying on the reader to
 * zoom, and the OS-level display-size and accessibility-zoom settings still
 * apply.
 */
for (const type of ['gesturestart', 'gesturechange', 'gestureend']) {
  document.addEventListener(type, (event) => event.preventDefault(), { passive: false })
}

let lastTouch = 0
document.addEventListener(
  'touchend',
  (event) => {
    const now = Date.now()
    if (now - lastTouch <= 300) event.preventDefault()
    lastTouch = now
  },
  { passive: false },
)
