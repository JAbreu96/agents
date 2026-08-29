#!/usr/bin/env python3
"""
Copy the remote job tracker into a local SQLite file you can safely write to.

This is the sanctioned way to verify anything that writes. The remote database
is the real tracker -- the GUI, the MCP server and the scheduled runs all share
it -- and `DB_PATH` is ignored whenever TURSO_DATABASE_URL is set, so pointing a
scratch script at a temp file does NOT protect it. That mistake has already put
ten invented rows into the tracker.

Usage:
    python scripts/clone_remote_db.py                 # -> data/snapshots/<stamp>.db
    python scripts/clone_remote_db.py --out /tmp/x.db

Then run against the copy:

    JOBS_DB_PATH=data/snapshots/<stamp>.db python your_script.py

JOBS_DB_PATH alone is enough, and `env -u TURSO_DATABASE_URL` is NOT: jobs_db
calls load_dotenv() at import, which puts the Turso vars straight back. Naming a
file is the one signal dotenv cannot undo.

The copy is a plain SQLite file. Nothing here writes to the remote: it issues
SELECTs only, and the remote-write guard in jobs_db would refuse anything else.
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import jobs_db  # noqa: E402


def _tables(conn) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def clone(out_path: str) -> tuple[str, dict[str, int]]:
    if not jobs_db._use_libsql():
        raise SystemExit(
            "TURSO_DATABASE_URL is not set, so there is no remote database to copy.\n"
            "You are already pointed at a local file -- nothing to do."
        )

    src = jobs_db._connect()
    if src is None:
        raise SystemExit("could not open the remote database.")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    if os.path.exists(out_path):
        raise SystemExit(f"{out_path} already exists; refusing to overwrite it.")

    dst = sqlite3.connect(out_path)
    counts: dict[str, int] = {}
    try:
        for table in _tables(src):
            ddl = src.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,)
            ).fetchone()["sql"]
            dst.execute(ddl)

            rows = src.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608 - name from sqlite_master
            if rows:
                cols = rows[0].keys()
                placeholders = ", ".join("?" for _ in cols)
                dst.executemany(
                    f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
                    [tuple(r[c] for c in cols) for r in rows],
                )
            counts[table] = len(rows)

        # Indexes last, so the bulk insert above is not paying to maintain them.
        for row in src.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
        ).fetchall():
            dst.execute(row["sql"])
        dst.commit()
    finally:
        dst.close()
        src.close()
    return out_path, counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="where to write the copy "
                                  "(default: data/snapshots/<timestamp>.db)")
    args = ap.parse_args()

    out = args.out or os.path.join(
        "data", "snapshots", f"tracker-{datetime.now():%Y%m%d-%H%M%S}.db")
    path, counts = clone(out)

    width = max(len(t) for t in counts) if counts else 0
    print(f"copied the remote tracker to {path}\n")
    for table, n in sorted(counts.items()):
        print(f"  {table:<{width}}  {n:>5} rows")
    print(f"\nTotal: {sum(counts.values())} rows across {len(counts)} tables\n")
    print("Write against it with:\n")
    print(f"    JOBS_DB_PATH={path} python your_script.py\n")
    print("(JOBS_DB_PATH alone is enough -- `env -u TURSO_DATABASE_URL` is not,")
    print(" because load_dotenv() at import puts it straight back.)")


if __name__ == "__main__":
    main()
