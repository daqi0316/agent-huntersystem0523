"use client";

import { useEffect, useRef, useState } from "react";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "ai-recruitment-token";

function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function useEventSource(endpoint: string | null) {
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const cleanupFnsRef = useRef<Array<() => void>>([]);

  useEffect(() => {
    if (!endpoint) return;

    const token = getStoredToken();
    const sep = endpoint.includes("?") ? "&" : "?";
    const url = token
      ? `${BASE_URL}${endpoint}${sep}token=${encodeURIComponent(token)}`
      : `${BASE_URL}${endpoint}`;
    const es = new EventSource(url);
    esRef.current = es;
    cleanupFnsRef.current = [];

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    return () => {
      es.close();
      esRef.current = null;
      setConnected(false);
      cleanupFnsRef.current.forEach((fn) => fn());
      cleanupFnsRef.current = [];
    };
  }, [endpoint]);

  function subscribe(event: string, handler: (data: unknown) => void) {
    const es = esRef.current;
    if (!es) {
      const noop = () => {};
      cleanupFnsRef.current.push(noop);
      return noop;
    }
    const wrapped = (e: MessageEvent) => {
      try {
        handler(JSON.parse(e.data));
      } catch {
        handler(e.data);
      }
    };
    es.addEventListener(event, wrapped);
    const unsubscribe = () => es.removeEventListener(event, wrapped);
    cleanupFnsRef.current.push(unsubscribe);
    return unsubscribe;
  }

  return { connected, subscribe };
}
