import { useCallback, useEffect, useRef, useState } from "react";

import { errorText } from "../services/api";

export type AsyncState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

/**
 * Load data when ``key`` changes, cancel the previous request, and keep stale data visible while
 * a refresh is running. ``key = null`` means "nothing to load yet".
 */
export function useAsync<T>(
  load: ((signal: AbortSignal) => Promise<T>) | null,
  key: string | null,
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(key !== null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    const run = loadRef.current;
    if (key === null || run === null) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    run(controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setData(value);
        setLoading(false);
      })
      .catch((failure: unknown) => {
        if (controller.signal.aborted) return;
        setError(errorText(failure) || "The request failed.");
        setLoading(false);
      });
    return () => controller.abort();
  }, [key, tick]);

  const reload = useCallback(() => setTick((value) => value + 1), []);
  return { data, loading, error, reload };
}

/** Run a user-triggered mutation once at a time and expose its outcome. */
export function useAction<A extends unknown[], R>(action: (...args: A) => Promise<R>) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<R | null>(null);
  const busy = useRef(false);

  const run = useCallback(
    async (...args: A): Promise<R | null> => {
      if (busy.current) return null;
      busy.current = true;
      setRunning(true);
      setError(null);
      try {
        const value = await action(...args);
        setResult(value);
        return value;
      } catch (failure) {
        setError(errorText(failure) || "The request failed.");
        return null;
      } finally {
        busy.current = false;
        setRunning(false);
      }
    },
    [action],
  );

  const clear = useCallback(() => {
    setError(null);
    setResult(null);
  }, []);

  return { running, error, result, run, clear };
}
