"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { errorMessage, formatDateTime } from "@/lib/format";
import type { AuditLogEntry } from "@/lib/types";
import { useAuth } from "@/hooks/useAuth";
import { useLoader } from "@/hooks/useLoader";
import { useToast } from "@/components/ui/Toast";
import { CardHead, PageHeader, initials } from "@/components/ui/Basics";
import { Icon, type IconName } from "@/components/ui/Icon";

/** Picks an icon and colour for an audit action from its name. */
function actionLook(action: string): { icon: IconName; tone: string } {
  const a = action.toLowerCase();
  if (a.includes("delete") || a.includes("remove")) return { icon: "trash", tone: "error" };
  if (a.includes("login") || a.includes("password") || a.includes("auth")) return { icon: "key", tone: "accent" };
  if (a.includes("review")) return { icon: "shield", tone: "success" };
  if (a.includes("publish") || a.includes("pause") || a.includes("replay")) return { icon: "broadcast", tone: "accent" };
  if (a.includes("upload") || a.includes("scan") || a.includes("ballot")) return { icon: "ballot", tone: "" };
  if (a.includes("create") || a.includes("add") || a.includes("seed")) return { icon: "plus", tone: "success" };
  if (a.includes("recount")) return { icon: "calculator", tone: "" };
  return { icon: "edit", tone: "" };
}

export default function AuditPage() {
  const { token } = useAuth();
  const toast = useToast();
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [limit, setLimit] = useState(100);
  const [filter, setFilter] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setEntries(await api.admin.auditLog(token, limit));
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }, [token, limit, toast]);

  useLoader(load);

  const q = filter.trim().toLowerCase();
  const shown = q ? entries.filter((e) => `${e.action} ${e.details ?? ""} ${e.username ?? ""}`.toLowerCase().includes(q)) : entries;

  return (
    <div className="page">
      <PageHeader eyebrow="System" title="Audit log" subtitle="Every admin action, newest first"
        actions={
          <>
            <select className="input input-sm" style={{ width: 130 }} value={limit} onChange={(e) => setLimit(Number(e.target.value))} aria-label="How many entries">
              {[50, 100, 250, 500, 1000].map((n) => <option key={n} value={n}>Last {n}</option>)}
            </select>
            <button className="btn btn-ghost btn-sm" onClick={load}><Icon name="refresh" size={14} /> Refresh</button>
          </>
        } />
      <div className="card">
        <CardHead icon="scroll" title={<>Activity <span className="badge badge-muted" style={{ marginLeft: 6 }}>{shown.length}</span></>} gold>
          <div className="input-wrap" style={{ width: 260 }}>
            <Icon name="search" size={15} />
            <input className="input input-sm" style={{ paddingLeft: 36 }} placeholder="Filter actions, users, details…" value={filter} onChange={(e) => setFilter(e.target.value)} />
          </div>
        </CardHead>
        {shown.length === 0 ? <div className="empty-inline"><Icon name="scroll" size={30} />{entries.length ? "No entries match the filter." : "Nothing logged yet."}</div> : (
          <div className="table-wrapper">
            <table className="table">
              <thead><tr><th style={{ width: 44 }}></th><th>Action</th><th>Details</th><th>User</th><th>When</th></tr></thead>
              <tbody>
                {shown.map((e) => {
                  const look = actionLook(e.action);
                  return (
                    <tr key={e.id}>
                      <td><span className={`timeline-dot ${look.tone}`} style={{ width: 30, height: 30, borderRadius: 9 }}><Icon name={look.icon} size={14} /></span></td>
                      <td><span className="audit-action">{e.action}</span></td>
                      <td style={{ maxWidth: 520 }}>{e.details}</td>
                      <td>
                        {e.username
                          ? <span className="flex items-center gap-2"><span className="avatar avatar-sm">{initials(e.username)}</span>{e.username}</span>
                          : <span className="badge badge-muted"><Icon name="server" />system</span>}
                      </td>
                      <td className="text-faint text-small" style={{ whiteSpace: "nowrap" }}>{formatDateTime(e.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
