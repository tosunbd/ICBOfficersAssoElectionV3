# ICB Officers' Association Election — Task List

## Phase 1: Project Setup & Docker
- [x] Create root `docker-compose.yml` and `.env.example`
- [x] Create backend `Dockerfile` and `requirements.txt`
- [x] Create frontend `Dockerfile` and scaffold Next.js 16.3.5 project

## Phase 2: Backend — Database & Models
- [x] `app/config.py` — Settings
- [x] `app/database.py` — SQLAlchemy async setup
- [x] `app/models/` — All 7 ORM models (dynamic candidate count per position)
- [x] `app/schemas/` — Pydantic schemas

## Phase 3: Backend — Auth & Core APIs
- [x] `app/utils/security.py` — JWT + password hashing
- [x] `app/routers/auth.py` — Login endpoint
- [x] `app/routers/elections.py` — Election CRUD
- [x] `app/routers/candidates.py` — Candidate CRUD (variable count)
- [x] `app/routers/ballots.py` — Upload, process, review
- [x] `app/routers/dashboard.py` — Results + SSE stream
- [x] `app/routers/admin.py` — Publish/pause controls
- [x] `app/main.py` — FastAPI app with all routers

## Phase 4: Backend — OCR & Processing Pipeline
- [x] `app/services/ocr_service.py` — PDF → checkbox detection (dynamic layout)
- [x] `app/services/ballot_processor.py` — Orchestrate scan → DB
- [x] `app/services/file_watcher.py` — Watch Scanned/ folder
- [x] `app/services/vote_counter.py` — Tally & ranking

## Phase 5: Frontend — Design System & Layout
- [x] `globals.css` — Full design system
- [x] `layout.tsx` — Root layout with fonts
- [x] `admin/layout.tsx` — Admin sidebar layout
- [x] UI components (Button, Card, Modal, Table, Badge, etc.)

## Phase 6: Frontend — Pages
- [x] Public dashboard page (live results)
- [x] Admin login page
- [x] Admin dashboard overview
- [x] Ballot upload & review pages
- [x] Candidate management page
- [x] Results & controls page

## Phase 7: Frontend — Real-time & Hooks
- [x] `useSSE.ts` — Server-Sent Events hook
- [x] `useAuth.ts` — Auth context
- [x] `useApi.ts` — API client
- [x] Dashboard components (LiveResults, PositionCard, VoteProgressBar)

## Phase 8: Integration & Testing
- [ ] Docker Compose build test
- [ ] End-to-end ballot processing test
- [ ] Dashboard real-time update verification
