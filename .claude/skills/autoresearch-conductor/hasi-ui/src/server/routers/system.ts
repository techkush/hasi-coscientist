import { z } from "zod";
import path from "node:path";
import fs from "node:fs/promises";
import { spawn } from "node:child_process";
import { router, procedure } from "../trpc";

const WORKSPACE = process.env.WORKSPACE_ROOT ?? "/home/node/.openclaw/workspace";

function projectRoot(slug: string) {
  const base = path.resolve(WORKSPACE);
  const root = path.resolve(base, slug);
  if (root !== base && !root.startsWith(base + path.sep)) {
    throw new Error("path escape");
  }
  return root;
}

interface TreeNode {
  name: string;
  path: string;
  type: "dir" | "file";
  children?: TreeNode[];
  bytes?: number;
}

const IGNORE = new Set([
  ".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache",
  ".pytest_cache", ".idea", ".vscode", "dist", "build", ".next", ".autoresearch",
]);

async function readTree(absRoot: string, rel = "", depth = 0): Promise<TreeNode[]> {
  if (depth > 6) return [];
  const dir = path.join(absRoot, rel);
  let entries;
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  entries.sort((a, b) => {
    if (a.isDirectory() !== b.isDirectory()) return a.isDirectory() ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  const out: TreeNode[] = [];
  for (const e of entries) {
    if (e.name.startsWith(".") && e.name !== ".autoresearch") continue;
    if (IGNORE.has(e.name)) continue;
    const childRel = path.join(rel, e.name);
    if (e.isDirectory()) {
      out.push({
        name: e.name,
        path: childRel,
        type: "dir",
        children: await readTree(absRoot, childRel, depth + 1),
      });
    } else {
      let bytes = 0;
      try { bytes = (await fs.stat(path.join(dir, e.name))).size; } catch {}
      out.push({ name: e.name, path: childRel, type: "file", bytes });
    }
  }
  return out;
}

const slug = z.object({ slug: z.string().min(1) });

export const systemRouter = router({
  tree: procedure.input(slug).query(async ({ input }) => {
    const root = projectRoot(input.slug);
    return readTree(root);
  }),

  readFile: procedure
    .input(slug.extend({ path: z.string().min(1) }))
    .query(async ({ input }) => {
      const root = projectRoot(input.slug);
      const safe = path.resolve(root, input.path);
      if (!safe.startsWith(root + path.sep)) throw new Error("path escape");
      try {
        const raw = await fs.readFile(safe, "utf8");
        return { ok: true as const, content: raw.slice(0, 400_000), truncated: raw.length > 400_000 };
      } catch (e) {
        return { ok: false as const, error: (e as Error).message };
      }
    }),

  /**
   * Best-effort launch of VS Code on the host. The `code` CLI must be on PATH.
   * On Docker hosts where the UI is in a container, this won't reach the host
   * desktop — there's no portable workaround, so we surface the failure.
   */
  openInVSCode: procedure.input(slug).mutation(async ({ input }) => {
    const root = projectRoot(input.slug);
    return new Promise<{ ok: boolean; error?: string }>((resolve) => {
      const child = spawn("code", [root], { detached: true, stdio: "ignore" });
      let settled = false;
      child.on("error", (err) => {
        if (settled) return;
        settled = true;
        resolve({ ok: false, error: err.message });
      });
      child.on("spawn", () => {
        if (settled) return;
        settled = true;
        child.unref();
        resolve({ ok: true });
      });
      setTimeout(() => {
        if (settled) return;
        settled = true;
        resolve({ ok: true });
      }, 800);
    });
  }),
});
