"use client";

import { useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { Icon } from "@/components/ui/Icon";

/**
 * PAUSE / START button of the live screen.  The election commission pauses
 * the count for a break: no ballot is read (files wait in the Scanned folder)
 * until START.  Only a committee login may press it; on a screen that is not
 * signed in, the button asks for the login first.
 */
export function CountingControl({ electionId, paused, onChanged }: {
  electionId: number; paused: boolean; onChanged?: (paused: boolean) => void;
}) {
  const { token, isAuthenticated, login, logout } = useAuth();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = async (useToken: string | null) => {
    if (!useToken) {
      setAsking(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.admin.pauseCounting(useToken, electionId, !paused);
      onChanged?.(!paused);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();  // the session has expired: sign in again
        setAsking(true);
      } else {
        setError(err instanceof Error ? err.message : "Could not change the count.");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        className={`live-count-toggle ${paused ? "is-paused" : ""}`}
        onClick={() => toggle(isAuthenticated ? token : null)}
        disabled={busy}
        title={paused ? "Start counting again" : "Pause the count (break)"}
      >
        <Icon name={paused ? "play" : "pause"} size={14} strokeWidth={2.4} />
        {busy ? "…" : paused ? "START" : "PAUSE"}
        {!isAuthenticated && <Icon name="lock" size={11} />}
      </button>
      {error && <span className="live-count-error" role="alert">{error}</span>}
      {asking && (
        <CommitteeLogin
          action={paused ? "start the count again" : "pause the count"}
          onCancel={() => setAsking(false)}
          onLogin={async (username, password) => {
            await login(username, password);
            setAsking(false);
            const stored = readToken();
            if (stored) await toggle(stored);
          }}
        />
      )}
    </>
  );
}

// login() stores the session; read it straight back so the click can go ahead at once
function readToken(): string | null {
  try {
    return (JSON.parse(localStorage.getItem("icb_auth") ?? "null") as { token?: string } | null)?.token ?? null;
  } catch {
    return null;
  }
}

function CommitteeLogin({ action, onCancel, onLogin }: {
  action: string; onCancel: () => void; onLogin: (username: string, password: string) => Promise<void>;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onLogin(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
      setBusy(false);
    }
  };

  // on <body>: the live header is transformed, which would trap a fixed overlay inside it
  return createPortal(
    <div className="modal-backdrop" onClick={onCancel}>
      <form className="modal live-count-login" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="modal-header">
          <h4><Icon name="lock" size={16} /> Election commission</h4>
          <button type="button" className="live-fullscreen" onClick={onCancel} aria-label="Close"><Icon name="x" size={13} /></button>
        </div>
        <div className="modal-body" style={{ display: "grid", gap: 14 }}>
          <p className="input-hint" style={{ fontSize: "0.86rem" }}>Sign in with a committee account to {action}.</p>
          <div className="input-group">
            <label className="input-label" htmlFor="count-user">Username</label>
            <input id="count-user" className="input" autoComplete="username" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor="count-pass">Password</label>
            <input id="count-pass" type="password" className="input" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && <div className="alert alert-error">{error}</div>}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={busy || !username || !password}>{busy ? "Signing in…" : "Sign in"}</button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
