"use client";

import * as React from "react";

export type WsEvent =
  | { ch: "hello"; data: { ok: true; poll_ms: number } }
  | { ch: "task"; data: unknown }
  | { ch: "project"; slug: string; data: unknown }
  | { ch: "run"; slug: string; data: unknown }
  | { ch: "manifest"; slug: string; data: unknown }
  | { ch: "files"; slug: string; data: { changed: string[] } }
  | { ch: "results"; slug: string; data: { rows: number } };

type Listener = (e: WsEvent) => void;

interface Ctx {
  send: (msg: { op: "subscribe" | "unsubscribe"; slug?: string }) => void;
  subscribe: (listener: Listener) => () => void;
  connected: boolean;
}

const WsContext = React.createContext<Ctx | null>(null);

export function WSProvider({ children }: { children: React.ReactNode }) {
  const wsRef = React.useRef<WebSocket | null>(null);
  const listenersRef = React.useRef<Set<Listener>>(new Set());
  const sendQueueRef = React.useRef<string[]>([]);
  const [connected, setConnected] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    let retry = 0;

    function open() {
      if (cancelled) return;
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const url = `${proto}://${window.location.host}/ws`;
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = () => {
        if (cancelled) { ws.close(); return; }
        retry = 0;
        setConnected(true);
        for (const m of sendQueueRef.current) ws.send(m);
        sendQueueRef.current = [];
      };
      ws.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data) as WsEvent;
          for (const l of listenersRef.current) l(ev);
        } catch { /* ignore */ }
      };
      ws.onerror = () => { /* close handles reconnect */ };
      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        if (cancelled) return;
        retry = Math.min(retry + 1, 6);
        setTimeout(open, 250 * 2 ** retry);
      };
    }
    open();
    return () => {
      cancelled = true;
      wsRef.current?.close();
    };
  }, []);

  const send: Ctx["send"] = React.useCallback((msg) => {
    const raw = JSON.stringify(msg);
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(raw);
    } else {
      sendQueueRef.current.push(raw);
    }
  }, []);

  const subscribe: Ctx["subscribe"] = React.useCallback((listener) => {
    listenersRef.current.add(listener);
    return () => { listenersRef.current.delete(listener); };
  }, []);

  return (
    <WsContext.Provider value={{ send, subscribe, connected }}>
      {children}
    </WsContext.Provider>
  );
}

export function useWs() {
  const ctx = React.useContext(WsContext);
  if (!ctx) throw new Error("useWs must be used inside <WSProvider>");
  return ctx;
}

/** Subscribe to a specific channel for a (optional) slug and run a callback. */
export function useWsChannel<T = unknown>(
  ch: WsEvent["ch"],
  slug: string | undefined,
  cb: (data: T) => void
) {
  const { subscribe, send } = useWs();
  const cbRef = React.useRef(cb);
  React.useEffect(() => { cbRef.current = cb; }, [cb]);
  React.useEffect(() => {
    if (slug) send({ op: "subscribe", slug });
    const off = subscribe((ev) => {
      if (ev.ch !== ch) return;
      if ("slug" in ev && slug && ev.slug !== slug) return;
      cbRef.current(ev.data as T);
    });
    return () => {
      off();
      if (slug) send({ op: "unsubscribe", slug });
    };
  }, [ch, slug, subscribe, send]);
}
