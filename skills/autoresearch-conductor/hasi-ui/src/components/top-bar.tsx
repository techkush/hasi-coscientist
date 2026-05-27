"use client";

import * as React from "react";
import Link from "next/link";
import { ChevronLeft, Sparkles, Wifi, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ThemeToggle } from "@/components/theme-toggle";
import { useWs } from "@/lib/ws";
import { cn } from "@/lib/utils";

interface Props {
  /** Optional sub-label rendered after the title (typically the project folder name). */
  scope?: string;
  /** When set, shows a back button that links to this href. */
  backHref?: string;
  backLabel?: string;
  right?: React.ReactNode;
}

export function TopBar({ scope, backHref, backLabel = "Projects", right }: Props) {
  const { connected } = useWs();

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur-md md:px-6">
      {backHref && (
        <Button asChild variant="ghost" size="sm" className="-ml-2">
          <Link href={backHref}>
            <ChevronLeft className="h-4 w-4" />
            {backLabel}
          </Link>
        </Button>
      )}

      <Link href="/" className="flex items-center gap-2 group">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground shadow-sm">
          <Sparkles className="h-4 w-4" />
        </div>
        <div className="hidden sm:flex flex-col leading-tight">
          <span className="text-[11px] font-semibold tracking-[0.18em] text-muted-foreground uppercase">
            HASI
          </span>
          <span className="text-xs text-muted-foreground -mt-0.5">
            Hybrid Autonomous Scientific Intelligence
          </span>
        </div>
      </Link>

      {scope && (
        <>
          <Separator orientation="vertical" className="mx-2 h-5" />
          <div className="flex items-center gap-1 text-sm">
            <span className="text-muted-foreground">/</span>
            <span className="font-medium truncate max-w-[16rem]">{scope}</span>
          </div>
        </>
      )}

      <div className="ml-auto flex items-center gap-2">
        {right}
        <div
          className={cn(
            "hidden md:flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-[11px]",
            connected ? "text-muted-foreground" : "text-destructive border-destructive/40"
          )}
          title={connected ? "Live updates connected" : "Reconnecting…"}
        >
          {connected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
          {connected ? "live" : "offline"}
        </div>
        <ThemeToggle />
      </div>
    </header>
  );
}
