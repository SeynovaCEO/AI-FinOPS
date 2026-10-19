"""
FinOps Platform - Database Bootstrap Script

Creates the application role and database (from POSTGRES_* in .env) using a
PostgreSQL superuser, then creates all tables from the SQLAlchemy models.

Usage:
    python create_db.py            # create role + database + tables
    python create_db.py --seed     # ...and also load sample data (seed.py)

The superuser password is prompted for (never stored). To skip the prompt,
set PG_SUPERUSER_PASSWORD in the environment for that one run.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg2
from psycopg2 import sql

from app.core.config import settings


def create_role_and_database(superuser: str, superuser_password: str) -> None:
    app_user = settings.POSTGRES_USER
    app_password = settings.POSTGRES_PASSWORD
    app_db = settings.POSTGRES_DB

    conn = psycopg2.connect(
        host=settings.POSTGRES_SERVER,
        port=settings.POSTGRES_PORT,
        user=superuser,
        password=superuser_password,
        dbname="postgres",
    )
    # CREATE DATABASE cannot run inside a transaction
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (app_user,))
            if cur.fetchone():
                print(f"[1/3] Role '{app_user}' exists - resetting its password to match .env")
                cur.execute(
                    sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                        sql.Identifier(app_user), sql.Literal(app_password)
                    )
                )
            else:
                print(f"[1/3] Creating role '{app_user}'")
                cur.execute(
                    sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(
                        sql.Identifier(app_user), sql.Literal(app_password)
                    )
                )

            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (app_db,))
            if cur.fetchone():
                print(f"[2/3] Database '{app_db}' already exists - skipping")
            else:
                print(f"[2/3] Creating database '{app_db}'")
                cur.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(app_db), sql.Identifier(app_user)
                    )
                )
    finally:
        conn.close()


def create_tables() -> None:
    # Imported here so the engine connects only after the database exists
    from app.db.session import engine
    from app.models import Base

    print("[3/3] Creating tables from models")
    Base.metadata.create_all(bind=engine)
    print(f"      {len(Base.metadata.tables)} tables ready:")
    for name in sorted(Base.metadata.tables):
        print(f"        - {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create FinOps database and tables")
    parser.add_argument("--superuser", default="postgres", help="PostgreSQL superuser (default: postgres)")
    parser.add_argument("--seed", action="store_true", help="Also load sample data via seed.py")
    args = parser.parse_args()

    print(f"Target: {settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT} / {settings.POSTGRES_DB}")
    superuser_password = os.getenv("PG_SUPERUSER_PASSWORD") or getpass.getpass(
        f"Password for PostgreSQL superuser '{args.superuser}': "
    )

    try:
        create_role_and_database(args.superuser, superuser_password)
    except psycopg2.OperationalError as exc:
        print(f"\n[ERROR] Could not connect as '{args.superuser}': {str(exc).strip()}")
        sys.exit(1)

    create_tables()

    if args.seed:
        from seed import seed_database

        seed_database()

    print("\nDone.")


if __name__ == "__main__":
    main()
