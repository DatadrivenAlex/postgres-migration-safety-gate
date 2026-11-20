# PostgreSQL Migration Safety Gate

A small Python CLI and FastAPI service that flags common PostgreSQL schema-migration rollout hazards before a reviewer ships them. It focuses on the backend/platform side of reliable data systems: destructive changes, lock-prone DDL, and expand–migrate–contract sequencing.

This is an educational static-analysis demo. It parses SQL locally with SQLGlot and applies explicit heuristic rules; it does not connect to PostgreSQL, inspect live schemas, estimate table size, prove whether a lock will occur, or guarantee a migration is safe. Always review the target PostgreSQL version and run migrations against a representative environment.

## Quick start

```bash
uv sync --all-groups
uv run migration-guard examples/risky.sql
uv run uvicorn migration_guard.api:app --reload
```

The CLI emits JSON. By default it exits nonzero only for parse errors and destructive `PG001`/`PG002` findings. Use `--fail-on warning` to make any finding fail CI, or `--fail-on never` to report without gating.

```bash
curl -s http://127.0.0.1:8000/analyze \
  -H 'content-type: application/json' \
  -d '{"sql":"ALTER TABLE users DROP COLUMN email;"}'
```

## Checks

- `PG000`: SQL parse error.
- `PG001` / `PG002`: object or column removal.
- `PG003`: adding a `NOT NULL` column without a default.
- `PG004`: column type change.
- `PG005` / `PG006`: ordinary index build, or concurrent index creation inside an explicit transaction.
- `PG007`: adding a foreign-key or check constraint without `NOT VALID`.
- `PG008`: dropping an index without `CONCURRENTLY`.
- `PG009`: column rename during a rolling deployment.
- `PG010`: immediate `SET NOT NULL` validation.

Rules are intentionally conservative and explain why a finding matters and a safer rollout pattern. They are not a complete PostgreSQL linter or substitute for migration-runner configuration checks. The `examples/expand_contract.sql` file is illustrative; its `VALIDATE CONSTRAINT` step should be scheduled only after the application backfill has completed.

## Tests and CI

```bash
uv run ruff check .
uv run pytest -q
```

GitHub Actions runs lint and tests on Python 3.11 and 3.12. The API is unauthenticated and intended for local/demo use only; do not expose it to untrusted networks.
