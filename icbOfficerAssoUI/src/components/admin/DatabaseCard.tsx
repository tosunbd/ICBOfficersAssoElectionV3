"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { errorMessage, formatDateTime } from "@/lib/format";
import type { DatabaseInfo } from "@/lib/types";
import { useAuth } from "@/hooks/useAuth";
import { useElection } from "@/hooks/useElection";
import { useLoader } from "@/hooks/useLoader";
import { useToast } from "@/components/ui/Toast";
import { ConfirmDialog } from "@/components/ui/Modal";
import { Alert, CardHead, Spinner } from "@/components/ui/Basics";
import { Icon } from "@/components/ui/Icon";

function formatSize(bytes: number | null): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Settings card: one database file per election year (icbOfficerAssoDB{Year}.db). */
export function DatabaseCard() {
  const { token } = useAuth();
  const { refresh } = useElection();
  const toast = useToast();
  const [info, setInfo] = useState<DatabaseInfo | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [confirmYear, setConfirmYear] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setInfo(await api.admin.database(token));
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }, [token, toast]);

  useLoader(load);

  const target = year ?? info?.year ?? new Date().getFullYear();
  const validYear = target >= 2000 && target <= 2100;
  const targetFile = info?.files.find((f) => f.year === target);
  const templateName = (y: number) => info?.file_name?.replace(String(info.year), String(y)) ?? `icbOfficerAssoDB${y}.db`;

  const switchYear = async () => {
    if (!token || confirmYear == null) return;
    setBusy(true);
    try {
      const next = await api.admin.setDatabaseYear(token, confirmYear);
      setInfo(next);
      setYear(null);
      await refresh();
      toast.success(`Now using ${next.file_name}`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
      setConfirmYear(null);
    }
  };

  const confirmExists = info?.files.some((f) => f.year === confirmYear);

  return (
    <div className="card mb-6" id="database">
      <CardHead icon="server" title="Database" subtitle="Every election year is kept in its own file, which stays as the record of that election" />
      {!info ? <Spinner /> : (
        <div className="flex flex-col gap-4">
          <div className="db-current">
            <span className="db-current-icon"><Icon name="shield" size={20} /></span>
            <div className="flex-1" style={{ minWidth: 0 }}>
              <div className="info-row-label">In use · {info.year}</div>
              <div className="db-current-name">{info.file_name ?? "—"}</div>
              <div className="text-faint text-small db-current-path" title={info.path ?? ""}>{info.path} · {formatSize(info.size_bytes)}</div>
            </div>
          </div>

          {!info.per_year ? (
            <Alert type="warning">
              <code>DATABASE_URL</code> in <code>.env</code> has no <code>{"{Year}"}</code> placeholder, so the file cannot be chosen by year here.
              Use <code>sqlite+aiosqlite:///./data/icbOfficerAssoDB{"{Year}"}.db</code> and restart the API.
            </Alert>
          ) : (
            <>
              <div className="db-switch">
                <div className="input-group" style={{ flex: "0 1 180px" }}><label className="input-label" htmlFor="db-year">Election year</label>
                  <div className="input-wrap"><Icon name="clock" size={16} />
                    <input id="db-year" className="input" type="number" min={2000} max={2100} value={target}
                      onChange={(e) => setYear(Number(e.target.value))} /></div></div>
                <div className="db-switch-file">
                  <Icon name="arrowRight" size={15} />
                  <code>{templateName(target)}</code>
                  {validYear && target !== info.year && (
                    <span className={`badge ${targetFile ? "badge-muted" : "badge-warning"}`}>{targetFile ? "exists" : "new, empty"}</span>
                  )}
                </div>
                <button className="btn btn-accent" disabled={!validYear || target === info.year || busy} onClick={() => setConfirmYear(target)}>
                  <Icon name="refresh" size={16} /> Use this year
                </button>
              </div>

              {info.files.length > 0 && (
                <div className="db-files">
                  {info.files.map((file) => (
                    <div key={file.year} className={`db-file ${file.current ? "is-current" : ""}`}>
                      <span className="db-file-year">{file.year}</span>
                      <div className="flex-1" style={{ minWidth: 0 }}>
                        <div className="db-file-name">{file.file_name}</div>
                        <div className="text-faint text-small">{formatSize(file.size_bytes)} · changed {formatDateTime(file.modified_at)}</div>
                      </div>
                      {file.current
                        ? <span className="badge badge-success badge-dot">In use</span>
                        : <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => setConfirmYear(file.year)}>Open</button>}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          <Alert type="info">
            Just before counting starts, double-click <strong>DBCLEAR.bat</strong> in the project folder to empty this database after rehearsals.
            A full copy is saved to <code>data/Archive</code> first and the admin logins are kept.
          </Alert>
        </div>
      )}

      <ConfirmDialog open={confirmYear !== null} busy={busy} title={`Use the ${confirmYear} database?`} confirmLabel="Switch database"
        message={confirmExists
          ? `The system will read and write ${templateName(confirmYear ?? 0)} from now on. The ${info?.year} file stays exactly as it is.`
          : `${templateName(confirmYear ?? 0)} does not exist yet: a new, empty database is created and your admin login is copied into it. The ${info?.year} file stays exactly as it is.`}
        onConfirm={switchYear} onCancel={() => setConfirmYear(null)} />
    </div>
  );
}
