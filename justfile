# Default command to list all available commands.
default:
    @just --list

# setup: Install the pinned Python and web dependencies.
setup:
    uv sync
    pnpm --dir web install --frozen-lockfile

# check: Everything that must pass before a change is handed over.
check: lint test web-check api-check

# lint: Ruff over the Python sources and tests.
lint:
    uv run ruff check .

# test: Python tests (adapters, collector, service, installer).
test:
    uv run pytest -q

# web-check: Type-check and unit-test the page.
web-check:
    pnpm --dir web typecheck
    pnpm --dir web test

# build: Build the page into web/dist, which the service serves.
build:
    pnpm --dir web build

# api: Regenerate the OpenAPI schema and the page's generated types.
api:
    CREW_HOME=/nonexistent uv run python -m crew openapi > web/openapi.json
    pnpm --dir web api

# api-check: Fail when the committed API contract is out of date.
api-check: api
    git diff --exit-code -- web/openapi.json web/src/api.d.ts
