
# BKQuiz Frontend

React 18 + Vite frontend for BKQuiz. The visual foundation comes from the original [Figma design](https://www.figma.com/design/IL6nUQrUX7yeuyEaQOZto5/BKQuiz).

## Local development

1. Run the backend on `http://localhost:8080`.
2. Run `npm ci`.
3. Run `npm run dev`.

The frontend calls `/api` and Vite proxies those requests to the backend. Seeing a request such as
`http://localhost:5173/api/auth/login` in DevTools is expected: Vite forwards it to port 8080 without
rewriting the path. Copy `.env.example` to `.env.local` only when you need to override
`VITE_DEV_API_TARGET` or `VITE_API_BASE_URL`.

The frontend sends cookies with API calls. The backend must allow the frontend origin and local development must use `COOKIE_SECURE=false`.

## Cloudflare Pages

Configure this build variable before deploying:

```text
VITE_API_BASE_URL=https://<cloud-run-service-host>/api
VITE_REALTIME_PROVIDER=ably
```

The value is embedded by Vite at build time, so changing it requires a new Pages
deployment. Do not leave it as `/api`: Vite's development proxy does not exist on
Cloudflare Pages and POST requests such as registration would be sent to the
static site and return HTTP 405.

`VITE_REALTIME_PROVIDER=ably` enables the production classroom realtime client.
The browser obtains a short-lived, subscribe-only token from Spring; never put an
Ably API key in any `VITE_*` variable.

Only set `VITE_API_SAME_ORIGIN_PROXY=true` when Cloudflare actually has a Worker
or another reverse proxy forwarding `/api` to Spring. The Spring environment
`FRONTEND_ORIGINS` must contain the exact Pages/custom-domain origin without a
path or trailing slash.

## Quality checks

- `npm test` runs the Vitest and React Testing Library suite once.
- `npm run test:watch` starts interactive test watch mode.
- `npm run typecheck` runs TypeScript in strict mode.
- `npm run lint` runs ESLint without allowing warnings.
- `npm run build` creates the production bundle.
  
