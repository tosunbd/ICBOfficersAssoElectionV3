# ICB Officers' Association Election — Phase 8: Integration & Testing

## Phase 8.1: Backend Verification
- [x] Install Python dependencies and verify imports
- [x] Start FastAPI backend and test health endpoint
- [x] Fix any runtime errors in backend
- [x] Verify all API endpoints respond correctly (40/40 tests passed)

## Phase 8.2: Frontend Build Verification
- [x] Verify Next.js frontend builds without errors (12 routes)
- [x] Fix any TypeScript/build errors (ESLint clean incl. React Compiler rules)
- [x] Test frontend dev server starts (all routes return HTTP 200)

## Phase 8.3: Docker Compose Verification
- [x] Verify Docker Compose file syntax (YAML validated; `version:` removed, unused volume removed)
- [x] Fix any Docker-related issues (missing `public/` folder, removed `libgl1-mesa-glx`/tesseract/poppler,
      production CMD without `--reload`, non-root users, health checks, `.dockerignore`, build arg for API URL)
- [x] Document any remaining Docker testing for user → docs/RUNNING.md "Docker verification checklist"
      (Docker is not installed on the development PC; run the checklist on the target machine)

## Phase 8.4: End-to-End Integration
- [x] Test API: Create election -> Seed positions -> Add candidates
- [x] Test API: Upload ballot -> Process -> Verify votes
- [x] Test SSE dashboard stream endpoint
- [x] Verify file watcher functionality (live: 3 PDFs / 6 pages dropped in data/Scanned → counted in ~6 s)
- [x] Test audit log tracking

## Phase 8.5: Final Polish & Documentation
- [x] Update README with complete instructions
- [x] Create walkthrough document (docs/WALKTHROUGH.md)
- [x] docs/INSTALL.md, docs/RUNNING.md, docs/CODE_GUIDE.md
- [x] scripts/setup-local.* and scripts/start-local.* helpers

## Phase 9: Hardening done during Phase 8 (2026-09-17)
- [x] Folder watcher now actually processes files (queue + worker + polling sweep + stable-size wait)
- [x] Mark detection rewritten for the real 2-column ballot layout (table detection, deskew, outline test)
- [x] Over-vote validation, needs_review flagging, per-page ballots for multi-page PDFs
- [x] Review screen with annotated scan preview; reprocess / delete keep counters consistent
- [x] Push-based SSE, publish gating on the API, single active election
- [x] pypdfium2 replaces pdf2image/poppler; Tesseract removed (not needed)
- [x] Automated tests: 23 (OCR + API), `pytest` in icbOfficerAssoAPI
