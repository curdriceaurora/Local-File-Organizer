# Database Migrations

The web/API persistence layer uses Alembic migrations so schema changes are
tracked and reproducible across local development and deployment.

## Why this exists

- Keeps SQLite (dev) and PostgreSQL (prod) schema definitions aligned.
- Allows safe forward/backward schema transitions in CI/CD.
- Avoids hidden `create_all()` drift between environments.

## Configure database target

Alembic reads `FO_API_DATABASE_URL` first. If unset, it uses the URL from
`alembic.ini`.

Examples:

- SQLite file:
  - `FO_API_DATABASE_URL=sqlite+pysqlite:///./.tmp/file-organizer.db`
- SQLite in-memory (testing):
  - `FO_API_DATABASE_URL=sqlite+pysqlite:///:memory:`
- PostgreSQL:
  - `FO_API_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/file_organizer`

## Apply migrations

From the `file_organizer_v2` directory:

```bash
FO_API_DATABASE_URL=sqlite+pysqlite:///./.tmp/file-organizer.db \
  alembic -c alembic.ini upgrade head
```

## Roll back one revision

```bash
FO_API_DATABASE_URL=sqlite+pysqlite:///./.tmp/file-organizer.db \
  alembic -c alembic.ini downgrade -1
```

## Generate a new migration

```bash
FO_API_DATABASE_URL=sqlite+pysqlite:///./.tmp/file-organizer.db \
  alembic -c alembic.ini revision --autogenerate -m "describe change"
```

## Gotchas

- Keep model imports in `alembic/env.py` in sync with new ORM modules; otherwise
  autogenerate will miss tables.
- For PostgreSQL support, the URL must include an installed driver such as
  `psycopg` (`postgresql+psycopg://...`).
- Migration scripts should avoid database-specific SQL unless guarded, so both
  SQLite and PostgreSQL remain supported.
