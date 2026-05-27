import { z } from "zod";
import path from "node:path";
import fs from "node:fs/promises";
import { router, procedure, withConductor } from "../trpc";
import { conductor } from "../conductor";

const slug = z.object({ slug: z.string().min(1) });
const WORKSPACE = process.env.WORKSPACE_ROOT ?? "/home/node/.openclaw/workspace";

/**
 * Count the rows in results.tsv where status==="keep". The user requirement
 * is that Analyze should refuse to generate a report unless there are at
 * least 2 kept results. We compute this from disk rather than the conductor
 * to short-circuit the request (no model call wasted on a no-op).
 */
async function countKept(projectSlug: string) {
  const tsv = path.join(WORKSPACE, projectSlug, "results.tsv");
  let raw = "";
  try {
    raw = await fs.readFile(tsv, "utf8");
  } catch {
    return 0;
  }
  const lines = raw.split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return 0;
  const header = lines[0].split("\t").map((h) => h.trim().toLowerCase());
  const statusIdx = header.findIndex((h) => h === "status" || h === "decision");
  if (statusIdx < 0) return 0;
  let kept = 0;
  for (let i = 1; i < lines.length; i++) {
    const cells = lines[i].split("\t");
    if ((cells[statusIdx] ?? "").trim().toLowerCase() === "keep") kept += 1;
  }
  return kept;
}

export const analyzeRouter = router({
  summary: procedure.input(slug).query(({ input }) =>
    withConductor(() => conductor.analyzeSummary(input.slug))),
  reportUrl: procedure.input(slug).query(({ input }) => {
    const base = process.env.CONDUCTOR_URL ?? "http://127.0.0.1:8780";
    return `${base}/api/report?slug=${encodeURIComponent(input.slug)}`;
  }),
  keptCount: procedure.input(slug).query(({ input }) => countKept(input.slug)),
  execute: procedure.input(slug).mutation(async ({ input }) => {
    const kept = await countKept(input.slug);
    if (kept < 2) {
      return { ok: false, kept, reason: "need-at-least-2-keeps" as const };
    }
    await withConductor(() => conductor.analyzeExecute(input.slug));
    return { ok: true, kept };
  }),
});
