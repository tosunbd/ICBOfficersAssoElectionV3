import type { Metadata } from "next";
import { LiveScreen } from "@/components/live/LiveScreen";
import { AuthProvider } from "@/hooks/useAuth";

export const metadata: Metadata = {
  title: "Live Results · ICB Officers' Association Election",
};

/** Public live counting screen (projector / TV); only PAUSE / START needs a committee login. */
export default function DashboardPage() {
  return (
    <AuthProvider>
      <LiveScreen />
    </AuthProvider>
  );
}
