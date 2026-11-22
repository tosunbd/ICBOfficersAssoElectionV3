# Installing the requirements

You need **either** Docker **or** Python + Node.js. Nothing else: the ballot
reader has no external programs to install (no Tesseract, no poppler).

## Option A — Docker (simplest for a server)

1. Install **Docker Desktop** (Windows/macOS) from https://www.docker.com/products/docker-desktop/
   or **Docker Engine + Compose plugin** on Linux (`sudo apt install docker.io docker-compose-plugin`).
2. Check it works:
   ```bash
   docker --version
   docker compose version
   ```
That is all. `docker compose up --build` downloads everything else.

## Option B — Local installation (Windows PC or Linux server)

### 1. Python 3.11 or newer
* Windows: https://www.python.org/downloads/ → run the installer → **tick "Add python.exe to PATH"**.
* Linux: `sudo apt install python3 python3-venv python3-pip`

Check: `python --version` (Windows) or `python3 --version` (Linux).

### 2. Node.js 20 or newer (LTS)
* Download from https://nodejs.org/ (LTS) and install with the defaults.

Check: `node --version` and `npm --version`.

### 3. Project packages
Run the setup script once from the project folder. It creates an isolated Python
environment (`icbOfficerAssoAPI/.venv`), installs the Python packages, installs
the npm packages, creates `.env` from `.env.example` and the `data/` folders.

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1
```
```bash
# Linux / macOS
bash scripts/setup-local.sh
```

Manual equivalent, if you prefer to see each step:

```bash
cd icbOfficerAssoAPI
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt     # Windows
# .venv/bin/python -m pip install -r requirements-dev.txt       # Linux

cd ../icbOfficerAssoUI
npm install

cd ..
copy .env.example .env      # Windows   (cp on Linux)
```

### What gets installed (backend)

| Package | Purpose |
|---|---|
| fastapi, uvicorn | web API server |
| sqlalchemy, aiosqlite | SQLite database access |
| pydantic-settings | reads `.env` |
| python-jose, bcrypt | login tokens and password hashing |
| pypdfium2 | renders PDF pages to images (bundled PDF engine) |
| opencv-python-headless, numpy, Pillow | detects the marked boxes |
| watchdog | notices new files in the Scanned folder |
| sse-starlette | live dashboard stream |
| pytest, httpx (dev only) | automated tests |

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not recognised | Re-run the Python installer and tick "Add to PATH", or use `py -3` |
| `npm install` is slow / fails behind a proxy | `npm config set proxy http://proxy:port` then retry |
| PowerShell refuses to run scripts | Use the `-ExecutionPolicy Bypass` form shown above |
| Port 8000 or 3000 already in use | Change `API_PORT` / `UI_PORT` in `.env` (Docker) or the `--port` in the start commands |
