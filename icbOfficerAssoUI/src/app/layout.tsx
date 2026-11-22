import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./live.css";
import { ThemeProvider, THEME_INIT_SCRIPT } from "@/hooks/useTheme";
import { Aurora } from "@/components/ui/Motion";
import { withBase } from "@/lib/basePath";

export const metadata: Metadata = {
  title: "ICB Officers' Association Election System",
  description: "Live vote counting and results dashboard for the ICB Officers' Association Executive Council Election",
  icons: { icon: withBase("/favicon.svg") },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#05080f" },
    { media: "(prefers-color-scheme: light)", color: "#f5f3ee" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // suppressHydrationWarning: the inline script below sets data-theme before
    // React hydrates, so the server-rendered attribute may legitimately differ.
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        {/* Apply the saved / system theme before first paint to avoid a flash. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        {/* Fonts are loaded at runtime so the build works on machines without internet;
            the CSS font stack falls back to system fonts when offline. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font -- app router: loaded once in the root layout */}
        <link
          href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=JetBrains+Mono:wght@500;600;700&family=Noto+Sans+Bengali:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <Aurora />
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
