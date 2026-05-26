/**
 * UI-side mirror of the project list. The Python conductor remains the source
 * of truth (per-project .autoresearch/conductor.json); this file lets the home
 * page render fast and lets the UI track its own per-project metadata (last
 * opened, pinned, etc.) without round-tripping. Refreshed by syncProjects().
 */

import fs from "node:fs/promises";
import path from "node:path";
import { conductor, type ProjectCard } from "./conductor";

const DB_DIR =
  process.env.HASI_DATABASE_DIR ??
  path.resolve(process.cwd(), "..", "..", "database");
const DB_FILE = path.join(DB_DIR, "projects.json");

export interface DbProject {
  slug: string;
  name: string;
  description: string;
  status: "pending" | "in_progress" | "looping" | "done";
  created: string;
  updated: string;
  loop_running?: boolean;
  done_count?: number;
}

interface DbShape {
  version: 1;
  projects: DbProject[];
}

async function readDb(): Promise<DbShape> {
  try {
    const raw = await fs.readFile(DB_FILE, "utf8");
    const parsed = JSON.parse(raw) as DbShape;
    if (!parsed.projects) return { version: 1, projects: [] };
    return parsed;
  } catch {
    return { version: 1, projects: [] };
  }
}

async function writeDb(db: DbShape) {
  await fs.mkdir(DB_DIR, { recursive: true });
  await fs.writeFile(DB_FILE, JSON.stringify(db, null, 2), "utf8");
}

function deriveStatus(c: ProjectCard): DbProject["status"] {
  if (c.loop_running) return "looping";
  if ((c.done_count ?? 0) > 0) return "in_progress";
  return "pending";
}

function nowIso() {
  return new Date().toISOString();
}

export async function syncProjects(): Promise<DbProject[]> {
  const live = await conductor.projects().catch(() => ({ projects: [] as ProjectCard[] }));
  const db = await readDb();
  const bySlug = new Map(db.projects.map((p) => [p.slug, p]));
  const next: DbProject[] = [];
  for (const card of live.projects) {
    const prev = bySlug.get(card.slug);
    next.push({
      slug: card.slug,
      name: card.name,
      description: card.description ?? prev?.description ?? "",
      status: deriveStatus(card),
      created: card.created ?? prev?.created ?? nowIso(),
      updated: card.updated ?? nowIso(),
      loop_running: !!card.loop_running,
      done_count: card.done_count ?? 0,
    });
  }
  await writeDb({ version: 1, projects: next });
  return next;
}

export async function listProjects(): Promise<DbProject[]> {
  const db = await readDb();
  if (db.projects.length === 0) return syncProjects();
  return db.projects;
}
