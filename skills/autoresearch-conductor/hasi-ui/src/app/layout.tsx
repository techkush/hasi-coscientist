import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { TRPCProvider } from "@/components/trpc-provider";
import { WSProvider } from "@/lib/ws";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "sonner";
import { ConductorHealthBanner } from "@/components/conductor-health-banner";

export const metadata: Metadata = {
  title: "HASI — Hybrid Autonomous Scientific Intelligence",
  description: "Dashboard for the autoresearch pipeline.",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background text-foreground antialiased font-sans">
        <ThemeProvider>
          <TRPCProvider>
            <WSProvider>
              <TooltipProvider delayDuration={250}>
                <ConductorHealthBanner />
                {children}
                <Toaster position="bottom-right" richColors closeButton />
              </TooltipProvider>
            </WSProvider>
          </TRPCProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
