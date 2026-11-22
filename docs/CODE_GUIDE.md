# Code guide — how the system works and where to change things

## Big picture

```
 icbOfficerAssoUI (Next.js, browser)          icbOfficerAssoAPI (FastAPI, server)
 ┌──────────────────────────────┐   HTTP/JSON  ┌──────────────────────────────────────┐
 │ /dashboard  public results   │◀── SSE ──────│ routers/dashboard.py  results + stream│
 │ /admin/**   committee panel  │──────────────▶│ routers/*.py          REST endpoints  │
 │ src/lib/api.ts (typed client)│              │ services/ballot_processor.py  pipeline│
 └──────────────────────────────┘              │ services/ocr_service.py   mark finder │
                                               │ services/file_watcher.py  Scanned/    │
                                               │ models/*.py  SQLAlchemy → SQLite      │
                                               └──────────────────────────────────────┘
                                                          data/  Scanned  Completed  Failed  Previews  *.db
```

The browser talks directly to the API (port 8000). The UI never touches the
files or the database.

---

## Backend (`icbOfficerAssoAPI/app`)

| File | Role |
|---|---|
| `main.py` | Creates the FastAPI app, CORS, registers routers, startup (create tables, default admin, start watcher) |
| `config.py` | All settings (`Settings` class). Reads `.env`. Resolves relative folder paths against the project root |
| `database.py` | Async SQLite engine (WAL mode), `get_db()` dependency, `init_db()` creates tables and **adds missing columns** (light migration) |
| `models/` | One SQLAlchemy model per table: `Election`, `Position`, `Candidate`, `Ballot`, `Vote`, `AdminUser`, `AuditLog` |
| `schemas/` | Pydantic request/response shapes (what the API sends and accepts) |
| `routers/` | HTTP endpoints, one file per area (auth, elections, candidates, ballots, dashboard, admin) |
| `services/ocr_service.py` | **Mark detection.** Image in → which boxes are marked out. Pure OpenCV |
| `services/ballot_processor.py` | **Pipeline.** File in → OCR → validation → votes in DB → file moved → dashboards notified |
| `services/file_watcher.py` | Watches `Scanned/` (OS events + 5 s sweep) and feeds the processor for the *active* election |
| `services/vote_counter.py` | Builds the dashboard JSON: stats, ranking, percentages, leading candidates |
| `services/events.py` | `notifier`: wakes SSE connections immediately after any change |
| `utils/security.py` | Password hashing (bcrypt), JWT tokens, `get_current_user` / `get_optional_user` dependencies |
| `utils/audit.py` | `audit.record(db, user_id, action, details)` |
| `utils/sample_ballot.py` | Draws synthetic ballots (tests, `scripts/make_sample_ballots.py`, `scripts/seed_rehearsal.py`) |
| `scripts/seed_rehearsal.py` | Creates the "Rehearsal Election" with anonymous candidates directly in the DB and writes sample PDFs to `Scanned/` |
| `scripts/make_sample_ballots.py` | Writes sample PDFs matching any running election (uses the API) |
| `scripts/make_test_ballots.py` | Rebuilds the manual test set in `Sample Ballots/` (10 PDFs + 10 JPGs at varied DPI/orientation, candidates.csv, answer key, expected tally) |

### Data model

```
elections 1──* positions 1──* candidates 1──* votes *──1 ballots *──1 elections
admin_users 1──* audit_log
```

* `candidates.vote_count` is a cached counter (fast dashboard). It is updated
  with every insert/delete and can be rebuilt with **Recount** (`recount_votes`).
* `ballots.status`: `processing → processed | needs_review | error`, and
  `reviewed` after an admin saved a review. `COUNTED = (processed, needs_review, reviewed)`.
* `votes.is_valid = False` for over-voted positions — stored for the audit trail, not counted.

### Ballot layout → expected boxes

`BallotProcessor.build_layout()` orders candidates by `position.position_order`
then `candidate.display_order` and lays them out `BALLOT_COLUMNS` (2) per row:

```
row 0: [101] [102]      ← President
row 1: [103] [104]      ← Vice President
...
row 12: [125] [126]     ← Executive Member (6 candidates = 3 rows)
row 13: [127] [128]
row 14: [129] [130]
```

The detector must find exactly that many boxes and rows; otherwise the ballot is
flagged. **If the printed ballot changes** (e.g. 3 candidates per row) only
`BALLOT_COLUMNS` in `.env` and the candidate order need to change.

### Mark detection step by step (`ocr_service.py`)

1. `render_pages` — PDF page → image at `OCR_DPI` (pypdfium2); images (JPG/PNG/TIFF/BMP/WebP, every TIFF frame) loaded with Pillow. `normalize` then applies the EXIF orientation, flattens transparency onto white and scales every page so its short side is A4 width at `OCR_DPI` (1654 px at 200 dpi). All size filters and kernels below assume that scale — without it a 72 dpi JPG finds no boxes.
   `extract_oriented` wraps steps 2–8: a landscape page is turned upright; if the box grid does not match, the opposite orientation (180°) is tried. A wrong orientation cannot match by accident because the right-hand box column would fall into the ignored left part of the table.
2. `binarize` — grey → adaptive threshold, ink becomes white.
3. `largest_component` + `deskew` — the table grid is the largest ink blob; its angle (normalised to ±45°, as OpenCV versions report it differently) is used to rotate the page straight (±10°).
4. `find_table` — long horizontal/vertical lines (morphological opening) → bounding box of the table. Title text and the ballot-number box are outside it.
5. `detect_boxes` — outer contours (`RETR_CCOMP` level 0) inside the table with a plausible size (3.5–10% of the page width), aspect ratio 0.6–2.2, ink along all four edges (`_is_outline`), and not in the left 15% of the table (candidate numbers and names; no box there).
6. `build_grid` — group boxes into rows by y, into columns by the largest x gap.
7. `recover_lost_box` — a box whose row was found but which itself is missing usually has an X drawn across its border (the contour merged); if there is ink where it should be, it is recorded as an "outside" mark (rule খ).
8. `measure` — per box: ink ratio inside (minus a 15% margin) → marked if ≥ `MARK_THRESHOLD`; ink in the ring around the box (grid lines masked out, compared with the page baseline) → `outside` (rule খ); box ≥ `SMUDGE_THRESHOLD` ink → `smudged` (rule গ); both diagonals inked → `x`, otherwise `mark` with reduced confidence (rule ক). Confidence ramps from 0.5 at the threshold to 1.0 at `STRONG_MARK` (18%).
9. `render_preview` — annotated PNG (green = counted mark, red = void by a rule, grey = empty) for the review and live screens.

`BallotProcessor._store_page` turns the marks into votes: void marks get
`is_valid=False` + `invalid_reason`; then rule ক is applied to the remaining
marks per post (over-vote → all of that post's marks invalid). Any void mark
flags the ballot `needs_review`. Ballot paper numbers are assigned in
`_process_locked` (`_next_paper_no`) and the completed file is renamed
`Ballot_<no>.pdf` (`completed_file_name`, `rename_completed_file`); image files keep their own extension (`Ballot_<no>.jpg`).

Candidates can be loaded in bulk from CSV: `POST /api/candidates/import`
(`routers/candidates.py`, UI button on the Candidates page). Rows are taken in
ballot order per `post_no`; the whole file is rejected if any row is invalid;
`replace=true` is refused once ballots exist for the election.

Tuning knobs: `.env` (`OCR_DPI`, `MARK_THRESHOLD`, `LOW_CONFIDENCE_THRESHOLD`,
`BALLOT_COLUMNS`) and the class constants at the top of `OCRService`
(`MIN_BOX_RATIO`, `MAX_BOX_RATIO`, `MIN_EDGE_COVERAGE`, `TABLE_LEFT_IGNORE`).
To tune against real scans: put a few PDFs in a folder and run

```python
from app.services.ocr_service import ocr_service
from app.services.ballot_processor import ballot_processor   # for build_layout, or hand-write a layout
result = ocr_service.process_file("scan.pdf", layout)[0]
print(result.boxes_detected, result.warnings, [(m.candidate_id, m.density) for m in result.marks])
ocr_service.render_preview(result, Path("debug.png"))
```

### Processing pipeline (`ballot_processor.py`)

`process_file(db, path, election_id, source)`:

* one `asyncio.Lock` → files are processed one at a time; `in_flight` prevents the
  watcher from touching a file that an upload is already handling;
* OCR runs in a worker thread (`asyncio.to_thread`) so the API stays responsive;
* each page becomes one `Ballot`; `_store_page` applies the validation rules
  (over-vote → invalid votes; layout mismatch / low confidence → `needs_review`);
* the file is moved to `Completed` (or `Failed`), previews are written,
  `notifier.notify()` wakes the dashboards.

`reprocess_ballot`, `remove_votes` and `recount_votes` keep the cached counters consistent.

### Folder watcher (`file_watcher.py`)

* `watchdog` observer thread → `loop.call_soon_threadsafe(enqueue)`;
* `_sweeper` re-scans the folder every `SCAN_POLL_INTERVAL` s (needed for network
  shares and Docker bind mounts on Windows, and for files present at startup);
* `_worker` waits until the file size is stable, looks up the **active** election
  and calls the processor. Without an active election files stay in the folder.
* `AUTO_PROCESS_ENABLED=false` disables the watcher entirely (files are only
  processed by the "Process Scanned folder now" button or by uploads);
  `PROCESS_DELAY_SECONDS` inserts a pause between files (rehearsals only).

### Live updates (`routers/dashboard.py`, `services/events.py`)

`dashboard_events()` is an async generator behind the SSE endpoint. It sends:

* `ballot` — one event per counted ballot, in order (published by
  `BallotProcessor.publish_live_event`). It carries the ballot's votes with
  candidate names, a link to the annotated scan, `display_seconds`, and the
  full results **after** that ballot. Events are kept in a bounded log in
  `notifier`, so a stream that wakes up late still receives every ballot once.
* `update` — the full results, after every other change and at least every
  `SSE_REFRESH_INTERVAL` seconds.
* `paused` — while the committee has paused the screen.

Unpublished elections return `results_visible: false` with empty `positions`
to anonymous callers; admins (with a token) always get the numbers. The public
scan preview (`/api/dashboard/ballots/{id}/preview`) is only served while the
dashboard is published.

### Public live screen (`icbOfficerAssoUI/src/components/live/`)

`liveReducer.ts` is the playback logic: `ballot` events are queued and shown
one at a time for `display_seconds` (the totals shown always belong to the
ballot on screen); `update` events received meanwhile are applied when the
queue drains; when the queue grows the hold time shrinks (min 3 s) so the
screen never lags far behind real counting. `LiveScreen.tsx` renders the
header (logo, KPIs, clock, full-screen button), the "Now counting" panel
(scan, countdown, votes), the results board (a green `+1` marks the candidate
who just received a vote) and the footer. Styles live in `app/live.css`.

### Adding an endpoint

1. Add the Pydantic shapes in `schemas/`.
2. Add the function in the matching `routers/` file (use `Depends(get_db)` and
   `Depends(get_current_user)` for admin-only routes; call `audit.record` and
   `notifier.notify()` when results may change).
3. Add the TypeScript type in `icbOfficerAssoUI/src/lib/types.ts` and a wrapper
   in `src/lib/api.ts`.
4. Add a test in `tests/test_api.py`.

### Tests

```bash
cd icbOfficerAssoAPI
.venv\Scripts\python -m pytest -q          # 23 tests, ~15 s
```
`tests/conftest.py` points the app at a temporary folder + database, so tests
never touch `data/`. `test_ocr.py` checks detection on synthetic ballots and the
real template scan; `test_api.py` runs the whole flow through the HTTP API.

---

## Frontend (`icbOfficerAssoUI/src`)

| Path | Role |
|---|---|
| `app/layout.tsx` | Root HTML, fonts, global CSS |
| `app/dashboard/page.tsx` | Public live results (uses `useSSE`) |
| `app/admin/layout.tsx` | Wraps all admin pages in `AuthProvider`, `ToastProvider`, `ElectionProvider`, `AdminShell` |
| `app/admin/login/page.tsx` | Login form |
| `app/admin/page.tsx` | Overview: stats, processing status, recent ballots, quick actions |
| `app/admin/elections/page.tsx` | Election CRUD, status, positions |
| `app/admin/candidates/page.tsx` | Candidates per position |
| `app/admin/ballots/page.tsx` | Upload zone, list with filters and pagination |
| `app/admin/ballots/[id]/page.tsx` | **Review screen**: annotated scan + editable votes |
| `app/admin/results/page.tsx` | Ranked results, publish/pause switches, recount, CSV export |
| `app/admin/audit/page.tsx`, `settings/page.tsx` | Audit log; password change + system info |
| `components/admin/AdminShell.tsx` | Sidebar, election selector, login redirect |
| `components/admin/BallotUploader.tsx` | Drag & drop uploader |
| `components/dashboard/ResultsView.tsx` | `StatsGrid`, `PositionCard`, `PositionsGrid` shared by public and admin views |
| `components/ui/*` | Toast, Modal/ConfirmDialog, badges, spinner, alerts |
| `hooks/useAuth.tsx` | Token in localStorage (via `useSyncExternalStore`), auto-logout on 401 |
| `hooks/useElection.tsx` | Which election the admin is working on (persisted) |
| `hooks/useSSE.ts` | EventSource subscription with reconnect |
| `hooks/useLoader.ts` | "load now and every N ms" helper used by the admin pages |
| `lib/api.ts` | Base-URL resolution + typed wrappers for every endpoint |
| `lib/types.ts` | TypeScript mirrors of the API schemas |
| `lib/format.ts` | Date formatting, status labels |
| `app/globals.css` | The whole design system (CSS variables, components) |

### How the UI finds the API

`getApiBaseUrl()` in `lib/api.ts`: `NEXT_PUBLIC_API_URL` if it was set at build
time, otherwise `http://<hostname of the page>:8000`. That is why the same build
works on `localhost` and on a LAN server.

### Page pattern

Every admin page follows the same shape:

```tsx
const load = useCallback(async () => { setState(await api.something(token, ...)); }, [token, ...]);
useLoader(load /*, 5000 to poll */);
// actions: try { await api.x(); toast.success(); await load(); } catch (e) { toast.error(errorMessage(e)); }
```

### Commands

```bash
npm run dev     # development server with hot reload
npm run lint    # ESLint (Next.js + React Compiler rules)
npm run build   # production build (also type-checks)
npm run start   # serve the production build
```

---

## Conventions

* Times are stored in UTC (naive) in SQLite; the UI converts to local time (`formatDateTime`).
* Every admin action writes an `audit_log` row.
* Anything that changes counts calls `notifier.notify()`.
* Never edit `data/` files by hand while the API runs; use the admin panel.
