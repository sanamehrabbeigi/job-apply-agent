import { useEffect, useRef } from "react";
import type { AppEvent } from "../types";

/** Subscribe to the backend's server-sent events for the lifetime of the component. */
export function useEvents(onEvent: (event: AppEvent) => void): void {
  const handler = useRef(onEvent);
  handler.current = onEvent;
  useEffect(() => {
    const source = new EventSource("/api/events");
    source.onmessage = (message) => {
      try {
        handler.current(JSON.parse(message.data) as AppEvent);
      } catch {
        // ignore malformed events
      }
    };
    return () => source.close();
  }, []);
}
