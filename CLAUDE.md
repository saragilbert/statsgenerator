# StatsReader

Turns photos/scans/PDFs of hand-filled WFTDA paperwork into a filled official WFTDA StatsBook (.xlsx).
Full plan: `docs/PLAN.md`. Read it before starting any phase. If the plan and the code disagree, ask; don't silently pick one.

## Non-negotiables
- **Transcribe, don't referee.** Never auto-fix a value to make a rule pass. A correction is either `transcription` (misread) or `paperwork_discrepancy` (paper says this). Discrepancies export as written.
- **No real data in the repo.** No real scans, real statsbooks, or real skater/official names in code, fixtures, tests, commits or logs. Fixtures are synthetic with fake names.
- **Don't commit the WFTDA workbook.** It's fetched or user-supplied until WFTDA permission is confirmed.
- **Never write formula cells** in the workbook, and never ship a file saved by LibreOffice (recalc check only).
- **Model confidence is measured, not asked for.** Use dual reads, rule redundancy, and vocabulary checks; never use the model's self-reported confidence.
- Expulsion/suspension forms and signatures are never sent to a model.
- Mark rules sourced from the StatsBook Manual as unverified until checked against the Manual.

## Stack
Python 3.12, FastAPI, Postgres (data + job queue via SKIP LOCKED / procrastinate, no Redis), S3-compatible storage behind one interface (local disk in dev), OpenCV, pypdfium2. Workbook writer: openpyxl only if the Phase 0 XML-diff test shows nothing is lost; otherwise patch sheet XML inside the zip.

## Layout
One module per pipeline step, each with typed input/output and re-runnable in isolation:
`ingest/ classify/ register/ extract/ validate/ export/`
Validation rules are pure functions with ids (SC-01, X-01, ...) and one unit test file each.

## Working style
- Work phase by phase (see PLAN.md "Phased delivery plan"). Don't start a phase before the previous gate passes.
- Phase 0.5 is a notebook spike: no services, no API.
- Small commits; run tests before committing.
- Python: clean, modular, typed (pydantic models at step boundaries), ruff + pytest.

## Commands
- `uv sync` — install (Python 3.12, pinned in `.python-version`)
- `uv run pytest`
- `uv run ruff check .` and `uv run ruff format .`
- `uv run pre-commit install` — once per clone; hooks run ruff and strip notebook outputs
- Code lives in `src/statsreader/<step>/`; tests in `tests/`
