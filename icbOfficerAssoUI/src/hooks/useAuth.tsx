"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { api, onUnauthorized } from "@/lib/api";

const STORAGE_KEY = "icb_auth";
const AUTH_EVENT = "icb-auth-changed";

interface AuthState {
  token: string | null;
  username: string | null;
  role: string | null;
}

interface AuthContextValue extends AuthState {
  /** true during server render / hydration, before localStorage can be read */
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const EMPTY: AuthState = { token: null, username: null, role: null };

// --- localStorage as an external store -------------------------------------
function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener(AUTH_EVENT, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(AUTH_EVENT, callback);
  };
}

function readStored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStored(value: AuthState | null) {
  try {
    if (value) localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private mode etc. – the session then only lives in memory */
  }
  window.dispatchEvent(new Event(AUTH_EVENT));
}

const noopSubscribe = () => () => {};

export function AuthProvider({ children }: { children: ReactNode }) {
  // false on the server and during hydration, true afterwards
  const hydrated = useSyncExternalStore(noopSubscribe, () => true, () => false);
  const raw = useSyncExternalStore(subscribe, readStored, () => null);

  const auth = useMemo<AuthState>(() => {
    if (!raw) return EMPTY;
    try {
      const parsed = JSON.parse(raw) as Partial<AuthState>;
      return parsed.token ? { token: parsed.token, username: parsed.username ?? null, role: parsed.role ?? null } : EMPTY;
    } catch {
      return EMPTY;
    }
  }, [raw]);

  const logout = useCallback(() => writeStored(null), []);

  // Expired / invalid token anywhere in the app -> back to login
  useEffect(() => {
    onUnauthorized(logout);
    return () => onUnauthorized(null);
  }, [logout]);

  const login = useCallback(async (username: string, password: string) => {
    const response = await api.auth.login(username, password);
    writeStored({ token: response.access_token, username: response.username, role: response.role });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ ...auth, isLoading: !hydrated, isAuthenticated: Boolean(auth.token), login, logout }),
    [auth, hydrated, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
