# Day 1 — Product orientation & app skeleton

## What I set up
- **Vite** scaffolds the project: `npm create vite@latest` (chose React + TypeScript). Vite compiles React+TS into browser-ready JavaScript and runs the dev server.
- Run the dev server with `npm run dev`.

## How a React app starts (the chain)
- `index.html` contains an **empty** `<div id="root">` and a `<script>` that loads `main.tsx`.
- `main.tsx` reaches back into the page, finds that empty `#root` div with `document.getElementById('root')`, and injects `<App />` into it via `createRoot(...).render()`.
- `App.tsx` is the actual UI (a component — a function returning JSX). The screen I see in the browser comes from here, not from index.html.
- Direction matters: the div is passive; **main.tsx grabs the div and fills it**.

## Route map (URL → screen)
```
/login                    →  <LoginPage />
/dashboard                →  <DashboardPage />
/documents                →  <DocumentsPage />
/documents/:documentId    →  <DocumentDetailPage />
/chat                     →  <ChatPage />
/actions                  →  <ActionsPage />
/settings                 →  <SettingsPage />
```

## Key concepts
- **Component:** a function that returns UI (JSX). Used as `<App />`.
- **Route parameter:** `:documentId` is a variable segment — one route handles every document (`/documents/42`), the same idea as FastAPI's `{document_id}`. Can't write a separate route per document.
- **PascalCase components:** React uses the capital letter to tell components apart from plain HTML tags — `<LoginPage />`, not `<loginpage />`.

# Day 2 — Web fundamentals & typed models

## Semantic HTML

- **Meaning:** using a *descriptive* element that says what the content is (`<header>`, `<nav>`, `<button>`) instead of a generic, meaningless `<div>`.
- **Why `<button>` over a styled `<div>`:** a real `<button>` comes with built-in behaviour that assistive tech and keyboards depend on — screen readers announce it as a button, `Tab` reaches it, `Enter`/`Space` activate it — all without manual JavaScript. A styled `<div>` is invisible to keyboard and screen-reader users. Accessibility is the headline reason; code readability is the bonus.
- **App shell regions:** `<header>` (top bar — app title, user menu), `<nav>` (left sidebar — links to the screens), `<main>` (the area where the active route's page renders).

## CSS refresh

- **Box model (inside → out):** content → padding → border → margin.
- **`box-sizing: border-box`:** makes `width` include padding and border, so an element doesn't render wider than the value I set. Keeps layout sizing predictable. Applied globally to `*, *::before, *::after`.
- **Flex vs Grid:** Flexbox for one-dimensional layouts (a single row or column); Grid for two-dimensional (rows *and* columns at once). Rule of thumb: **grid for the page skeleton, flex for the contents inside each region.**
- **Custom properties (CSS variables):** define a small spacing/type scale once (`--space-md`, `--text-base`) and reference it everywhere, instead of scattering magic numbers. Gives visual consistency and lets me change a value in one place. They're live and overridable (which is how the dark-mode block re-themes by swapping variable values).

## Typed product models

- **Keywords:** `interface` (or `type`) to describe an object's shape; `type` + literal values (`'user' | 'assistant'`) to define a named union.
- **`?`** after a field name = optional (may be `undefined`). A list of Messages = `Message[]`.
- **Ordering:** a union/interface must be defined *before* anything that references it (`Sender` above `Message`; `Message` above `Chat`).
- **Why `password` is NOT on the frontend `User`:** the password is typed once into the login form, sent to the server to be checked, and never comes back — the server stores only a hash and never returns it. Holding it in the browser (state, logs, API payloads) would be a secret lying around for no reason. The DB has `passwordHash`; the API's `User` omits it.
- **`id` and date field types — the rule:** the frontend type must match what the backend's API contract actually returns. IDs → `string` (UUIDs). Timestamps → `string`, because **JSON has no date type** — the API sends ISO strings like `"2026-06-17T09:30:00Z"`. If a component needs a real `Date`, it parses the string locally; that's a derived value, not the contract shape.

## Techniques / habits

- **Linter (ESLint) vs TypeScript:** TypeScript checks *type/structural* correctness (right data shapes). ESLint checks *code quality* — unused variables, dead code, style — independent of types. Run both. Clean lint run = no output. Habit: keep warnings at zero so a *new* one stands out.
- **`min-height: 100vh; min-height: 100svh;`** — a fallback / progressive-enhancement technique. The last *valid* declaration wins: old browsers don't understand `svh` and keep `100vh`; modern browsers apply `100svh`, which measures the *actually visible* area (accounting for the mobile address bar, where `100vh` overflows).

## Decisions I made

- **`Task`: simple `done: boolean` over a discriminated union** — the boolean answers the yes/no directly, and `completedAt?` (optional) carries the timestamp only when done. The discriminated union is more type-safe but more complex; adopt advanced patterns when the simple one starts hurting — it isn't hurting here.
- **Date fields: plain `string` over `Date | string`** — the contract only ever returns ISO strings (JSON has no date type), so a `Date | string` union would force every use site to handle both cases for no benefit. Parsing to a `Date` is a local concern, not the model shape.
- **`--space-lg: 20px` over `24px`** — kept the template's value deliberately. Trade-off: the scale `4, 8, 16, 20, 32` isn't a uniform doubling rhythm, so I check the scale when reaching for spacing rather than assuming each step doubles.

## What I built (deliverables)

- `src/types.ts` — six exported models (`User`, `Document`, `Chat`, `Message`, `Action`, `Task`) + three named unions (`Sender`, `DocumentStatus`, `ActionStatus`).
- `index.css` — spacing + type scales as custom properties, base resets (`border-box`, `body` margin 0, base font), and the `.app-shell` grid primitive (`grid-template-areas` topology, to be claimed by Day 3's components).
- ESLint run clean (`npm run lint` → no output).


---

# Day 3 — App shell: components, props, composition

## Components & composition
- **Component:** a reusable JavaScript function that accepts inputs (props) and returns UI via JSX.
- **Composition:** building complex UIs by nesting smaller, focused components inside larger wrappers, instead of one massive file. `Layout` was assembled this way:
  - **Assembly** — imported `<Header />` and `<Sidebar />` as autonomous blocks and used them like custom tags, rather than rebuilding a nav/brand bar from scratch.
  - **The `children` hole** — `{children}` inside `<main>` leaves a structural gap, making `Layout` a blank frame that wraps any page.
  - **One-way data flow** — `Layout` coordinates: it holds config (the `navLinks` array) and passes it down via `<Sidebar links={navLinks} />`.
- **Why it's NOT OOP inheritance:** inheritance is an *is-a* relationship (subclass extends a base); React is *has-a* — object composition. The parent doesn't absorb or extend the child's identity; it manages, configures, and houses it. A "parent" just renders a "child" and hands it arguments.

## Props
- **What a prop is:** a function argument. `<Sidebar links={navLinks} />` is like calling `sidebar(links=navLinks)`.
- **Hard rule:** props are read-only inside the child — it reads and renders them but never reassigns/mutates them.
- **Direction:** data flows strictly one way, parent → child (down).

## The `children` prop
- **What it is:** an automatically-provided prop capturing whatever is nested between a component's opening and closing tags. Lets a component be a flexible wrapper without knowing its contents in advance.
- **`<Layout><h1>Dashboard</h1></Layout>`** → the `<h1>` arrives inside `Layout` as its `children` prop.
- **Type:** `React.ReactNode` — "any valid renderable UI" (elements, strings, numbers, components, arrays of these).

## Rendering a list
- **Why `.map()` not hardcoded `<li>`s:** `.map()` turns a data array into an array of UI elements, so `Sidebar` is data-driven — links can change/grow without editing the JSX.
- **`key`:** a stable, unique identity per list item so React can efficiently track/add/update/reorder items instead of re-rendering the whole list. Used `key={link.to}` (routes are unique).

## Grid wiring (Day 2 promise kept)
- Naming regions with `grid-template-areas` on the container is only the blueprint; **each child needs its own `grid-area: <name>` rule** to claim its spot. Wrote `.app-header`, `.app-sidebar`, and `grid-area: main` on `.main-content`.
- **Source order is irrelevant for placement:** each element is positioned by its named `grid-area`, so rendering `<Sidebar />` before `<Header />` in the JSX doesn't change where they appear. (Source order still governs DOM order, keyboard focus, and screen-reader reading order — grid only overrides *visual* placement.)

## Decisions / techniques
- **`import type { NavLink }` over plain `import`** — (1) tells the build it's type-only so it's stripped from the production bundle (no ghost code); (2) satisfies the `consistent-type-imports` ESLint rule. (`import React` stays a normal import — React is runtime code.)
- **`<a href>` in sidebar links is a placeholder** — a plain `<a>` triggers a full page reload, wiping app state. Day 4 replaces it with a client-side router component (`<Link>` / `<NavLink>`) that swaps pages instantly without reload.
- **Known smell to revisit:** `navLinks` currently lives *inside* `Layout`, so the layout component also owns app data (two jobs mixed). Candidate to lift up to `App` or a config file later and pass into `Layout` as a prop.

## What I built (deliverables)
- `types.ts` — added the `NavLink` interface (label + to) alongside the Day 2 models.
- `Header.tsx` — semantic `<header className="app-header">`; brand + profile, laid out with flex.
- `Sidebar.tsx` — semantic `<nav className="app-sidebar">`; receives `links` via props and `.map()`s over them with `key`.
- `Layout.tsx` — the app-shell grid container; composes `Header` + `Sidebar`, holds `navLinks`, wraps arbitrary pages via `children`.
- `App.tsx` — renders `<Layout>` with a page nested as children (the consuming side of the `children` contract).
- Verified rendering: header / sidebar / main appear in three correct regions in the browser.
- _Pending (cosmetic):_ region styling for the bare classes (`.app-header`, `.app-sidebar`, `.sidebar-links`, etc.) using Day 2 tokens.

---

# Day 4 — Routing

## Client-side routing
- **What it does:** intercepts the browser's native navigation. Instead of fetching a new HTML file from the server on every URL change, JS running in the browser watches the URL, unmounts the current page component, and mounts the matching one — no server round-trip, no reload, no lost state.
- **`<Link>` vs `<a href>`:** `<a href>` triggers a full browser navigation — discards JS state and refetches the whole page. `<Link>` prevents that default, updates the URL via the history API, and tells the router to swap components instantly. Use `<Link>` for internal navigation.

## The version gotcha
- On **v7.16** (what I installed), imports come from `react-router`. The old `react-router-dom` is a leftover v6→v7 compatibility shim — fully removed in v8. Most online tutorials still say `react-router-dom`; copying that breaks. Core APIs (`BrowserRouter`, `Routes`, `Route`, `Link`, `useParams`, `Outlet`, `Navigate`) all import from `react-router`.

## The pieces
- **`<BrowserRouter>`:** the context that syncs the UI with the browser's URL/history. Goes at the top in `main.tsx` wrapping `<App />`, so the whole component tree below it has routing access. (It's where `<App />` is injected into `#root`, so wrapping there covers everything.)
- **`<Routes>` / `<Route>`:** `<Routes>` works like a switch — it reads the URL and renders the *one* matching `<Route>`. On a `<Route>`, `path` is the URL pattern, `element` is the component to render when it matches.

## Nesting & layout (the Day 3 bridge)
- **`<Outlet />`:** the placeholder where the matched child route renders. It's the router-driven version of Day 3's `children` hole.
- **Difference from `children`:** `children` was filled manually by whoever wrote `<Layout>…</Layout>`; `<Outlet />` is filled automatically by the router based on which child route matches the URL. Same "hole where the page goes," but the router fills it now.
- **Why `/login` sits outside the `Layout` branch:** an unauthenticated user shouldn't see the shell (sidebar links, user header). Keeping `/login` as a bare top-level route gives a clean full-screen page; all shell pages nest under the `Layout` parent route.

## Params & extras
- **`useParams`:** a hook that reads dynamic segments from the URL. The destructured key must match the route's token name exactly (`:documentId` → `{ documentId }`), or it's `undefined`. The value is always a **string** (URLs are text); convert with `Number(...)` if a number is needed.
- **Index route:** what renders when the URL is exactly the parent path (`/`). Mine is `<Navigate to="/dashboard" replace />` — forwards `/` to the canonical `/dashboard`. `replace` overwrites the history entry instead of pushing one, so the back button doesn't bounce between `/` and `/dashboard`.
- **`path="*"`:** catch-all for any unmatched URL (typos, unknown paths) — renders the 404 page instead of a blank screen.

## Decisions I made
- **Dashboard canonical URL:** `/dashboard` is the real route; `/` redirects to it via the index route. One canonical URL, not two.
- **404 placement:** nested *inside* the `Layout` branch, so a lost user keeps the header/sidebar to navigate back out.
- **Sidebar coverage:** started with 3 links (Dashboard/Documents/Settings), then expanded `navLinks` to all 5 app pages once their routes existed, so every routed shell page is reachable. `/login` (outside the shell) and `/documents/:documentId` (reached by clicking a document, not nav) are deliberately excluded.

## What I built (deliverables)
- `main.tsx` *(modified)* — wrapped `<App />` in `<BrowserRouter>` to switch routing on.
- `App.tsx` *(modified)* — the route table: bare `/login` branch + nested `Layout` branch (index redirect, page routes, `:documentId` param route, `path="*"` 404).
- `Layout.tsx` *(modified)* — replaced `children`/`LayoutProps` with `<Outlet />`; expanded `navLinks` to 5 pages.
- `Sidebar.tsx` *(modified)* — swapped `<a href>` for `<Link to>` (no-reload navigation).
- `src/pages/` *(created)* — 8 stub pages: Login, Dashboard, Documents, DocumentDetail (reads `:documentId` via `useParams`), Chat, Actions, Settings, NotFound.
- Verified live: URL drives the page, navigation swaps without reload, `/documents/<anything>` renders the id, bad URLs hit the 404.

---

# Day 5 — Mock API foundation (MSW)

## Mock layer concept
- **What MSW does differently:** instead of swapping out functions to return canned data, MSW registers a **Service Worker** that intercepts real outgoing `fetch` calls at the browser's network layer. So my UI code makes genuine network requests — written exactly as they'll be in Month 2. When Spring Boot is ready, I turn MSW off and the frontend is untouched, because it was already doing real fetches.
- **The three setup pieces:**
  - `public/mockServiceWorker.js` — static script (generated by `npx msw init public --save`) that the browser registers as the interception proxy. Not hand-written.
  - `src/mocks/browser.ts` — imports the handlers and builds the worker via `setupWorker(...handlers)` (from `msw/browser`).
  - `main.tsx` startup — an async `enableMocking()` that awaits `worker.start()` before rendering, and only runs in dev (`import.meta.env.DEV`).
- **Why await `start()` before rendering:** registering a Service Worker is async. If I don't await it, components mount and fire their first fetches before the interceptor is ready — a race condition where requests slip past the mock. Awaiting defers render until the worker is live.

## Architecture & contract
- **Why split `db.ts` from `handlers.ts`:** mirrors a controller/database split. `db.ts` holds the mutable, typed sample records; `handlers.ts` handles HTTP mechanics — URL matching, params, delays, status codes. Adding sample data is a different concern from changing endpoint behavior.
- **Why type sample data as `Document[]` and errors as `APIError`:** the annotations enforce the contract at compile time. If a model changes, TypeScript breaks the mock files until they realign — so the fake data can never drift from the real shape the components expect.
- **The `?scenario` toggle — and why it's NOT in the contract:** a client-side test hook to force edge cases (500, empty). It's deliberately excluded from the API contract because it's test scaffolding — the real backend should never know it exists, so the UI never depends on a param the real server can't replicate. Clean `fetch('/api/documents')` (no scenario) is what production code always sends; `null` falls through to the happy path.
- **Why one error envelope (`APIError`) now:** committing to `{ message, code? }` early means every component reads `error.message` uniformly, and the Month 2 backend gets one error shape to implement. `message` is the always-present guarantee; optional `code` (e.g. `DOCUMENT_NOT_FOUND`) is a machine-readable token the UI can branch on instead of parsing text.

## Mechanics
- **Latency:** make the resolver `async` and `await delay(ms)` before returning. Lets me build/see real loading states next week, because the data genuinely takes time.
- **The five modes:**
  - Latency — `await delay()` in the resolver.
  - Success — clean request → `200` + `mockDocuments`.
  - Validation error — a sentinel param (`/invalid-id-test`) → typed `APIError`, `400`.
  - Empty state — `?scenario=empty` → `[]`.
  - Server failure — `?scenario=error` → bodyless `500`.
- **Testing with no UI:** fire requests manually in the DevTools console, e.g. `fetch('/api/documents').then(r => r.json()).then(console.log)`. MSW intercepts it at the network layer like any other fetch, so I can inspect the JSON and status codes directly. Verified all five modes plus a 404 this way.

## Techniques / gotchas
- **Case-sensitive imports:** my types file is `Type.ts`. macOS/Windows file systems are case-*insensitive*, so `'./types'` and `'./Type'` both resolve locally — but Linux (CI, deploy servers) is case-*sensitive* and one of them won't exist. File names and import paths must match exactly. Habit when keeping a non-standard name: grep for stray lowercase `'./types'` imports, since the local machine won't catch the mismatch.

## What I built (deliverables)
- `public/mockServiceWorker.js` *(created)* — the network-interception worker script.
- `Type.ts` *(modified)* — added the `APIError` interface (`message`, optional `code`).
- `main.tsx` *(modified)* — `enableMocking()` async wrapper; awaits the worker before rendering, dev-only.
- `src/mocks/browser.ts` *(created)* — `setupWorker(...handlers)`.
- `src/mocks/db.ts` *(created)* — typed `mockDocuments: Document[]` sample data.
- `src/mocks/handlers.ts` *(created)* — `/api/health`, `GET /api/documents` (latency + success/empty/error toggles), `GET /api/documents/:id` (success/400/404), errors typed against `APIError`.
- Verified live in console: all five modes + 404 fire correctly.
- _Open action:_ confirm every import of the types file uses the canonical `'./Type'` casing (grep should return no lowercase `'./types'`).

---

# Day 6 — Authentication UI (login, auth context, protected routes)

## Core concepts

### useState & controlled inputs
- **`useState`** gives a component a piece of state — data that changes over time. Calling the setter re-renders the component so the UI stays in sync with the data. `const [email, setEmail] = useState('')` → current value + setter; never reassign directly, always call the setter.
- **Controlled input:** bind the input both ways — `value={email}` (input shows the state) and `onChange={e => setEmail(e.target.value)}` (typing updates the state). State becomes the single source of truth for what's on screen. This is *the* React form pattern.

### React Context
- App-wide state shared across the whole tree without passing props through every level ("prop drilling").
- **Provider:** sits near the top, holds the state + the `login`/`logout` functions, makes them available to everything nested inside.
- **Consumer:** any component below calls the hook (`useAuth()`) to read the value directly — header reads `user`, login page calls `login()`.
- The `useAuth` hook null-checks the context and throws if used outside the provider — a clear error instead of a confusing later crash.

### The refresh race condition (the key lesson)
- On refresh, `AuthProvider` mounts fresh → `user` starts `null` (initial state). The `useEffect` that restores from `localStorage` runs *after* the first render, not during it.
- So the order is: (1) `user = null`, (2) first render → `ProtectedRoute` sees null → redirects to `/login`, (3) *then* `useEffect` restores the user — too late, already bounced.
- It passed before adding the gate because nothing was redirecting; the gate exposed the race.
- **Fix — a third state:** a `loading` flag defaulting to `true`. The `useEffect` flips it to `false` *after* checking storage (outside the `if`, so it runs whether or not a session was found). `ProtectedRoute` checks `loading` first (render a fallback, decide nothing yet), then the `user` check. The gate waits until the answer is known instead of guessing.

### useEffect
- Runs code after a component mounts. Empty dependency array `[]` = run once on mount — the hook for "do something on app load," like reading `localStorage`.

## Engineering tradeoffs

### localStorage security
- `localStorage` is readable by any JavaScript running on the page, so it's vulnerable to XSS (an injected script can read the token). Production-grade alternative: **httpOnly cookies**, set by the server and invisible to client-side JS. For a *demo* login, `localStorage` is a standard, acceptable choice — but it's a demo-grade decision, not production-hardened.

### Storing user vs token-only (chose: store user, for demo)
- Storing the user object locally assumes it stays valid; if permissions/details change on the backend, the local copy goes stale.
- Proper production choice: store only the token, and on app load call a `GET /api/auth/me` endpoint to fetch the current user (server stays source-of-truth).
- **Decision:** stored the user in `localStorage` for now — chose the right-sized option because the staleness problem doesn't exist with a mock backend (no changing permissions, no real server to drift from). Documented the tradeoff in a code comment; would switch to `/me` bootstrap once there's a real backend.

## Decisions / techniques
- **`POST` reads the request body** with `await request.json()` (async) — different from Day 5's GETs. Wrapped it in `try/catch` for malformed JSON → `400 BAD_REQUEST`.
- **Status codes:** `400` = malformed request (missing field); `401` = valid request, wrong credentials. Different problems, different codes.
- **`unknown` over `any`** for the parsed body: `unknown` forces a type assertion/guard before use; `any` switches off the checker entirely. Narrowed with `as LoginRequest` (a compile-time assertion, not a runtime guarantee — the field checks do the runtime guarding).
- **`useNavigate`** for programmatic navigation (code triggers it), vs `<Link>` (user clicks). Used to redirect after login/logout. This is why `AuthProvider` sits *inside* `BrowserRouter` — it needs router hooks.
- **Bodyless-error guard:** in `LoginPage`, check the response `content-type` before calling `.json()` on an error, since a bodyless error (e.g. the 500 toggle) would make `.json()` throw.
- **`{user && (...)}` conditional rendering** in the header — renders the profile block only when logged in, cleaner than `?.` which would leave an empty shell.

## What I built (deliverables)
- `Type.ts` *(modified)* — added `LoginRequest` (email + password, both required) and `LoginResponse` (`user` + `token`).
- `mocks/db.ts` *(modified)* — `DEMO_CREDENTIALS` and `mockUser` (the valid demo account lives in the data layer).
- `mocks/handlers.ts` *(modified)* — `POST /api/auth/login`: reads body, 400/401/200 paths, typed against `APIError`/`LoginResponse`, defensive JSON parsing.
- `context/AuthContext.tsx` *(created)* — context + `AuthProvider` (holds `user`/`loading`, `login`/`logout`, `localStorage` persistence + restore via `useEffect`) + `useAuth` hook.
- `components/ProtectedRoute.tsx` *(created)* — auth gate: loading → fallback, no user → `<Navigate to="/login">`, else `<Outlet />`.
- `main.tsx` *(modified)* — wrapped `<App />` in `<AuthProvider>` inside `<BrowserRouter>`.
- `pages/LoginPage.tsx` *(modified)* — stateful controlled form: email/password/error/loading state, submit → fetch login → context + redirect.
- `Header.tsx` *(modified)* — reads `user` from context, shows name, logout button (`logout()` + navigate to `/login`).
- Verified: login → dashboard, refresh stays logged in, logout clears session + bounces, logged-out `/dashboard` bounces to `/login`.
- _Polish noted, not done:_ the "Restoring session…" text flashes on every refresh; production would style it as a proper splash/spinner.

---

# Day 7 — Dashboard (first data-driven screen)

## Data fetching
- **Fetch-on-mount pattern:** `useState` holds the data (+ `loading` + `error`); `useEffect` with `[]` runs the fetch once, right after the component mounts. Different trigger from the login form (which fetched on submit) — this fires automatically on load.
- **Why the `useEffect` callback can't be `async`:** `useEffect` expects its callback to return nothing or a cleanup function, but an `async` function returns a Promise — violating that. Workaround: define an async function *inside* the effect and call it.
- **`loading` starts `true`, cleared in `finally`:** true because data is missing on load; `finally` clears it whether the fetch succeeds or throws, so a failure can't leave the spinner stuck.

## The four states
- **Loading → Error → Empty → Populated.** Check in that order: don't assume you have data until you've ruled out "still loading" and "network broke," then check for an empty array before rendering the populated layout. (Same ordering discipline as `ProtectedRoute`.)
- **Ceiling of this pattern:** one set of states per fetch works for a single data source. When cards load independently, the fetch + states move *down into each card* — a page-level `loading` would otherwise block the whole screen while one card loads.
- **Testing each state:** temporarily pointed the fetch at the Day 5 toggles — `/api/documents?scenario=empty` (empty), `?scenario=error` (error), plain URL (populated), and watched the loading text during the 800ms delay.

## Composition & types
- **`Record<DocumentStatus, string>` for the badge map:** enforces exhaustiveness — TypeScript errors if any status in the union is missing an entry, so adding a new status later can't silently render unmapped. Union types doing structural work.
- **Extracted `StatusBadge`, inlined the loading/error states:** the badge is a pure component (input `status` → styled output) reused identically on the Documents page tomorrow, so extract now. The loading/error states are tied to this page's layout; abstracting after one use is guessing at a shared shape — extract when the second screen actually needs them.
- **Date: string in the model, formatted in the component:** keeping `uploadDate` a string matches the JSON contract; parsing to a `Date` with `toLocaleDateString` inside the component keeps formatting a local UI concern (the Day 2 "parse at point of use" decision).

## CSS & tokens (today's real lesson)
- **First render was completely unstyled — two causes:** (1) didn't import `dashboard.css` into the component (a co-located CSS file does nothing until imported — unlike `index.css`, which `main.tsx` imports globally); (2) referenced `--color-*`, `--radius-*`, `--text-2xl/3xl` tokens that didn't exist in `index.css`.
- **Undefined CSS `var()`:** the property is invalid and dropped — for inheritable properties (color, font) it falls back to the inherited value; for non-inheritable ones (background, border) it just does nothing. Discipline: every `var(--x)` used anywhere must be defined in `:root` — a token reference is a promise the token exists.
- **Co-locate `dashboard.css` + import it** rather than one giant `index.css`: keeps page styles next to the component, easy to find/update/delete, stops the global sheet becoming an unmaintainable dumping ground. Global layer (`index.css`) keeps tokens, resets, shell, and reusable primitives (badges); page-specific styling lives co-located.
- **Extended the token system:** re-based the semantic tokens (`--text`, `--text-h`, `--border`) onto a new `--color-*` gray ramp + status colors, added `--radius-*` and `--text-2xl/3xl`, with dark-mode overrides for the whole ramp so everything built on it flips automatically.

## What I built (deliverables)
- `index.css` *(modified)* — added a gray ramp, status colors, radius tokens, `--text-2xl/3xl`; re-based semantic tokens on the ramp; dark-mode overrides.
- `components/StatusBadge.tsx` *(created)* — type-safe badge, `Record<DocumentStatus, string>` mapping status → colored badge.
- `pages/DashboardPage.tsx` *(modified)* — fetch-on-mount, four-state handling, sort-and-slice recent docs, documents card + placeholder cards.
- `styles/dashboard.css` *(created)* — dashboard grid + card styling, all via tokens.
- Verified live: populated/loading/error/empty all render; styled dashboard with count, formatted dates, colored status badges, placeholder cards.
- _Polish noted, not done:_ grid leaves System Status alone on row 2 (uneven); check the blue count's contrast in dark mode.

---

# Day 8 — Documents (list + detail screens)

## Derived state (the core concept)
- **Derived state** = any value computable synchronously from existing state. `visibleDocuments` is computed *during render* (`documents.filter(...)`), not stored in its own `useState`. Storing it would need a syncing `useEffect` to keep it aligned whenever docs or filter change — redundant and bug-prone.
- **Bug it prevents:** state desync/drift — a stored filtered list can show stale data when the source changes (a doc added/removed in the background). Deriving means the visible list is *always* current by construction.
- **Rule:** state is for *inputs* (raw docs, current filter); derived values are *outputs* you compute — don't store what you can derive.

## The dependency array
- Detail page uses `useEffect(..., [documentId])`, not `[]`. React may keep the same component instance mounted when navigating `/documents/doc-1` → `/documents/doc-2`, so `[]` (mount-only) would never refetch. `[documentId]` re-runs the effect (after the re-render) whenever the param changes. First real use of a non-empty dependency array.

## Type-safety patterns
- **`DOCUMENT_STATUSES as const` + `typeof DOCUMENT_STATUSES[number]`:** one source of truth for both runtime and types. `as const` locks the array into a read-only literal tuple (instead of widening to `string[]`); `typeof [...][number]` extracts those literals into the union. Now the array is runtime-iterable (dropdown can `.map()` it) *and* the type source — add a status once, and the type, the exhaustive badge `Record`, and the dropdown all stay in sync.
- **`catch (err)` + `err instanceof Error`, not `catch (err: any)`:** a thrown value can be anything, not guaranteed an Error. `any` bypasses checking; `instanceof Error` confirms it's an Error before reading `.message`. Same `unknown`-over-`any` discipline as Day 6.

## UX / states
- **Two distinct empty states:** "no data" (whole library empty) → top-level early return, swaps the whole view. "No filter matches" (docs exist, none match the filter) → check `visibleDocuments.length` *inside `<tbody>`*, render a `colSpan={4}` placeholder row so the table headers + filter stay on screen for context.
- **`<Link>` on filename over `<tr onClick>`:** a `<Link>` is a real anchor — keyboard focus, Enter to activate, screen-reader announcement, right-click-to-open-new-tab. `onClick` on a `<tr>` strips all of that. (Day 2 semantic-element lesson.)
- **404 vs generic error on detail:** inspect `response.status === 404` before parsing → throw a specific "not found" message; otherwise a generic server/connection error.

## Architecture decisions
- **Client-side filtering (chosen):** right for now — tiny mock dataset, fetching all once is cheap, and it *is* the derived-state lesson. Would switch to **server-side** (`GET /documents?status=…` with DB filtering + pagination) at scale (thousands of docs) where sending everything over the wire is wasteful. Scheduled on the roadmap: Day 21 contract freeze (pagination) + Month 2 backend perf pass.
- **Formatters in `utils/`:** `formatBytes`/`formatDate` are stateless pure functions already reused across dashboard, list, and detail — extract-when-you-feel-the-repetition. Dropdown keeps `value` lowercase (must match the data model for the filter comparison) while capitalizing only the display text — raw value vs presentation.
- **Known duplication (scheduled Day 15):** the four-state fetch block is now written 3× (dashboard, list, detail). Day 15 centralizes it into a custom hook (`useFetch`/`useDocuments`) — the repetition is now felt across 3 files, which makes that refactor earned rather than premature.

## What I built (deliverables)
- `Type.ts` *(modified)* — `DocumentStatus` now derived from a runtime-iterable `DOCUMENT_STATUSES as const` array.
- `utils/format.ts` *(created)* — pure `formatBytes` (log-ladder, zero guard) + `formatDate`.
- `pages/DocumentsPage.tsx` *(modified)* — semantic table, fetch + four states, derived-state filter, union-sourced dropdown options, both empty states.
- `pages/DocumentDetailPage.tsx` *(modified)* — `useParams` + `[documentId]` fetch, 404/error/loading/success, reuses badge + formatters.
- `styles/management.css` *(created)* — table + detail styling via tokens (inline styles lifted into classes).
- Verified: list renders + filters + both empty states; detail shows correct doc per URL, refetches on param change, 404 for bad ids.

---

# Day 9 — Upload flow (file input, FormData, progress, states)

## File handling
- **`<input type="file">` is uncontrolled** — browsers forbid setting its `value` from state for security: a script could otherwise pre-populate a path to a sensitive file (`/etc/passwd`, an SSH key) and upload it without consent. So you read the file in `onChange`, don't bind `value`.
- **`e.target.files`** is a `FileList` (array-*like* — indexing + `.length`, but not `.map`; convert with `Array.from` if needed). `?.[0]` takes the first file and guards the "opened picker then cancelled" case (empty list).
- **`FormData` not JSON:** files are binary and can't go in a JSON string without Base64 overhead. `FormData` = `multipart/form-data`, built for binary. Handler reads it with `await request.formData()` (not `.json()`), then `formData.get('file')`.

## Validation
- **Client + server, both:** client validation is UX — catches obvious mistakes instantly, no wasted round-trip. Server validation is the real gate — anything on the client can be bypassed, so the server is the immutable gatekeeper. Client for speed, server for security.
- **MIME (`file.type`) over extension:** MIME is the browser's guess from headers/OS association — more reliable than an extension anyone can spoof (`malware.exe` → `report.pdf`). Extension fallback for flaky formats (`.md`, `.csv` return mismatched or empty MIME depending on OS). (Server still can't fully trust MIME either.)
- **`validateFile` in `utils/`, imported by both client and mock handler** — single source of truth for the rule, so pre-flight and gatekeeping can't drift. (Constants `MAX_FILE_SIZE_BYTES`/`ALLOWED_MIME_TYPES` live in `Type.ts` — the neutral contract layer that survives the Month 2 mock deletion, not in `mocks/`.)

## Upload UX
- **Simulated progress:** `fetch` doesn't expose upload-progress events (real byte tracking needs `XMLHttpRequest` or a streaming lib). For a mock, animating an interval is a lightweight way to build/test the progress UI. Tracker says "mock progress" — this is the hint.
- **Cap fake progress at 95% until the server responds:** otherwise the bar could hit 100% while the request is still in flight — a lie. Hold at 95%, snap to 100% only when the fetch resolves successfully.
- **Reset `fileInputRef.current.value = ''` after success:** file inputs fire `onChange` only when the value-path changes; without clearing, re-selecting the *same* file wouldn't fire.
- **"Optimistic-add" vs true optimistic UI:** true optimistic updates the screen *before* the request leaves, then rolls back on failure. What I built waits for the server to confirm, then injects the returned object into local state (`setDocuments(prev => [newDoc, ...prev])`) — instant, no full re-fetch, but no rollback risk. Arguably better here (never show a doc that then vanishes).
- **Read the server's `APIError.message` on failure** instead of a hardcoded string — so a validation rejection (oversized/invalid slipping past the client) shows the real, actionable reason, not a misleading "network error." Guard the `.json()` for the bodyless 500.

## Incident & lesson
- **Clobbered `management.css`:** overwrote the whole file when adding upload classes instead of appending — deleted the Day 8 table styles. Recovered with `git show HEAD:src/styles/management.css` (prints the last-committed version), then merged both rule sets back. **Lesson: commit daily; append don't overwrite; git history is the safety net.**

## What I built (deliverables)
- `Type.ts` *(modified)* — `MAX_FILE_SIZE_BYTES` + `ALLOWED_MIME_TYPES` constants (shared contract).
- `utils/format.ts` *(modified)* — added `validateFile` (shared by client + handler).
- `mocks/handlers.ts` *(modified)* — `POST /api/documents/upload`: FormData read, server-side validation, `?scenario=error` toggle, `201` + new Document.
- `pages/DocumentsPage.tsx` *(modified)* — renders `<UploadPanel>` above the four states (visible even when empty); `handleUploadSuccess` optimistic-add.
- `components/UploadPanel.tsx` *(created)* — file input, client validation, simulated progress, four states (idle/invalid/uploading/success/failed).
- `styles/management.css` *(modified)* — upload panel + progress bar rules (merged with recovered table styles).
- Verified: all four states (success, invalid, uploading, failed via `?scenario=error`) working.
- _Open item:_ restore `catch (err)` + `instanceof Error` in UploadPanel (the `any` regression, same standard as Day 6/8).

---

# Day 10 — Chat UX (session list + message history)

## Data modeling
- **Two endpoints (`/chat/sessions` + `/chat/:id/messages`) not one:** returning full chats-with-messages for the list would balloon the payload — loading every message of every conversation just to render a sidebar of titles. Split = fetch only what the view needs, defer message history until a session is clicked.
- **Separate lightweight `ChatSession` type:** reusing `Chat` would force the list to carry `messages: Message[]`. `ChatSession` (id, title, `lastMessagePreview`, `updatedAt`) is the summary the sidebar actually needs.
- **`Record<string, Message[]>` map over a flat array + `sessionId`:** the map mirrors the containment hierarchy (messages only ever accessed within a session scope), gives O(1) lookup on switch, and keeps `Message` a pure record with no redundant foreign key. (First relational mock data.)

## Two-pane architecture
- **Split into `ChatPage` + `SessionList` + `MessageView`:** one component would merge two independent network cycles + their state machines into one blob. Split isolates concerns — each child owns its own load; `ChatPage` orchestrates.
- **`selectedSessionId`** is the single source of truth for the active thread. It drives the sidebar highlight *and* triggers the message fetch. Lives in `ChatPage` (the parent) because both children need it — `SessionList` to highlight, `MessageView` to fetch. State lives at the lowest common ancestor.
- **Dependent fetch:** `MessageView`'s `useEffect` lists `[sessionId]`; when the prop changes, the effect re-runs (after the re-render) and refetches.

## The fiddly bits
- **Stale-data flash:** switching A→B, A's messages linger in state until B's fetch resolves — a flash of old messages under the new title. Fix: `setMessages([])` at the top of the effect, clearing before the new request fires.
- **Scroll-to-bottom:** a `useRef` on an empty anchor `<div>` at the end of the list; `scrollIntoView()` finds the nearest scrollable ancestor (the `overflow-y: auto` message pane) and scrolls *that*, not the page. Runs in a separate effect keyed on `[messages]` (scroll after render).
- **`behavior: 'auto'` for history, `'smooth'` for new messages:** opening a chat should drop you at the latest instantly (no watching it animate-scroll through old context); a newly-sent message (Day 11) should smooth-scroll so you track it appearing.

## States & UX
- **Empty session = distinct state:** a successful fetch returning `[]` is healthy, not an error — needs its own "no messages yet" layout. Check goes inline after the loading and error returns.
- **Skeletons over "Loading...":** skeleton shapes match the incoming bubble layout, keeping it steady; a text loader collapses then snaps when data arrives.
- **Each session is a `<button>` not a `<div onClick>`:** native focusability (Tab), Enter/Space activation, screen-reader support — free. A div needs `tabindex` + manual key handlers to match.

## Known simplification
- **`lastMessagePreview` is denormalized:** hardcoded copy of the last message; editing a message without syncing the preview would drift. Real backend derives it (a `LIMIT 1` subquery) or keeps it in sync via the write transaction.

## What I built (deliverables)
- `Type.ts` *(modified)* — `ChatSession` summary interface.
- `mocks/db.ts` *(modified)* — sample sessions + `Record<string, Message[]>` message map.
- `mocks/handlers.ts` *(modified)* — `GET /chat/sessions` and `GET /chat/:sessionId/messages` (latency, `?scenario`, 404).
- `pages/ChatPage.tsx` *(modified)* — two-pane grid, owns `selectedSessionId`, renders `MessageView` only when narrowed non-null.
- `components/SessionList.tsx` *(created)* — accessible `<button>` rows, four-state pattern, active highlight.
- `components/MessageView.tsx` *(created)* — dependent fetch, stale-flush, skeletons, bubbles (sender-driven alignment), scroll anchor, empty state.
- `styles/chat.css` *(created)* — two-pane layout, bubbles, skeleton shimmer.
- Verified: switch sessions (no stale flash), bubbles align by sender, scroll contained to pane.
- _Noted, not done:_ relative time for sidebar; pad a session to >15 msgs to actually see scroll act; header-height offset was brittle (fixed to `height:100%`).

---

# UI Redesign (mentor-triggered detour, between Days 10 and 11)

Mentor reviewed the app and rejected the UI ("worst of worst"). Paused the tracker to rebuild every screen to a professional bar, using the **Adminator** admin template as a reference target (studied its decisions; wrote all code myself).

## The design system I landed on
- **One accent + semantic status colors + structural gray.** Replaced the garish template purple (`#aa3bff`) with a true blue (`--accent: var(--color-blue-600)` = `#2563eb`). Rule: if a color isn't the accent, a status color, or structural gray — cut it.
- **Color only where it carries meaning.** Blue = brand/interactive (the user's name, links, active nav, primary buttons). Green/amber/red = status only. Gray = everything structural.
- **Surfaces:** light-gray page canvas (`--color-gray-50`) with white cards on top — the contrast is what makes cards read as elevated surfaces. Metric tiles = filled/borderless; content cards = white/bordered.
- **Hierarchy:** two font weights max (400/500 — 600/700 read amateur), sentence case everywhere, muted secondary text, section labels (small uppercase gray) to divide regions.
- **Real icons, never emoji.** `lucide-react` — tree-shakeable SVGs that inherit `currentColor` (emoji don't recolor and render differently per OS; they're the biggest single amateur tell).
- **Emphasis discipline:** one confident primary action per view (accent-filled); secondary actions recede (ghost buttons — transparent, muted, subtle hover). Logout is low-emphasis, login's submit is high.
- **Plain product copy.** "Documents / Upload and manage the files in your knowledge base" — not "Knowledge base registry / indexed tracking documents synced with model vector pipelines."

## Information design (the mentor's real point: "not just static numbers")
- Every number gets a **label above** and a **consequence below**. "3" → "Total documents / 3 / across all statuses". "1" (red) → "Need attention / 1 / requires manual re-upload".
- **Personalize:** greet the real user from `useAuth()`, breadcrumb showing where you are.
- **Surface what needs action:** a conditional alert banner naming the actual failed file with what to do about it.
- Derive stats from real data (`documents.filter(d => d.status === 'ready').length`), never hardcode. And never show an alarming red "0" — calm when nothing's wrong.

## Techniques learned
- **`NavLink` + `isActive`** for the sidebar "you are here" state — react-router gives it free; the active item gets an accent-tinted background, accent text/icon, and a left accent bar. Biggest single upgrade to the app (it's on every page).
- **Avatar initials** instead of a long full name in the header.
- **Drag-and-drop upload:** a drop zone needs `onDragOver` (with `e.preventDefault()` — required, or the browser blocks the drop), `onDragLeave`, `onDrop` (file from `e.dataTransfer.files[0]`). Browse and drop funnel into **one** `processFile(file)` engine — the label (`<label htmlFor>` pointing at a hidden `<input type="file">`) opens the picker with no JS.
- **MSW unhandled-request scoping:** MSW warned on `GET /chat` — which was the *browser's page-navigation request*, not a bug. Fixed with a scoped predicate in `main.tsx`: warn only if `url.pathname.startsWith('/api/')`, ignore everything else. (Blanket `onUnhandledRequest: 'bypass'` would have silenced *real* future typos too — silencing the smoke detector instead of the fire.)

## Debugging lessons (the "silent mismatch" class — hit repeatedly)
- **The ghost file:** edits to `UploadPanel.tsx` did nothing because *nothing imported it* — I'd been editing an orphaned copy. **The tell: saving the file produced no `[vite] page reload` in the terminal.** If a save doesn't trigger hot-reload, the file isn't in the module graph. Defense: Cmd+click the import in the parent to see which file actually resolves.
- **Wrong endpoint URL:** login fetched `/api/login` instead of `/api/auth/login` → "invalid credentials" with correct credentials. The MSW `/api/` warning would have caught this — another reason not to blanket-bypass.
- **Undefined CSS tokens (six times):** `--radius-md`, `--text-xxs`, `--color-gray-400`, `--radius-xs`, `--danger`, `--space-1/2`. Browsers **silently drop** invalid `var()` — no error, just missing spacing/color. Defense: grep every new `var(--x)` against `:root`.
- **Restyling can silently drop functionality** — a rebuilt component can keep the *visuals* and lose the *wiring* (a drop zone with no drop handlers, a "browse" link with no input behind it). Restyle working code; don't re-implement it inside a pretty shell.

---

# Day 11 — Chat send flow (ask, answer, retry)

## The send state machine
- **Idle** → waiting for input. **Sending** (form submit or retry) → append/update the message, lock the input, show the thinking indicator. **Answered** (200) → append the AI response, strip the user message's `sending` status, unlock input. **Failed** (throw or `!ok`) → mark the message `failed`, capture the error, show retry, unlock input.
- **True optimistic UI** (vs Day 9's "optimistic-add"): the user's message renders *before the request fires* — assume success for instant feel, roll back to a failed state if it doesn't. Day 9 waited for the `201` and *then* appended (no rollback needed).
- **Client-generated temp id** on the optimistic message: the state machine needs a stable identifier to target that exact message later (strip `sending`, or mark `failed`) — and React needs it as a `key`.

## Type modeling
- **`UIMessage = Message & { status?, errorMessage? }`** — client-only bookkeeping stays out of `Type.ts`. Putting ephemeral UI state on the server contract pollutes the domain model and forces stripping properties (or type-guards) before sending payloads back.
- **`citations?`/`actions?` optional on `Message`** — user messages never have them. Optional beats forcing empty arrays. ("Model what's actually true.")

## The unified send engine
- **`processMessage(content, existingId?)`** — one engine, two triggers. The optional `existingId` forks the behavior: absent → new send (optimistic append); present → retry (reset the existing message to `sending`). Same principle as `processFile` in the upload panel: shared pipeline, lightweight dispatchers.
- **Updating an item in state** (vs appending): `.map()` over the array, match the id, spread in new props (`{...m, status: undefined}`), return the rest unchanged. Appending is `[...prev, item]`; updating requires the map.

## Scroll & async
- **Smooth vs auto scroll:** a `useRef<ScrollBehavior>` flag read by the scroll effect — set `'auto'` before a history fetch (instant jump), `'smooth'` before a send (new message slides in). A **ref, not state**, because changing the scroll *intent* shouldn't trigger a re-render; it's just read during the DOM update.
- **Disable the input AND guard the submit** (`if (isAwaitingResponse) return`) — prevents double-submits from enter-mashing, which would fire overlapping requests and corrupt message order.

## The mock
- **Keyword router** in the handler (health → telemetry answer, cors → API answer, else fallback) instead of one static response — lets me test how the UI handles realistic response lengths and varied content, not a robotic canned string. ~2s delay so the thinking state and input lock are actually observable.
- **Response carries citations/actions today, unrendered** — contract-first: establish the full data shape now, so Days 12/13 are purely rendering tasks with no backend/network changes.

## Failure handling
- **Surface the server's `APIError.message`**, not a generic "failed" — the real reason is often actionable. (Guard the `.json()` for bodyless errors.)
- **Retry** strips `errorMessage`, flips `status` back to `'sending'`, and re-runs the *same* engine — so a retry follows the identical network/success path as a first attempt (no divergent-behavior bugs).

## What I built (deliverables)
- `Type.ts` *(modified)* — `Citation`, `ActionProposal`, optional `citations?`/`actions?` on `Message`, `SendMessageRequest`.
- `mocks/handlers.ts` *(modified)* — `POST /api/chat/message` (flat path per contract; `sessionId`+`content` in body), keyword router, ~2s delay, `?scenario=error` toggle.
- `components/MessageView.tsx` *(modified)* — `UIMessage` layer, optimistic send, thinking indicator, `processMessage` engine, failed state + retry, ref-driven scroll behavior.
- `styles/chat.css` *(modified)* — `.is-sending`, `.is-failed`, retry affordance; inline styles lifted to tokenized classes.
- Verified: send → thinking → answer; failed send shows the server's error + retry; retry succeeds and appends the answer.

---

# Day 12 — Citations (source grounding + document anchors)

Payoff of Day 11's contract-first discipline: **purely a rendering task.** The `citations` array was already on the `Message` type and already returned by the mock — the data was waiting; I only built the UI.

## Citation UI
- **Expandable, not always-shown:** the answer is primary content; burying a paragraph under 3 citation cards inverts the hierarchy and breaks chat readability. A "Sources (N)" toggle keeps the receipts one click away.
- **Expand state lives locally in `<MessageCitations>`** — purely local UI bookkeeping; `MessageView` doesn't care which tray is open. "State lives at the lowest level that needs it" — the *inverse* of Day 10's `selectedSessionId`, which had to be lifted because siblings shared it.
- **Two components:** `<MessageCitations>` = smart wrapper (owns expand/collapse, maps the array); `<CitationCard>` = dumb presentational (data → UI), reusable elsewhere (e.g. Day 14 tasks referencing sources).

## Source grounding & the document anchor
- **Source grounding** ties an AI claim to verifiable material (document + section + excerpt) — turns an unverifiable black-box answer into something the user can audit. It's the core trust mechanism of a RAG assistant.
- **The document anchor:** each citation is a `<Link to={/documents/${documentId}}>` back to the source's detail page. A 404 meant the citation's `documentId` didn't exist in the document store.

## Referential integrity (bug caught + fixed)
- **Dangling reference:** the FastAPI citation pointed at `doc-102`, which wasn't in `mockDocuments` → clicking it hit "Document not found."
- **Why patching to any valid id is wrong ("silent data corruption"):** the link would *work* but point at the wrong document (FastAPI answer → Financial Report), breaking the demo's coherence and user trust more subtly than a 404.
- **Fix:** added the real referenced documents (`doc-101/102/103`) to `mockDocuments` so every citation resolves to a content-appropriate document.
- **The concept:** a citation's `documentId` is a **foreign key** into `documents`. The dangling reference is a FK pointing at a non-existent row — which Month 2's PostgreSQL will reject via real FK constraints.

## In-memory persistence
- **Why messages vanished before:** sent messages lived only in React state; navigating away unmounted the component (state destroyed), and navigating back re-fetched from the *unmodified* `mockChatMessages` seed. So only the two seed messages ever loaded.
- **Fix:** the `POST /chat/message` handler now *mutates* the store — pushes both the user message and the AI response into `mockChatMessages[sessionId]`, so subsequent GETs return the updated history.
- **Also update the session summary:** the handler syncs `mockChatSessions`' `lastMessagePreview` + `updatedAt` on write. The chat log and the sidebar are *separate denormalized structures* — updating only the log leaves the sidebar stale. This mirrors a real DB keeping denormalized parent data in sync on the write path (the Day 10 preview lesson, applied).
- **Boundary:** in-memory persistence survives route navigation but resets on a hard page reload (the module re-initializes to seed). Acceptable — a mock provides demo fidelity for a session; real durability is Month 2's Postgres.
- **Ordering detail:** the user message is timestamped `Date.now() - delayMs` so it sorts before the assistant's, preserving chronological order.
- **No duplication:** the optimistic user message (React state) is discarded and replaced by the persisted copy on re-fetch (Day 10's stale-flush `setMessages([])`), so navigating back shows each message once.

## What I built (deliverables)
- `mocks/db.ts` *(modified)* — added `doc-101/102/103` so citation anchors resolve (referential integrity).
- `mocks/handlers.ts` *(modified)* — `POST /chat/message` returns citations, persists both messages in-memory, syncs session summary.
- `components/CitationCard.tsx` *(created)* — dumb presentational card: linked doc name, section, blockquoted excerpt.
- `components/MessageCitations.tsx` *(created)* — smart wrapper owning the expand/collapse tray.
- `components/MessageView.tsx` *(modified)* — renders `<MessageCitations>` under assistant bubbles with citations.
- `styles/chat.css` *(modified)* — tokenized toggle, tray, blockquote excerpt styles.
- Verified: sources expand; every link resolves to a real document; messages persist across navigation (once each); sidebar preview/timestamp update on send.

---

# Day 13 — Tool-calling UI (AI action proposal + confirmation)

The "agentic" feature, with a safety principle baked in. Action-proposal data was already flowing in chat responses (contract-first) — extended the handler to populate it, added a new execution endpoint.

## Human-in-the-loop
- **Why a confirmation gate:** answers are read-only/low-risk (ignore a bad one). Actions *mutate state* — an unauthorized or destructive side effect (bad records, deleted files, sent emails) is real damage. The AI *proposes*; a human *approves* before execution. The AI never acts unilaterally.
- **Inline Approve/Reject over a modal:** keeps the user in the conversation, low friction for a binary decision. The buttons *are* the confirmation. A modal is only justified when the human must add input (edit an AI-drafted email) or for high-stakes/destructive actions needing hard confirmation. Friction should be proportional to consequence.

## The action flow & audit trail
- **Reject hits the server** (not client-only): auditability. A client-side-only rejection leaves the system blind to what the AI *attempted*. The human's veto must be logged alongside the AI's intent.
- **The audit trail** is the system of record for AI behavior. Logging *rejections* (not just approvals) is core governance — it's the signal for where the model hallucinates capabilities or misreads intent, so prompts/guardrails can be tuned. "You cannot measure what you do not log."
- **Client sends `type` + `payload` back on approval:** the mock is stateless — it doesn't remember the proposal it generated. The client passes the full payload so the execution endpoint has everything to fulfill the request independently.

## Type modeling — discriminated unions (the warranted use)
- **Why a discriminated union now, when I rejected it for `Task` on Day 2:** on Day 2 all tasks behaved identically, so branching was premature. Here the `payload` shape is *intrinsically tied to* the `type` discriminant (`create-task` needs `title`; `lookup-knowledge` needs `query`). The union guarantees this correlation at compile time. Recognizing "*now* it's warranted" is the judgment. Applied across `ActionProposal`, `ActionRequest`, `ActionResult`.
- **Why field-by-field assembly forced a cast:** writing `{ type: proposal.type, payload: proposal.payload }` evaluates each property independently — TS sees a union of types and a union of payloads and can't prove they align in the new object. **Building inside `switch (proposal.type)` fixes it cast-free:** the switch narrows `proposal` to one concrete branch, where the compiler knows exactly which literal type and payload belong together. Narrowing restores the compiler's ability to verify correlated unions.
- **`as any` vs `as ActionRequest`:** `as any` disables the checker entirely (blind to typos, missing fields, drift). `as ActionRequest` is a targeted boundary assertion — "trust me at this exact seam, enforce the contract downstream." When you must assert, assert narrowly and specifically. (Best of all: narrow so you need no assertion.)

## State & structure
- **Self-contained state in `<ActionCard>`** (not lifted): each action is an independent unit of work; nothing outside needs its status. Keeps `MessageView` uncluttered and components decoupled.
- **Why local state works given Day 14 needs the tasks:** persistence carries the data across the seam. The card mutates *server* state (`mockTasks`); Day 14 reads from that server state. The DB is the source of truth, so no lifted React state is needed. (If there were no persistence, you'd *have* to lift it.)
- **Five states:** proposed (on render) → executing (Approve/Reject clicked, POST in flight) → completed (200 success) / rejected (server acks rejection) / failed (network error or 500 → error + retry). Retry re-fires the same decision (`lastDecision`).

## Tool result previews
- **Show the result, not just "done":** render the created task title / the summary text / the lookup snippets. Closes the feedback loop and builds trust — the user verifies exactly what the tool did without navigating away. Narrows on `ActionResult.type` to render each type's preview.

## The Task reconciliation
- Fixed the `Task` shape *today* (Day 2's `{done: boolean}` → `{priority, status, createdAt}`) rather than mid-Day-14 — so the persisted data the history screen reads is already structurally correct. Reconciling at the point of creation prevents a downstream render crash.

## What I built (deliverables)
- `Type.ts` *(modified)* — discriminated unions for `ActionProposal`/`ActionRequest`/`ActionResult`; reconciled `Task`; `ActionAudit`.
- `mocks/db.ts` *(modified)* — typed `mockTasks: Task[]`, `mockActionAudit: ActionAudit[]`.
- `mocks/handlers.ts` *(modified)* — chat proposes actions; `POST /api/ai/actions` executes approvals (persists task), logs both decisions, `?scenario=error`.
- `components/ActionCard.tsx` *(created)* — self-contained 5-state card, unified `submitDecision`, type-safe payload/result rendering via narrowing.
- `components/MessageActions.tsx` *(created)* — wrapper mapping proposals beneath assistant bubbles.
- `components/MessageView.tsx` *(modified)* — renders `MessageActions`, threads `sessionId` down.
- `styles/chat.css` *(modified)* — action card, buttons, result text, status styles.
- Verified: propose → approve → result preview (all 3 types); reject → logged, no task; failure → error + retry; audit logs both decisions.
- _Backlog:_ "New chat" flow (create-session) — noticed as a product gap, deferred as future polish (out of tracker scope).

---

# Day 14 — Tasks/actions history screen (the action arc capstone)

Everything approved on Day 13 finally gets a home; the `Actions` nav stub (Day 4) becomes a real screen. Closes the loop: propose → approve → persist task → show in history + governance audit.

## Screen & structure
- **Two separate endpoints** (`GET /tasks`, `GET /actions/audit`): tasks are *mutable operational state* (todo → done); the audit trail is an *immutable governance log* (a record of AI proposals + human decisions). Different domains, different consumers — one combined endpoint returns a heterogeneous blob the client must untangle.
- **Tabs, Active Tasks default:** gives the operational view (what to do) immediately, keeps the governance view one click away without clutter. Default aligns with the primary user goal (getting work done).
- **Lazy-fetch the audit tab:** least-privilege data loading — don't fetch data the user may never view. Tasks (+ sessions for title lookup) on mount; audit only when its tab first opens. A `!auditFetched` "loaded once" guard stops refetching on tab-switch.

## Data integrity
- **`Task` needed `sourceSessionId`:** without it a task is orphaned. Same lesson as the citation `documentId` — a task must anchor to its source conversation so the user can trace *why* it was created. The handler already receives `sessionId` in the `ActionRequest`; it just needed to persist it (`sourceSessionId: req.sessionId`).
- **Seed mixed-status tasks:** can't prove a filter works if all data is identical — a "done" filter on all-`todo` data tests nothing.
- **Reconcile the audit seed with the tasks:** an audit trail that can't explain its own system's tasks is a failing governance log. In a real system the same execution creates both; the mock data must corroborate itself.

## Relational mapping
- **Show the session title, not the raw `sourceSessionId`:** leaking a database key ("chat-1") undercuts the feature's purpose — the UI must show human-readable context ("AeroTwin Health Metrics"). Same raw-id-vs-display lesson as formatting dates.
- **Client-side join (chosen) over denormalizing the title into the payload:** `Task`/`ActionAudit`/`ChatSession` are distinct domains — stitching the title into their payloads would pollute the contracts for a UI string. Instead: fetch `GET /chat/sessions`, store as a reference dictionary, look up the title locally. Keeps APIs pure; realistic frontend relational mapping.

## Component reuse
- **Generic `<Badge variant="success"|"warning"|"neutral"|"error">`** where the *consumer* maps domain→variant, rather than wedging `TaskStatus` into the `DocumentStatus`-coupled `StatusBadge`. The badge knows about *visual variants*, not domains — so it's reusable across documents, tasks, and anything future. The "dumb reusable presentational component" idea, one level more abstract.

## Observations
- **`tasks`/`sessions` fire twice on mount:** React `StrictMode` intentionally double-invokes effects in *dev* to expose impure logic / missing cleanup. Harmless (idempotent GETs), strips out in production. Not a bug to "fix" — understand it. (A proper fetch hook with caching — Day 15 — would dedupe if wanted.)
- **Source-chat link goes to `/chat` but can't select the specific session:** chat uses local `selectedSessionId` state, not a URL param. True deep-linking needs the active session in the router (`/chat/:sessionId`). Honest limitation, backlogged.

## Accessibility
- The status filter `<select>` needed an `id` + associated `<label htmlFor>` (DevTools flagged "no label associated with a form field"). Without it a screen-reader user hears "combobox" with no context. Same semantic-HTML/label pattern as the login form.

## What I built (deliverables)
- `Type.ts` *(modified)* — `sourceSessionId` on `Task`.
- `mocks/db.ts` *(modified)* — mixed-status seed tasks; reconciled audit seed for coherence.
- `mocks/handlers.ts` *(modified)* — handler stores `req.sessionId` on tasks; `GET /api/tasks` + `GET /api/actions/audit` (with `?scenario=error`).
- `pages/ActionsPage.tsx` *(modified)* — tabbed history: lazy-fetch, client-side title join, derived-state status filter, labeled select.
- `styles/actions.css` *(modified)* — cards, audit timeline, tabs, badges.
- Verified: both tabs render; lazy fetch confirmed in Network (audit only on tab open, no refetch); filter works; source links show titles and navigate to /chat.

---

# Gap-filling batch (mentor: "implement gaps a real product needs")

Mentor asked me to find and fill product gaps not written in the tracker. Audited the app as a user, prioritized, built six. **Deep-linking (`/chat/:sessionId`) backlogged** — it's a routing refactor, cleaner after Day 15.

## Prioritization
Picked **new chat** first by **pipeline dependency**, not by what I noticed first: no new conversation → no new questions → no new AI actions → no new tasks. Fixing it unblocks the whole product loop at the source. Find the bottleneck that gates the most downstream value.

## 1. New chat (lazy session creation)
- **Lazy over eager creation:** eager (`POST` on button click) is easier but litters the sidebar with empty "New Chat" stubs if the user clicks and wanders off. Lazy = the DB only mutates when the user commits intent (sends the first message). Industry standard for a reason.
- **Atomic transaction:** `POST /chat/sessions` takes an optional `initialMessage`, creates the session, derives the title from the prompt, routes it through the same AI logic, and returns `{ session, messages }` in one round-trip. Two calls (create-then-post) would risk succeeding on step 1 and failing on step 2 — leaving the exact orphaned session lazy creation was meant to avoid. Git-commit semantics: all or nothing.
- **Sentinel id:** `selectedSessionId = 'new'` makes "new chat" just another selection state, reusing existing machinery. Requires a **fetch guard** (`if (!sessionId || sessionId === 'new') return`) or it fires `GET /chat/new/messages` and 404s.
- **Lift a signal, not data:** `ChatPage` holds a `refreshKey` integer, not the sessions array. Lifting the array would couple the whole page's render to every session update; an integer is a minimal trigger. `onSessionCreated(newId)` swaps the sentinel for the real id and bumps the key.
- **The flicker fix:** a `prevSessionId` ref detects the `'new'` → real transition and *skips* the loading flush, so the just-sent message doesn't vanish and reappear. Distinguishing "switched conversations" (flush correct) from "this conversation got its real id" (flush wrong).

## 2. Delete document (optimistic remove + rollback)
- `DELETE /api/documents/:id` → `200 { success, deletedId }` (helps a normalized client know what to purge), 404, `?scenario=error`.
- **Inline click-to-confirm** over `window.confirm()` (jarring) or a modal (heavy context-switch for one row). Trash icon expands to a red "Confirm Delete" + Cancel. Localized friction, proportional to consequence.
- `confirmingId` hoisted to the parent so only one row can be confirming at a time.
- **Position-preserving rollback:** capture `targetDoc` **and** `originalIndex` from the *source* array (not the filtered view), then `splice(originalIndex, 0, targetDoc)` on failure. Appending to the bottom would jar the user's spatial map.
- The failure is **surfaced**, not silent — a banner naming the file and saying it was restored.

## 3. Search documents (client-side)
- Derived state composing status AND name (case-insensitive `includes`), same pattern as the Day 8 filter.
- **No debounce:** we're CPU-bound, not network-bound. Filtering an in-memory array is sub-millisecond. Debounce belongs at a *network* boundary (backend load, DB compute, and the race where `a`'s response lands after `ab`'s). Debouncing an in-memory filter actively *degrades* UX by making it wait.

## 4. Task status transitions (first mutation endpoint)
- **`PATCH` not `PUT`:** send the delta (`{ status }`), not the whole resource.
- **Bidirectional side-effect:** `completedAt` set when → done, **cleared** when moving out of done. Most implementations forget the clear and leave a completion date on a reopened task.
- Returns the **full updated task** so the client syncs the server-generated `completedAt` without a second fetch.
- `<select>` over a cycle button: three states, and a cycle means overshooting "Done" costs two more clicks.
- **Optimistic update — the third variant.** Add (no rollback needed) → remove (capture item + index) → update (capture just `previousStatus`, revert one field). Then sync with the server's full response for authoritative fields.

## 5. Error boundary
- Must be a **class component** — `static getDerivedStateFromError` (show fallback) and `componentDidCatch` (log). No hook equivalent.
- Catches **render-phase errors only** — not event handlers, not async/promise rejections (those are what try/catch is for), not itself.
- **Placement: wrapping `<Outlet/>` inside `Layout`**, not the whole app — so a crashed page shows the fallback while the sidebar/header stay alive and the user can navigate away instead of hard-refreshing. Error *recovery*, not just error catching.
- **`key={location.pathname}`** forces a fresh boundary instance per route, clearing the error on navigation. Idiomatic React (identity tied to route) vs. `componentDidUpdate` boilerplate.
- Dev-only error detail via `import.meta.env.DEV`.
- Tested by deliberately throwing: fallback shows, sidebar intact, clicking Dashboard clears it.

## 6. Settings (minimal, honest)
Scope fenced *before* writing: read-only account + workspace info, nothing editable — because with no persistence layer, toggles that reset on refresh are worse than no toggles.
- **First attempt failed its own scope:** hardcoded a `mockUser` (while `useAuth()` was right there), invented counts (24 sessions / 12 documents when the real app has 4 / 6), a fake version string, and "managed by your workspace administrator" — an administrator that doesn't exist. Rebuilt honest and *smaller*.
- **The lesson isn't knowledge, it's process:** re-read your own stated principle and check the output against it before calling it done. Knowing the rule and applying it under time pressure are different skills.

## Recurring failures worth naming
- **A revert takes everything in the file, not just the feature you're backing out.** Reverting `MessageView` to rebuild new-chat silently dropped Day 13's `MessageActions` integration — proposals stopped rendering and `ActionCard` fell out of the module graph. After any revert of a layered file, ask: *what else lived here?* A diff against the last good commit shows it instantly.
- **No Vite output on save = the file isn't in the module graph.** Caught it twice (UploadPanel, ActionCard) and was right both times. Note: components print `hmr update` (quieter), non-components print `page reload` — but *silence* is the orphan signal.

---

# Day 15 — State management (the refactor day)

Tracker's phrasing matters: "centralize shared product state **where useful**." Half the skill is knowing what *not* to hoist.

## The audit first
Every page duplicated the same plumbing: three `useState` (data/loading/error) + a `useEffect` with async `try/catch/finally`. They **differed** in: trigger (mount vs. dependency), bail-out logic (missing param, lazy tab), manual refetch mechanism, and error-body parsing. Those differences *are* the hook's requirements — a spec I could only write because I'd built all seven by hand.

## The rule I broke and re-learned
**A refactor changes *how*, never *what*.** My first Dashboard migration invented a `/api/dashboard` endpoint, fabricated a data shape, and deleted the derived metrics, the `useAuth()` greeting, the named-failure banner, and `StatusBadge` — a destructive rewrite wearing a refactor's clothes. Restored from the commit; the real migration was **two lines in, four out**, everything downstream untouched.
- **Commit before refactoring** — the return point is what made recovery trivial.
- **One page at a time, verify each.** Sequenced so each migration exercised one new hook feature (Dashboard: plain mount → DocumentDetail: `deps` → ActionsPage: `skip` + parallel hooks → DocumentsPage: `setData` → SessionList: `deps: [refreshKey]`). A failure points straight at the feature that caused it.

## The hook: `useFetch<T>(url, { skip, deps })`
Returns `{ data, loading, error, refetch, setData }`.
- **The generic is the success criterion.** `useFetch<Document[]>` gives `data: Document[] | null` — no `as` casting at any call site. "Consistent *typed* pattern."
- **`skip`** serves two cases with one flag: bail on a missing route param, and lazy-load the audit tab. Better than `skipIfNew` + `isLazy`.
- **`deps` AND `refetch()`** — different triggers. `deps` = parent-driven (a route param changes, or `ChatPage` bumps `refreshKey`). `refetch()` = self-driven, so a component can reload without a dummy integer.
- **`setData` exposed** for the optimistic flows. Deliberately breaks strict encapsulation — the right price for keeping bespoke mutations readable instead of building a bloated `useMutation`.
- **The `ignore` cleanup kills a race:** click chat A then B quickly; if A resolves last it overwrites B. Cleanup sets `ignore = true` so late responses are discarded. **Fixing a correctness bug in six places at once is the strongest ROI argument for the whole refactor** — not "less typing."
- Consistent `APIError.message` parsing (with a guard for bodyless errors) — DocumentDetail's 404 now shows the server's real message for free.

## What I deliberately left alone ("where useful")
- **No new Context.** Data is URL-driven and page-local; the Dashboard doesn't need Task data. Hoisting page data into Context creates stale global state and cleanup overhead. `AuthContext` stays the only one because auth genuinely *is* global.
- **No `useReducer`.** Reducers manage *synchronous* transitions; `MessageView`'s complexity is entirely in the *async* lifecycle. Swapping `setState` for `dispatch` trades readable linear code for boilerplate without touching the actual difficulty.
- **No generic `useMutation`.** Reads are uniform; mutations are bespoke (rollback by array index vs. rollback one string field). A generic hook makes each flow *harder* to read. Centralize reads, leave mutations inline.
- **No client cache.** It would immediately hand me cache invalidation — delete a task, now manually invalidate the dashboard's counts. For this size, honest redundant fetching on mount is the simpler, truer trade.
- **`MessageView` keeps its own effect.** Its `prevSessionId` ref deliberately suppresses the loading flush on the `'new'` → real transition; the hook always sets `loading: true` when deps change. Accommodating it would mean a `keepPreviousData` flag for *one* call site — making the hook worse for the six it already fits. **Documented with an architecture comment**, because undocumented deliberate inconsistency reads as an oversight.

## Behavior change, declared
The audit tab now **refetches on every tab visit** (the `skip` flip re-runs the effect) instead of the old fetch-once guard. Kept as an **intentional upgrade** — approve an action in chat, switch to Actions, see it immediately; stale governance data is worse than an extra request. Declared explicitly rather than inherited by accident, because a refactor shouldn't silently change behavior.

## What I built (deliverables)
- `hooks/useFetch.ts` *(created)* — typed hook, `skip`/`deps`/`refetch`/`setData`, race-safe cleanup, unified error parsing.
- `pages/DashboardPage.tsx` *(migrated)* — plain mount; all derived metrics and UI preserved.
- `pages/DocumentDetailPage.tsx` *(migrated)* — `deps: [documentId]` + `skip: !documentId`; manual 404 handling deleted (hook surfaces the server message).
- `pages/DocumentsPage.tsx` *(migrated)* — optimistic add/delete/rollback routed through `setData`.
- `pages/ActionsPage.tsx` *(migrated)* — two eager hooks + one lazy via `skip`; audit refetch declared an upgrade.
- `components/SessionList.tsx` *(migrated)* — `deps: [refreshKey]`, parent-signal architecture intact.
- `components/MessageView.tsx` *(deliberately not migrated)* — architecture comment added.
- `styles/index.css` — promoted `.transient-error-banner` to a global utility, removing accidental cross-stylesheet load-order coupling.

---

# Day 16 — Forms (validation + reusable controls)

Day 15's twin: extract the repeated thing. Same rules — commit first, refactor don't rewrite, one form at a time.

## The audit came back mostly empty — and that shaped everything
There is exactly **one** multi-field form (Login, two fields). Everything else is a specialized single control: the upload dropzone (custom DOM, file parsing), the chat input (bound to an optimistic send cycle), search/filters (no validation — you just get zero results).

So the duplication isn't a **state** problem, it's a **DOM-structure and accessibility** problem: `label + input + error + the aria wiring between them`. That diagnosis is what kept today from becoming a mini-Formik for a two-field form — the same over-engineering trap as Day 15's mini-React-Query, wearing a different hat.

## Component design
- **`TextInput` is presentational only.** Props in (`label`, `id`, `error`, `rightElement`, + native attrs), a11y wiring out. **No internal `touched` state** — because validation has *two* triggers: blur (field-local) and submit (form-level). If `touched` lived in the input, the parent couldn't force all fields to validate on submit without refs or a `key` remount hack. Same "where does state live" question as Day 10's `selectedSessionId` — and it lands *opposite* to the citation tray, where expand state stayed local because nothing outside cared.
- **Extends `InputHTMLAttributes<HTMLInputElement>`** so `autoComplete`, `disabled`, `type`, `onBlur` pass through natively. That's why the login migration preserved every existing behavior instead of re-declaring each prop.
- **`PasswordInput` composes `TextInput`** with `Omit<TextInputProps, 'type' | 'rightElement'>` — the wrapper owns those two props so callers can't override them, `showPassword` stays local (the form doesn't care), and `TextInput` doesn't grow password-specific branching. Better than a `showToggle` boolean.
- **`rightElement`** is a generic slot, not a password-specific hack.

## Validation
- **Timing: touched-hybrid (blur-then-change).** On-change is hostile (yells "invalid email" at the letter `m`). On-submit is safe but late. Touched-hybrid stays quiet until the field is left once (or submit forces all fields touched), then validates live so the error clears on the exact keystroke that fixes it.
- **`fieldErrors` derived, never stored.** Storing derived data invites drift; deriving guarantees errors always match current `values`. (Same rule as the dashboard metrics.)
- **Validators in a pure module** (`utils/validators.ts`) — UI-agnostic, testable, easy to align with server rules. `isValidEmail` stays pragmatic (`text@text.text`); RFC-complete regexes are monstrous and still wrong, and the server is the real authority.
- **`validateFile` deliberately stayed out** — its domain is bytes and MIME types, not string formatting.

## Accessibility (the day's real substance)
The four-part wiring, baked into `TextInput` once so every field gets it free:
- `<label htmlFor={id}>` ↔ `<input id={id}>` — binds the label text to the control.
- `aria-invalid={!!error}` — announces the field is in an error state.
- `aria-describedby={`${id}-error`}` — tells the screen reader *which* message belongs to this field.
- `role="alert"` on the error element — announces it the moment it appears.

Other a11y work:
- **`aria-label` for the chat and search inputs** rather than wrapping them in `TextInput`. A visible label would clutter those single-bar UIs, and they have no validation — the component would be pure ceremony. The native attribute satisfies the screen reader directly.
- **The file input's keyboard trap:** `display: none` removes the input from the accessibility tree entirely — unreachable by Tab, so a keyboard user had *no* way to trigger the file picker. Fixed with `.visually-hidden-input` (1px, clipped, still focusable) plus `:focus-within` on the dropzone to paint a visible ring when it receives focus. A mouse-first control made keyboard-usable.
- **Submit is disabled only on `loading`, never on invalid.** A permanently disabled button is a dead end — keyboard and screen-reader users can't interact with it to discover *why* they can't proceed. Letting the click through, forcing all fields touched, and announcing the errors is the accessible path.

## What I built (deliverables)
- `utils/validators.ts` *(created)* — pure `isRequired` / `isValidEmail`.
- `components/TextInput.tsx` *(created)* — presentational, four-part a11y wiring, `rightElement` slot.
- `components/PasswordInput.tsx` *(created)* — composes TextInput, owns visibility state.
- `pages/LoginPage.tsx` *(migrated)* — `values`/`touched` lifted, derived `fieldErrors`, touched-hybrid machine; all prior UX preserved (autoComplete, tabIndex on the eye, demo hint, error banner).
- `components/UploadPanel.tsx` — visually-hidden input restores keyboard access; `role="alert"` on the error banner.
- `pages/DocumentsPage.tsx`, `components/MessageView.tsx` — `aria-label` on unlabeled inputs.
- `styles/index.css` — global `.form-error`, `.visually-hidden-input`, `.transient-error-banner`.
- `styles/documents.css` — purged duplicated blocks, fixed phantom tokens, stripped hex fallbacks, added the `:focus-within` ring.

## STANDING ITEM: automate the token check
Undefined CSS tokens have now bitten **14 times** (`--color-red-200/600`, `--color-gray-300/400`, `--radius-md`, `--text-xxs`, `--space-1/2`, `--danger`, `--surface-base`…). Browsers drop invalid `var()` silently, so it never errors — it just renders wrong. Manual grep has demonstrably failed as a control. **Fix it with tooling, not discipline:** stylelint with a custom-property allowlist, or generate CSS from typed tokens so an undefined one is a compile error. Natural fit for Day 18 (testing/tooling).

---

# Day 17 — Quality states (loading / empty / error / retry)

Not a build day — a **systematic audit** of screens already written, using the mock's `?scenario=error` / `?scenario=empty` toggles as the instrument.

## Method: a grid, filled in the browser
Rows = every data view (Dashboard, Documents list, Document detail, Session list, Message view, Tasks tab, Audit tab, Login). Columns = loading / empty / error / retry. Each cell filled by **looking at it**, not by remembering what I wrote.

**What the audit exposed — chronological drift.** Screens built early (Dashboard, Documents: Day 7–8) had bare `<p>Loading...</p>` and unstyled `⚠️ {error}`. Screens built late (MessageView, Login) had shimmer skeletons and `role="alert"` banners. Nothing was *broken* — the baseline standard rises as a project matures and early work silently falls below it. That's why periodic audits are a practice, not a one-off.

**Why audit in the browser, not in code:** reading code hides layout shift, transition jank, and whether a component visually dominates the space it's in. A bare `<p>` looks fine in the source and causes a violent snap when data arrives.

**The biggest finding:** `refetch` was built on Day 15 and *no page called it*. Every error state was a dead end — recovery required a browser reload. Same argument as Day 16's disabled-submit-button: leaving the user with no application-level path forward.

## Shared components: `<ErrorState>` / `<EmptyState>`
- **`action?: ReactNode` slot — inversion of control.** The component owns layout, icon, typography; the *parent* formulates the interactive element. Avoids prop bloat (`buttonText` + `onClick` + `href` + `linkText`) and lets Dashboard pass a retry button while Document Detail passes a router link, with no special-casing. Same pattern as `TextInput`'s `rightElement` slot (Day 16).
- **Shared `.page-state-*` CSS with an icon modifier** (`.error` / `.empty`) — both occupy the identical footprint (centered, icon, title, message, action); only the icon tint differs.
- **SessionList deliberately did NOT use them.** They're sized for a 40vh page region; in a 320px sidebar they dominated and pushed content out of frame. Plain text instead. *Abstractions must fit the physical space* — same judgment as MessageView declining `useFetch`.

## Three empty-ish states, three next actions
| State | Message | User's next action |
|---|---|---|
| Pure empty | "No documents yet" | Create/upload something |
| Filtered empty | "Nothing matches your search" | Clear the filter |
| Error | "Failed to load" | Retry |
Conflating them leaves the user unsure whether the app is broken or just empty.

## Per-screen decisions
- **Dashboard empty replaces only the metrics + list, keeping the header.** A full-page takeover reads as "the app crashed"; keeping the personalized greeting reads as "fresh workspace." Also suppressed the "0 documents" meta line so it doesn't contradict the onboarding message.
- **Documents empty has no button** — `UploadPanel` is permanently mounted directly above it. A second CTA would compete with the real one; the empty state is purely instructional ("drag a file into the area above").
- **Document Detail branches 404 vs 500.** 404 = the resource doesn't exist, retry is futile → back-link. 500 = the server dropped it, retry is exactly right → retry button. Same component, different action, because the *recovery* genuinely differs.
- **Audit tab gets an explicit "No actions logged"** even though it's seeded — a production system purges logs, and a new user has triggered nothing. Without it, an empty tab reads as broken.

## Retry: two mechanisms, one reason
- Pages on `useFetch` call the hook's **`refetch`**.
- **MessageView and SessionList use a local `retryTrigger` counter** added to their effect's dep array — they bypass `useFetch` (bespoke optimistic lifecycles), so there's no `refetch` to call. Bumping an integer re-runs the effect. In SessionList it composes cleanly with the existing `refreshKey`: two independent triggers, one dep array.

## Skeletons vs spinners
Skeletons earn their markup cost where content has a **known shape** and they prevent layout shift — tables, card grids, metric tiles. They're overkill for a short sidebar list, where a quiet shimmer or text is honest. Don't skeleton everything.

## What I built (deliverables)
- `components/ErrorState.tsx` *(created)* — icon + title + message + `action?` slot.
- `components/EmptyState.tsx` *(created)* — same footprint, caller-supplied icon.
- `styles/index.css` — `.page-state-*`, `.state-wrapper-*`, reusable skeleton shapes.
- `pages/DashboardPage.tsx` — metric-card skeletons, onboarding empty state (header preserved), retry.
- `pages/DocumentsPage.tsx` — table-row skeletons, pure vs filtered empty split, retry.
- `pages/DocumentDetailPage.tsx` — granular skeletons, 404/500 branch, retry; inline styles purged.
- `pages/ActionsPage.tsx` — grid + timeline skeletons, both tabs' empty states, per-tab retry.
- `components/SessionList.tsx` — sidebar-appropriate shimmer/text states, `retryTrigger`.
- `components/MessageView.tsx` — shared `ErrorState` + `retryTrigger`.

---

# Day 18 — Testing (frontend basics)

Tracker named five **flows**, not units: login, document list, upload failure, chat answer, action confirmation. That framing is the steer — component tests that exercise behavior through the UI, not tests of implementation details.

## Setup
- **Vitest over Jest** because the project is Vite. Vitest shares `vite.config.ts`, module resolution, and plugins; Jest would need a parallel compile pipeline (`ts-jest`/Babel) to understand ESM + JSX — duplicated config, slower runs.
- `@testing-library/react` + `user-event` + `jsdom` + `@testing-library/jest-dom`.
- `src/test/setup.ts`: jest-dom matchers, MSW **node** server (`setupServer`, not the browser worker), lifecycle `beforeAll(listen)` / `afterEach(resetHandlers)` / `afterAll(close)`. Also mocks `scrollIntoView`, which jsdom doesn't implement.

## The test boundary
**Mock the network; keep everything else real.** Real DOM, real `AuthProvider`, real router — stop only at the HTTP boundary.
- **Real `AuthProvider`, not a fake:** a spy only proves the component *called* a function. The real provider proves the auth state actually updated and downstream effects fired. General rule: mock other people's code, not your own.
- **A `/dashboard` stub route** inside `MemoryRouter` makes the success test honest — asserting the stub rendered proves the whole chain (network resolved → auth updated → router navigated), rather than just "navigate was called."
- Assert on **your seam**, not on library behavior.

## Querying: how a user perceives the DOM
`getByRole` / `getByLabelText` over CSS selectors or test IDs. Classes churn during refactors; test IDs clutter markup without user value. **If a test can't find a button by role and name, a screen reader can't either.**
- **Day 16's accessibility work paid off directly** — `role="alert"` on error banners turned brittle `findByText(/error/i)` into explicit `findByRole('alert')`. Accessible markup and testable markup are the same markup.
- `getBy` = must exist now (throws). `findBy` = async, retries until it appears (returns a Promise). `queryBy` = asserting *absence*, returns `null` instead of throwing.

## MSW in tests
- **Reusing the dev handlers prevents mock rot.** Contract changes in `handlers.ts` update the browser *and* the whole suite at once — no second set of mocks to drift.
- **`server.use()` vs `?scenario=error`:** `use()` surgically overrides one endpoint for one test (a 401 with a specific message), torn down by `resetHandlers()`. `?scenario=` is the browser-side toggle where you can't inject JS at runtime.
- **`onUnhandledRequest: 'error'` in tests, scoped predicate in the browser.** The browser legitimately loads CSS, fonts, HMR scripts. In tests, an unmocked request is a bug — fail loudly.
- **`resetHandlers()` resets handlers, NOT the mock database.** Mutations to `mockTasks` / `mockChatMessages` persist across tests in a file.

## The bug: untyped fixtures test hallucinations
The action-approval test crashed with `Cannot read properties of undefined (reading 'title')`. The fixture flattened the shape — `{ type, title }` — when `ActionProposal` requires `{ type, label, payload: { title, priority } }`. **TypeScript never caught it because `HttpResponse.json()` takes an untyped body — type safety evaporates at the network boundary.**

The same applied to the `/api/ai/actions` override returning `{ success: true }` when `ActionCard` checks `data.status === 'completed'` — that one wouldn't even crash, just silently render the rejected state.

**Lesson: type your fixtures** (`const proposal: ActionProposal = {...}`). Otherwise the test verifies an imaginary scenario and the component crashes on the real contract. Next step would be `test/fixtures.ts` with typed builders so every test starts from a valid object.

## What I built (deliverables)
- `vite.config.ts` — `defineConfig` from `vitest/config` to expose the `test` block; jsdom env + setup file.
- `src/test/setup.ts` *(created)* — MSW node server lifecycle, jest-dom matchers, `scrollIntoView` stub.
- `src/pages/LoginPage.test.tsx` *(created)* — validation guard, 401 transient error, successful auth → dashboard stub.
- `src/pages/DocumentsPage.test.tsx` *(created)* — populated list, pure empty state, fetch error **+ retry recovery**, upload failure.
- `src/pages/MessageView.test.tsx` *(created)* — optimistic send → thinking → AI answer; action proposal → approve → completed state.

## Backlog (decided deliberately, not omitted)
- **`useFetch` race-condition test.** Covered *indirectly* by every page test, but the `ignore`-cleanup race needs `renderHook` + staggered MSW delays asserting only the second fetch lands. Brittle to test through a component; belongs in isolation. **Must be written.**
- **Automated CSS token check** (the 14-incident standing item) — chose Vitest over stylelint: ~10 lines of `fs` to parse `:root` into a Set and assert every `var(--x)` across `src/**/*.css` exists in it. No new dependencies, runs in `npm test`. *Caveat: the regex must handle nested/fallback forms `var(--a, var(--b))` or it'll pass files referencing an undefined `--b`.*

---

# Day 19 — Responsive UX + accessibility

Like Day 17, an **audit** — instrument was DevTools' device toolbar at 375px / 768px, not `?scenario=`. Every layout was desktop-only; the audit found where each broke. Two findings weren't "add a media query" — they were design decisions (the sidebar, the chat two-pane).

## Responsive layout
- **The desktop regression, and the rule it taught:** adding the mobile drawer styles broke *desktop* — content dropped below the sidebar with an empty band. Cause: a mobile layout rule (grid collapse / `position: fixed`) leaked into the **base** CSS instead of being fenced inside the `max-width` query. **Rule: base styles define the desktop layout; media queries are scoped overrides only.** Same "did the change leak where it shouldn't" discipline as the refactor days — an unscoped media rule is a global change in disguise.
- **Sidebar → off-canvas drawer** (over icons-only or bottom-bar): preserves full label readability, fits the 5-item nav without truncation, avoids the space crunch of the alternatives.
- **Chat two-pane → CSS-only master-detail.** Single column at ≤768px, tapping a session swaps the list for the messages, in-UI back returns. **Knowingly accepted limitation:** selection lives in component state, not the URL — so the *hardware/browser* back button exits the app instead of returning to the list. Fixing that is the `/chat/:sessionId` refactor, still backlogged. (Mobile is the forcing function, exactly as predicted on Day 14.)
- **Documents table → ruthless column-hiding** (show Name + Status, hide Size + Uploaded at ≤768px). Horizontal scroll hides data off-screen; card-per-row destroys comparative scannability. Tables genuinely don't reflow, so you choose what to drop.

## Accessibility — the drawer (the day's real substance)
- **`role="dialog"` + `aria-modal="true"` inform, they don't enforce.** They tell assistive tech the background is suppressed — but they do **not** intercept physical `Tab`. Keyboard focus still leaks into the background unless something blocks it. "Labeled as a modal" ≠ "behaves as a modal."
- **The trap: `inert` on the background** (`.main-content` + header), not a manual keydown wrap. `inert` is browser-native — it removes a subtree from *both* the accessibility tree and the tab sequence at once, avoiding a brittle ~15-line Tab/Shift+Tab hijacker.
- **The bug `inert` created:** the hamburger lived *inside* the `<header>` that got inerted. On close, `hamburgerRef.current?.focus()` fired synchronously in the event handler, but `removeAttribute('inert')` runs in an effect *after* render — so focus targeted a still-inert element and silently dropped to `<body>`. **Fix: move the hamburger out of the inerted region** — a direct child of `.app-shell`, positioned into the header's visual space via CSS. The toggle is a shell control, so it belongs outside both inertable regions.
- **The full keyboard contract for a modal drawer** (all six needed):
  1. Focus moves into the drawer on open.
  2. Focus is trapped (Tab/Shift+Tab cycle within).
  3. Escape closes.
  4. Backdrop click closes.
  5. Route change closes.
  6. Focus restores to the trigger (hamburger) on close.
  Most production drawers miss at least one — usually the trap or the focus-return.

## Accessibility — the rest
- **Two form-field warnings** (DevTools Issues): the filter `<select>`s lacked `id`/`name` mapped to a `<label htmlFor>`. Without it a screen reader can't announce what the control filters. (Same pattern as Day 16's login fields.)
- **Contrast:** `--color-gray-500` (#6b7280) on `--color-gray-50` failed for the small uppercase labels. Small + uppercase = tighter density, most prone to failing. Bumped to `--color-gray-700` → 8.5:1, well past the AA 4.5:1 minimum for normal text. (Verified in Lighthouse, not by eye.)

## What I built (deliverables)
- `Layout.tsx` — off-canvas shell, `inert` focus trap, hamburger moved outside inerted regions, Escape/backdrop/route-close, focus entry + restore.
- `Header.tsx` — prop-less, brand + user session.
- `styles/layout.css` — mobile drawer + grid-stack rules fenced inside `max-width: 768px`; base stays desktop.
- `styles/management.css` — column-hiding at ≤768px, 44px touch targets for row actions.
- `pages/ActionsPage.tsx` (+ documents filter) — `id`/`name`/label on the selects.

## Still open / backlog
- URL-driven chat sessions (`/chat/:sessionId`) so the hardware back button works on mobile — the recurring deep-linking debt, now with a concrete mobile cost.
- Verify at runtime: Tab genuinely can't escape the open drawer; Escape/backdrop return focus to the hamburger (not `<body>`).

---

# Day 20 — Framework mindset (React → Vue translation)

A writing day, not a build day. Point: prove React understanding is *conceptual*, not memorized syntax — if you know *why* you made a choice, you can map it onto a different framework's model. Started from zero Vue; learned Vue's model by asking "how would *my* components work here?"

**The thesis the whole doc rests on:** *Vue formalizes and enforces what React leaves to convention and discipline* — and the reactivity-model difference underneath explains most of the specifics.

## 1. State & reactivity (the foundational difference)
- **React re-runs the whole component function on every state change**, then diffs — so it needs `useMemo`/`useCallback`/deps arrays to *opt out* of redundant work. **Vue tracks dependencies granularly and updates only what changed** — so memoization is largely unnecessary.
- Honest framing: not "Vue is faster." React's re-run is cheap; Vue's tracking has proxy overhead. The difference is *where the optimization burden lies* — Vue moves it into the framework, React exposes the primitives to you.
- `useState` → `ref`/`reactive` (`.value`, no setter). Tradeoff: React's `[value, setValue]` is verbose but uniform; Vue's `.value` has unwrapping rules (`.value` in script, auto-unwrap in template, `reactive` destructuring loses reactivity without `toRefs`).
- `useMemo` → `computed` (auto dependency-tracking + caching — what `useMemo` wishes it were).
- `useEffect` deps → `watchEffect` (auto-tracks reads, no array) / `watch`.
- **The deepest point — stale closures:** React effects close over the render they were created in, so a missing dep reads stale values (the bug class deps arrays guard against). Vue reads refs *live* via `.value`, so there's no closure capture to go stale. Root cause of why React needs machinery Vue doesn't.
- `useFetch` `skip` → `watch(src, fn, { immediate: false })` or a guard.

## 2. Props down, events up
- **React: one mechanism (props) for both directions.** "Events" are just callback props (`onSessionCreated`, `onUploadSuccess`) — a naming convention (`on*`), nothing enforced.
- **Vue: two declared channels.** Props down; `emits` up — `defineEmits(['session-created'])` + `emit(...)`, parent listens `@session-created`. A *declared contract*: undeclared emits warn.
- Deeper "why": Vue makes **props readonly by design** (mutating throws) — it *enforces* the one-way flow React only *recommends*. → the thesis in one line.
- `v-model` = sugar for `:modelValue` + `@update:modelValue` — Vue formalizing the two-way binding React deliberately omits. (Seed for §6.)

## 3. Lifecycle & effects
- **React: one overloaded hook.** `useEffect` = mount (`[]`), change (`[x]`), or every render (no array) — intent hidden in the deps shape.
- **Vue: named tools.** `onMounted`/`onUnmounted` for timing; `watch`/`watchEffect` for change. Self-documenting.
- `useFetch` mount+refetch → `watch(url, fn, { immediate: true })` — `immediate` *unifies* what React bundles by deps-array accident.
- Scroll-after-messages → `watch(messages, ...)` + `nextTick()`. Depth: `nextTick` waits for Vue's *async update queue* to flush (Vue batches by design), not just "wait for DOM."
- **Nuance:** the drawer's Escape listener depends on `[isMobileMenuOpen]` (conditional), so it maps to `watch`, NOT `onMounted`/`onUnmounted` (those fire once per lifetime). Don't pattern-match "listener = lifecycle hook."

## 4. Shared state: Context vs provide/inject
- `AuthContext` → `provide('auth', state)` / `inject('auth')`. Same purpose.
- Day-15 "where useful" judgment transfers unchanged — global state for genuinely-global concerns (auth), never page-local/URL-driven data. Overuse trap is identical.
- State lifting is framework-agnostic ("lowest common ancestor that needs it"); React passes value+setter, Vue passes props + `emits` (or `provide/inject` if depth is awkward).
- **Payoff back to §1:** React Context re-renders *all* consumers when the value's reference changes (footgun → split contexts / Zustand). Vue's reactive `inject` updates only consumers that read the changed piece — because of granular reactivity. Same root difference explains it.

## 5. Error handling & the forced class
- **React forces a class** for `ErrorBoundary` — `getDerivedStateFromError`/`componentDidCatch` predate hooks and were never ported. Not a design choice, **legacy debt**: the one non-function component in the app.
- **Vue: uniform hook** — `onErrorCaptured((err, instance, info) => ...)` in any component, `return false` stops propagation.
- **Scope difference (not a shared limitation):** React's boundary is render-phase-only. Vue's `onErrorCaptured` covers render + lifecycle + watchers, and routes component event-handler errors through Vue's error system too — so Vue's manual try/catch burden is *smaller*. (React boundary genuinely can't catch async/event-handler errors — the Day 17 lesson.)
- `key={location.pathname}` reset → `<router-view :key="$route.fullPath">` — shared remount-to-clear-state pattern.

## 6. Forms: controlled inputs vs v-model
- **React: no two-way binding by design.** `TextInput` is controlled — `value` down + `onChange` up, wired every time, on principle (traceable one-way flow).
- **Vue: `v-model`** fuses them. On a *custom* component, `v-model` = the §2 `:modelValue`/`@update:modelValue` contract with sugar (the seed pays off).
- Touched-hybrid validation: `v-model` removes value-binding boilerplate, but the `touched`/error *machine* is custom in both. Vue's `fieldErrors` as a `computed` is *ergonomically* cleaner (auto-cache, no `useMemo` ceremony) — not a real perf win at this scale.
- Tradeoff: React explicit-but-verbose; `v-model` concise-but-hides-mechanism (a junior may see it as magic, not prop+emit).

## 7. Routing
- **React Router: component-based** (`<Route element={...} />`), `useNavigate`, `useParams`, guard via `ProtectedRoute` *wrapper*.
- **Vue Router: config-based** (`{ path, component }`), `useRouter().push()`, `useRoute()`, guard via `router.beforeEach` + `meta: { requiresAuth }`.
- `ProtectedRoute` component → `beforeEach` guard = the §2 thesis applied to routing (component convention vs declared framework contract).
- `useNavigate('/dashboard')` → `router.push('/dashboard')` — line-for-line.
- **Deep-linking backlog reframed:** chat-selection-in-state-not-URL was *never a React constraint* — a product architecture choice. Fix is the same shape in both (`sessionId` → route param, `useParams` vs `useRoute`). The rule is framework-agnostic: **state a user expects to refresh/share/navigate-back belongs in the URL.**

## Deliverable
`docs/react-to-vue-translation.md` — 7 sections, each anchored to a real artifact (`useFetch`, `MessageView`, `AuthContext`, `ErrorBoundary`, `TextInput`, `ProtectedRoute`), cross-referenced, on one thesis.

---

# Day 21 — Integration prep (API contract freeze)

Deliverable: `docs/API_CONTRACT.md` — the frozen mock-API contract Spring Boot implements against in Month 2. Success test: **backend replaces mocks, zero screens break.** This is where a month of contract-first discipline pays off — the doc is *extraction from `handlers.ts` + `Type.ts`*, not invention.

## The mindset: adversarial self-read
Read your own handlers as the backend dev who's never seen the frontend. Every place the doc is *nicer* than the code is a screen that breaks in Month 2. The rule: **doc matches code byte-for-byte, OR the divergence is flagged as a required frontend change.** No silent drift.

## The four drift bugs I caught reconciling against code
1. **Path prettification** — wrote `/chat/sessions/:id/messages`; frontend calls `/chat/:id/messages`. A tidier path in the doc = 404 in prod. Fix: document the path the frontend actually calls.
2. **Envelope drift** — `GET messages` returns a **bare array** (not `{ messages }`); `POST /chat/message` returns a **single assistant Message** (user msg is optimistic client-side), not `{ userMessage, assistantMessage }`. Doc the shape the consumer *reads*.
3. **Pagination envelope on `GET /sessions`** — frontend consumes a bare `ChatSession[]`. Applying `{ items, total, page, size }` silently breaks `SessionList`. Fix: document both — "mock-compatible bare array" + "v1 contract envelope (requires frontend update)".
4. **Field/enum drift** — `Citation` is `excerpt`+`section` (not `snippet`); `priority` is lowercase `'high'` (not `"HIGH"`). Renames/casing silently break rendering.

## Client-only fields must be *excluded*, not just omitted
The discriminated-union DTOs are where client-state and server-contract are easiest to conflate (the *card* has a rich state machine; the *proposal* is just data).
- `Message` excludes `status`/`errorMessage`/`retryTrigger` (client bookkeeping).
- `ActionProposal` excludes `status` (client UI-state machine) but **must include `label`** (the card's preview text) — the mirror-image fix. Same lesson twice.

## The high-risk DTOs (would get flattened in a naive handoff)
- **Discriminated unions** (`ActionProposal`/`ActionRequest`/`ActionResult`) — documented every variant with its per-`type` payload/result, plus a Jackson `@JsonTypeInfo`/`@JsonSubTypes` note. `ActionResult` especially: `type` → result shape (`create-task`→`Task`, `summarize`→`{summary}`, `lookup`→`{snippets}`) — else a backend builds `Object result` and loses the correlation. This is where the Day 13 type work survives the handoff.

## Cross-cutting decisions (contract ahead of the mock)
- **Error envelope standardized** to `{ message, code, timestamp }` with a defined `code` constant set — even though the mock drifted (some bare status codes). One `@ExceptionHandler` for the backend. Documenting the *intended* contract, not the mock's inconsistency.
- **Auth headers**: audit found `useFetch` sends *none* (mock never checked). Contract mandates `Authorization: Bearer` on every endpoint except login; flagged as a required Month-2 frontend change.
- **Pagination**: mock returns unbounded arrays. Specified `?page=&size=` + `{ items, total, page, size }` as **v1 backend requirement / v2 frontend consumption** — the backend builds it now, frontend adopts later.
- **FK relationships** summarized as a table (`Citation.documentId`, `Task.sourceSessionId`, `ActionAudit.sessionId`, `Message`→sessions) so the backend builds real DB constraints — the enforced version of the Day 12 "dangling reference" lesson.
- **Transactions/side-effects documented**: atomic `POST /chat/sessions` (`{session, messages}` in one txn); `POST /chat/message` persists 2 msgs + denormalized parent update; `POST /ai/actions` logs *both* decisions, executes only approvals; `PATCH /tasks` bidirectional `completedAt`.
- **Multipart flag**: `POST /documents/upload` is the *only* `multipart/form-data` endpoint — field name `file`, size/MIME rules the backend must enforce *independently* (client validation isn't trustworthy).
- **Prefix affirmation**: `/ai/actions` vs `/actions/audit` intentionally differ — "match exactly, don't normalize" (pre-empting the helpful fix).

## Format
Structured Markdown over OpenAPI — a handoff dev cares about narrative constraints, transaction side-effects, and inline mock-vs-contract notes that a rigid schema can't carry fluidly.

## Consolidated Month-2 frontend backlog
1. Inject `Authorization: Bearer` into `useFetch`.
2. Migrate list components to the pagination envelope.
3. `/chat/:sessionId` deep-linking (the recurring URL-state debt).

## Loose ends flagged
- `signup` referenced in auth exemptions but no endpoint exists — drop or mark "not in v1".
- `CHAT_NOT_FOUND` vs "session not found" naming — unify the code constant.

═══════════════════════════════════════════════════
# MONTH 2 — BACKEND (Java + Spring Boot + PostgreSQL)
═══════════════════════════════════════════════════

# Backend Day 1 — Spring Boot orientation + package map

Mirror of frontend Day 1: scaffold the project, map the product to modules. The Day 21 contract is the input. Teaching rule unchanged (I write every line; AI guides + reviews). Notes continue in this same file.

## Environment (from scratch — no Java was installed)
- **JDK 21** via Homebrew (`brew install openjdk@21`). Managed/work Mac → not in sudoers, so skipped the system symlink; the PATH export alone (`export PATH="/usr/local/opt/openjdk@21/bin:$PATH"` in `~/.zshrc`) is enough. Intel Mac → Homebrew paths are `/usr/local/...` not `/opt/homebrew/...`.
- **IntelliJ IDEA**, Maven build tool. Registered JDK 21 via Project Structure → SDKs (IntelliJ had auto-downloaded JDK 26 and was using it — fixed so build+runtime both = 21, matching `pom.xml`).

## Scaffold — Spring Initializr
- start.spring.io: Maven, Java 21, Jar. Group `com.knowledgeassistant`, Artifact `knowledge-assistant`.
- **Spring Boot 4.0.7** — the timeframe only offered 4.x (3.x is past its window). Chose 4.0.7: the settled non-SNAPSHOT option (avoid SNAPSHOT = nightly/unfinished; avoid newest-4.1.0 = least docs). Tax: most tutorials are 3.x, so some artifact names differ (`spring-boot-starter-webmvc` not `-web`; split `-test` starters) and some autoconfig classes moved packages.
- **4 dependencies, chosen deliberately** (not everything): Spring Web (REST + embedded Tomcat), Spring Data JPA (persistence), PostgreSQL Driver (JDBC connector), Validation (Bean Validation for Day 2 DTOs). Did NOT add Security (demo login only; Security locks every endpoint by default), Lombok (see plain Java first), or Flyway (Day 3 adds it).
- **Java package name = `com.knowledgeassistant`** — underscore, because the hyphen in the artifact is illegal in Java packages so Initializr converted it. Non-idiomatic (convention is no separators) but left as-is; not worth renaming mid-setup.

## Spring concept learned: inversion of control / auto-configuration
- Spring is an IoC container: you *declare* what you need (`@Service`, `@RestController`, `@Repository`) and Spring instantiates + wires the objects ("beans"). A controller doesn't `new` its service — it declares the dependency in its constructor and Spring injects it. Biggest shift from school-Java (where you wire by hand).
- **Auto-configuration:** Spring wires machinery based on what's on the classpath. Seeing `spring-boot-starter-webmvc` → it started an embedded Tomcat on 8080 with zero config. Seeing JPA + Postgres driver → it tried to open a DB connection *at startup*.

## The boot problem + the Maven-parent lesson
- First run **failed** (expected + informative): `Failed to configure a DataSource` → the JPA/Postgres auto-config tried to connect at startup with no DB configured. The bean chain (`entityManagerFactory` → `dataSource`) collapses; Spring aborts — **all-or-nothing bean wiring** (can't boot halfway).
- Fix for "boot empty today": exclude the DB auto-config so the app runs as a bare web server. **The properties-file exclude (`spring.autoconfigure.exclude`) did NOT work in Boot 4.x** — the JPA chain slipped through. The **annotation exclude worked**: `@SpringBootApplication(exclude = { DataSourceAutoConfiguration.class, HibernateJpaAutoConfiguration.class })` — read earliest, before the auto-config list is built. Had to exclude *both* (DataSource alone left JPA still trying to build `entityManagerFactory`).
- **4.x moved the autoconfig packages** — my 3.x import paths (`...autoconfigure.jdbc.*`, `...autoconfigure.orm.jpa.*`) didn't resolve. Lesson: don't guess import paths — put the cursor on the red symbol, **⌥Return → Import class**, and let IntelliJ find the real 4.x package. (Reusable technique for any unresolved symbol.)
- `// TODO: remove these excludes on Day 3-4 when PostgreSQL is configured` — the excludes are temporary scaffolding; on Day 3 they come off and the real DB connection goes in, at which point this auto-config is exactly what powers persistence.
- Clean boot achieved: `Started KnowledgeAssistantApplication in ~2s`, Tomcat on 8080, on Java 21.

## The deliverable: feature-first package map
Under `com.knowledgeassistant`, one package per contract resource + two cross-cutting:
```
auth      document   chat   action   task     (feature domains)
common    config                              (cross-cutting)
```
- **Feature-first over layer-first** (chosen): the Day 21 contract is already grouped by resource, so packages mirror it. Each feature will hold its full vertical slice — `controller`, `service`, `repository`, `entity`, `dto` as sub-packages. Avoids the "package explosion" of global layers (all controllers in one giant directory) and keeps a bounded context's code physically adjacent.
- **`common` vs `config` split:** `common` = shared domain types (the `{message, code, timestamp}` error envelope, base exceptions, shared DTOs multiple features consume). `config` = Spring wiring (`@ControllerAdvice` handler, future CORS/security, DataSource beans). Separates business-shared objects from framework wiring → clean dependency direction. (Aside: the `@ControllerAdvice` handler could arguably live in `common` as shared behavior — either is defensible, just be consistent.)

## Environment gotchas worth remembering
- Managed Mac blocks `sudo` — route around it (PATH export instead of system symlink); watch for the same wall on `brew install postgresql` at Day 3.
- Moving the project folder while IntelliJ has it open desyncs `.idea` ("Cannot find IntelliJ IDEA project files") → close project, delete `.idea`, reopen from the true path. Project home is now `~/IdeaProjects/knowledge-assistant` — don't move it again.
- Empty Java packages are fiddly to create (IntelliJ's New menu showed only Python options when right-clicking the wrong node) — right-click the actual package node under a blue Sources Root; if needed, Mark Directory as → Sources Root first.

## Next (Backend Day 2)
REST fundamentals — health endpoint + base response/error DTOs (the `{message, code, timestamp}` envelope from the contract), Bean Validation, consistent HTTP status codes. First actual controller.

---

# Day 15 — FE-BE Integration: swap MSW mock for real Spring Boot (frontend slice)

THE PAYOFF of both months: the Month-1 React frontend now runs against the real Spring Boot + PostgreSQL backend built in Month 2 — with NO screen rewrites. (Backend CORS config recorded in backend-notes.md.) Success: frontend runs against the real backend without major screen rewrites — MET.

## The mock/real toggle (MSW seam)
The Month-1 mock was MSW intercepting `fetch` at the network layer — which is why components DON'T change: the toggle is at the network layer, not the component layer.
- `enableMocking()` gated on the env flag: `if (import.meta.env.VITE_USE_MOCK !== 'true') return;` — when false, the worker never starts, so `fetch` hits the real network. When true, MSW intercepts as before. Mock mode stays fully available (flip the flag, restart Vite).

## Environment config (Vite)
- `.env` in the PROJECT ROOT (next to package.json — Vite only loads it there). Vars MUST be prefixed `VITE_` to reach client code.
- `VITE_API_BASE_URL=http://localhost:8080`, `VITE_USE_MOCK=false`.
- **Restart Vite after editing .env** — vars are read at dev-server startup; edit-and-forget-to-restart is the #1 "env var not working" cause.
- `.env` gitignored; commit `.env.example` documenting the vars.

## The adapter (api/client.ts — apiFetch)
A thin `fetch` wrapper, the single seam that makes real mode work:
- `BASE_URL` = '' in mock mode (relative → MSW intercepts) or `VITE_API_BASE_URL` in real mode (absolute → backend). Same wrapper, env-driven.
- Reads token from localStorage, sets `Authorization: Bearer <token>` when present.
- Sets `Content-Type: application/json` UNLESS the body is `FormData` — critical: forcing JSON content-type on the multipart upload would break it (the browser must set the multipart boundary itself).

## Auth token plumbing
- Login `POST /api/auth/login` (real creds `user@example.com` / `securepassword123` — NOT the old mock hint `developer@example.com`/`Password123!`; the real seeded DB differs).
- On 200, store `token` (`demo-token-<uuid>` — an OPAQUE demo token, NOT a JWT) + the user object in localStorage. Adapter attaches the token to all subsequent requests.
- Backend receives but IGNORES the token today (endpoints still open; enforcement is backend Day 16). Wiring it now means tomorrow's route protection slots in.
- (localStorage is the pragmatic demo choice; it's XSS-exposed — a production app would use httpOnly cookies or in-memory+refresh. Noted, not changed.)

## The scattered-fetch finding (honest retro)
Components called raw `fetch('/api/...')` scattered across pages (not a clean central API module) → the swap touched every API-calling component: `fetch(` → `apiFetch(` + import. NOT a screen rewrite (no UI/state/JSX change — same call, wrapped), but more than the ideal one-file flip. A shared `useFetch.ts` hook was a partial centralization point — swapping the one `fetch`→`apiFetch` there cascaded to every screen using it. LESSON: a fully centralized API layer in Month 1 would have made today a single-file change. Worth doing next time.

## The HTML-instead-of-JSON gotcha
Before swapping a component: with MSW off + a relative path, `fetch('/api/documents')` hit `localhost:5173` (Vite dev server, not the backend) → Vite returned its `index.html` SPA fallback → `JSON.parse('<!doctype html>...')` → "Unexpected token '<'". Diagnosis: that screen still used raw `fetch`. Fix: the apiFetch swap (absolute base URL).

## Contract-first paid off — what DIDN'T happen today
No field-name mismatches, no `uploadDate` vs `created_at` scrambles, no chat-route 404s. All pre-empted: the DTO boundaries (backend Days 3-4), the reserved-word mapping (`created_at`→`timestamp`), and the chat-route regression fix (backend Day 14's integration test caught `/sessions/{id}/messages` drift the day before this swap). Two months of "match the frozen contract" made today plumbing, not surgery.

## Verified
Login → 200 from real Spring Boot, token+user in localStorage, UI logged in. After swapping all components + the useFetch hook: documents (real seeded rows), chat ("Airport Operations Review", real messages), tasks, actions — all live against PostgreSQL. Zero component rewrites.

## Day 15 addendum — post-integration fixes (the mock-hid-bugs the real backend exposed)

Swapping to the real backend surfaced a class of bugs the MSW mock hid — the mock faked session creation permissively, so the new-conversation flow was never truly exercised against real persistence. Three real issues found + fixed (this IS what Day-15 integration is for):

1. **500 on `POST /api/chat/sessions`** — `createSession` violated a NOT-NULL constraint (empty session fields). Fixed by setting all required fields.
2. **`Cannot read properties of undefined (reading 'id')`** — response-shape mismatch: the mock returned a differently-shaped/wrapped create-session response; the real backend returns a bare `ChatSessionDto {id,...}`. Frontend was reading a nested path. Aligned the frontend to read the bare DTO's `.id` (consistent with all other endpoints returning bare DTOs).
3. **Empty orphaned sessions (the real bug).** `POST /sessions` created a session but IGNORED the frontend's `initialMessage` body → the first message was never persisted → sessions with 0 messages (confirmed: `SELECT ... FROM messages WHERE session_id=...` returned 0 rows) and generic "New Conversation" titles. This was the **Day-8 "session created atomically with the first message" design never actually built** — the frontend sent `initialMessage`, the backend dropped it.
   - **Fix (atomic createSession):** `CreateSessionRequest(@NotBlank initialMessage)` DTO; `createSession(userId, initialMessage)` now derives the title from the first message (truncated ~50 chars), creates the session, AND persists the user message + AI placeholder + preview — all in one `@Transactional` (same shape as `sendMessage`, plus session creation). The Day-8 design finally realized.
   - Result: new chats show a real title (e.g. "tell formulas of adbms"), the first message persists (survives refresh), no more empty sessions.
   - TODO: delete the orphaned empty sessions already in dev (`DELETE FROM chat_sessions WHERE title='New Conversation' AND id NOT IN (SELECT DISTINCT session_id FROM messages)`), and ADD an integration test for create-session-persists-first-message-and-derives-title (Day-14 suite missed this path — no test for it).

LESSON: the mock was more permissive than the real backend. Parallel frontend/backend dev via a contract works, but only REAL integration proves the halves mesh — the create-conversation flow "worked" against the mock and was broken against the real backend. Exactly what Day 15 is designed to catch.

## Four project-wide gaps spotted (mentor's rule: fix gaps you find, even if not in the tracker) — dispositions

Reasoned about scope/sequencing rather than building all four reflexively:
1. **Multi-user scoping** — only one seeded user; `DEMO_USER_ID` hardcoded everywhere. → This IS Day 16 (authorization boundaries / user scoping). Do it tomorrow properly, not today. (Self-service SIGNUP is a separate, bigger question — reason about whether a demo needs registration at all vs. correct per-user scoping of existing users.)
2. **Forgot password** — none. → **DROPPED as out of scope.** A correct impl needs a reset-token table, SMTP/email infra, token expiry, request+confirm endpoints, reset UI — multi-day, serves demo-grade auth while the core RAG thesis waits. Logged as a known production limitation, not built. (Scope discipline: not building a real gap is sometimes the right call.)
3. **Open the real document from the site** (not just metadata) — the file is stored (Day 7, UUID in uploads/) but there's NO retrieval endpoint. → Approved, DEFERRED to Day 16/17 so it's born secure: a `GET /documents/{id}/download` that streams the bytes AND checks user ownership from the start (not scoped as an afterthought).
4. **Delete a chat** — no delete. → Approved, DEFERRED to Day 16/17, same reason: a `DELETE /chat/sessions/{id}` with an ownership check. Schema already supports the cascade (messages FK ON DELETE CASCADE, Day 3).

Principle: #3 and #4 have a security dimension (scoping downloads/deletes to the owner). Building them today = building them again tomorrow to add scoping. Bundling them WITH Day-16 scoping means the first version already checks ownership — secure by design, not by patch.

## Day 15 (cont.) — the missing endpoints + the agentic loop, finally testable

Integration kept surfacing gaps the mock had hidden. Beyond the session-creation fixes above:

### Missing endpoints the frontend expected but the backend never built
- **`GET /api/actions/audit`** — audit rows were WRITTEN since Day 10 but never READABLE. Built the endpoint + `ActionAuditDto` + a `getAuditTrail()` sorted newest-first.
- **`PATCH /api/tasks/{id}`** — `TaskController` had only GET; the status dropdown had no endpoint to call. Symptom was a `0 B transferred` request with no status code = a CORS-blocked method (PATCH wasn't in `allowedMethods`). Built: `TaskNotFoundException` + `TASK_NOT_FOUND` (the Day-11 DRY payoff — one class, no handler change), `Task.setStatus/setCompletedAt`, a transactional `TaskService.updateStatus` with conditional `completedAt` (set on `done`, cleared otherwise), the `@PatchMapping`, and PATCH added to CORS. Also removed a duplicate `updateTaskStatus` in `ActionController` (two mappings on the same path = ambiguous-handler startup crash).
- **The hyphen boundary, third appearance:** `TaskDto` was serializing raw enum names (`in_progress`) while the React dropdown expects `in-progress` → the "silent revert". (Fixed at the DTO. NOTE: the hyphen rule now lives in three places — the DB `@Converter`, `@JsonValue` on the enum, and this DTO mapping. One source of truth would be better; small consolidation debt.)
- **Chat links** from tasks/audit went to `/chat` not `/chat/{id}` — root cause was NOT data (backend sent correct UUIDs) but a hardcoded `<Link to="/chat">` in `ActionsPage.tsx`. Fixed with template literals. (An earlier `@JsonProperty` remap on `ActionAuditDto` had been a fix for a MISDIAGNOSED cause — reverted once the real cause was found. DTO names now follow their DB columns: `session_id`→`sessionId` for audit, `source_session_id`→`sourceSessionId` for tasks. Coherent vertical slices per domain, not an artificial unified convention.)

### The agentic loop — human-in-the-loop was never testable from the UI
The governance backend worked (DB proof Day 10, Swagger Day 12, tests Day 14) but was UNREACHABLE from the product: the placeholder AI only ever returned a canned string, `MessageDto` deferred `actions` (Day 9 YAGNI), so `msg.actions` was always undefined and `MessageActions` never rendered. The whole discriminated-union/governance design was curl-only.
- **Fix (rule-based proposer, non-AI placeholder logic):** `ActionProposalDto`; `MessageDto` extended with `List<ActionProposalDto> actions`; a keyword scanner in `sendMessage` ("create a task"/"todo"...) that attaches a `create-task` proposal to the response. Clean seam: Month 3's real tool-calling replaces the PROPOSER only — the `POST /ai/actions` governance contract is unchanged.
- **Verified through the real UI:** trigger → proposal card renders → Approve → audit row + Task created → task appears in the Actions tab. And the asymmetry holds through the UI path: **9 approvals → 9 audit rows → 9 tasks; 2 rejections → 2 audit rows → 0 tasks.**

### ActionStatus — a modeling gap the frontend's vocabulary revealed
The frontend expected `completed` where the backend sent `approved`. NOT a rename-to-appease-the-client: added an `ActionStatus` enum (`completed, rejected, failed`) and typed `ActionResult.status` to it.
- **The decisive argument:** `approved` = what the human DECIDED; `completed` = what the system DID. Approved-but-execution-failed is a REACHABLE state that `ActionDecision` cannot express — and a type that can't represent a reachable state is the wrong type for that field.
- Two different FACTS about one event, each recorded where it belongs: `action_audit.decision` stays `approved` forever (it records authorization; saying `completed` there would corrupt the audit's meaning); the API response reports outcome, which is what the caller renders.
- The test that separates this from bending-to-the-frontend: *would I keep `ActionStatus` if the frontend vanished tomorrow?* Yes — execution outcome is a real server-side concept. (Renaming a field to match a client's spelling of the SAME concept would be the slippery slope; adding a concept the backend was MISSING is not.)

### Known debt / Day-16 list additions
- `failed` in `ActionStatus` is never produced — exceptions propagate to the error handler and the client sets its own failed state. Headroom to wire when execution can fail partway.
- **Proposal payload uses `Map<String,Object>` with hardcoded `"title"`/`"priority"` keys** that must match `CreateTaskPayload`'s component names. A rename breaks it SILENTLY at deserialization on a later request, not at compile time. Constructing proposals from the sealed `ActionPayload` would make that a compile error. (Serialization is forgiving — polymorphic-in/flat-out from Day 10 — but this is a correctness hazard, not just asymmetry.)
- **Proposals are ephemeral** — confirmed in code: `sendMessage` returns `MessageDto.from(aiMessage, proposals)` while `getMessages` uses the single-arg `from`. A refresh before deciding drops a pending proposal permanently. Fine for a demo; a governance flow in Month 3 wants pending decisions to survive a refresh.
- **No route protection at all** — `POST /api/ai/actions` currently accepts any session id from anyone; there's no Spring Security on the backend. (Testing reached the UI by setting the token/user keys in localStorage directly rather than via the login form.) This is Day-16 work.

---

# Day 16 — Security (frontend slice) + the cross-cutting lessons

Backend auth architecture is in backend-notes.md. This is the client half plus the lessons that aren't specific to either side.

## Token pair + transparent refresh
- `AuthResponse` replaces `LoginResponse`; `api/tokenStorage.ts` isolates the storage keys so swapping localStorage for an httpOnly cookie is a one-file change.
- `apiFetch` refreshes on 401 and retries once. **A 401 is an ordinary event when tokens live 15 minutes, not an error** — only a *failed refresh* ends the session.

### The refresh storm — a correctness requirement, not an optimisation
First version let concurrent requests each start their own refresh. Because rotation is single-use, the first succeeds and the rest present a spent token — **which the backend correctly reads as reuse and answers by revoking the whole family, logging the user out precisely because the client tried harder.** Single-flight refresh is therefore imposed by the server's security design.
Verified with `JWT_ACCESS_TTL=5s`: two concurrent 401s → exactly one `POST /refresh` → both retried 200.

## Other frontend work
- **Delete chat:** trash control per conversation row, hover-revealed, inline two-step confirm (matching Documents), optimistic removal with rollback. **Deleting the conversation you're currently reading navigates to `/chat` first** so the route never points at a dead session.
- **Document preview:** "Open original" + separate explicit "Download"; renders in-page, not a new tab. Detail view rebuilt as a two-column grid (sticky metadata rail + preview).
- Sign-up / forgot / reset screens, validating against the same rules the backend enforces. The forgot-password confirmation is worded so it's **true whether or not the account exists**, matching the backend's refusal to disclose.
- Theme system (Light/Dark/System, `data-theme`). Responsive work (Day-19 material, pulled forward).

## Frontend bugs found — diagnoses worth keeping
- **`window.open(url, name, 'noopener,noreferrer')` returns `null` by specification** — those flags deliberately sever the handle. So the browser opened a tab, the code read `null` as "pop-up blocked", and ran a download fallback → a blank `about:blank` tab *and* an unwanted download from one line. Dropped the pop-up for inline preview.
- **Browsers only render a narrow set of MIME types.** PDFs/images render in an iframe; `text/markdown`, `text/csv` and Office types are "save this", so pointing an iframe at them **silently downloads**. Now a strategy per format — iframe for PDF/image, in-app `<pre>` for text (no blob URL and no anchor click exist on that path, so a download is *impossible*, not merely avoided), honest "no preview" for Office. **The markdown check had passed only because the test browser renders `text/markdown` and Chrome doesn't — caught by verifying on a browser that wasn't the one being used.**
- **Action proposals vanished on the first message.** Frontend half: proposals are never persisted, so any refetch erases them. Two failed attempts first — skipping the refetch failed because React's dev double-invocation runs the effect twice; a `useRef` failed because navigating `/chat/new → /chat/{id}` **remounts** the component and resets the ref microseconds after it was written. A console diagnostic showing the response carrying actions while the ref read empty is what identified it. Now a module-scoped `Map`.
- **A `pointer: coarse` CSS block that did nothing.** A bare `input` selector is specificity 0,0,1 and loses to `.form-input` at 0,1,0. The CSS *read* correctly; only measuring the computed font-size (still 15px) caught it. Prefixed with `:root` for 0,1,1.
- **Seven CSS tokens referenced but never defined** (`--color-yellow-50/700`, `--color-gray-300/600`, `--color-green-600`, `--color-red-600`, `--social-bg`) — resolved to nothing, so the medium-priority badge had no colour at all, broken in light mode too, just less visibly.
- **`--color-white` used as text colour on blue buttons/chat bubbles.** It's a *surface* token and correctly inverts to near-black in dark — which would have put dark text on a blue button. Added `--on-accent`, which never inverts.

## THE recurring pattern — backend capability with no path from the product
**Five times this month:** the audit trail was written for six days before it was readable · the governance loop worked in curl for six days before a proposal card could trigger it · `DELETE /chat/sessions/{id}` shipped with an ownership check and no UI · `DELETE /documents/{id}` never existed while the UI button called it and got a **405 the whole time** · the citations table and the citation cards both existed for two months and nothing joined them.
**Each time the backend work was complete, correct, and invisible.**
- **The cause, named:** the tracker is organised by *layer*, so "the feature works" and "a user can do it" were never the same milestone, and nothing between them ever checked.
- Citations is the sharpest case because each half was individually correct — **a test can only fail against a contract it knows about, and no contract said the stored citation must reach the rendered card.** Tests are structurally blind to this class.
- **The fix is two questions at the end of any backend change, not more tests:** *What does a user click to reach this? If nothing yet, is that written down as deliberate?*

## Principle: ambiguity + assumed attack = a client obligation
> When a server responds to an ambiguous signal by assuming attack, every client behaviour that can produce that signal innocently becomes a bug — and the server can never tell you which one it's looking at.

Reuse detection can't distinguish a stolen token replayed from an honest client racing itself; both are a spent token arriving twice. Same family: **idempotency keys** (a naive retry looks like a duplicate submission), **optimistic locking** (a double-submit looks like a lost update), **rate limiting** (a retry storm looks like abuse). Wherever a server chooses safety under ambiguity, **the client's concurrency model becomes part of the security model.**
Worth asking of any such mechanism: *what innocent client behaviour is indistinguishable from the attack this defends against?* Whatever the answer, the client is now obliged not to do it.

## Verification method
**Make the slow failure fast, then assert on the mechanism, not the symptom.** `JWT_ACCESS_TTL=5s` turned a 15-minute failure mode into seconds; the assertion was the network log (two 401s → one refresh → two 200s), not the UI looking fine.

## Why the frontend test suite rotted — and it wasn't neglect
`package.json` had **no `test` script**. Vitest was installed and three test files existed, but `npm test` errored outright; the only way in was `npx vitest run`, which nobody types by habit. **The suite was never reachable by the conventional command, so it was never in any loop — while still looking like coverage from the file tree.** That's worse than forgetting to run it, because it's invisible. Added `"test": "vitest run"`. The 8 failures are now visible to anyone typing the obvious thing; **fixing them is still outstanding.**

## Narrative memory is not evidence
Twice in one day, confident claims were made without running a one-command check: branch position stated in a handoff without `git branch` (the backend had drifted onto `main` after commit 3; the "branch" was a stale pointer), and "clean fast-forward" asserted when `main` held a commit the branch lacked (a rebase made it true). The mentor made the same shape of error twice about what had shipped, reading prose summaries as a delivery record.
**Same lesson as the clean-load check: make it a step that runs, not a fact that's remembered.**

## Outstanding
1. 8 failing frontend tests — pre-existing, now runnable via `npm test`. Needs its own pass.
2. Password-reset links point at `http://localhost:5173` — fine same-machine, dead if opened elsewhere. Set `FRONTEND_BASE_URL`.
3. Every document is now `ready`, so the status badge has no variety left to demonstrate.
4. Month 3 replaces the deterministic citation picker with real retrieval — the row, the API shape and the card all stay; only "which document?" gets a better answer.
day#16 notes