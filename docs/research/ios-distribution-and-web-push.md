# iOS distribution options (EU, no paid Apple account) and Web Push reliability

Research for [#6](https://github.com/webstriker-lab/forexcast/issues/6). Researched 2026-09-11.

## TL;DR

- **Only zero-cost, durable option on iPhone: installable PWA** (Add to Home Screen). Every native route (TestFlight, EU marketplaces incl. AltStore PAL, Web Distribution) needs a **paid** Apple Developer Program membership, because apps must be notarized/signed by a program member.
- **Free Apple ID sideload (Xcode or AltStore Classic) works but is a dev toy**: profiles expire every 7 days, max 3 apps per device, 3 devices.
- **Web Push on iOS 16.4+ works for home-screen web apps** using standard Push API + VAPID; no Apple account needed. Gotchas: must be installed to Home Screen, permission only from a user gesture, every push must show a visible notification (no silent push), not available in Safari tabs on iOS.
- **Android: Capacitor** wraps the existing Vite `dist/` as-is. Expo would mean a React Native app (DOM components are an escape hatch, not a drop-in for a whole Vite SPA).

## iOS options compared

| Option | Paid account? | Durability | Notes | Source |
|---|---|---|---|---|
| PWA (Add to Home Screen) | No | Permanent | Manifest `display: standalone`; supports Web Push + Badging | [WebKit blog: Web Push for Web Apps on iOS](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/) |
| Xcode sideload, free Apple ID (Personal Team) | No | **7 days**, then rebuild/reinstall | 3 apps/device, 3 devices, 10 App IDs (also expiring); needs a Mac + native wrapper (e.g. Capacitor iOS) | [Apple: Compare memberships](https://developer.apple.com/support/compare-memberships/) |
| AltStore Classic | No (free Apple ID) | 7 days, auto-refresh via AltServer on a computer | Same Apple limits: 3 sideloaded apps | [AltStore FAQ: Classic](https://faq.altstore.io/altstore-classic/your-altstore) |
| AltStore PAL / other EU alt marketplaces | **Yes** (developer must be ADP member; app must be notarized under Alternative Terms) | Permanent | PAL available in EU, Japan, Brazil; installs notarized apps only | [AltStore FAQ: PAL](https://faq.altstore.io/altstore-pal/what-is-altstore-pal), [Apple: Alt marketplaces in EU](https://developer.apple.com/support/alternative-app-marketplace-in-the-eu/) |
| TestFlight | **Yes** | 90-day builds | TestFlight is a paid-membership feature | [Apple: Compare memberships](https://developer.apple.com/support/compare-memberships/) |

Note: in early 2024 Apple briefly planned to drop Home Screen web apps in the EU (iOS 17.4) and reversed that decision; EU PWAs keep working (Apple developer news, Mar 2024).

## Web Push on iOS 16.4+ — reliability and gotchas

Source: [WebKit blog](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/), [Apple: Sending web push notifications](https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers).

- Works only for web apps **added to the Home Screen** with a manifest (`standalone`/`fullscreen`). Not in a normal Safari tab on iPhone.
- `Notification.requestPermission()` / `pushManager.subscribe()` must be triggered by a **direct user interaction** (e.g. a "Enable alerts" button).
- `userVisibleOnly: true` is mandatory; **every push must display a notification**. Pushes that don't show one can get the subscription's push permission revoked. So: no silent/background data pushes — design alerts as always-visible.
- Standard VAPID Web Push; endpoints are on `*.push.apple.com` — allowlist it if the backend restricts egress. Existing `web-push`/`pywebpush` libraries work.
- Delivery is best-effort (TTL/urgency honoured, Focus modes may hold notifications). Users can disable per-app in Settings > Notifications. Subscriptions can disappear if the user deletes the home-screen icon — handle `410 Gone` by deleting the subscription server-side.
- Badging API supported for icon badge counts.
- Practical implication for ForexCast: rate alerts via Web Push are viable on iOS as long as onboarding tells iPhone users to install first, then tap "Enable alerts".

## Android: Capacitor vs Expo

| | Capacitor | Expo |
|---|---|---|
| Reuse `frontend/` | Yes, as-is: `npm i @capacitor/core @capacitor/cli @capacitor/android`, `npx cap init` with `webDir: dist`, `npx cap add android`, `npm run build && npx cap sync` | UI must be React Native; `'use dom'` DOM components can embed web components in a WebView incrementally, but no `children`, async JSON bridge, no shared global state |
| Effort | Hours | Rewrite (weeks) or awkward hybrid |
| Push | FCM via `@capacitor/push-notifications` (or keep Web Push inside the WebView/TWA) | expo-notifications |
| Sources | [Capacitor: Getting started](https://capacitorjs.com/docs/getting-started) | [Expo: DOM components](https://docs.expo.dev/guides/dom-components/) |

Also viable for Android with zero wrapper: the PWA itself is installable in Chrome and supports Web Push natively.

## Recommendation

1. Ship ForexCast as a proper PWA (manifest, service worker, Web Push with VAPID) — covers iPhone and Android for free.
2. If a Play Store/APK is wanted, use **Capacitor** over the existing Vite build.
3. Don't pursue native iOS distribution unless paying the €99/yr ADP fee; free sideloading's 7-day expiry makes it unsuitable for daily use.
