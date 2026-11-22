# Running the system

All configuration lives in the `.env` file in the project root (copy
`.env.example`). The most important values:

| Setting | Meaning |
|---|---|
| `ADMIN_DEFAULT_USERNAME` / `ADMIN_DEFAULT_PASSWORD` | first admin account (created on first start only) |
| `JWT_SECRET_KEY` | change to a long random string on the real server |
| `SCANNED_FOLDER_PATH` | where the scanner saves files (`./data/Scanned` by default) |
| `COMPLETED_FOLDER_PATH`, `FAILED_FOLDER_PATH` | where processed / unreadable files are moved |
| `AUTO_PROCESS_ENABLED` | `true` = process new files automatically |
| `OCR_DPI`, `MARK_THRESHOLD`, `LOW_CONFIDENCE_THRESHOLD` | detection tuning (see CODE_GUIDE.md) |

Relative paths are relative to the project root, no matter where you start the
programs from. Restart the API after changing `.env`.

---

## 1. Local PC (development or a single-PC election)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-local.ps1
```
Two windows open: the API (port 8000) and the UI (port 3000). Close the windows to stop.

Linux/macOS: `bash scripts/start-local.sh` (Ctrl+C stops both).

Manual equivalent:

```bash
# terminal 1
cd icbOfficerAssoAPI
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# terminal 2
cd icbOfficerAssoUI
npm run dev -- --hostname 0.0.0.0 --port 3000
```

Open http://localhost:3000/admin → log in → follow [WALKTHROUGH.md](WALKTHROUGH.md).

---

## 2. Server on the office network (without Docker)

1. Install as in [INSTALL.md](INSTALL.md) on the server.
2. Edit `.env`: set a real `JWT_SECRET_KEY` and `ADMIN_DEFAULT_PASSWORD`; if the
   scanner saves to a shared folder, point `SCANNED_FOLDER_PATH` to it
   (e.g. `D:/ElectionScans/Scanned` or `//FILESERVER/Election/Scanned`).
3. Start in production mode (builds the optimised UI once):
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\start-local.ps1 -Production
   ```
   ```bash
   bash scripts/start-local.sh --prod
   ```
4. Other PCs open `http://<server-ip>:3000/dashboard` (public) and
   `http://<server-ip>:3000/admin` (committee). The browser calls the API on
   `http://<server-ip>:8000` automatically, so no rebuild is needed when the IP
   changes. Open ports **3000** and **8000** in the Windows Firewall
   ("Allow an app" → node.exe and python.exe, or an inbound rule for the ports).
5. To keep it running after logout, register both commands as Windows services
   (e.g. with NSSM) or as `systemd` units on Linux:

   ```ini
   # /etc/systemd/system/icb-api.service
   [Service]
   WorkingDirectory=/opt/ICBOfficersAssoElection/icbOfficerAssoAPI
   ExecStart=/opt/ICBOfficersAssoElection/icbOfficerAssoAPI/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   Restart=always
   [Install]
   WantedBy=multi-user.target
   ```
   (and the same for the UI with `npm run start -- --hostname 0.0.0.0 --port 3000`
   after `npm run build`).

---

## 3. Docker (recommended for a server)

```bash
cp .env.example .env         # edit JWT_SECRET_KEY / ADMIN_DEFAULT_PASSWORD
docker compose up --build -d # build both images and start
docker compose logs -f api   # watch ballots being processed
docker compose down          # stop; data/ on the host is kept
```

* The host folder `./data` is mounted into the API container, so the scanner
  must save into `<project>/data/Scanned` on the host (or change the volume line
  in `docker-compose.yml` to another host folder, e.g. `- D:/ElectionScans:/app/data`).
* Ports are `API_PORT` and `UI_PORT` from `.env` (defaults 8000 / 3000).
* Development with hot reload for the API:
  `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`

### Docker verification checklist (to run on a machine with Docker)

Docker is not installed on the development PC, so the compose files were
validated for syntax only. Please run these once on the target machine:

1. `docker compose config` — prints the merged configuration without errors.
2. `docker compose build` — both images build (API ≈ 2 min, UI ≈ 3 min).
3. `docker compose up -d` then `docker compose ps` — both containers show `healthy`
   (the UI waits for the API health check before starting).
4. `curl http://localhost:8000/api/health` — returns `"status":"healthy"` and
   `"file_watcher":true`.
5. Open http://localhost:3000/admin, log in, create an election, seed positions
   **with template candidates**, set it **active**, publish the dashboard.
6. Generate test ballots into the mounted folder:
   `docker compose exec api python scripts/make_sample_ballots.py --count 5 --out /app/data/Scanned`
   — within ~10 s the files move to `data/Completed` on the host and the
   dashboard at http://localhost:3000/dashboard updates.
7. `docker compose logs api` shows `Processed sample_ballot_... processed`.
8. Windows only: if files copied into `data/Scanned` are **not** picked up
   within 5 s, the bind mount is not delivering file events; the 5-second
   polling sweep still processes them (check `files_waiting` in Admin → Overview).
9. `docker compose down && docker compose up -d` — the database and the
   folders survive a restart (they live in `./data` on the host).

---

## 4. Everyday operation

| Task | Where |
|---|---|
| Watch processing status, files waiting | Admin → Overview |
| Upload a file by hand | Admin → Ballots → drop zone |
| Process everything waiting in the folder now | "Scan folder now" button |
| Check a flagged ballot | Admin → Ballots → filter "Needs review" → Review |
| Show / hide results on the public screen | Admin → Overview or Results & Controls |
| Freeze the public screen (e.g. during a recount) | "Pause live updates" |
| Export results | Admin → Results & Controls → Export CSV |
| Change the admin password | Admin → Settings |
| See who did what | Admin → Audit Log |

### Backups
Everything is in `data/`: the database `icbOfficerAssoDB<year>.db` (plus `-wal`/`-shm`
files while running), the scanned files and the previews. Copy the whole folder.

### Resetting for a new election
Each election year has its own database file, `data/icbOfficerAssoDB<year>.db`
(`DATABASE_URL=sqlite+aiosqlite:///./data/icbOfficerAssoDB{Year}.db` in `.env`).
Choose the year in **Admin → Settings → Database**: a year without a file starts
with an empty database (the admin logins are copied over), and the files of
earlier years stay untouched as the record of those elections.

Just before counting starts, double-click **`DBCLEAR.bat`** in the project root
to empty the current year's database after rehearsals. It stops the system if
needed, saves a full copy to `data/Archive/<date>_<time>_before-clear/`,
optionally moves the files of the Scanned / Completed / Failed / Previews
folders into that archive, then empties every table except the admin accounts.
Start the system again with `Start.bat` and create the election.
