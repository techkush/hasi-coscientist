/**
 * Custom Next.js server that also hosts the WebSocket gateway on /ws.
 * Run as `tsx server.ts` (dev or prod). The bin scripts shell into this.
 */

import http from "node:http";
import next from "next";
import { parse } from "node:url";
import { attachWebSocket } from "./src/server/ws/gateway";

const dev = process.env.NODE_ENV !== "production";
const port = Number(process.env.PORT ?? 3000);
const hostname = process.env.HOST ?? "127.0.0.1";

const app = next({ dev, hostname, port });
const handle = app.getRequestHandler();

async function main() {
  await app.prepare();
  const server = http.createServer((req, res) => {
    handle(req, res, parse(req.url ?? "/", true)).catch((err) => {
      console.error("[next handler]", err);
      if (!res.headersSent) {
        res.statusCode = 500;
        res.end("internal error");
      }
    });
  });
  attachWebSocket(server);
  server.listen(port, hostname, () => {
    console.log(`▲ HASI dashboard ready on http://${hostname}:${port}`);
    console.log(`  WebSocket on ws://${hostname}:${port}/ws`);
    console.log(`  Conductor: ${process.env.CONDUCTOR_URL ?? "http://127.0.0.1:8780"}`);
  });
}

main().catch((err) => {
  console.error("[server] failed to start", err);
  process.exit(1);
});
