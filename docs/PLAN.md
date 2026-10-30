# StatsReader — Implementation Plan

2026-10-29

## Scope and assumptions

**In scope (backend + skeleton UI)**

v1 turns photos/scans/PDFs of hand-filled WFTDA paperwork into a filled official StatsBook .xlsx, with a mandatory human review step before export. Recognition will never be 100%, so the product is "fast assisted data entry", not "magic".

**Core principle: the tool transcribes, it does not referee.** A rule failure is either a misread (fix the value) or an error on the paper itself (keep what the paper says, mark it as a paperwork discrepancy). Changing the official record is the Head NSO's decision, labelled as such in the audit trail.

**In scope (backend + skeleton UI)**

- Create game → capture/upload pages → automatic processing → review/correct → human sign-off → validated .xlsx download

- Score sheets are the minimum upload; other paper types optional but required for a "full" StatsBook

- Machine-read confidence, cross-sheet validation, error handling, audit trail of corrections

- Mobile capture, desktop review

**Out of scope for v1**

- Auth, users, billing (existing app handles it; we receive a user/org id)

- Digital-source imports (CRG scoreboard exports already produce StatsBooks)

- Submitting to WFTDA, stats dashboards, multi-language forms; junior (under-18) games until a lawful basis is confirmed

**Assumptions to confirm**

- Target workbook: the current WFTDA StatsBook (February 2025 release), US Letter and A4 variants

- Paper is the official WFTDA printable paperwork, not league-customised forms

- The IGRF (rosters, officials, venue) is sometimes, not always, filled digitally before the game, so users can upload that pre-game .xlsx as the starting template; if not, the New Game screen collects team names, colours, date and rosters directly

- Backend in Python, exposed as a REST API the existing app calls

## The target: StatsBook sheets and source paper

A full StatsBook needs IGRF, Score, Penalties and Lineups filled for both teams and both periods; summary tabs and the IGRF score section are formula-driven and are never written to. The current workbook is the [February 2025 release](https://resources.wftda.org/competition/statsbook/); the [StatsBook Manual](https://static.wftda.com/stats/wftda-statsbook-manual.pdf) and the [printable paperwork](https://static.wftda.com/stats/wftda-printable-statsbook-paperwork-us-letter.pdf) define how each part is filled.

| Workbook part | Source paper | Required for | What we extract |

|---|---|---|---|

| IGRF Section 1 | Pre-game .xlsx, New Game form, or scan | Minimum | Venue, date, game #, start time, host league, team names, colours → Home/Away, rosters |

| IGRF Sections 2–4 | Scan of signed IGRF | Full | Official Score adjustment + reason, written final score (for X-07 only), signature *presence*, officials roster, OR/expulsion/suspension fields |

| Score | Score sheets, 1 per team per period (4 pages, plus continuation pages if jams overflow) | Minimum | Per row: jam # (incl. SP / SP*), jammer #, Lost / Lead / Call / Inj / NI, trips 2–10, handwritten jam total |

| Penalties | Penalty Tracker (2 pages, one per period, both teams) or PLT (4 pages, team × period) | Full | Per skater: penalty code + jam #; FO/EXP code + jam #; non-skater expulsions |

| Lineups | Lineup Tracker or PLT | Full | Per row: jam # (incl. SP / SP*), no-pivot flag, jammer, pivot, blockers, box codes per position |

| Summary tabs | None (formulas) | — | Never written; cross-check after recalculation |

| Official Reviews, Expulsion/Suspension forms | Paper filed with the IGRF, not workbook tabs | When applicable | Filled into the IGRF fields only; scans kept beside the export, never inside the workbook; expulsion forms never sent to the model |

| Penalty Box Timer sheets | Paper only, no tab | — | Recognised and ignored by the classifier (optional cross-check later) |

**Minimum StatsBook** = the 4 Score pages + IGRF Section 1 basics, from a pre-game .xlsx or typed on the New Game screen. For paper-only IGRFs, typing two rosters is tedious, so reading the paper IGRF's Section 1 (teams, rosters) moves into Phase 2. This matches the spec (score sheets are the only mandatory upload) while giving X-03 and the workbook's own checks the roster they need. Export is labelled "score-only, not sanction-complete".

**Notation the schema must know** (closed vocabularies, from the paperwork legend; Manual details unverified until Phase 0):

- Star pass: "SP" for the passing team and "SP*" for the other team in the jam column, on Score and Lineups

- Box codes: "–" entered mid-jam, "S" entered between jams or carried over, "|" finished serving, "+" (– and |), "$" (S and |), "3" injured skater sits out 3 jams; PLT adds "X", "?" and "n/a"

- Known confusion: "|" vs "I" vs "1" (I is also a penalty code)

**To verify in Phase 0**: exact tab names and cell ranges, whether an OS Offset tab exists, overtime numbering (expected to continue inside period 2), the Trip 10 convention for more than 10 trips, and how the Manual splits PLT data into Penalties and Lineups. The reviewer could not open the Manual directly, so every Manual-sourced rule stays unverified until then.

## Architecture

A stateless API, a background worker pipeline and a review loop; nothing is exported without passing validation and a human.

```

```

All steps read and write the same storage. Stack, deliberately small for v1: Python 3.12, FastAPI, Postgres (also the job queue, via `SKIP LOCKED` / procrastinate, so no Redis), S3-compatible storage behind one interface (local disk in dev), OpenCV and pypdfium2 for image work, a zip/XML cell patcher for the workbook (see Export below), and headless LibreOffice for the recalculation check only. Modules map 1:1 to pipeline steps (`ingest/`, `classify/`, `register/`, `extract/`, `validate/`, `export/`), each with a typed input/output so steps can be re-run in isolation.

**Export writer.** openpyxl drops parts of real workbooks on save (x14 data validations, which include the StatsBook's cross-sheet dropdowns; extended conditional formatting; sometimes drawings) and writes formulas without cached values, so mobile viewers show zeros. Phase 0 tests this on the untouched template: load, save, diff every XML part. If anything is lost, we write values by patching sheet XML inside the zip and leave every other part byte-identical, with `fullCalcOnLoad` set. A file saved by LibreOffice is never shipped.

## Recognition approach

Recommendation unchanged: deterministic geometry, model-based reading. Classic computer vision finds the form and cuts it into known rows; a vision LLM reads each row strip into a fixed schema; rules decide what is trustworthy. What changed after review is how "trustworthy" is measured.

| Option | How | Pros | Cons |

|---|---|---|---|

| A. Whole page to vision LLM | Send the page image, get JSON for the sheet | Fastest to prototype | Hallucinates plausible numbers, drifts rows, no usable confidence, high cost per page |

| B. Classic per-cell OCR | Align to template, crop every cell, handwriting OCR (e.g. TrOCR) | Cheap, deterministic | Weak on derby notation, needs training data we do not have |

| **C. Hybrid (recommended)** | Align with OpenCV, crop row strips, LLM reads each strip into a schema, rules validate | Row alignment guaranteed by geometry; model reads a small region; crop shown beside every value | Two systems to build; template coordinates per sheet version |

**Confidence is measured, not asked for.** A vision LLM's self-reported confidence is noise, and Anthropic models expose no logprobs. So the 0.85 threshold is dropped. Each value gets a tier from signals we can check:

- **Dual read**: two independent reads per strip (second model, or same model with crop jitter and a different prompt); disagreement flags the cell

- **Built-in redundancy**: handwritten jam total vs trip sum, Score jammer vs Lineups jammer, running totals

- **Vocabulary and format checks** against the closed notation lists

- **Logprobs** as an extra signal only where a provider offers them

Tiers: *agreed and consistent* → accepted but visible; *disagreed* → flagged; *rule-violating* → issue. Tier thresholds are tuned on the gold set to a flag-recall target (start: ≥ 95% of wrong cells flagged). The second read is counted in the cost budget.

**Failure modes and answers**

- Curled pages: one global homography, then per-strip re-alignment on detected printed lines

- Writing outside boxes: strip crops with a bleed margin

- Crossings-out: schema fields `struck` and `alternatives[]`; the model never silently picks one

- Photos of screens or photos: moiré/glare detection → "retake"

- Carbon/NCR copies: low-contrast normalisation before reading

- Star-pass rows: matched by content (SP / SP* marker), not by row position

- Paper version mismatch: detect the revision string in the footer, refuse unknown versions

- Model output that fails the schema is rejected and retried, never "cleaned up"

## Data model and API

Machine reads and human corrections are separate layers: re-processing replaces machine reads, never a correction. The .xlsx is a rendering of the resolved values, and every export stores a snapshot so a download can be reproduced.

**Core entities**

| Entity | Key fields |

|---|---|

| Game | id, owner_user_id, org_id, status (draft / processing / review / signed_off / complete / failed), template_version, template_sha256, paper_format, home/away colour mapping, version, created_at |

| Upload | id, game_id, filename, mime (sniffed), sha256, storage_key, page_count, idempotency_key |

| Page | id, upload_id, page_index, detected_type (score / penalties / lineups / plt / igrf / box_timer / unknown), team, period, sequence (continuation pages), quality_score, registration_ok |

| ExtractionRun | id, page_id, model, prompt_version, read_no (1 or 2), cost, started_at |

| CellValue (machine read) | id, run_id, sheet, team, period, row, field, raw_value, normalized_value, struck, alternatives[], crop_box |

| LineupSlot | id, run_id, jam_row, position (jammer / pivot / blocker 1–3), skater, box_codes[] |

| ResolvedValue | game_id, cell key, value, tier, source (machine / correction) — a view, not a table |

| Correction | id, cell key, old_value, new_value, kind (transcription / paperwork_discrepancy), reason, user_id, at |

| ValidationIssue | id, game_id, rule_id, severity, cells[], message, status (open / fixed / acknowledged), override_reason, resolved_by |

| SignOff | id, game_id, user_id, at, export_id |

| Export | id, game_id, storage_key, completeness (score-only / full), values_snapshot_hash, checksum, created_at |

If a new machine read disagrees with an existing correction, a ValidationIssue is raised; the correction is not overwritten.

**REST endpoints (FastAPI)**

| Method | Path | Purpose |

|---|---|---|

| POST | /games | Create game (IGRF Section 1 fields or pre-game .xlsx) |

| POST | /games/{id}/uploads | Upload images/PDFs (multipart, idempotency key) |

| GET | /games/{id}/pages | Detected pages, types, quality, missing-page checklist |

| PATCH | /pages/{id} | User overrides page type/team/period/sequence |

| POST | /games/{id}/process | Start or re-run machine reads (idempotent; corrections survive) |

| GET | /games/{id}/status | Job progress, per-page state (polling; no webhooks in v1) |

| GET | /games/{id}/cells?sheet=&team=&period= | Resolved values with tier and crop URLs |

| PATCH | /cells/{key} | Correct a value, with `kind` and `If-Match` version |

| GET | /games/{id}/issues | Validation results |

| POST | /issues/{id}/acknowledge | Accept a paperwork discrepancy with a reason |

| POST | /games/{id}/signoff | Human sign-off after side-by-side check |

| POST | /games/{id}/export | Build .xlsx (refused without sign-off or with open blocking issues) |

| GET | /exports/{id}/download | Short-lived signed URL, `Content-Disposition: attachment` |

Auth: the existing app passes a signed JWT; every endpoint, including crop images, checks game ownership. Optimistic locking (`version` + `If-Match`) on every PATCH.

## Validation and control checks

Four control layers, one of them a human sign-off. Rules catch both misreads and genuine paperwork errors, so a failure on a value the reviewer has confirmed against the crop becomes an *acknowledged* discrepancy that exports as written, never a blocker forcing someone to "fix" the official record.

**Layer 1 — read confidence** (tiers from the Recognition section)

- Disagreeing dual reads → flagged for review

- Value outside the closed vocabulary (penalty codes, box codes, SP / SP*, roster numbers) → flagged

- Empty cell in a row with other data → warning

**Layer 2 — consistency rules** (each a pure function with an id and unit tests). "Blocking" means blocking until the value is confirmed or acknowledged as a paperwork discrepancy.

| Rule | Check | Severity |

|---|---|---|

| SC-01 | Handwritten jam total equals the trip sum (never writes the formula cell) | Blocking |

| SC-02 | Jam numbers sequential per period, SP / SP* rows counted correctly, no fixed jam count (overtime continues in period 2) | Blocking |

| SC-03 | Both teams have the same jams and SP / SP* rows per period | Blocking |

| SC-04 | Lead only on the original jammer's row; at most one team Lead per jam; Call not with Lost; no Call on an SP row; NI checked per row (jammer vs SP), not per jam | Warning |

| SC-05 | Trips 2–9: 0–4 points; Trip 10: any value (extra trips are written there) | Warning |

| SC-06 | Inj ticked on both teams' sheets for that jam | Warning |

| X-01 | Score-sheet jammer equals the Lineups jammer for the same jam | Blocking |

| X-02 | SP / SP* rows match between Score and Lineups, per period | Blocking |

| X-03 | Every skater number exists in the IGRF roster | Blocking |

| X-04 | Penalty in jam N has a box entry near jam N (wide tolerance; double penalties = one box trip) | Warning |

| X-05 | Skater with a foul-out is marked and does not skate after | Warning |

| X-06 | Skater appears at most once per jam per team | Blocking |

| X-07 | Recalculated total + Official Score adjustment equals the final score written on the signed IGRF (if uploaded) | Warning |

| X-08 | A skater with box code "3" does not appear for the next 3 jams | Warning |

Every rule is confirmed against the Manual in Phase 0; the foul-out threshold and the NI-after-Lead-and-call edge case are flagged as unverified.

**Layer 3 — human sign-off** (confirmed: "create control to check" means automated checks and a human check)

- Before download, a side-by-side page-vs-output check per sheet and a "checked by" sign-off, stored with the export

**Layer 4 — export control**

- Recalculate headless (LibreOffice) and compare summary totals with our own computed totals; Phase 0 confirms LibreOffice and Excel agree on the template's formulas

- No formula cell overwritten; the workbook opens without repair prompts; XML diff against the template shows only intended cells changed

- Mismatch → export marked failed, issue raised, file withheld

## Error handling

Fail per page, not per game: one unreadable page never kills the job, and every error tells the user what to do next. Errors are typed, logged with a correlation id, and surfaced in the API as `{code, message, page_id?, action}`.

| Stage | Error | Response to user | System behaviour |

|---|---|---|---|

| Upload | Wrong type, over size limit, corrupt or password-protected PDF | "File not accepted" + reason | Rejected synchronously, nothing stored |

| Upload | Duplicate file (same sha256) | "Already uploaded" | Ignored, idempotent |

| Quality | Blurry, too dark, page cut off | "Retake page N" with the failing check | Page marked low quality; processing continues for others |

| Classification | Unknown page type or team/period unclear | Ask user to label the page | Page held until labelled |

| Classification | Unsupported form revision | "This paperwork version isn't supported" | Page skipped |

| Registration | Form corners/grid not found | "Couldn't align page N" | One retry with alternate method, then manual-label path |

| Recognition | Model timeout, rate limit, invalid JSON | Shown as "still processing" | Retry with exponential backoff (max 3), then the region is flagged for manual entry |

| Completeness | Required pages missing (e.g. no Away P2 score sheet) | Checklist shows what's missing | Export blocked for that level |

| Validation | Blocking rule fails (misread or paperwork error) | Issue list linked to cells | Export blocked until the value is corrected or acknowledged as a paperwork discrepancy with a reason |

| Export | Template write or recalculation mismatch | "Export failed, we've logged it" | File withheld, alert raised |

**Mechanics**

- Jobs from a Postgres-backed queue; each page step is idempotent and resumable

- Per-page state machine: uploaded → classified → registered → extracted → validated, with failed_at_step

- Per-game model budget cap; a game that hits it stops reading and asks the user to enter the rest

- Structured logs + Sentry; no images, names, crop URLs or model request/response bodies in logs, breadcrumbs or traces

**Upload security**

- Size, page-count and rendered-pixel caps (pypdfium2 limits, PIL `MAX_IMAGE_PIXELS`) against PDF and image bombs

- File type sniffed from magic bytes, not the extension; `.xlsm` rejected; IGRF .xlsx opened with defusedxml and a zip-ratio check

- EXIF and GPS stripped on ingest

## Skeleton UI flow

Capture happens on a phone at the venue; review happens later on a desktop. The review screen is the product, the rest is plumbing. Functional, not pretty; the existing app's design takes over later.

- **New game** (phone or desktop) — "New game statsbook" button; teams, date, venue, colour → Home/Away mapping, paper format; optional pre-game IGRF .xlsx

- **Capture** (phone-first) — multi-shot camera with corner guide overlay; on-device blur/glare check before a shot is accepted; tips for poor hall lighting (no flash, flat surface); PDF/image upload as fallback

- **Checklist** — expected pages (Score H/A × P1/P2, plus Penalties, Lineups, IGRF for full) ticking off as pages are detected, shown *before* the user leaves the venue; the game resumes on any device

- **Processing** — per-page progress; failed pages show the reason and "retake" / "label manually"

- **Review** (desktop) — a grid per sheet type matching the paper layout; cells coloured by tier; click a cell → the original crop beside it; issue list jumps to cells; each correction asks "misread" or "paper says this"; keyboard-first

- **Check and export** — side-by-side page-vs-output view per sheet, "checked by" sign-off, completeness badge (score-only / full), remaining warnings, download

Pitfall: don't build the review grid generically. Score, Penalties and Lineups each need their own layout matching the paper, or reviewers will mis-map rows.

## Privacy, licensing and name censoring

Two gates sit before any real data or public release: WFTDA permission to use the workbook this way, and a GDPR setup that names who is responsible for what. "GDPR applies" alone is not a plan.

**Licensing (Phase 0 gate)**

- The [StatsBook page](https://resources.wftda.org/competition/statsbook/) says the material may not be reproduced or modified without WFTDA's consent. Filling it in is the intended use; hosting it inside an app and filling it programmatically may not be.

- Get written confirmation from WFTDA covering: holding the template, programmatic filling, and use of Public StatsBook Repository data for testing

- Until then: the workbook is not committed to the repo; it is fetched from WFTDA or supplied by the user, and we write cell values only

**GDPR roles and data flow**

- The league is the controller, the app is the processor (DPA with each league), the model vendor is a sub-processor

- Model transfer: name the provider and region; if data leaves the EU, document the basis (EU–US Data Privacy Framework or SCCs) and a transfer assessment. Prefer an EU-region endpoint if one exists.

- Data minimisation in production: send only the strips a step needs; name columns are not sent to the model when names come from the IGRF .xlsx or New Game form

- Expulsion/suspension forms record conduct and legal names: stored encrypted as attachments, never sent to the model

- Signatures: only their presence is detected; signature regions are masked before any processing and never cropped or transmitted

- Junior (under-18) games excluded from v1

- DPIA (data protection impact assessment) completed in Phase 4

**Development data (from day one)**

- Raw scans and real .xlsx files are git-ignored; fixtures are synthetic only

- Real data lives in an access-controlled bucket; developers work on redacted copies from Phase 1, not Phase 4

- Synthetic data uses the *structure* of public repository games (jams, penalties, lineups) with generated fake names and numbers; real names are never printed, photographed or stored as fixtures

**Name censoring (for demos and anything public)**

- Roster names replaced with pseudonyms ("Home Skater 07"); name regions on page images blurred using template coordinates

- The pseudonym mapping is dev/test only and is not kept in production

**Retention**

- The league (controller) sets retention; default suggestion 30 days for originals after export

- Before deletion, the league can download an export bundle (.xlsx + original scans), since originals may be needed as evidence for the official record

- The exported .xlsx contains names indefinitely by nature; the plan says so to the league

- Delete game = uploads, crops, reads, corrections and exports removed

## Testing and accuracy measurement

Accuracy is measured against ground truth from day one; the real gold set carries the weight, because handwriting fonts predict real accuracy poorly.

**Ground truth sources**

- Real gold set (primary): hand-filled games from our own league, keyed in once by hand; access-controlled, never in the repo

- Synthetic (secondary, about 5 games): structure from public repository games, fake names and numbers, rendered onto blank paperwork, printed and photographed. Subject to the WFTDA permission gate.

**Metrics (per sheet type)**

| Metric | Definition | Target |

|---|---|---|

| Flag recall | Wrong cells that were flagged / all wrong cells | ≥ 95% (primary) |

| False-flag rate | Correct cells flagged / all flagged | Low enough that reviewers keep reading flags; set after baseline |

| Cell accuracy | Correct cells / all cells | Baseline first |

| End-to-end time | Minutes from first photo to accepted export, vs manual keying of the same game | ≤ 50% of manual |

| Errors after export | Mistakes found after sign-off | Tracked per game |

| Model cost per game | Sum of ExtractionRun cost | Under the per-game cap |

| Repeat use | Same user returns for a second game | Pilot signal |

**Test layers**: unit tests for every validation rule; golden-file tests for the workbook writer (write → XML diff → recalc → compare); an offline eval CLI on the gold set that runs in CI on every prompt or model change and blocks merges that regress flag recall or cell accuracy. Every machine value records model, prompt version and run id.

Flag recall is the primary number, false-flag rate the guard on it: if most flags are noise, people stop reading them and confident errors slip through anyway.

## Phased delivery plan

Prove value before building infrastructure: a one-week spike decides whether the product exists, then Score sheets end to end, then widen. Each phase ends at a gate.

- **Phase 0 — Spec, permissions, market check.** Download the Feb 2025 workbook, paperwork and Manual; map every writable range into a versioned template config; confirm every rule; run the openpyxl round-trip XML diff; request WFTDA permission; ask a handful of Head NSOs what share of their games are paper-only vs CRG. *Gate:* template config covers the input tabs; writer approach chosen; WFTDA reply received or requested with a fallback; paper-only share is big enough to matter.

- **Phase 0.5 — Spike (about 1 week, notebook only).** 3 real games, Score sheets only, hand-coded crop coordinates, 2 models, dual reads. Measure cell accuracy, flag recall and timed review in a plain grid vs manual keying. *Kill/continue gate:* review time ≤ 50% of manual time.

- **Phase 1 — Skeleton.** FastAPI, Postgres (data + queue), storage interface, game/upload endpoints, workbook writer from a JSON fixture, redacted dev data. *Gate:* fixture → .xlsx → XML diff clean → recalculated totals match.

- **Phase 2 — Score sheets.** Classification, registration, dual-read extraction, SC rules, Score review grid, mobile capture, sign-off, and paper IGRF Section 1 reading (team names, rosters) with its own review screen. *Gate:* score-only StatsBook from real phone photos; flag recall and false-flag rate baselined; cost per game known.

- **Phase 3 — Lineups and Penalties.** Both paper styles (trackers and PLT), box codes, X rules, review layouts. *Gate:* full StatsBook from a gold-set game.

- **Phase 4 — IGRF and hardening.** IGRF Sections 2–4 from paper, error-path tests, retention and deletion, DPIA, DPA template, redaction tooling, metrics dashboard. *Gate:* censoring policy and DPIA signed off; a non-developer completes a game unaided.

- **Phase 5 — Integration.** Plug into the existing app's auth and UI; pilot with one or two leagues.

## Risks and open questions

**Risks**

| Risk | Impact | Mitigation |

|---|---|---|

| Reviewers "fix" real paperwork errors to clear rules | Export no longer matches signed paperwork | Correction kinds, acknowledged discrepancies, rules never auto-fix |

| Confident wrong values pass review | Corrupt official record | Dual reads, cross-sheet rules, flag recall target, mandatory sign-off |

| Too many false flags | Reviewers rubber-stamp | False-flag rate tracked; rules that fire on legitimate games downgraded to warnings |

| Review is not faster than manual entry | No product | Phase 0.5 kill gate |

| Most target games already use CRG | Small market | Phase 0 market check |

| WFTDA refuses or limits permission | Can't ship the workbook | Ask in Phase 0; user-supplied template as fallback |

| WFTDA changes workbook or paperwork | Writer and templates break | Versioned template configs; footer revision and template hash checks |

| Workbook writer drops dropdowns or formatting | File rejected or confusing | XML-diff gate; zip/XML cell patcher |

| Model cost per game exceeds volunteer time value | Unit economics | Strip-level calls, per-game cap, cost tracked from Phase 0.5 |

**Open questions**

- "Create control to check" = both automated validation and a final human check (answered 2026-10-30)

- IGRF is sometimes filled digitally before the game, sometimes not: both paths needed, paper IGRF reading is required (answered 2026-10-30)

- Do leagues mostly use separate Penalty/Lineup trackers or PLT sheets?

- Letter, A4, or both at launch?

- Which model provider and region; what transfer basis?

- Will WFTDA permit hosting and programmatic filling of the workbook?

- What share of target games are paper-only?

- Who signs the DPA on the league side?

## Review log (2026-10-30)

Three independent reviews (domain, engineering, product/privacy) found the original plan sound in shape but wrong in several places that would have hurt in production. Accepted changes are already applied above.

| Finding | Reviewer | Decision |

|---|---|---|

| LLM self-reported confidence is meaningless; 0.85 threshold had nothing to compute it from | Engineering | Accepted: dual reads + rule redundancy, tiered confidence |

| Rules would push tired officials to "fix" the official record | Product | Accepted: correction kinds, acknowledged discrepancies, tool transcribes only |

| SC-04 (NI), SC-05 (trip range) and X-07 would block legitimate games | Domain | Accepted: rules rewritten, downgraded to warnings |

| Star-pass (SP / SP*) and box-code notation missing from schema | Domain | Accepted |

| Penalty paper and OR/expulsion forms described wrongly | Domain | Accepted |

| openpyxl drops the StatsBook's dropdowns and cached values | Engineering | Accepted: XML-diff gate, zip/XML patcher fallback |

| Re-processing could overwrite user corrections | Engineering | Accepted: machine reads and corrections in separate layers |

| Infrastructure built before value is proven | Engineering | Accepted: Phase 0.5 spike with a kill gate |

| Redis + arq unnecessary | Engineering | Accepted: Postgres queue |

| WFTDA licensing never checked | Product | Accepted: Phase 0 permission gate |

| GDPR roles, transfers, expulsion forms, minors undefined | Product | Accepted |

| Synthetic data would reuse real skater names | Product | Accepted: structure only, fake names |

| Score-only minimum lacks team names/rosters | Domain + Product | Accepted: IGRF Section 1 typed on New Game screen; spec still requires only score-sheet uploads |

| Phone capture vs desktop review | Product | Accepted |

| "Create control to check" may mean a human check | Product | Partly: sign-off step added, meaning still an open question |

| Dual reads on every strip roughly double model cost | Engineering | Accepted with a per-game cap; revisit after Phase 0.5 cost data |

| Manual-sourced rules (foul-out count, Trip 10, overtime, Inj) | Domain | Not verified: Manual PDF was unreachable, so they stay flagged for Phase 0 |