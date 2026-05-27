"use client";

import * as React from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { trpc } from "@/lib/trpc";

/**
 * Shows a loud warning when the Python conductor REST API can't be reached.
 * Without this, mutations like "create project" silently fail because the UI
 * just sees a 502 from the tRPC handler and the user can't tell whether
 * anything is wrong with their stack vs. just slow.
 */
export function ConductorHealthBanner() {
  const q = trpc.health.conductor.useQuery(undefined, {
    refetchInterval: 5000,
    retry: false,
  });
  if (q.isLoading || !q.data || q.data.ok) return null;

  return (
    <div className="border-b border-destructive/40 bg-destructive/10 px-4 py-2 md:px-6">
      <div className="mx-auto flex max-w-7xl items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 text-destructive shrink-0" />
        <div className="text-xs leading-relaxed">
          <div className="font-medium text-destructive">
            Conductor unreachable at {q.data.url}
          </div>
          <p className="text-foreground/80 mt-0.5">
            {q.data.reason}. Until this is reachable, nothing will be passed to the Claude agent — new-project requests will fail silently.
          </p>
          <p className="text-foreground/70 mt-1">
            Likely causes:
          </p>
          <ul className="ml-4 list-disc text-foreground/70">
            <li><code>conductor_server.py</code> not running</li>
            <li>Server is bound to <code>127.0.0.1</code> inside the container — pass <code>--bind 0.0.0.0</code> (or set <code>AUTORESEARCH_BIND=0.0.0.0</code>) so Docker port-forwarding works</li>
            <li>Container port 8780 not published (check <code>docker-compose.extra.yml</code>)</li>
            <li><code>CONDUCTOR_URL</code> in <code>.env.local</code> points to the wrong host</li>
          </ul>
        </div>
        <Button
          size="sm"
          variant="outline"
          className="ml-auto h-7 gap-1 text-[11px] shrink-0"
          onClick={() => q.refetch()}
        >
          <RefreshCw className="h-3 w-3" />
          Retry
        </Button>
      </div>
    </div>
  );
}
