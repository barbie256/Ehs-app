# EHS Mall

EHS Mall is a monorepo for the new EHS marketplace platform. The existing
WordPress/Directorist website remains an external, read-only source during the
MVP coexistence period.

Gate 2 contains only the repository skeleton and FastAPI configuration
foundation. Database models, migrations, catalogue integration, authentication,
mobile, admin-web, synchronization, and AI features are intentionally absent.

## Repository areas

- `docs/`: approved architecture, audit, fixture, and implementation documents.
- `backend/`: minimal FastAPI application and typed settings foundation.
- `mobile/`: reserved for a later approved React Native/Expo gate.
- `admin-web/`: reserved for a later approved React dashboard gate.

See `docs/development-setup.md` for the Gate 2 verification workflow.
