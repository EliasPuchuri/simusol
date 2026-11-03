import { useCallback, useEffect, useState } from "react";

import { api, type ComparisonReport } from "./api";
import { POLL_MS } from "./config";

const MAX_RETRIES = 4;

/** Loads the classification of a pair of periods, polls while it is being calculated and can start it. */
export function useComparison(previousId: string | null, currentId: string | null) {
  const [report, setReport] = useState<ComparisonReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const [failures, setFailures] = useState(0);

  const load = useCallback(async () => {
    if (!previousId || !currentId) return;
    try {
      setReport(await api.getComparison(previousId, currentId));
      setError(null);
      setFailures(0);
    } catch {
      setError("No se pudo consultar el estado de la comparación.");
      setFailures((n) => n + 1);
    }
  }, [previousId, currentId]);

  useEffect(() => {
    setReport(null);
    setError(null);
    setFailures(0);
    void load();
  }, [load]);

  // A transient failure of the first query must not leave the view empty: retry a few times.
  useEffect(() => {
    if (report || failures === 0 || failures > MAX_RETRIES) return;
    const timer = setTimeout(() => void load(), POLL_MS.comparison * failures);
    return () => clearTimeout(timer);
  }, [report, failures, load]);

  const running = report?.run?.state === "queued" || report?.run?.state === "running";
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => void load(), POLL_MS.comparison);
    return () => clearInterval(timer);
  }, [running, load]);

  async function start() {
    if (!previousId || !currentId) return;
    setStarting(true);
    setError(null);
    try {
      await api.startComparison(previousId, currentId);
      await load();
    } catch {
      setError("No se pudo iniciar el cálculo. Inténtalo de nuevo.");
    } finally {
      setStarting(false);
    }
  }

  const rows = report?.rows ?? [];
  const calculated = rows.some((r) => r.status === "ok" || r.status === "failed");
  const interrupted = report?.run?.state === "failed";
  return { report, rows, error, starting, running, calculated, interrupted, start };
}

export type Comparison = ReturnType<typeof useComparison>;
