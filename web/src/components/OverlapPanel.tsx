import { useCallback, useEffect, useState } from "react";

import { api, type OverlapReport } from "../api";
import { POLL_MS } from "../config";
import { exclusionText, volumeShort } from "../dashboard";
import { plural } from "../format";

type Props = { datasetId: string; refreshKey: number };

const pct = (v: number | null) => (v == null ? "—" : v < 0.01 ? "< 0.01 %" : `${v.toFixed(2)} %`);

/** Which solids of one period share volume (RF-58). Optional: the page works without it, so a failed query stays silent. */
export function OverlapPanel({ datasetId, refreshKey }: Props) {
  const [report, setReport] = useState<OverlapReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const load = useCallback(async () => {
    try {
      setReport(await api.getOverlaps(datasetId));
    } catch {
      /* optional panel */
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
      await api.startOverlaps(datasetId);
      await load();
    } catch {
      setError("No se pudo iniciar la búsqueda. Inténtalo de nuevo.");
    } finally {
      setStarting(false);
    }
  }

  if (!report) return null;
  const s = report.summary;
  const done = report.evaluated && !running;
  const interrupted = report.run?.state === "failed";
  const issues = s.not_evaluable + s.failed + s.unreadable.length;

  return (
    <section className="quality overlaps" aria-labelledby={`ov-${datasetId}`}>
      <h3 id={`ov-${datasetId}`}>Superposición entre sólidos</h3>
      {!report.evaluated && !running && (
        <p className="note">Todavía no se buscó si algún sólido de este periodo ocupa el mismo espacio que otro. Si pasa, el volumen total cuenta ese espacio dos veces.</p>
      )}
      {running && report.run && (
        <div role="status" aria-live="polite" className="progress">
          <progress max={report.run.total} value={report.run.done} />
          <span>Buscando: {report.run.done} de {plural(report.run.total, "par", "pares")}…</span>
        </div>
      )}
      {interrupted && <p role="alert" className="alert alert-warn">La búsqueda se interrumpió. Puedes volver a iniciarla: lo ya calculado no se repite.</p>}
      {error && <p role="alert" className="alert alert-error">{error}</p>}

      {done && (
        <>
          <p className={s.overlapping > 0 ? "alert alert-warn" : "ok-line"}>
            {s.overlapping === 0
              ? `Ningún sólido se superpone con otro (${plural(s.pairs, "par revisado", "pares revisados")}).`
              : `${plural(s.overlapping, "par de sólidos comparte volumen", "pares de sólidos comparten volumen")}.`}
          </p>
          {s.contact > 0 && <p className="note">{plural(s.contact, "par solo se toca", "pares solo se tocan")} en una superficie, sin volumen en común.</p>}
          {issues > 0 && (
            <p role="alert" className="alert alert-warn">
              No se pudo evaluar {plural(issues, "par o sólido", "pares o sólidos")}: no entra en el conteo.
              {s.unreadable.length > 0 && ` Sin leer: ${s.unreadable.join(", ")}.`}
            </p>
          )}
          {report.pairs.length > 0 && (
            <ul className="overlap-list" aria-label="Pares con superposición">
              {report.pairs.filter((p) => p.relation !== "contact").map((p) => (
                <li key={`${p.a}|${p.b}`}>
                  <strong>{p.key_a}</strong> y <strong>{p.key_b}</strong>
                  {p.relation === "overlap"
                    ? <> comparten {volumeShort(p.common_m3)} m³ ({pct(p.common_pct_of_smaller)} del menor)</>
                    : <> no se pudo evaluar{p.reason ? ` (${exclusionText(p.reason)})` : ""}</>}
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {!running && (
        <button type="button" disabled={starting} onClick={start}>
          {interrupted ? "Reintentar la búsqueda" : done ? "Volver a buscar" : "Buscar superposiciones"}
        </button>
      )}
    </section>
  );
}
