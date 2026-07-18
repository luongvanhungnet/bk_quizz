
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

## Quality checks

- `npm test` runs the Vitest and React Testing Library suite once.
- `npm run test:watch` starts interactive test watch mode.
- `npm run typecheck` runs TypeScript in strict mode.
- `npm run lint` runs ESLint without allowing warnings.
- `npm run build` creates the production bundle.
  
