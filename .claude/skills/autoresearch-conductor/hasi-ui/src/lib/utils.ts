import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function slugify(input: string) {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

export function formatTimeAgo(iso?: string) {
  if (!iso) return "";
  const date = new Date(iso.replace(" ", "T"));
  const diff = Date.now() - date.getTime();
  if (Number.isNaN(diff)) return iso;
  const s = Math.round(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}

export function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

/** "needs scaffold" → "Needs Scaffold". Used to clean lowercase status strings
 * coming from the Python conductor (stage_status returns "done", "pending", etc). */
export function titleCase(s?: string | null) {
  if (!s) return "";
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
}
