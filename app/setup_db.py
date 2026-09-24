"""Create the Postgres database from DATABASE_URL if it does not exist."""

from __future__ import annotations

import sys

import psycopg
from sqlalchemy import text

from app.config import settings
from app.database import admin_database_url, parse_database_url


def ensure_database() -> None:
    if settings.is_sqlite:
        print("SQLite configured — no database create step needed.")
        return

    parts = parse_database_url(settings.database_url)
    dbname = parts["dbname"]
    admin_url = admin_database_url(settings.database_url, "postgres")
    # psycopg wants postgresql:// not +psycopg
    dsn = admin_url.replace("postgresql+psycopg://", "postgresql://", 1)

    print(f"Connecting to Postgres at {parts['host']}:{parts['port']} as {parts['user']}…")
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
                exists = cur.fetchone() is not None
                if exists:
                    print(f"Database '{dbname}' already exists.")
                else:
                    # Identifier cannot be parameterized; validate name first
                    if not dbname.replace("_", "").isalnum():
                        raise ValueError(f"Unsafe database name: {dbname}")
                    cur.execute(f'CREATE DATABASE "{dbname}"')
                    print(f"Created database '{dbname}'.")
    except psycopg.OperationalError as exc:
        print("Could not connect to PostgreSQL.")
        print("Edit backend/.env and set DATABASE_URL with your real password, e.g.")
        print("  DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/lala_traders")
        print(f"Details: {exc}")
        sys.exit(1)


def smoke_connect() -> None:
    from app.database import engine

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print(f"Connected to app database OK ({settings.database_url.split('@')[-1]}).")


if __name__ == "__main__":
    ensure_database()
    smoke_connect()
