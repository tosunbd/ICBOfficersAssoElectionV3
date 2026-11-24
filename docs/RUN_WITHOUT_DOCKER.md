# Running the project WITHOUT Docker

Docker is optional. The system is two ordinary programs:

| Program | Folder | Runs with | Port |
|---|---|---|---|
| API (ballot reading, database, live stream) | `icbOfficerAssoAPI/` | Python 3.11+ | 8000 |
| Web UI (admin panel + public dashboard) | `icbOfficerAssoUI/` | Node.js 20+ | 3000 |

Nothing else is needed: no Tesseract, no poppler, no database server. The
database is a single SQLite file created automatically in `data/`.

---

## Step 1 — Install Python and Node.js (once)

**Windows**
1. Python: https://www.python.org/downloads/ → run the installer → tick
   **"Add python.exe to PATH"** → Install.
2. Node.js: https://nodejs.org/ → download the **LTS** version → install with defaults.
3. Open a new PowerShell window and check:
   ```powershell
   python --version     # Python 3.11 or newer
   node --version       # v20 or newer
   ```

**Linux (Ubuntu/Debian)**
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
```

---

## Step 2 — Set up the project (once)

Open a terminal **in the project folder** (the one containing `docker-compose.yml`).

**Windows (PowerShell)**
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1
```

**Linux / macOS**
```bash
bash scripts/setup-local.sh
```

The script:
* creates an isolated Python environment in `icbOfficerAssoAPI/.venv` and installs the packages from `requirements-dev.txt`;
* runs `npm install` in `icbOfficerAssoUI`;
* creates `.env` from `.env.example` (if it does not exist yet);
* creates the `data/Scanned`, `data/Completed`, `data/Failed`, `data/Previews` folders.

It takes 2–5 minutes the first time (downloads ~300 MB). Run it again any time; it only installs what is missing.

<details>
<summary>Doing the same by hand</summary>

```powershell
cd icbOfficerAssoAPI
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements-dev.txt
cd ..\icbOfficerAssoUI
npm install
cd ..
copy .env.example .env
mkdir data\Scanned, data\Completed, data\Failed, data\Previews
```
On Linux use `.venv/bin/python`, `cp` and `mkdir -p`.
</details>

---

## Step 3 — Edit `.env` (recommended)

Open `.env` in the project root with any editor:

```ini
ADMIN_DEFAULT_PASSWORD=admin123      # change before the real election
JWT_SECRET_KEY=change-me-...         # any long random text
SCANNED_FOLDER_PATH=./data/Scanned   # or the folder your scanner saves into
```

Relative paths are relative to the project root. Restart the API after changes.

---

## Step 4 — Start the system

**Windows (PowerShell)** — opens two windows, one per program:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-local.ps1
```
Close the two windows to stop.

**Linux / macOS** — runs both in the foreground; `Ctrl+C` stops both:
```bash
bash scripts/start-local.sh
```

<details>
<summary>Starting by hand (two terminals)</summary>

Terminal 1 — API:
```powershell
cd icbOfficerAssoAPI
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Terminal 2 — UI:
```powershell
cd icbOfficerAssoUI
npm run dev -- --hostname 0.0.0.0 --port 3000
```
Add `--reload` to the uvicorn command while developing the backend.
</details>

You should see in the API window:
```
INFO [app.services.file_watcher] Watching folder: ...\data\Scanned
INFO [app.main] API is ready
```

---

## Step 5 — Use it

| Page | URL |
|---|---|
| Admin panel | http://localhost:3000/admin — login `admin` / the password from `.env` |
| Public dashboard (projector / TV) | http://localhost:3000/dashboard |
| API documentation (Swagger) | http://localhost:8000/docs |

First-time flow: Elections → New election → Seed the 13 positions → Candidates
→ set the election **Active** → drop scanned PDFs into `data/Scanned` → Publish
results. Full details in [WALKTHROUGH.md](WALKTHROUGH.md).

### Ready-made rehearsal (no scanner needed)

A rehearsal election with **500 voters** and **anonymous candidates** (Mr. Alpha,
Mr. Bravo, … for the 13 posts of `resources/ballot.jpg`) and 10 sample ballot
PDFs is already in place in `data/`. Ballot 1 breaks rule ক (two marks for
President), ballot 2 breaks rule খ (X outside the box) and ballot 3 breaks
rule গ (scribbled box). To recreate it at any time (the API may be stopped):

```powershell
cd icbOfficerAssoAPI
.venv\Scripts\python scripts\seed_rehearsal.py --count 10 --overvote 1 --violations --voters 500
```

Counted files are renamed with their ballot paper number, e.g.
`data/Completed/Ballot_000001.pdf`.

Then:
1. Start the system (Step 4) and open **http://localhost:3000/dashboard** on the
   projector / TV. Press **⛶ Full screen** in the top-right corner.
2. Log in at http://localhost:3000/admin → **Ballots** → **Process Scanned folder now**.
3. Every 20 seconds one ballot is counted: the live screen shows the scanned
   paper with the detected marks on the left, the votes it contains, a
   countdown, and on the right the totals for every post grow by one with a
   green **+1** on the candidate who received the vote. One ballot is
   deliberately over-voted and is marked "Under review by the committee".

Three `.env` values control this behaviour; change them for a real election:

| Setting | Rehearsal value | Election-day value |
|---|---|---|
| `AUTO_PROCESS_ENABLED` | `false` — files wait until you press the button | `true` — every scanned file is counted automatically |
| `PROCESS_DELAY_SECONDS` | `20` — one ballot every 20 s | `0` — count as fast as they arrive |
| `LIVE_BALLOT_DISPLAY_SECONDS` | `20` — the starting value of **Seconds per ballot** for a new election; change it per election in Admin → Elections | `20` (the screen shortens the hold automatically when ballots arrive faster) |
| `PUBLISH_REPLAY_ENABLED` | `true` — on Publish, every ballot is shown again from the first | `true` (`false` = Publish shows the totals at once) |

To create more sample ballots while the API is running, `scripts\make_sample_ballots.py --count 5` also works with any election.

---

## Running on a server for the whole office (no Docker)

1. Do Steps 1–3 on the server PC.
2. Start in **production mode**, which builds the optimised UI once and does not
   use hot reload:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\start-local.ps1 -Production
   ```
   ```bash
   bash scripts/start-local.sh --prod
   ```
3. Allow ports **3000** and **8000** through the firewall
   (Windows: *Windows Defender Firewall → Advanced settings → Inbound Rules → New Rule → Port → TCP 3000,8000*).
4. Find the server's IP (`ipconfig` / `ip a`). Other PCs open
   `http://<server-ip>:3000/dashboard` and `http://<server-ip>:3000/admin`.
   The page automatically calls the API at `http://<server-ip>:8000`; no rebuild needed.
5. Keep it running after log-off (optional):
   * **Windows**: register both start commands as services with
     [NSSM](https://nssm.cc/) (`nssm install icb-api`, path = `...\.venv\Scripts\python.exe`,
     arguments = `-m uvicorn app.main:app --host 0.0.0.0 --port 8000`, startup dir = `...\icbOfficerAssoAPI`;
     and `icb-ui` with `node` / `npm run start -- --hostname 0.0.0.0 --port 3000` in `icbOfficerAssoUI`
     after `npm run build`), or create two entries in **Task Scheduler** that run at startup.
   * **Linux**: two `systemd` units (example in [RUNNING.md](RUNNING.md)).

---

## Stopping, restarting, updating

| Action | How |
|---|---|
| Stop | close the two windows / `Ctrl+C` / stop the services |
| Restart after editing `.env` | stop and start the API again |
| Update the code | pull the new files, run the setup script again (installs new packages), restart |
| Rebuild the UI after frontend changes (production mode) | `cd icbOfficerAssoUI && npm run build` then restart the UI |

## Where everything is stored

```
data/
├── icbOfficerAssoDB2026.db  the database of the 2026 election (one file per year; back it up)
├── Archive/                 copies saved by DBCLEAR.bat
├── Scanned/                 drop scans here
├── Completed/               processed scans
├── Failed/                  unreadable files
└── Previews/                annotated PNGs shown on the review screen
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `python` / `node` not recognised | PATH not set; reinstall Python with "Add to PATH", open a **new** terminal |
| PowerShell: "running scripts is disabled" | use the `-ExecutionPolicy Bypass` form shown above |
| `Address already in use` on 8000 or 3000 | another program uses the port; stop it or change `--port` |
| Files stay in `data/Scanned` | no election is **Active**, or `AUTO_PROCESS_ENABLED=false` in `.env`; check Admin → Overview |
| Dashboard says "Reconnecting…" | the API is not running or the firewall blocks port 8000 |
| A ballot shows "needs review" | expected for over-votes or bad scans; open it in Admin → Ballots and confirm the votes |
| Fonts look different offline | Google Fonts could not load; the UI falls back to system fonts, nothing is broken |
