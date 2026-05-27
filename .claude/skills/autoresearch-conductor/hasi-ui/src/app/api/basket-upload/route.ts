import { NextRequest, NextResponse } from "next/server";

const CONDUCTOR_URL = process.env.CONDUCTOR_URL ?? "http://127.0.0.1:8780";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const form = await req.formData();
  const slug = String(form.get("slug") ?? "").trim();
  const file = form.get("file");
  if (!slug || !(file instanceof File) || !file.name) {
    return NextResponse.json({ error: "slug and file are required" }, { status: 400 });
  }
  const buf = Buffer.from(await file.arrayBuffer());
  const url = new URL("/api/ideas/upload", CONDUCTOR_URL);
  url.searchParams.set("slug", slug);
  url.searchParams.set("name", file.name);

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: buf,
  });
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json" },
  });
}
