"use client";

import { useCallback, useState, type FormEvent } from "react";
import { api, getApiBaseUrl } from "@/lib/api";
import { errorMessage } from "@/lib/format";
import type { SystemStatus } from "@/lib/types";
import { useAuth } from "@/hooks/useAuth";
import { useLoader } from "@/hooks/useLoader";
import { useToast } from "@/components/ui/Toast";
import { CardHead, PageHeader, Spinner } from "@/components/ui/Basics";
import { Icon, type IconName } from "@/components/ui/Icon";
import { FolderPicker } from "@/components/admin/FolderPicker";
import { ElectionTitleCard } from "@/components/admin/ElectionTitleCard";
import { DatabaseCard } from "@/components/admin/DatabaseCard";

type FolderKey = "scanned_folder" | "completed_folder" | "failed_folder";
const FOLDERS: Array<{ key: FolderKey; label: string; desc: string; icon: IconName; tone: string }> = [
  { key: "scanned_folder", label: "Scanned folder", desc: "The scanner saves ballots here; they are picked up automatically", icon: "folderScan", tone: "primary" },
  { key: "completed_folder", label: "Completed folder", desc: "Counted ballots are moved here, renamed Ballot_<paper no>.pdf (or .jpg, .png … for images)", icon: "checkCircle", tone: "success" },
  { key: "failed_folder", label: "Failed folder", desc: "Files that could not be read are moved here", icon: "xCircle", tone: "error" },
];

/** Rough strength hint for the new password (display only; the server enforces its own rules). */
function strength(password: string): { score: number; label: string } {
  if (!password) return { score: 0, label: "" };
  let score = 0;
  if (password.length >= 6) score++;
  if (password.length >= 10) score++;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score++;
  if (/\d/.test(password) && /[^A-Za-z0-9]/.test(password)) score++;
  score = Math.max(1, score);
  return { score, label: ["", "Weak", "Fair", "Good", "Strong"][score] };
}

export default function SettingsPage() {
  const { token, username } = useAuth();
  const toast = useToast();
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState<FolderKey | null>(null);
  const [savingFolder, setSavingFolder] = useState<FolderKey | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setSystem(await api.admin.system(token));
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }, [token, toast]);

  useLoader(load);

  const changePassword = async (event: FormEvent) => {
    event.preventDefault();
    if (!token) return;
    if (next !== confirm) { toast.error("New passwords do not match"); return; }
    setBusy(true);
    try {
      await api.auth.changePassword(token, current, next);
      toast.success("Password changed");
      setCurrent(""); setNext(""); setConfirm("");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const chooseFolder = async (key: FolderKey, path: string) => {
    if (!token) return;
    setPicking(null);
    setSavingFolder(key);
    try {
      setSystem(await api.admin.updateFolders(token, { [key]: path }));
      toast.success(`${FOLDERS.find((f) => f.key === key)?.label} set to ${path}`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSavingFolder(null);
    }
  };

  const meter = strength(next);
  const mismatch = confirm.length > 0 && next !== confirm;
  const rows: Array<{ label: string; icon: IconName; value: React.ReactNode }> = system ? [
    { label: "API URL", icon: "server", value: <code>{getApiBaseUrl()}</code> },
    { label: "Auto processing", icon: "zap", value: <span className={`badge badge-dot ${system.auto_process_enabled ? "badge-success" : "badge-warning"}`}>{system.auto_process_enabled ? "enabled" : "disabled"}</span> },
    { label: "Folder watcher", icon: "activity", value: <>{system.watcher_running ? "running" : "stopped"} <span className="text-faint">({system.os_events_active ? "OS events + polling" : "polling"})</span></> },
    { label: "Active election id", icon: "landmark", value: system.active_election_id ?? <span className="text-faint">none</span> },
    { label: "Render DPI", icon: "zoomIn", value: system.ocr_dpi },
    { label: "Mark threshold", icon: "target", value: `${(system.mark_threshold * 100).toFixed(0)}% ink inside a box` },
  ] : [];

  return (
    <div className="page">
      <PageHeader eyebrow="System" title="Settings" subtitle="Election title, folders, database, account and system information" />

      <ElectionTitleCard />

      <div className="card card-gold mb-6" id="folders">
        <CardHead icon="folderScan" title="Ballot folders" subtitle="Choose where scanned ballots arrive and where counted ones are filed — applied immediately" gold />
        <div className="folder-grid">
          {FOLDERS.map((folder) => {
            const current = system ? system[folder.key] : "";
            return (
              <div key={folder.key} className={`folder-card tone-${folder.tone}`}>
                <div className="folder-card-top">
                  <span className="folder-card-icon"><Icon name={folder.icon} size={20} /></span>
                  <div className="flex-1">
                    <div className="folder-card-title">{folder.label}</div>
                    <div className="folder-card-desc">{folder.desc}</div>
                  </div>
                </div>
                <div className="folder-card-path" title={current}>{current ? <code>{current}</code> : <span className="skeleton" style={{ height: 22, display: "block" }} />}</div>
                <button className="btn btn-ghost btn-sm btn-block" disabled={!system || savingFolder !== null} onClick={() => setPicking(folder.key)}>
                  {savingFolder === folder.key ? <><span className="btn-spinner" /> Saving…</> : <><Icon name="search" size={14} /> Browse…</>}
                </button>
              </div>
            );
          })}
        </div>
      </div>
      <DatabaseCard />
      <div className="two-columns">
        <div className="card">
          <CardHead icon="key" title="Change password" subtitle={`Signed in as ${username}`} gold />
          <form onSubmit={changePassword} className="flex flex-col gap-4">
            <div className="input-group"><label className="input-label" htmlFor="pw-current">Current password</label>
              <div className="input-wrap"><Icon name="lock" size={16} />
                <input id="pw-current" className="input" type={show ? "text" : "password"} autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
                <button type="button" className="input-affix" onClick={() => setShow((v) => !v)} aria-label={show ? "Hide passwords" : "Show passwords"}><Icon name={show ? "eyeOff" : "eye"} size={15} /></button>
              </div></div>
            <div className="input-group"><label className="input-label" htmlFor="pw-next">New password</label>
              <div className="input-wrap"><Icon name="key" size={16} />
                <input id="pw-next" className="input" type={show ? "text" : "password"} autoComplete="new-password" minLength={6} value={next} onChange={(e) => setNext(e.target.value)} required /></div>
              <div className={`strength s${meter.score}`}><span /><span /><span /><span /></div>
              <span className="input-hint">{meter.label ? `${meter.label} · ` : ""}Minimum 6 characters</span>
            </div>
            <div className="input-group"><label className="input-label" htmlFor="pw-confirm">Repeat new password</label>
              <div className="input-wrap"><Icon name={mismatch ? "xCircle" : confirm && !mismatch ? "checkCircle" : "key"} size={16} />
                <input id="pw-confirm" className="input" type={show ? "text" : "password"} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required
                  style={mismatch ? { borderColor: "var(--color-error)" } : undefined} /></div>
              {mismatch && <span className="input-hint text-error">Passwords do not match yet</span>}
            </div>
            <button className="btn btn-primary" type="submit" disabled={busy}>
              {busy ? <><span className="btn-spinner" /> Updating…</> : <><Icon name="shield" size={16} /> Update password</>}
            </button>
          </form>
        </div>

        <div className="card">
          <CardHead icon="server" title="System" subtitle="Read from the API server" />
          {!system ? <Spinner /> : (
            <div className="info-list stagger">
              {rows.map((row) => (
                <div className="info-row" key={row.label}>
                  <span className="info-row-icon"><Icon name={row.icon} size={16} /></span>
                  <div style={{ minWidth: 0 }}><div className="info-row-label">{row.label}</div><div className="info-row-value">{row.value}</div></div>
                </div>
              ))}
            </div>
          )}
          <p className="text-faint text-small mt-4">
            Detection thresholds are configured in the <code>.env</code> file of the server (see docs/RUNNING.md). Restart the API after changing them.
          </p>
        </div>
      </div>
      <FolderPicker open={picking !== null} token={token}
        title={`Choose the ${FOLDERS.find((f) => f.key === picking)?.label.toLowerCase() ?? "folder"}`}
        initialPath={picking && system ? system[picking] : ""}
        onClose={() => setPicking(null)} onPick={(path) => picking && chooseFolder(picking, path)} />
    </div>
  );
}
