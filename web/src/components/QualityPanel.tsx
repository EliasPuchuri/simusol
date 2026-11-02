import { useCallback, useEffect, useState } from "react";

import { api, type QcReport, type QcResult } from "../api";
import { POLL_MS } from "../config";
import { describeProblem, describeQcError, formatBytes, plural } from "../format";

type Props = { datasetId: string; refreshKey: number };

const STATUS: Record<QcResult["status"], string> = {
  ok: "Sin observaciones",
  with_issues: "Con observaciones",
  failed: "No se pudo revisar",
  pending: "Pendiente",
};

function volumeText(r: QcResult): string | null {
  if (r.status === "failed" || r.status === "pending") return null;
  const value = r.volume_m3?.value;
  return value == null ? "Volumen: no confirmado" : `Volumen: ${Math.round(value).toLocaleString("es-PE")} m³`;
}

export function QualityPanel({ datasetId, refreshKey }: Props) {
  const [report, setReport] = useState<QcReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const load = useCallback(async () => {
    try {
      setReport(await api.getQc(datasetId));
      setError(null);
    } catch {
      setError("No se pudo consultar el estado de la revisión.");
    }
  }, [datasetId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const running = report?.run?.state === "queued" || report?.run?.state === "running";
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => void load(), POLL_MS.qc);
    return () => clearInterval(timer);
  }, [running, load]);

  async function start() {
    setStarting(true);
    setError(null);
    try {
      await api.startQc(datasetId);
      await load();
    } catch {
      setError("No se pudo iniciar la revisión. Inténtalo de nuevo.");
    } finally {
      setStarting(false);
    }
  }

  if (!report) return error ? <p role="alert" className="alert alert-error">{error}</p> : null;

  const { summary, results, run } = report;
  const reviewed = summary.ok + summary.with_issues + summary.failed;
  const inverted = results.filter((r) => r.problems.includes("inverted_orientation")).length;
  const interrupted = run?.state === "failed";

  return (
    <section className="quality" aria-labelledby={`q-${datasetId}`}>
      <h3 id={`q-${datasetId}`}>Calidad de las mallas</h3>

      {running && run && (
        <div role="status" aria-live="polite" className="progress">
          <progress max={run.total} value={run.done} />
          <span>Revisando las mallas: {run.done} de {run.total} listas…</span>
        </div>
      )}

      {!running && reviewed === 0 && !interrupted && (
        <p className="note">Todavía no se revisó la calidad de las mallas. La revisión detecta problemas (huecos, cruces, orientación) sin modificar ningún archivo.</p>
      )}

      {interrupted && <p role="alert" className="alert alert-warn">La revisión se interrumpió antes de terminar. Puedes volver a iniciarla: lo ya revisado no se repite.</p>}

      {reviewed > 0 && !running && (
        <>
          <p className="count">
            <strong>{plural(reviewed, "sólido revisado", "sólidos revisados")}</strong>: {summary.ok} sin observaciones, {summary.with_issues} con observaciones
            {summary.failed > 0 && <>, {summary.failed} no se pudo revisar</>}
            {summary.pending > 0 && <>, {summary.pending} sin revisar</>}.
          </p>
          {inverted > 0 && (
            <p className="alert alert-warn">
              {inverted === 1 ? "1 sólido tiene" : `${inverted} sólidos tienen`} la orientación invertida: su volumen no se puede confirmar todavía. Es un tema a revisar con el área; los sólidos igualmente se pueden ver y comparar por nombre.
            </p>
          )}
          <details className="files">
            <summary>Ver detalle por sólido</summary>
            <div className="table-wrap">
              <table aria-label="Calidad por sólido">
                <thead><tr><th>Sólido</th><th>Estado</th><th>Observaciones</th></tr></thead>
                <tbody>
                  {results.map((r) => (
                    <tr key={r.filename}>
                      <td>{r.filename}<br /><small>{formatBytes(r.size_bytes)}</small></td>
                      <td><span className={`pill pill-qc-${r.status}`}>{STATUS[r.status]}</span></td>
                      <td>
                        {r.status === "failed" ? <p>{describeQcError(r.error)}</p> : (
                          <>
                            {r.problems.length > 0 && <ul>{r.problems.map((p) => <li key={p}>{describeProblem(p, r)}</li>)}</ul>}
                            {volumeText(r) && <p><small>{volumeText(r)}</small></p>}
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          <p><a className="button" href={api.qcCsvUrl(datasetId)} download>Descargar reporte (CSV)</a></p>
        </>
      )}

      {error && <p role="alert" className="alert alert-error">{error}</p>}

      {!running && (
        <button type="button" disabled={starting} onClick={start} className={reviewed === 0 && !interrupted ? "primary" : undefined}>
          {interrupted ? "Reintentar la revisión" : reviewed === 0 ? "Revisar calidad de las mallas" : "Volver a revisar"}
        </button>
      )}
    </section>
  );
}
