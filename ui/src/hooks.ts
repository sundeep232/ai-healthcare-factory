import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

export interface Loaded<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => Promise<void>;
  set: (value: T) => void;
}

/**
 * Load data and optionally keep refreshing it while ``poll(data)`` returns true
 * (used while a background stage is running). A failed refresh keeps the last data.
 */
export function useLoad<T>(
  load: () => Promise<T>,
  deps: unknown[],
  poll?: (data: T) => boolean,
  intervalMs = 3000,
): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);
  loadRef.current = load;

  const reload = useCallback(async () => {
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    setLoading(true);
    void reload();
  }, [reload]);

  const shouldPoll = data !== null && !!poll?.(data);
  useEffect(() => {
    if (!shouldPoll) return;
    const id = setInterval(() => void reload(), intervalMs);
    return () => clearInterval(id);
  }, [shouldPoll, reload, intervalMs]);

  return { data, error, loading, reload, set: setData };
}
