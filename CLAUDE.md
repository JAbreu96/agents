# agents

## The database is live

`TURSO_DATABASE_URL` in `.env` points this project at a cloud database holding the real job
tracker. Every entry point reaches it through `src/jobs_db.py` — the GUI, the MCP server, the
cron scripts, a throwaway `python3 -c`. `data/jobs.db` is a stale local copy that nothing
reads and that is hundreds of rows behind; it makes a convincing decoy.

Check which one you are on before any write:

```bash
python3 -c "import sys; sys.path.insert(0,'.'); from src import jobs_db; print(jobs_db._use_libsql())"
```

`True` means the next write is production. To work on a throwaway copy instead, set the
variables **empty** — `jobs_db` calls `load_dotenv(override=False)`, so a key that is absent
gets refilled from `.env`, and an *unset* variable silently reconnects you to live:

```bash
TURSO_DATABASE_URL="" TURSO_AUTH_TOKEN="" python3 ...
```

`tests/conftest.py` does this for the whole session, after a run wrote 138 job rows, 78
interviews and 4 recruiters into the live database.

Snapshot before a schema change; a file copy of `data/jobs.db` snapshots nothing:

```bash
turso db shell job-tracker ".dump" > data/turso-snapshot-$(date +%Y%m%d-%H%M%S).sql
```

## Ship a feature as a stack

A feature whose plan has more than one phase ships as a **stack**: one PR per phase, each
based on the previous, only the bottom one on `main`. A five-phase plan is five PRs.

Follow `.claude/skills/stacked-pr/` when a plan has more than one phase, when a change is
heading past ~500 lines or ~10 files, or when a merged parent leaves its children to restack.
