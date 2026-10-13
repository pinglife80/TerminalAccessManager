"""Compare the live database schema against the ORM metadata.

Use this to distinguish two states of a database that was bootstrapped with
``Base.metadata.create_all`` instead of Alembic migrations:

* ``CLEAN DRIFT``
    All ORM tables and columns already exist; only the ``alembic_version``
    stamp is missing. Safe to ``alembic stamp head``.
* ``PARTIAL MIGRATION``
    Some tables/columns from the migration chain are missing. The database
    must be migrated (or rebuilt), and must NOT be stamped.

Usage (inside the backend container):

    python scripts/schema_compare.py

or from the host:

    docker compose exec -T backend python scripts/schema_compare.py

Exit codes:
    0  clean drift — safe to ``alembic stamp head``
    1  partial migration — needs migration, do not stamp
    2  comparison error — DB unreachable / unexpected failure
"""

import asyncio
import os
import sys

# Allow running as ``python scripts/schema_compare.py`` regardless of CWD by
# putting the repo root (backend container WORKDIR, i.e. the parent of this
# ``scripts`` dir) on sys.path before importing the ``app`` package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect  # noqa: E402

# Import model modules so every table registers on Base.metadata. ``app.models``
# imports most of them; ``backup_config`` is loaded explicitly since it is not
# re-exported by the package __init__.
import app.models  # noqa: E402, F401
import app.models.backup_config  # noqa: E402, F401

from app.core.database import Base, engine  # noqa: E402


async def main() -> int:
    async with engine.connect() as conn:
        def _compare(sync_conn):
            insp = inspect(sync_conn)
            db_tables = set(insp.get_table_names())
            md_tables = set(Base.metadata.tables.keys())
            missing_tables = sorted(md_tables - db_tables)
            extra_tables = sorted(db_tables - md_tables)
            col_missing = {}
            col_extra = {}
            for t in sorted(md_tables & db_tables):
                db_cols = {c["name"] for c in insp.get_columns(t)}
                md_cols = {c.name for c in Base.metadata.tables[t].columns}
                miss = sorted(md_cols - db_cols)
                extra = sorted(db_cols - md_cols)
                if miss:
                    col_missing[t] = miss
                if extra:
                    col_extra[t] = extra
            return missing_tables, extra_tables, col_missing, col_extra

        missing_tables, extra_tables, col_missing, col_extra = await conn.run_sync(
            _compare
        )

    print("=" * 62)
    print("SCHEMA DRIFT COMPARISON (ORM metadata vs database)")
    print("=" * 62)

    print("\n[missing tables] in ORM but not DB -> needs migration")
    print("  " + (", ".join(missing_tables) if missing_tables else "(none)"))

    print("\n[extra tables] in DB but not ORM -> typically alembic_version / legacy")
    print("  " + (", ".join(extra_tables) if extra_tables else "(none)"))

    print("\n[missing columns] in ORM but not DB -> needs migration")
    if col_missing:
        for t, cols in col_missing.items():
            print(f"  {t}: {cols}")
    else:
        print("  (none)")

    print("\n[extra columns] in DB but not ORM -> usually harmless")
    if col_extra:
        for t, cols in col_extra.items():
            print(f"  {t}: {cols}")
    else:
        print("  (none)")

    print("=" * 62)
    if not missing_tables and not col_missing:
        print("VERDICT: CLEAN DRIFT -> safe to 'alembic stamp head'")
        print("=" * 62)
        return 0

    print("VERDICT: PARTIAL MIGRATION -> must migrate, do NOT stamp head")
    print("=" * 62)
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: comparison failed: {exc}")
        raise SystemExit(2)