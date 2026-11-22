"""Clear the election database before the real count starts (run via DBCLEAR.bat).

What it does, in order:
  1. Stops if the system is still running (offers to stop it with Stop.bat's script).
  2. Saves a full copy of the current database to data/Archive/<date>_<time>/.
  3. Optionally moves the files in the Scanned / Completed / Failed / Previews
     folders into the same archive folder, so rehearsal ballots cannot mix with
     the real ones.
  4. Empties every table except the admin accounts (logins and passwords stay),
     resets the id counters and writes one "database_cleared" audit entry.

The database cleared is the one for the current election year:
icbOfficerAssoDB<year>.db (year from Admin -> Settings -> Database, or .env).

    python scripts/clear_db.py            # asks before doing anything
    python scripts/clear_db.py --yes      # no questions (keeps the ballot files)
"""

import argparse
import shutil
import socket
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import PROJECT_ROOT, settings  # noqa: E402

KEEP_TABLES = {"admin_users", "sqlite_sequence"}
API_PORT = 8000


def ask(question: str) -> bool:
    while True:
        answer = input(f"{question} [Y/N]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


def api_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", API_PORT)) == 0


def stop_system() -> None:
    script = PROJECT_ROOT / "scripts" / "stop-local.ps1"
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], check=False)


def counts(connection: sqlite3.Connection) -> dict[str, int]:
    tables = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    return {table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables}


def archive_files(archive: Path) -> int:
    moved = 0
    folders = {
        "Scanned": settings.scanned_path, "Completed": settings.completed_path,
        "Failed": settings.failed_path, "Previews": settings.preview_path,
    }
    for label, folder in folders.items():
        files = [p for p in folder.iterdir() if p.is_file()]
        if not files:
            continue
        target = archive / label
        target.mkdir(parents=True, exist_ok=True)
        for path in files:
            shutil.move(str(path), str(target / path.name))
            moved += 1
        print(f"  moved {len(files):>4} file(s) from {folder}")
    return moved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation (ballot files are kept)")
    args = parser.parse_args()

    db_file = settings.database_file
    print()
    print("  ICB Officers' Association Election - clear database")
    print("  ---------------------------------------------------")
    if db_file is None:
        print("  DATABASE_URL is not a SQLite file; nothing to do.")
        return 1
    print(f"  Election year : {settings.database_year}")
    print(f"  Database file : {db_file}")
    if not db_file.exists():
        print("\n  This database does not exist yet - it will be created empty when the system starts.")
        return 0

    if api_running():
        print("\n  The system is running. It has to be stopped before the database is cleared.")
        if args.yes or ask("  Stop it now?"):
            stop_system()
        if api_running():
            print("  The system is still running - run Stop.bat and try again.")
            return 1

    connection = sqlite3.connect(db_file)
    try:
        before = counts(connection)
        print("\n  Current contents:")
        for table, count in before.items():
            print(f"    {table:<16} {count:>7}{'   (kept)' if table in KEEP_TABLES else ''}")

        move_files = False
        if not args.yes:
            print()
            if not ask(f"  Clear icbOfficerAssoDB data for {settings.database_year}? A backup copy is saved first."):
                print("  Cancelled - nothing was changed.")
                return 0
            move_files = ask("  Also move the files in the Scanned / Completed / Failed / Previews folders into the archive?")

        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        archive = db_file.parent / "Archive" / f"{stamp}_before-clear"  # next to the database (data/Archive)
        archive.mkdir(parents=True, exist_ok=True)
        backup_file = archive / db_file.name
        with sqlite3.connect(backup_file) as backup:  # consistent copy, includes the WAL
            connection.backup(backup)
        backup.close()
        print(f"\n  Backup saved  : {backup_file}")
        if move_files:
            print(f"  Ballot files  : {archive_files(archive)} moved to {archive}")

        connection.execute("PRAGMA foreign_keys=OFF")
        with connection:
            for table in before:
                if table not in KEEP_TABLES:
                    connection.execute(f'DELETE FROM "{table}"')
            has_sequence = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
            ).fetchone()
            if has_sequence:  # only exists for AUTOINCREMENT tables; plain ids restart at 1 anyway
                connection.execute("DELETE FROM sqlite_sequence WHERE name != 'admin_users'")
            if "audit_log" in before:
                connection.execute(
                    "INSERT INTO audit_log (admin_user_id, action, details, created_at) VALUES (NULL, ?, ?, ?)",
                    ("database_cleared",
                     f"Database cleared with DBCLEAR; previous contents saved to {backup_file}",
                     datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")),
                )
        connection.execute("VACUUM")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()

    print("\n  Done. The database is clean; admin logins were kept.")
    print("  Start the system with Start.bat, then create the election in the admin panel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
