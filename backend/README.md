# EHS Mall backend

This directory contains the Gate 2 FastAPI and typed-configuration foundation.
It intentionally has no database connection, Directorist client, catalogue,
authentication, synchronization, or AI implementation.

The application exposes only `GET /` as a controlled startup check. Configuration
values are never included in that response.

Run all commands from the repository root as documented in
`docs/development-setup.md`.
