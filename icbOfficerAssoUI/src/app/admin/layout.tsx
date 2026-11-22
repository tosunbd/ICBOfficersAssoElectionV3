"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { AuthProvider } from "@/hooks/useAuth";
import { ElectionProvider } from "@/hooks/useElection";
import { ToastProvider } from "@/components/ui/Toast";
import { AdminShell } from "@/components/admin/AdminShell";

export default function AdminLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isLogin = pathname === "/admin/login";
  return (
    <AuthProvider>
      <ToastProvider>
        {isLogin ? children : (
          <ElectionProvider>
            <AdminShell>{children}</AdminShell>
          </ElectionProvider>
        )}
      </ToastProvider>
    </AuthProvider>
  );
}
