"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

type ToastType = "success" | "error" | "info";
interface Toast { id: number; message: string; type: ToastType; leaving?: boolean }

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
  success: (message: string) => void;
  error: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const DURATION = 4500;
const ICONS: Record<ToastType, IconName> = { success: "checkCircle", error: "xCircle", info: "info" };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((list) => list.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 260);
  }, []);

  const toast = useCallback((message: string, type: ToastType = "info") => {
    const id = Date.now() + Math.random();
    setToasts((list) => [...list.slice(-3), { id, message, type }]);
    setTimeout(() => dismiss(id), DURATION);
  }, [dismiss]);

  const value = useMemo<ToastContextValue>(() => ({
    toast,
    success: (message) => toast(message, "success"),
    error: (message) => toast(message, "error"),
  }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type} ${t.leaving ? "leaving" : ""}`} role={t.type === "error" ? "alert" : "status"}>
            <span className="toast-icon"><Icon name={ICONS[t.type]} size={17} /></span>
            <span className="toast-message">{t.message}</span>
            <button className="toast-close" onClick={() => dismiss(t.id)} aria-label="Dismiss"><Icon name="x" size={15} /></button>
            <span className="toast-progress" style={{ animationDuration: `${DURATION}ms` }} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within a ToastProvider");
  return context;
}
