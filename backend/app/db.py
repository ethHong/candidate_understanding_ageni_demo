# backend/app/db.py
from __future__ import annotations
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

# Resolve DB path explicitly next to this file: backend/app/comes.db
_BASEDIR = Path(__file__).resolve().parent
DB_FILE = _BASEDIR / "comes.db"

# You can also override via env if you want:
DB_URL = os.getenv("COMES_DB_URL", f"sqlite:///{DB_FILE}")

# Create engine with check_same_thread for SQLite
engine = create_engine(
    DB_URL,
    connect_args=(
        {"check_same_thread": False} if DB_URL.startswith("sqlite:///") else {}
    ),
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def run_naive_migrations():
    """Very small dev-friendly migrator. Safe to run on every startup."""
    with engine.connect() as conn:
        # Helper: check if table exists
        def has_table(name: str) -> bool:
            row = conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=:n",
                {"n": name},
            ).first()
            return row is not None

        # Helper: check if column exists
        def has_column(table: str, col: str) -> bool:
            rows = conn.exec_driver_sql(f'PRAGMA table_info("{table}")').all()
            # row format: (cid, name, type, notnull, dflt_value, pk)
            return any(r[1] == col for r in rows)

        # sessions additions
        if has_table("sessions"):
            if not has_column("sessions", "resume_text"):
                conn.exec_driver_sql(
                    'ALTER TABLE sessions ADD COLUMN resume_text TEXT DEFAULT "";'
                )
            if not has_column("sessions", "target_intro"):
                conn.exec_driver_sql(
                    'ALTER TABLE sessions ADD COLUMN target_intro TEXT DEFAULT "";'
                )

        # answers additions
        if has_table("answers"):
            if not has_column("answers", "text"):
                conn.exec_driver_sql("ALTER TABLE answers ADD COLUMN text TEXT;")

        conn.commit()


# backend/app/db.py  — replace only db_info_snapshot()
def db_info_snapshot() -> dict:
    """Introspect DB path & schemas for debugging."""
    out = {"db_url": DB_URL, "db_file_exists": None, "database_list": [], "schemas": {}}
    if DB_URL.startswith("sqlite:///"):
        out["db_file_exists"] = DB_FILE.exists()
        out["db_file_path"] = str(DB_FILE)

    with engine.connect() as conn:
        # Which file(s) are actually open
        dblist = conn.exec_driver_sql("PRAGMA database_list;").all()
        # cols: seq, name, file
        out["database_list"] = [
            {"seq": int(r[0]), "name": r[1], "file": r[2]} for r in dblist
        ]

        # Tables to inspect
        tables = ["sessions", "questions", "answers", "actions", "action_links"]
        out["schemas"] = {}

        for tbl in tables:
            try:
                rows = conn.exec_driver_sql(f'PRAGMA table_info("{tbl}")').all()
                # row: (cid, name, type, notnull, dflt_value, pk)
                out["schemas"][tbl] = [
                    {
                        "cid": int(row[0]),
                        "name": row[1],
                        "type": row[2],
                        "notnull": int(row[3]),
                        "default": row[4],
                        "pk": int(row[5]),
                    }
                    for row in rows
                ]
            except Exception as e:
                out["schemas"][tbl] = {"error": str(e)}

    return out
