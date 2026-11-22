"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { Election } from "@/lib/types";

const STORAGE_KEY = "icb_selected_election";

interface ElectionContextValue {
  elections: Election[];
  election: Election | null;
  loading: boolean;
  selectElection: (id: number) => void;
  refresh: () => Promise<void>;
  /** Merge changed fields into the selected election (optimistic UI). */
  patch: (changes: Partial<Election>) => void;
}

const ElectionContext = createContext<ElectionContextValue | null>(null);

/** Keeps "which election is the admin working on" in one place. */
export function ElectionProvider({ children }: { children: ReactNode }) {
  const [elections, setElections] = useState<Election[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const list = await api.elections.list();
      setElections(list);
      setSelectedId((current) => {
        if (current && list.some((e) => e.id === current)) return current;
        let stored: number | null = null;
        try {
          stored = Number(localStorage.getItem(STORAGE_KEY)) || null;
        } catch {
          /* ignore */
        }
        if (stored && list.some((e) => e.id === stored)) return stored;
        return list.find((e) => e.status === "active")?.id ?? list[0]?.id ?? null;
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh().catch(console.error);
  }, [refresh]);

  const selectElection = useCallback((id: number) => {
    setSelectedId(id);
    try {
      localStorage.setItem(STORAGE_KEY, String(id));
    } catch {
      /* ignore */
    }
  }, []);

  const patch = useCallback((changes: Partial<Election>) => {
    setElections((list) => list.map((e) => (e.id === selectedId ? { ...e, ...changes } : e)));
  }, [selectedId]);

  const value = useMemo<ElectionContextValue>(() => ({
    elections,
    election: elections.find((e) => e.id === selectedId) ?? null,
    loading,
    selectElection,
    refresh,
    patch,
  }), [elections, selectedId, loading, selectElection, refresh, patch]);

  return <ElectionContext.Provider value={value}>{children}</ElectionContext.Provider>;
}

export function useElection(): ElectionContextValue {
  const context = useContext(ElectionContext);
  if (!context) throw new Error("useElection must be used within an ElectionProvider");
  return context;
}
