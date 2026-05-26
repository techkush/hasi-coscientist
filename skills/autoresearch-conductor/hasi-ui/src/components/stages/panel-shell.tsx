"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface Props {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function PanelShell({ title, subtitle, actions, children, className }: Props) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-3 border-b border-border px-5 py-3 bg-card/30">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold leading-tight">{title}</h2>
          {subtitle && (
            <p className="text-[11px] text-muted-foreground truncate mt-0.5">{subtitle}</p>
          )}
        </div>
        <div className="ml-auto flex items-center gap-2">{actions}</div>
      </div>
      <div className={cn("flex-1 min-h-0 overflow-hidden", className)}>{children}</div>
    </div>
  );
}
