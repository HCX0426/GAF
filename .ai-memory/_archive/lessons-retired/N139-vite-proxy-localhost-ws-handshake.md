---
date: 2026-07-02
id: N139
category: dev-env
symptom: [vite, websocket, proxy, localhost, handshake, 500]
solution: Change Vite proxy target from `localhost` to `127.0.0.1` for both `/api` and `/ws` routes on Windows to avoid IPv6/IPv4 resolution ambiguity.
root_cause: Vite dev server proxy target `ws://localhost:8000` may resolve `localhost` to IPv6 ::1 while Django runserver binds to IPv4 127.0.0.1, causing WebSocket handshake failures (HTTP 500 or connection refused) in the browser even though direct `ws://127.0.0.1:8000/ws/.../` works.
fix: Change Vite proxy target from `localhost` to `127.0.0.1` for both `/api` and `/ws` routes.
prevention: Always use explicit `127.0.0.1` loopback address in dev proxy configs on Windows to avoid IPv6/IPv4 resolution ambiguity.
related_files:
  - frontend/vite.config.ts
  - frontend/src/websocket/client.ts
  - frontend/src/hooks/useNotificationWebSocket.ts
created_by: AI
added_at: 2026-07-02
example_commit: '-'
level: L1
n_id: N139
topic: platform-env
---

# N139 — Vite dev proxy `localhost` causes WebSocket handshake failures

## Symptom

After implementing a frontend WebSocket consumer (e.g. notification audio alerts), the browser console shows:

```
WebSocket connection to 'ws://127.0.0.1:5173/ws/dashboard' failed:
Error during WebSocket handshake: Unexpected response code: 500
```

Direct connection from Python `websockets.connect('ws://127.0.0.1:8000/ws/dashboard/')` succeeds.

## Root Cause

`vite.config.ts` configured the WebSocket proxy as:

```ts
'/ws': {
  target: 'ws://localhost:8000',
  ws: true,
}
```

On Windows, `localhost` may resolve to IPv6 `::1` while Django `runserver` binds to IPv4 `127.0.0.1`. Vite forwards the WS upgrade to the wrong address, resulting in a failed handshake.

## Fix

Use the explicit IPv4 loopback address:

```ts
'/ws': {
  target: 'ws://127.0.0.1:8000',
  ws: true,
}
```

Apply the same change to `/api` proxy for consistency.

## Prevention

- Default dev proxy targets to `127.0.0.1` instead of `localhost`.
- When debugging WS handshake errors, test direct connection to backend IP first to isolate proxy vs consumer issues.

## Related Files

- [frontend/vite.config.ts](file:///d:/code/AUTO_PROJECTS/GAF/frontend/vite.config.ts)
- [frontend/src/websocket/client.ts](file:///d:/code/AUTO_PROJECTS/GAF/frontend/src/websocket/client.ts)
- [frontend/src/hooks/useNotificationWebSocket.ts](file:///d:/code/AUTO_PROJECTS/GAF/frontend/src/hooks/useNotificationWebSocket.ts)
