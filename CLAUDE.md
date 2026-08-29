# agents

## Never write to the live database

`TURSO_DATABASE_URL` in `.env` points this project at a cloud database holding the real job
tracker. Every entry point reaches it through `src/jobs_db.py` — the GUI, the MCP server, the
cron scripts, a throwaway `python3 -c`. `data/jobs.db` is a stale local copy that nothing
reads; it makes a convincing decoy.

**The rule: nothing ad-hoc writes to it. Ever.** Not to check a fix, not to confirm a count,
not "just one row". Take a copy and write to that:

```bash
python scripts/clone_remote_db.py                      # -> data/snapshots/<stamp>.db
JOBS_DB_PATH=data/snapshots/<stamp>.db python your_script.py
```

`JOBS_DB_PATH` is the whole workflow — it beats `TURSO_DATABASE_URL`, so the snapshot wins
outright. Reads against production are fine and never blocked.

This is enforced, not merely asked for. `src/jobs_db.py` refuses INSERT/UPDATE/DELETE/REPLACE
on a remote connection and raises `RemoteWriteBlocked`, at the connection layer so a
hand-written `conn.execute("DELETE ...")` is caught along with the helpers. Only a declared
entry point may write: it calls `jobs_db.allow_remote_writes()` in its `__main__`, which is
why importing one grants nothing. `tests/test_remote_write_guard.py` holds the line.

### Two traps that have each cost real data

**`DB_PATH` is ignored while `TURSO_DATABASE_URL` is set.** Pointing a scratch script at a
temp file protects nothing. This put 3 invented jobs and 7 invented interview rows into the
tracker, two of them marked as rounds that had occurred, which moved the rates.

**Unsetting the Turso vars does not disarm them.** `jobs_db` calls `load_dotenv(override=False)`
at import, so `env -u TURSO_DATABASE_URL` hands over an absent key that gets refilled straight
from `.env`. Setting it **empty** does work, because an existing key is not overridden:

```bash
TURSO_DATABASE_URL="" TURSO_AUTH_TOKEN="" python3 ...   # works
env -u TURSO_DATABASE_URL python3 ...                   # does NOT — dotenv refills it
```

`tests/conftest.py` empties them for the whole session, after an earlier run wrote 138 job
rows, 78 interviews and 4 recruiters into the live database. Prefer `JOBS_DB_PATH`: it is one
variable and it cannot be undone by dotenv.

Snapshot before a schema change; a file copy of `data/jobs.db` snapshots nothing:

```bash
turso db shell job-tracker ".dump" > data/turso-snapshot-$(date +%Y%m%d-%H%M%S).sql
```

## Ship a feature as a stack

A feature whose plan has more than one phase ships as a **stack**: one PR per phase, each
based on the previous, only the bottom one on `main`. A five-phase plan is five PRs.

Follow `.claude/skills/stacked-pr/` when a plan has more than one phase, when a change is
heading past ~500 lines or ~10 files, or when a merged parent leaves its children to restack.
