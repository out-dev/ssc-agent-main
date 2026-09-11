
# Agent Guide

## Repository overview

This is a monorepo containing:

- `backend/`: the FastAPI API, Microsoft Agent Framework Foundry integration, and tests.
- `frontend/`: the React 19 + TypeScript + Vite application.
- `docs/`: architecture and operational documentation.
- `cognee/`: the separate Cognee runtime image.

The API is the runtime boundary. Its OpenAPI document is exposed at `/openapi/v1.json`, and Orval generates the typed frontend client from that document.

## Frontend architecture

The frontend must follow feature-based architecture. Use the following repository as the reference model:

<https://github.com/naserrasoulii/feature-based-react>

Organize `frontend/src` around these boundaries:

```text
src/
├── core/                    # Global application infrastructure
│   ├── assets/
│   ├── components/          # Global or third-party UI wrappers
│   ├── layouts/
│   └── styles/
├── shared/                  # Reusable code with no feature ownership
│   ├── components/
│   ├── hooks/
│   ├── services/
│   ├── utils/
│   ├── constants/
│   └── types/
├── features/                # Self-contained product capabilities
│   └── <FeatureName>/
│       ├── components/
│       ├── hooks/
│       ├── types/
│       ├── views/
│       ├── routes.ts
│       └── index.ts
├── router.tsx               # TanStack Router route tree and feature routes
└── main.tsx                 # Application bootstrap
```

### Rules

1. Keep feature code together. A component, hook, type, view, route, and feature-specific service belong under the owning `features/<FeatureName>/` directory.
2. Features may import from `shared/` and `core/`, but must not import directly from another feature. Move genuinely cross-feature code to `shared/` or introduce an explicit shared domain abstraction.
3. Keep `App.tsx` thin. It should compose application providers and feature-level views/routes, not become a home for feature components, hooks, state, or API orchestration.
4. Put global configuration, layouts, assets, styling, and third-party component wrappers in `core/`. Put only genuinely generic, cross-feature utilities and components in `shared/`.
5. Define routes beside their feature in `features/<FeatureName>/routes.ts` and aggregate them in the application router.
6. Keep generated files in `frontend/src/api` generated-only. Do not edit them manually or duplicate their request and response types. Use generated operations through a feature-owned adapter/service when feature logic needs the API.
7. Prefer feature-specific state and hooks inside the feature. Use a global store only for state that is truly application-wide.
8. Keep feature-specific CSS and tests close to the feature. Changes to global styles should be limited to application-wide concerns.
9. Use TanStack Router as the routing framework and preserve the existing TypeScript, Vite, React Query, and Orval conventions unless a change requires an intentional architectural decision.

When adding a feature, start by identifying its ownership and public surface. Keep its internal files private to the feature and expose only the components, routes, hooks, or types that other application layers actually need.

## API and runtime conventions

- Generate the frontend API client with `pnpm api:generate` after changing backend endpoints or contracts.
- Use the generated API operations rather than hand-writing duplicate HTTP request types.
- Keep secrets and credentials out of source control. Follow the environment configuration documented in `README.md`.
- Preserve the backend boundary: agent and infrastructure integration belongs in the API, not in browser-only feature code.

## Validation

Run the relevant checks before handing off changes:

```bash
pnpm build
pnpm lint
uv run --directory backend pytest
uv run --directory backend ruff check .
```

For frontend-only changes, `pnpm build` and `pnpm lint` are the minimum checks. For API or contract changes, also regenerate the client and run the Python checks.
