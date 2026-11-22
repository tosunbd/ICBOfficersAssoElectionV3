"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/format";
import type { FolderListing } from "@/lib/types";
import { Modal } from "@/components/ui/Modal";
import { Icon } from "@/components/ui/Icon";

interface Props {
  open: boolean;
  token: string | null;
  title: string;
  initialPath: string;
  onClose: () => void;
  onPick: (path: string) => void;
}

/** Browse the API server's folders and choose one (folders only). */
export function FolderPicker({ open, token, title, initialPath, onClose, onPick }: Props) {
  const [listing, setListing] = useState<FolderListing | null>(null);
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const go = useCallback(async (path: string) => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const next = await api.admin.browseFolders(token, path);
      setListing(next);
      setTyped(next.path);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => { void go(initialPath); });
    return () => cancelAnimationFrame(frame);
  }, [open, initialPath, go]);

  const submitTyped = (event: FormEvent) => {
    event.preventDefault();
    void go(typed.trim());
  };

  const here = listing?.path ?? "";
  const crumbs = here ? here.split(/[\\/]+/).filter(Boolean) : [];
  const sep = here.includes("\\") ? "\\" : "/";
  const crumbPath = (index: number) => {
    const joined = crumbs.slice(0, index + 1).join(sep);
    return sep === "\\" ? (index === 0 ? `${joined}\\` : joined) : `/${joined}`;
  };

  return (
    <Modal open={open} title={title} onClose={onClose} footer={
      <>
        <span className="picker-selected" title={here}>{here ? <><Icon name="folderScan" size={14} /> {here}</> : "Open a drive to choose a folder"}</span>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-accent" disabled={!here || loading} onClick={() => onPick(here)}><Icon name="check" size={15} /> Use this folder</button>
      </>
    }>
      <form className="picker-path" onSubmit={submitTyped}>
        <button type="button" className="btn btn-ghost btn-sm btn-icon" disabled={listing?.parent === null || loading}
          onClick={() => listing && listing.parent !== null && go(listing.parent)} title="Up one level" aria-label="Up one level">
          <Icon name="arrowLeft" size={15} />
        </button>
        <div className="input-wrap flex-1">
          <Icon name="folderScan" size={15} />
          <input className="input input-sm" style={{ paddingLeft: 36 }} value={typed} onChange={(e) => setTyped(e.target.value)}
            placeholder="Type or paste a full path, e.g. D:\ElectionScans\Scanned" aria-label="Folder path" />
        </div>
        <button type="submit" className="btn btn-ghost btn-sm">Go</button>
      </form>

      <div className="picker-crumbs">
        <button className="picker-crumb" onClick={() => go("")}><Icon name="server" size={13} /> This PC</button>
        {crumbs.map((crumb, index) => (
          <span key={index} className="flex items-center">
            <Icon name="chevronRight" size={13} className="text-faint" />
            <button className="picker-crumb" onClick={() => go(crumbPath(index))}>{crumb}</button>
          </span>
        ))}
      </div>

      {listing && listing.shortcuts.length > 0 && (
        <div className="picker-shortcuts">
          {listing.shortcuts.map((s) => (
            <button key={s.path} className="picker-shortcut" onClick={() => go(s.path)} title={s.path}><Icon name="zap" size={12} /> {s.name}</button>
          ))}
        </div>
      )}

      {error && <div className="alert alert-error" style={{ marginBottom: 10 }}><Icon name="xCircle" size={16} /><div className="alert-body">{error}</div></div>}

      <div className={`picker-list ${loading ? "is-loading" : ""}`}>
        {listing && listing.folders.length === 0 && <div className="empty-inline"><Icon name="inbox" size={24} />No sub-folders here — you can use this folder.</div>}
        {listing?.folders.map((folder) => (
          <button key={folder.path} className="picker-item" onClick={() => go(folder.path)}>
            <span className="picker-item-icon"><Icon name={here ? "folderScan" : "server"} size={16} /></span>
            <span className="picker-item-name">{folder.name}</span>
            <Icon name="chevronRight" size={14} className="text-faint" />
          </button>
        ))}
      </div>
    </Modal>
  );
}
