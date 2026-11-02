import { useCallback, useEffect, useState } from "react";

import { api, type CharReport } from "../api";
import { POLL_MS } from "../config";
import { bodyTypeLabel, describeOrientation, describeReference, formatBytes, plural } from "../format";

type Props = { datasetId: string; refreshKey: number };

const deg = (v: number) => `${v.toLocaleString("es-PE", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}°`;

export function CharacterizationPanel({ datasetId, refreshKey }: Props) {
  const [report, setReport] = useState<CharReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const load = useCallback(async () => {
    try {
      setReport(await api.getCharacterization(datasetId));
      setError(null);
    } catch {
      setError("No se pudo consultar el estado del cálculo.");
    }
  }, [datasetId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const running = report?.run?.state === "queued" || report?.run?.state === "running";
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => void load(), POLL_MS.characterization);
    return () => clearInterval(timer);
  }, [running, load]);

  async function start() {
    setStarting(true);
    setError(null);
    try {
      await api.startCharacterization(datasetId);
      await load();
    } catch {
      setError("No se pudo iniciar el cálculo. Inténtalo de nuevo.");
    } finally {
      setStarting(false);
    }
  }

  if (!report) return error ? <p role="alert" className="alert alert-error">{error}</p> : null;

  const { summary, results, run } = report;
  const done = summary.ok + summary.failed;
  const interrupted = run?.state === "failed";
  const counts = { TABULAR: 0, "TABULAR CURVO": 0, GLOBULAR: 0 } as Record<string, number>;
  results.forEach((r) => r.body_type && (counts[r.body_type] = (counts[r.body_type] ?? 0) + 1));

  const compared = results.filter((r) => r.reference?.comparison.comparable);
  const withReference = results.filter((r) => r.reference);
  const maxAz = Math.max(0, ...compared.map((r) => (r.reference!.comparison as { delta_azimuth_deg: number | null }).delta_azimuth_deg ?? 0));
  const maxDip = Math.max(0, ...compared.map((r) => (r.reference!.comparison as { delta_dip_deg: number | null }).delta_dip_deg ?? 0));

  return (
    <section className="quality" aria-labelledby={`c-${datasetId}`}>
      <h3 id={`c-${datasetId}`}>Tipo de cuerpo y orientación</h3>

      {running && run && (
        <div role="status" aria-live="polite" className="progress">
          <progress max={run.total} value={run.done} />
          <span>Calculando: {run.done} de {run.total} listos…</span>
        </div>
      )}

      {!running && done === 0 && !interrupted && (
        <p className="note">Todavía no se calculó el tipo de cuerpo ni su orientación (Azimuth y Dip) de este periodo.</p>
      )}
      {interrupted && <p role="alert" className="alert alert-warn">El cálculo se interrumpió antes de terminar. Puedes volver a iniciarlo: lo ya calculado no se repite.</p>}

      {done > 0 && !running && (
        <>
          <p className="count">
            <strong>{plural(summary.ok, "sólido caracterizado", "sólidos caracterizados")}</strong>:{" "}
            {plural(counts.TABULAR, "tabular", "tabulares")}, {plural(counts["TABULAR CURVO"], "tabular curvo", "tabulares curvos")},{" "}
            {plural(counts.GLOBULAR, "globular", "globulares")}
            {summary.failed > 0 && <>; {summary.failed} no se pudo calcular</>}
            {summary.pending > 0 && <>; {summary.pending} sin calcular</>}.
          </p>
          {withReference.length > 0 && (
            <p className={compared.length > 0 ? "alert alert-ok" : "note"}>
              {compared.length} de {plural(withReference.length, "sólido comparable", "sólidos comparables")} con la referencia
              {compared.length > 0 && <>: diferencia máxima de {deg(maxAz)} en azimuth y de {deg(maxDip)} en dip</>}.
            </p>
          )}
          <p className="note">Los umbrales para decidir el tipo de cuerpo son provisionales y se calibrarán con el área. La orientación es la global de cada sólido.</p>
          <details className="files">
            <summary>Ver detalle por sólido</summary>
            <div className="table-wrap">
              <table aria-label="Tipo y orientación por sólido">
                <thead><tr><th>Sólido</th><th>Tipo</th><th>Orientación</th><th>Referencia</th></tr></thead>
                <tbody>
                  {results.map((r) => (
                    <tr key={r.filename}>
                      <td>{r.filename}<br /><small>{formatBytes(r.size_bytes)}</small></td>
                      <td>{r.status === "ok" ? bodyTypeLabel(r.body_type) : r.status === "failed" ? "No se pudo calcular" : "Pendiente"}</td>
                      <td>{r.status === "ok" ? describeOrientation(r.orientation) : "—"}</td>
                      <td>{r.reference ? describeReference(r.reference) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          <p><a className="button" href={api.characterizationCsvUrl(datasetId)} download>Descargar reporte de orientación (CSV)</a></p>
        </>
      )}

      {error && <p role="alert" className="alert alert-error">{error}</p>}

      {!running && (
        <button type="button" disabled={starting} onClick={start} className={done === 0 && !interrupted ? "primary" : undefined}>
          {interrupted ? "Reintentar el cálculo" : done === 0 ? "Calcular tipo y orientación" : "Volver a calcular"}
        </button>
      )}
    </section>
  );
}
