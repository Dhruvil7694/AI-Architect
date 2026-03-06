---
name: ai-site-planning-frontend-architecture
overview: Design of a scalable Next.js 14+ frontend for an AI-assisted architectural site planning dashboard, integrating with a Django/PostGIS backend and focusing on SVG-based geometry visualization, JWT auth, and modular domain-driven structure.
todos:
  - id: bootstrap-frontend-project
    content: Scaffold the `frontend` Next.js 14 + TypeScript + Tailwind app inside the monorepo and verify the dev server runs.
    status: completed
  - id: establish-routing-and-layouts
    content: Implement App Router layouts and pages for public, protected, planner, plots, dashboard, and admin sections, matching the planned route map.
    status: completed
  - id: setup-shared-infra-and-api-layer
    content: Implement React Query client, centralized query keys, base httpClient, and domain services (auth, plots, planner, metrics, admin).
    status: completed
  - id: implement-authentication-and-rbac
    content: Implement JWT cookie-based auth flows, authStore, middleware route protection, and role-based access control for admin routes.
    status: completed
  - id: configure-state-stores
    content: Create and wire Zustand stores for auth, global UI, and planner (including scenarios, layer visibility, and layout state).
    status: completed
  - id: build-geometry-engine
    content: Implement the geometry engine modules (geometryNormalizer, geojsonParser, bounds, transform, pathBuilder, centroid, layerManager, selection) and integrate with SvgCanvas.
    status: completed
  - id: implement-planner-module
    content: Build the planner workspace (PlotSelector, SiteMetricsPanel, DevelopmentInputsPanel, PlannerCanvas, Legend, PlanGenerationControls/Status, ScenarioBar) wired to backend APIs and geometry engine.
    status: completed
  - id: implement-plots-browser-with-previews
    content: Implement the `/plots` browser with plot cards and MiniPlotPreview using the geometry engine for SVG thumbnails.
    status: completed
  - id: build-admin-user-management
    content: Implement admin user management pages for listing, viewing, creating, updating, and deleting users, reusing design system components.
    status: completed
  - id: harden-performance-and-security
    content: Tune React Query caching, minimize re-renders, validate geometry transforms and hit-testing, and verify security constraints (cookies, RBAC, protected routes).
    status: completed
isProject: false
---

## System Architecture

- **Tech stack**
  - **Framework**: Next.js 14+ App Router, TypeScript, React 18.
  - **Styling**: TailwindCSS with a custom neutral, architect-focused theme.
  - **State**: React Query for server state; Zustand for UI/ephemeral and session state.
  - **Visualization**: SVG-based 2D rendering for all geometry, no GIS/3D libraries.
- **High-level structure**
  - **App entry & routing**: Next.js `app` directory for routes/layouts.
  - **Domain-oriented modules** under `frontend/src/modules` to keep features cohesive and extensible.
  - **Shared infrastructure** for API, auth, state, and utilities under `frontend/src`.
- **Suggested folder structure**

```text
frontend/
  app/
    layout.tsx                 # RootLayout
    (public)/
      login/
        page.tsx
    (protected)/
      layout.tsx               # Authenticated shell (DashboardLayout)
      dashboard/
        page.tsx
      planner/
        layout.tsx             # PlannerLayout
        page.tsx
      plots/
        page.tsx
      users/
        page.tsx               # If needed separate from /admin/users
      admin/
        layout.tsx             # Admin layout with RBAC guard
        users/
          page.tsx             # /admin/users list
          [id]/
            page.tsx           # /admin/users/{id} detail
  src/
    modules/
      auth/
        components/
        hooks/
        types.ts
      planner/
        components/
        hooks/
        services/
        state/
        types.ts
      plots/
        components/
          MiniPlotPreview.tsx   # Small SVG plot shape preview for list cards
        hooks/
        types.ts
      dashboard/
        components/
        hooks/
      admin/
        components/
        hooks/
        types.ts
      users/
        components/
        hooks/
      common/
        components/
        hooks/
        types.ts
      # Future: analytics/, projects/, comparisons/
    components/
      layout/                  # Shell, sidebars, headers, panels
      ui/                      # Design system primitives (Button, Card, etc.)
      feedback/                # Toasts, loaders, empty states
    services/
      httpClient.ts            # Base API client (fetch/axios wrapper)
      authService.ts
      plotsService.ts
      plannerService.ts
      metricsService.ts
      adminService.ts
    state/
      authStore.ts             # Auth/session + role
      uiStore.ts               # Global UI, theme, layout toggles
      plannerStore.ts          # Planner-specific UI + input state
    hooks/
      useAuth.ts
      useRequireAuth.ts
      useRoleGuard.ts
      useGeoJsonToSvg.ts
    types/
      api.ts                   # Shared DTOs
      auth.ts
      planner.ts
      plots.ts
      user.ts
    utils/
      formatting.ts
      constants.ts             # Route names, roles, non-query constants
      rbac.ts                  # Role-based access helpers
    geometry/                  # Geometry engine: parsing, normalization, transforms, paths, selection
      geometryNormalizer.ts    # Validate/normalize raw GeoJSON (flatten, holes, coordinates)
      geojsonParser.ts         # Normalized GeoJSON → internal geometry model
      bounds.ts                # Global and per-layer bounds computation
      transform.ts             # Fit-to-canvas transforms, pan/zoom matrices
      pathBuilder.ts           # Geometry model → SVG path data
      centroid.ts              # Polygon/line centroids for labels, tooltips, tower labels
      layerManager.ts          # Layer registration, z-order, visibility helpers
      selection.ts             # Hit-testing, hover/selection utilities
    lib/
      react-query-client.ts    # QueryClient setup and config
      jwt.ts                   # Decode/inspect JWT payload on client (for UI hints only)
      storage.ts               # Safe access to non-sensitive browser storage
      queryKeys.ts             # Centralized React Query keys
  public/
    # Static assets (logos, icons, etc.)
  tailwind.config.js
  postcss.config.js
  tsconfig.json
```

- **Extensibility for future modules**
  - New domains like analytics, project management, and design comparisons get their own subfolders in `src/modules`, routing entries in `app/(protected)/...`, and optional dedicated Zustand slices.
  - Shared UI and visualization primitives remain in `components` and `utils`, avoiding duplication.

### Project bootstrap & tooling setup

- **Prerequisites**
  - Install Node.js (LTS) and npm or pnpm on the dev machine.
  - From the monorepo root `code/`, the frontend will live in `code/frontend`.
- **Scaffold Next.js + React + Tailwind (one-shot)**
  - From `code/` run:

```bash
npx create-next-app@latest frontend ^
  --typescript ^
  --eslint ^
  --tailwind ^
  --app ^
  --src-dir ^
  --import-alias "@/*"
```

- This sets up:
  - Next.js 14+ with the App Router.
  - React 18 and TypeScript.
  - TailwindCSS preconfigured (including `tailwind.config.js`, `postcss.config.js`, base styles).
- **Install additional architecture-specific dependencies**
  - From `code/frontend` run:

```bash
npm install @tanstack/react-query zustand d3-zoom d3-scale
```

- Optionally add utility and UX helpers:

```bash
npm install classnames
```

- **Tailwind configuration**
  - Extend `tailwind.config.js` with:
    - Neutral, muted color palette tokens for the architect-focused UI.
    - Typography scale suitable for data-heavy dashboards.
    - Any shared spacing/font families you want to standardize.
- **Verify dev workflow**
  - From `code/frontend`:

```bash
npm run dev
```

- Confirm the app boots at `http://localhost:3000` before layering in the domain-specific architecture described in the rest of this plan.

## Routing

- **Route map (App Router)**
  - **Public**
    - `/login` → `app/(public)/login/page.tsx` (Login form, redirects if already authenticated).
  - **Protected (authenticated)** – wrapped by `app/(protected)/layout.tsx` (DashboardLayout):
    - `/dashboard` → Main overview (key metrics, quick links to planner, recent plots).
    - `/planner` → Planner workspace (plot selector, metrics, inputs, geometry canvas).
    - `/plots` → Plot browser (list/grid of plot cards with filters; each card shows plot name, area, road, and a small SVG polygon preview via `MiniPlotPreview`).
    - `/users` (optional) → Personal user profile/settings if needed.
  - **Admin (authenticated + role-based)** – nested under `/admin` and wrapped by `app/(protected)/admin/layout.tsx`:
    - `/admin` (optional redirect) → Redirect to `/admin/users` or an admin dashboard.
    - `/admin/users` → User list, search, and basic actions.
    - `/admin/users/[id]` → User detail, role assignment, delete/deactivate.
- **Layout hierarchy**
  - `**RootLayout` (`app/layout.tsx`)**
    - Sets HTML structure, global Tailwind classes, fonts, theme provider, React Query provider, and global Zustand context.
    - Renders a minimal shell and defers main chrome to nested layouts for better separation.
  - `**PublicLayout` (implicit in `(public)` group)**
    - Single-column layout focused on the login experience, with minimal chrome and brand identity.
  - `**DashboardLayout` (`app/(protected)/layout.tsx`)**
    - Provides the authenticated shell: sidebar navigation (Dashboard, Planner, Plots, Admin), top bar (user info, logout), and feature slot for page content.
    - Applies auth guard logic (redirects unauthenticated users to `/login`).
  - `**PlannerLayout` (`app/(protected)/planner/layout.tsx`)**
    - Specializes the shell for planner: optional dedicated toolbar, breadcrumb, and full-bleed center canvas.
    - Manages planner-specific layout state (panel collapse, split sizes) via `plannerStore`.
  - `**AdminLayout` (`app/(protected)/admin/layout.tsx`)**
    - Wraps admin pages with additional RBAC guard, admin navigation, and clear visual differentiation (e.g., subtle accent) to signal elevated privileges.
- **Route protection strategy**
  - **Next.js middleware** (`middleware.ts` at repo root of `frontend`):
    - Intercepts requests to `/(protected)` and `/admin` paths.
    - Checks presence/validity of auth token (from cookies) and optionally role claims for admin paths.
    - Redirects to `/login` when unauthenticated, or to `/dashboard` when accessing `/login` while already authenticated.
  - **Client-side guards**
    - `useRequireAuth` hook and `AuthGate` components ensure that protected pages handle edge cases (token expired while client-side navigating) gracefully.

## State Management

- **Division of responsibilities**
  - **React Query (server state)**
    - All backend-derived data: plots list, single plot detail, site metrics, optimization results, generated floor plans, geometry layers, users list, user details.
    - Mutations: login, logout, plan generation requests, plot updates, user CRUD, development input submission.
  - **Zustand (client/UI state)**
    - **Auth/session slice**: authenticated user info and roles, login status, and lightweight session metadata (e.g., token expiry timestamps), but **not** the raw JWTs (which live in httpOnly cookies).
    - **Planner slice**: selected plot ID, current development inputs, form UI state, panel open/closed (including collapsible inputs panel), active scenario, geometry layer visibility, selected geometry element (e.g., tower footprint).
    - **Global UI slice**: theme mode (if used), sidebar collapsed state, active route section, global toasts or modal visibility.
- **Zustand store structure**
  - `authStore.ts`
    - `user`: `{ id, email, name, roles }`.
    - `isAuthenticated`, `expiresAt`, and optional `sessionId`/`lastVerifiedAt` fields for resilience.
    - Actions: `login`, `logout`, `setUser`, `setSessionMeta`.
  - `plannerStore.ts`
    - `selectedPlotId`, `activeScenarioId`, `developmentInputs` (e.g., FAR, max height, tower count, setbacks), `layerVisibility` (for plot boundary, envelope, COP, etc.), `selection` (currently highlighted geometry feature), panel layout settings (including `isInputsPanelOpen`).
    - `scenarios`: array of `{ id, label, inputs, planResultSummary, createdAt }`, representing scenario history backed by React Query data.
    - Actions: setters, reset to defaults, apply preset scenarios, add/update/remove scenarios, set active scenario.
  - `uiStore.ts`
    - `sidebarCollapsed`, `isLoadingOverlay`, global modal states, optional theme setting.
- **How React Query and Zustand interact**
  - Zustand holds the **current selection and interaction state** (e.g., which plot is active); React Query uses that as part of its query keys to fetch relevant data.
  - Mutations (e.g., generate development plan) run via React Query; success callbacks update relevant queries (invalidate/re-fetch) and are associated to specific scenario IDs, while leaving UI control (like which scenario is active) in Zustand.
  - To avoid duplication, server-derived data is **never stored in Zustand** unless needed for offline scratch or optimistic editing; React Query remains source of truth.

## API Layer

- **Base API client**
  - `services/httpClient.ts` wraps `fetch` or `axios` with:
    - `baseURL` from environment (`NEXT_PUBLIC_API_BASE_URL`) pointing to Django backend.
    - Standard headers (`Content-Type: application/json` when applicable).
    - Authentication via cookies: access and refresh tokens are stored as **httpOnly cookies** and automatically sent by the browser to the Django API; server-side calls (Next route handlers/server components) can read cookies to construct `Authorization` headers if needed.
    - Unified error handling: normalized error shape `{ status, code, message, details }`.
    - Optional request/response logging in development only.
    - Interceptors to handle `401` responses by attempting a token refresh flow, then retrying (for idempotent requests).
- **Service layer per domain**
  - `authService.ts`
    - `login(credentials)` → returns tokens and user info.
    - `logout()` → invalidates refresh token server-side if applicable.
    - `refreshToken()` → exchanges refresh token for a new access token.
    - `getCurrentUser()` → optional endpoint for user profile/roles.
  - `plotsService.ts`
    - `getPlots(filters)` → list of plots (with pagination and basic metrics).
    - `getPlotById(id)` → detailed plot with associated metrics/geometry references.
  - `plannerService.ts`
    - `getSiteMetrics(plotId, options)` → metrics computed by backend.
    - `generateDevelopmentPlan(plotId, inputs)` → triggers optimization & returns job ID or result.
    - `getPlanResult(planId | jobId)` → returns geometry (GeoJSON) and metrics for chosen scenario.
  - `metricsService.ts`
    - Thin wrapper if metrics are separated from planner APIs; otherwise folded into `plannerService`.
  - `adminService.ts`
    - `getUsers(query)` → list users with pagination and filtering.
    - `getUser(id)` → user details.
    - `createUser(payload)` → create user with default or specified roles.
    - `updateUser(id, payload)` → update user details/roles.
    - `deleteUser(id)` or `deactivateUser(id)` → remove/deactivate accounts.
- **React Query integration patterns**
  - Shared `QueryClient` in `lib/react-query-client.ts`, configured with:
    - Reasonable defaults: e.g., `staleTime` tuned per resource (plots longer, planner results shorter), `retry` limited for mutation-heavy flows.
  - Domain-specific hooks in modules, e.g. `src/modules/plots/hooks/usePlotsQuery.ts`, `src/modules/planner/hooks/usePlanResultQuery.ts`, `useGeneratePlanMutation.ts`.
  - Centralized query key helpers in `lib/queryKeys.ts` to avoid collisions and ease invalidation, e.g.:
    - `plots.list`, `plots.detail(id)`
    - `planner.metrics(plotId)`, `planner.baseGeometry(plotId)`, `planner.plan(plotId, scenarioId)`
    - `admin.users.list`, `admin.users.detail(id)`

## Planner Module

- **Planner page composition (`/planner`)**
  - **High-level layout** inside `PlannerLayout`:
    - **Top bar**: context (selected plot name, scenario selection, quick metrics summary, plan generation button).
    - **Left sidebar**: `PlotSelector` and `SiteMetricsPanel`.
    - **Center**: `PlannerCanvas` (SVG geometry visualization, zoom/pan, selection) taking the majority of horizontal space.
    - **Right panel (collapsible)**: `DevelopmentInputsPanel` (FAR, GFA, heights, constraints, toggles, presets), which can be collapsed to maximize canvas area.
    - **Bottom bar** (optional): scenario timeline/history, compare scenarios, status messages.
- **Key components and interactions**
  - `**PlotSelector`**
    - Lists available plots from React Query (`usePlotsQuery`), driven by filters in local/Zustand state.
    - Selecting a plot updates `plannerStore.selectedPlotId` and triggers re-fetch of metrics and geometry.
  - `**SiteMetricsPanel`**
    - Displays aggregated site metrics from planner/metrics services: areas, ratios, COP, etc.
    - Subscribes to relevant React Query data keyed by `selectedPlotId`.
  - `**DevelopmentInputsPanel`**
    - Controlled form bound to `plannerStore.developmentInputs`.
    - On change, can either update derived metrics locally or mark state as "dirty" until the user explicitly clicks "Generate Plan".
    - Clicking "Generate Plan" triggers `useGeneratePlanMutation`, passing current inputs and plot ID.
  - `**PlannerCanvas`**
    - Receives GeoJSON-based geometry and layer visibility from React Query and `plannerStore.layerVisibility`.
    - Renders geometry via the Visualization System (described below).
    - Emits interactions back to `plannerStore` (e.g., when a tower footprint is clicked, set `selection` and show details in a side panel or tooltip).
  - `**PlanGenerationControls`**
    - Wraps the CTA buttons and status indicators (e.g., generating, complete, error).
    - Uses React Query mutation status to show spinners and disable UI while back-end processing runs.
  - `**PlanGenerationStatus`**
    - Dedicated status component that surfaces long-running optimization progress (e.g., "Generating plan…", success, error), potentially polling a job endpoint if the backend is asynchronous.
    - Lives near the top bar or bottom bar so status is always visible during optimization.
  - `**ScenarioBar`** (future-ready)
    - Simple list or tabs of saved scenarios (`plannerStore.scenarios`) allowing the user to switch active scenario quickly.
- **Data & control flow**
  - User selects a plot → `plannerStore.selectedPlotId` updates → relevant queries refetch (`metrics`, `base geometry`).
  - User adjusts development inputs → `plannerStore.developmentInputs` updates; optional local validations and hints.
  - User triggers plan generation → planner mutation calls backend with current inputs and plot ID; on success, a new scenario object is created in `plannerStore.scenarios` and associated React Query data (plan result, geometry, metrics) is cached under a scenario-specific key.
  - User can switch between scenarios via `ScenarioBar`, which updates `activeScenarioId` and drives which geometry and metrics the canvas and panels display.
  - Layer visibility toggles (for COP, envelopes, etc.) live entirely in Zustand; geometry is always fully fetched, but selectively rendered.
  - Planner state can be reset when the user navigates away or when a new plot is selected, optionally preserving a limited scenario history per plot.

## Plot Browser (/plots)

- **Purpose**
  - The `/plots` page lists available plots with filters and lets architects scan and select plots; each item should show the plot shape at a glance.
- **Plot list and cards**
  - The page renders a list (or grid) of **plot cards**. Each card summarizes one plot and includes a small SVG preview of its boundary so architects can recognize the plot shape without opening the planner.
- **MiniPlotPreview component**
  - **Location**: `src/modules/plots/components/MiniPlotPreview.tsx`.
  - **Role**: Renders a small SVG preview of a single plot’s boundary (polygon) using the **same geometry engine** as the planner (`src/geometry/`): parse plot GeoJSON → compute bounds → fit to a fixed viewBox → output SVG path. No pan/zoom; just a static, scaled thumbnail.
  - **Card contents** (each plot card should include):
    - Plot identifier (e.g. "Plot FP-12").
    - Key metrics: area (e.g. "1200 sqm"), road width (e.g. "Road: 18m"), and any other list-level metrics from the API.
    - **MiniPlotPreview**: the polygon preview in a compact area (e.g. 120×80px or similar), with consistent stroke/fill from the design system.
  - **Data**: Receives plot geometry (GeoJSON or pre-parsed model) from the plot list payload; if the list endpoint does not return geometry, the component may accept an optional `plotId` and fetch geometry via `plots.detail(id)` (React Query) when needed, with a simple loading/placeholder state.
- **Consistency**
  - Reusing the geometry engine (geojsonParser, bounds, transform, pathBuilder) keeps plot previews visually and semantically aligned with the planner canvas and avoids duplicate conversion logic.

## Visualization System

- **Overall architecture**
  - Central, reusable **SVG canvas** component (`SvgCanvas`) under `src/modules/planner/components/visualization/`.
  - **Layered rendering**: each semantic layer (plot boundary, envelope, COP, etc.) is its own component, all children of `SvgCanvas`.
  - **Geometry engine layer**: GeoJSON from backend → **normalized/validated geometry** (`src/geometry/geometryNormalizer.ts`) → internal geometry model (parsed in `src/geometry/geojsonParser.ts`) → bounds and transforms (`bounds.ts`, `transform.ts`) → SVG paths (`pathBuilder.ts`) → centroids (`centroid.ts`) for labels/tooltips → layer composition and selection (`layerManager.ts`, `selection.ts`).
- **Canvas & coordinate system**
  - `SvgCanvas` responsibilities:
    - Determine a canonical coordinate system for all incoming geometries (e.g., derive bounding box from all GeoJSON features and map to a fixed `viewBox`).
    - Provide pan/zoom context (managed with transforms on root `<g>` element rather than changing each layer separately).
    - Expose utilities via React context or render props so layers can map from world coordinates to SVG coordinates.
  - Coordinate handling:
    - Use bounding box of union of all relevant features, computed by the geometry engine (`bounds.ts`).
    - Apply scaling and translation so the entire plot fits within the canvas with padding, computed once per dataset and reused.
    - Maintain aspect ratio to avoid distortion of geometry.
  - Zoom & pan:
    - Use `d3-zoom` and `d3-scale` (not full D3) to manage smooth zoom and pan transforms on the canvas `<g>` element.
    - Provide fit-to-plot and reset-view helpers that compute appropriate scale/translate values from the geometry bounds.
- **Layer system**
  - Layers are responsible for **what** to draw; the canvas is responsible for **where/how** it is drawn.
  - Example layer components:
    - `PlotBoundaryLayer`
    - `EnvelopeLayer`
    - `CopLayer`
    - `CopMarginLayer`
    - `TowerFootprintsLayer`
    - `SpacingLinesLayer`
    - `LabelsLayer`
  - `plannerStore.layerVisibility` controls whether each layer is rendered.
  - Draw order ensures visual clarity (e.g., boundaries under towers, labels on top).
- **GeoJSON → SVG conversion**
  - Geometry engine functions in `src/geometry/`, e.g.:
    - `geometryNormalizer.ts`: validates raw GeoJSON, flattens multipolygons, removes or flags holes when needed, and standardizes coordinate structure before parsing.
    - `parseGeoJsonToModel(geoJsonFeatures)` → converts raw GeoJSON into an internal model annotated with layer types.
    - `computeBoundingBox(geometryModel)` → returns min/max x/y for all or per-layer features.
    - `createViewTransform(bounds, canvasSize)` → returns transform functions and matrices for fit-to-canvas.
    - `geometryToSvgPath(geometrySegment)` → returns SVG path data for Polygon/MultiPolygon/LineString.
    - `centroid.ts`: polygon centroid and line-midpoint helpers used for **label placement**, **tooltip anchors**, and **tower labels** in the canvas and in MiniPlotPreview tooltips if needed.
  - Conversion flow:
    - Run raw GeoJSON through `geometryNormalizer.ts` to validate shapes, flatten multipolygons into simpler structures, optionally remove or flag holes, and standardize coordinates.
    - Parse normalized GeoJSON into an internal geometry model once per query/mutation result.
    - Compute global and per-layer bounds from the model, then derive shared view transforms.
    - Convert geometry segments to SVG paths using the shared transforms, memoized per dataset to avoid recomputation on every render.
- **Interactions & labels**
  - Geometry elements can attach event handlers (on hover/click) to feed into `plannerStore.selection`.
  - `selection.ts` contains hit-testing helpers used by layers to determine which feature is under the pointer for hover/selection.
  - `LabelsLayer` uses `centroid.ts` (polygon centroid, line midpoint) for label placement; labels are positioned with simple offset logic and minimal collision avoidance to keep implementation light. The same centroid helpers support tooltip anchors and tower labels elsewhere.
  - The `Legend` component controls `plannerStore.layerVisibility`, enabling architects to toggle each layer (plot boundary, envelope, COP, COP margin, towers, spacing lines) interactively.
  - **Fit-to-selection UX (planned)**
    - Use the current `plannerStore.selection` plus the geometry model and bounds helpers to compute a focused transform that zooms/pans the canvas to the selected feature (e.g., a tower footprint).
    - Expose this as a helper in `transform.ts` (e.g., `createViewTransformForSelection`) so the planner UI can implement a Zoom to selection control without duplicating geometry math.

## Implementation Risk Areas

- **Geometry transforms (bounds & transforms)**
  - `bounds.ts` and `transform.ts` must handle all normalized geometry cases correctly; any errors will surface as broken zoom/pan, misaligned fit-to-plot, or incorrect fit-to-selection behavior.
  - Pay particular attention to coordinate ordering, extreme aspect ratios, and mixed Polygon/MultiPolygon inputs.
- **Hit testing & selection**
  - `selection.ts` must robustly support hover, click, and polygon selection, operating in the same coordinate space as rendered SVG paths.
  - Edge cases like overlapping features, very small towers, and thin spacing lines should be handled carefully to avoid unselectable geometry or flickering hover states.
- **Scenario switching & canvas state**
  - Scenario changes (driven by `plannerStore.scenarios` and `activeScenarioId`) must re-render geometry and metrics cleanly, using scenario-scoped React Query keys so old data does not leak.
  - Canvas transforms (zoom/pan) should not reset unnecessarily on scenario switch unless explicitly requested, to avoid disorienting users; this requires careful coordination between the geometry engine, planner store, and visualization components.

## Authentication

- **JWT-based auth model**
  - Backend issues **short-lived access tokens** (JWT) and optionally **refresh tokens**.
  - Recommended pattern:
    - **Access token stored in an httpOnly, secure, same-site cookie**, so both Next middleware and server components can read it via `cookies()` and Django receives it automatically on API calls.
    - **Refresh token also stored as an httpOnly, secure, same-site cookie** (if used) to rotate access tokens without exposing secrets to JavaScript.
- **Login flow**
  - `/login` page collects credentials and calls `authService.login`.
  - On success:
    - Backend sets access and refresh token cookies and returns user info (and optionally token metadata such as expiry).
    - Frontend stores **only** non-sensitive session state in `authStore` (`isAuthenticated`, `user`, `roles`, `expiresAt`), never the raw JWTs.
    - `authStore` sets `isAuthenticated`, `user`, `roles`, and `expiresAt`.
    - User is redirected to `/dashboard` or the page they attempted to access.
- **Session persistence**
  - On app startup (client and/or server), a hydration routine:
    - Reads cookies on the server (or relies on a `/me` endpoint) to determine whether a valid session exists.
    - Calls `authService.getCurrentUser` (backed by Django auth) to verify token and fetch latest roles, then hydrates `authStore` on the client.
  - Periodic background refresh (before expiry) using refresh token cookie to maintain seamless sessions; tokens are rotated entirely server-side.
- **Logout flow**
  - Calls `authService.logout` to invalidate refresh token (if backend supports).
  - Clears access token and user state from `authStore` and client storage.
  - Redirects to `/login` and invalidates all React Query caches.
- **Protected routes and role-based access control (RBAC)**
  - **Route-level**:
    - `middleware.ts` checks auth for `/(protected)` and both auth + admin role for `/admin` segments.
  - **Component-level**:
    - `useRoleGuard` and small `RequireRole` components hide or disable UI elements (e.g., admin navigation) when the user lacks required roles.
  - **Token parsing**:
    - `lib/jwt.ts` decodes JWT on client side (without trusting it for security) to show UI hints; backend remains source of truth for actual permissions.
- **Security considerations**
  - Prefer minimal token footprint in JavaScript-accessible storage; treat any local/session storage usage as a trade-off and keep access tokens short-lived.
  - Enforce HTTPS-only, secure cookies in production.
  - Avoid embedding secrets in frontend code; use environment variables for API endpoints only.
  - Ensure all admin endpoints are protected server-side in Django in addition to frontend RBAC.

## Admin Module

- **Scope**
  - User management features available only to users with `superuser`/`admin` role.
- **Routes & pages**
  - `/admin/users` (`app/(protected)/admin/users/page.tsx`)
    - Displays a table of users with pagination, search, and basic filters (role, status).
    - Actions per row: view, edit, delete/deactivate.
    - Uses React Query `useUsersQuery` for data and `useDeleteUserMutation` for destructive actions.
  - `/admin/users/[id]` (`app/(protected)/admin/users/[id]/page.tsx`)
    - Shows user details and editable fields (name, email, role assignments, active state).
    - Uses `useUserQuery(id)` and `useUpdateUserMutation`.
- **Components**
  - `UserListTable`, `UserRowActions`, `UserFilters`, `UserForm`, `RoleSelector`, `ConfirmDeletionModal`.
  - Reuse primitives from design system (Button, Input, Select, Card, Panel).
- **Access control**
  - Admin navigation items only visible to users with admin role (checked via `authStore.user.roles`).
  - `AdminLayout` enforces RBAC and redirects or shows an access-denied page for unauthorized users.

## Component System

- **Design system goals**
  - Minimal, clear components that emphasize **data and geometry**, not decoration.
  - Consistent use of spacing, typography, and color from Tailwind design tokens.
  - Prioritize accessibility (focus states, keyboard navigation, ARIA attributes where necessary).
- **Core UI primitives (in `src/components/ui`)**
  - `**Button`**: Variants like `primary`, `secondary`, `ghost`, `danger`; size variants; full-width option.
  - `**Card`**: For grouping content (metrics, forms); supports header, body, footer slots.
  - `**Panel`**: More structural than `Card`; used for side panels, collapsible areas in planner.
  - `**Input`**: Text, number; integrated label, error, helper text.
  - `**Select`**: Basic dropdown with clear label and consistent styling; can later be swapped with headless/radix.
  - `**MetricCard`**: Specialized card for key metrics (label, value, unit, subtext, trend arrow if needed).
  - `**Legend`**: Displays mapping between geometry layers and their colors/linestyles and controls visibility via `plannerStore.layerVisibility` (interactive layer toggles).
  - `**Toggle`, `Checkbox`, `Slider`**: For planner controls.
- **Layout components (in `src/components/layout`)**
  - `AppShell`, `Sidebar`, `TopBar`, `ContentArea`, `SplitPane`, `PlannerShell`.
- **Feedback components (in `src/components/feedback`)**
  - `Spinner`, `InlineLoader`, `EmptyState`, `ErrorState`, `Toaster`.
- **Styling consistency**
  - Use Tailwind utilities combined with a small set of composition classes (via `className` helpers) to avoid duplication.
  - Establish design tokens in Tailwind config (colors, spacing, typography) and reference them consistently in components.

## Performance Strategy

- **React Query performance**
  - Tune `staleTime` and `cacheTime` by resource:
    - Plots list and base plot data → relatively long `staleTime` (e.g., several minutes) to minimize refetching.
    - Planner optimization results → short `staleTime` but kept in memory for quick scenario comparisons.
  - Use query key scoping by `plotId`/`scenarioId` to avoid over-fetching.
  - Use `prefetchQuery` when navigating from plots list to planner for smoother UX.
- **SVG and geometry rendering**
  - Normalize and convert GeoJSON to SVG paths **once per dataset** and memoize results (e.g., using `useMemo` and stable keys from query data).
  - Split heavy layers into separate memoized components (`React.memo`) so that UI changes in inputs/panels do not cause full canvas re-renders.
  - Prefer simple stroke/fill styles and avoid filters (shadows, gradients) that might degrade performance on large geometries.
- **Avoiding unnecessary re-renders**
  - Use **Zustand selectors** to subscribe only to specific pieces of state rather than entire stores.
  - Keep global state small; push localized UI state (e.g., open/closed for a specific accordion) into component-local state when it does not need to be shared.
  - Ensure context providers (e.g., for theme, auth) are placed at appropriate granularity and avoid wrapping entire app when possible.
  - Lazy-load less frequented routes/modules (e.g., admin area) when appropriate, leveraging Next.js code-splitting.
- **Network considerations**
  - Paginate long lists (users, plots) and avoid fetching excessively detailed geometry when a low-detail preview is sufficient (could use backend flags for simplified geometry).
  - Compress responses on the backend (gzip/brotli) and rely on HTTP caching headers where appropriate.

## Security Considerations

- **JWT storage & handling**
  - Store **both** access and refresh tokens in httpOnly, same-site, secure cookies; do not persist JWTs in local or session storage to minimize XSS impact.
  - Implement strict token lifecycle management (refresh before expiry, clear on logout, handle 401 gracefully).
- **CSRF & CORS**
  - For cookie-based refresh flows, ensure CSRF protection is handled at the backend (e.g., CSRF tokens or same-site strict cookies), and limit cross-origin requests using CORS policies.
- **Route and component protection**
  - Use `middleware.ts` for coarse-grained route protection and client-side guards for fine-grained UI control.
  - Never rely solely on frontend checks for security; Django must enforce auth/roles on all protected endpoints.
- **Admin access control**
  - Admin routes (`/admin/`**) check both authentication and admin role claims.
  - UI for dangerous actions (delete users, etc.) includes confirmation dialogs and clearly labeled destructive buttons.

This blueprint defines the structure and responsibilities for each part of the frontend so that implementation can proceed in a modular, scalable, and production-aligned way.